import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from .materials import MATERIAL_LABELS
    from .routes.predict import router as predict_router
except ImportError:
    from materials import MATERIAL_LABELS
    from routes.predict import router as predict_router


load_dotenv(Path(__file__).resolve().parent / ".env")

EARTH911_BASE_URL = os.getenv("EARTH911_BASE_URL", "https://api.earth911.com").rstrip("/")
EARTH911_API_KEY = os.getenv("EARTH911_API_KEY")
EARTH911_TIMEOUT_SECONDS = 15
EARTH911_MAX_DISTANCE_MILES = 20
EARTH911_MAX_RESULTS = 5
LOCATION_CARD_ACCENTS = ("#88D39D", "#F2C572", "#7FC6FF")
LOCATION_CARD_MAP_STYLES = ("grid", "building", "pin")
EARTH911_SESSION = requests.Session()
EARTH911_SESSION.trust_env = False

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_earth911_api_key() -> str:
    if not EARTH911_API_KEY:
        raise HTTPException(
            status_code=500,
            detail={"error": "EARTH911_API_KEY is not set. Add it to backend/.env."},
        )

    return EARTH911_API_KEY


def _earth911_request(endpoint: str, params: dict[str, Any]) -> Any:
    try:
        response = EARTH911_SESSION.get(
            f"{EARTH911_BASE_URL}/{endpoint}",
            params={
                "api_key": _require_earth911_api_key(),
                **params,
            },
            timeout=EARTH911_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": f"Earth911 request failed: {exc}"},
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "Earth911 returned invalid JSON."},
        ) from exc

    return payload.get("result", [])


def _result_to_list(result: Any) -> list[Any]:
    if isinstance(result, list):
        return result

    if isinstance(result, dict):
        values = list(result.values())
        if values:
            return values
        return [result]

    return []


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value

    return None


def _format_distance(distance: Any) -> str:
    miles = _coerce_float(distance)
    if miles is None:
        return "Distance unavailable"

    return f"{miles:.1f} mi"


def _format_address(location: dict[str, Any], details: dict[str, Any] | None = None) -> str:
    address_line = _first_value(
        location.get("address"),
        location.get("address1"),
        location.get("street"),
        details.get("address") if details else None,
        details.get("address1") if details else None,
        details.get("street") if details else None,
    )
    city = _first_value(location.get("city"), details.get("city") if details else None)
    region = _first_value(
        location.get("province"),
        location.get("state"),
        details.get("province") if details else None,
        details.get("state") if details else None,
    )
    postal_code = _first_value(
        location.get("postal_code"),
        location.get("zip"),
        details.get("postal_code") if details else None,
        details.get("zip") if details else None,
    )

    locality_parts = [part for part in (city, region, postal_code) if part]
    if address_line and locality_parts:
        return f"{address_line}, {', '.join(locality_parts)}"
    if address_line:
        return str(address_line)
    if locality_parts:
        return ", ".join(str(part) for part in locality_parts)

    return "Address unavailable"


def _format_status(location: dict[str, Any], details: dict[str, Any] | None = None) -> str:
    hours = _first_value(
        location.get("hours"),
        location.get("hours_of_operation"),
        details.get("hours") if details else None,
        details.get("hours_of_operation") if details else None,
    )
    if hours:
        return str(hours)

    phone = _first_value(
        location.get("phone"),
        details.get("phone") if details else None,
        details.get("public_phone") if details else None,
    )
    if phone:
        return f"Call {phone}"

    return "Check hours before visiting"


def _location_type(location: dict[str, Any], details: dict[str, Any] | None = None) -> str:
    return str(
        _first_value(
            location.get("location_type"),
            location.get("type"),
            location.get("category"),
            details.get("location_type") if details else None,
            details.get("type") if details else None,
            "Recycling Site",
        )
    )


def _location_name(location: dict[str, Any], details: dict[str, Any] | None = None) -> str:
    return str(
        _first_value(
            location.get("description"),
            location.get("name"),
            location.get("business_name"),
            details.get("description") if details else None,
            details.get("name") if details else None,
            "Earth911 Partner Location",
        )
    )


def _build_directions_url(location: dict[str, Any], details: dict[str, Any] | None = None) -> str | None:
    latitude = _coerce_float(
        _first_value(
            location.get("latitude"),
            details.get("latitude") if details else None,
        )
    )
    longitude = _coerce_float(
        _first_value(
            location.get("longitude"),
            details.get("longitude") if details else None,
        )
    )

    if latitude is not None and longitude is not None:
        return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"

    address = _format_address(location, details)
    if address == "Address unavailable":
        return None

    return f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(address)}"


def _material_match_score(query: str, candidate: dict[str, Any]) -> tuple[int, int]:
    description = str(candidate.get("description", "")).strip().lower()
    normalized_query = query.strip().lower()
    query_terms = [term for term in normalized_query.split() if term]

    exact_flag = 1 if candidate.get("exact") else 0
    exact_text = 1 if description == normalized_query and normalized_query else 0
    starts_with = 1 if normalized_query and description.startswith(normalized_query) else 0
    contains_all_terms = 1 if query_terms and all(term in description for term in query_terms) else 0

    return (
        exact_flag * 100 + exact_text * 80 + starts_with * 40 + contains_all_terms * 20,
        -len(description),
    )


def _extract_material_id(material_result: Any, query: str) -> int | None:
    candidates: list[dict[str, Any]] = []
    for item in _result_to_list(material_result):
        if isinstance(item, dict) and item.get("material_id") is not None:
            candidates.append(item)

    if not candidates:
        return None

    best_match = max(candidates, key=lambda candidate: _material_match_score(query, candidate))
    try:
        return int(best_match["material_id"])
    except (TypeError, ValueError):
        return None


def _location_details(location_id: str) -> dict[str, Any] | None:
    details = _earth911_request("earth911.getLocationDetails", {"location_id": location_id})
    if not isinstance(details, dict):
        return None

    nested_details = details.get(location_id)
    if isinstance(nested_details, dict):
        return nested_details

    nested_values = [value for value in details.values() if isinstance(value, dict)]
    if nested_values:
        return nested_values[0]

    return details


def _normalize_location(location: dict[str, Any], index: int) -> dict[str, Any]:
    location_id = str(
        _first_value(
            location.get("location_id"),
            location.get("locationId"),
            location.get("id"),
            f"earth911-{index}",
        )
    )
    details = _location_details(location_id)

    return {
        "id": location_id,
        "type": _location_type(location, details),
        "name": _location_name(location, details),
        "address": _format_address(location, details),
        "status": _format_status(location, details),
        "distance": _format_distance(location.get("distance")),
        "accent": LOCATION_CARD_ACCENTS[index % len(LOCATION_CARD_ACCENTS)],
        "mapStyle": LOCATION_CARD_MAP_STYLES[index % len(LOCATION_CARD_MAP_STYLES)],
        "directionsUrl": _build_directions_url(location, details),
    }


def _raw_search_locations(lat: float, lon: float, material_id: int) -> list[Any]:
    return _result_to_list(
        _earth911_request(
            "earth911.searchLocations",
            {
                "latitude": lat,
                "longitude": lon,
                "material_id": material_id,
                "max_distance": EARTH911_MAX_DISTANCE_MILES,
                "max_results": EARTH911_MAX_RESULTS,
            },
        )
    )


def _search_locations_for_material(lat: float, lon: float, material_id: int) -> list[dict[str, Any]]:
    raw_locations = _raw_search_locations(lat, lon, material_id)

    normalized_locations: list[dict[str, Any]] = []
    for index, location in enumerate(_result_to_list(raw_locations)):
        if isinstance(location, dict):
            normalized_locations.append(_normalize_location(location, index))

    return normalized_locations

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/material_labels")
def material_labels() -> dict[str, list[str]]:
    return {"labels": MATERIAL_LABELS}


@app.get("/get_material_id")
def get_material_id(item: str) -> dict[str, int | None]:
    try:
        material_result = _earth911_request("earth911.searchMaterials", {"query": item})
        return {"material_id": _extract_material_id(material_result, item)}
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/search_locations")
def search_locations(lat: float, lon: float, material_id: int) -> dict[str, list[Any]]:
    try:
        return {"locations": _raw_search_locations(lat, lon, material_id)}
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/get_location_details")
def get_location_details(location_id: str) -> dict[str, Any]:
    try:
        return {"details": _location_details(location_id)}
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/nearby_locations")
def nearby_locations(item: str, lat: float, lon: float) -> dict[str, Any]:
    try:
        material_result = _earth911_request("earth911.searchMaterials", {"query": item})
        material_id = _extract_material_id(material_result, item)

        if material_id is None:
            return {"item": item, "material_id": None, "locations": []}

        return {
            "item": item,
            "material_id": material_id,
            "locations": _search_locations_for_material(lat, lon, material_id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


app.include_router(predict_router)
