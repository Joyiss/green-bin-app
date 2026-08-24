from __future__ import annotations

import logging
import threading
import uuid
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

try:
    from ..repositories import service_provider_repository
    from ..services import request_context, scan_rate_limit_service
    from ..services.guidance_service import build_prediction_response
    from ..services.recognition_router import recognize_item
except ImportError:
    from repositories import service_provider_repository
    from services import request_context, scan_rate_limit_service
    from services.guidance_service import build_prediction_response
    from services.recognition_router import recognize_item

router = APIRouter()
logger = logging.getLogger(__name__)
_ACTIVE_PREDICT_REQUESTS = 0
_ACTIVE_PREDICT_REQUESTS_LOCK = threading.Lock()


def _provider_official_domain(evidence_urls: Any) -> str | None:
    if not isinstance(evidence_urls, list):
        return None
    blocked_hosts = {
        "facebook.com", "google.com", "instagram.com", "linkedin.com",
        "mapquest.com", "nextdoor.com", "x.com", "yelp.com", "youtube.com",
    }
    for value in evidence_urls:
        if not isinstance(value, str):
            continue
        try:
            host = (urlparse(value).hostname or "").casefold().removeprefix("www.")
        except ValueError:
            continue
        if host and not any(
            host == blocked or host.endswith(f".{blocked}")
            for blocked in blocked_hosts
        ):
            return host
    return None


def _increment_active_predict_requests() -> int:
    global _ACTIVE_PREDICT_REQUESTS
    with _ACTIVE_PREDICT_REQUESTS_LOCK:
        _ACTIVE_PREDICT_REQUESTS += 1
        return _ACTIVE_PREDICT_REQUESTS


def _decrement_active_predict_requests() -> int:
    global _ACTIVE_PREDICT_REQUESTS
    with _ACTIVE_PREDICT_REQUESTS_LOCK:
        _ACTIVE_PREDICT_REQUESTS = max(0, _ACTIVE_PREDICT_REQUESTS - 1)
        return _ACTIVE_PREDICT_REQUESTS


def _has_predict_input(file: UploadFile | None, selected_item: str | None) -> bool:
    return file is not None or (isinstance(selected_item, str) and bool(selected_item.strip()))


def _scan_limit_response(
    error: str,
    metadata: scan_rate_limit_service.ScanRateLimitMetadata,
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": error, **metadata.to_response_payload()},
    )


def _confirmed_provider_for_location(
    *,
    client_id: str | None,
    city: str | None,
    county: str | None,
    state: str | None,
) -> dict[str, Any] | None:
    normalized_client_id = client_id.strip() if isinstance(client_id, str) else ""
    normalized_city = city.strip() if isinstance(city, str) else ""
    normalized_county = county.strip() if isinstance(county, str) else ""
    normalized_state = state.strip() if isinstance(state, str) else ""
    if not normalized_client_id or not normalized_city or not normalized_state:
        logger.info(
            "predict_provider_context request_id=%s used=False city=%s county=%s state=%s reason=missing_context",
            request_context.get_predict_request_id(),
            normalized_city or None,
            normalized_county or None,
            normalized_state or None,
        )
        return None

    try:
        provider = service_provider_repository.current_provider(
            client_id_hash=scan_rate_limit_service.hash_client_id(normalized_client_id),
            city=normalized_city,
            county=normalized_county or None,
            state=normalized_state,
        )
        if not isinstance(provider, dict):
            logger.info(
                "predict_provider_context request_id=%s used=False city=%s county=%s state=%s reason=not_found",
                request_context.get_predict_request_id(),
                normalized_city,
                normalized_county or None,
                normalized_state,
            )
            return None
        canonical_name = str(provider.get("canonical_name") or "").strip()
        if provider.get("status") != "verified" or not canonical_name:
            logger.info(
                "predict_provider_context request_id=%s used=False city=%s county=%s state=%s reason=invalid_record",
                request_context.get_predict_request_id(),
                normalized_city,
                normalized_county or None,
                normalized_state,
            )
            return None
        context = {
            "canonical_name": canonical_name,
            "city": str(provider.get("city") or normalized_city).strip(),
            "county": str(provider.get("county") or normalized_county).strip(),
            "state": str(provider.get("state") or normalized_state).strip(),
            "official_domain": _provider_official_domain(provider.get("evidence_urls")),
        }
        logger.info(
            "predict_provider_context request_id=%s used=True canonical_provider=%s city=%s county=%s state=%s",
            request_context.get_predict_request_id(),
            canonical_name,
            context["city"],
            context["county"] or None,
            context["state"],
        )
        return context
    except Exception:
        logger.warning(
            "predict_provider_context request_id=%s used=False city=%s county=%s state=%s reason=lookup_unavailable",
            request_context.get_predict_request_id(),
            normalized_city,
            normalized_county or None,
            normalized_state,
        )
        return None


@router.post("/predict")
async def predict(
    file: UploadFile | None = File(None),
    selected_item: str | None = Form(None),
    jurisdiction_id: str | None = Form(None),
    city: str | None = Form(None, max_length=120),
    county: str | None = Form(None, max_length=120),
    state: str | None = Form(None, max_length=120),
    country: str | None = Form(None, max_length=120),
    waste_provider: str | None = Form(None, max_length=120),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_original_request_id: str | None = Header(None, alias="X-Original-Request-ID"),
    x_greenbin_client_id: str | None = Header(None, alias="X-GreenBin-Client-Id"),
) -> Any:
    request_started = perf_counter()
    request_id = (
        x_request_id.strip()
        if isinstance(x_request_id, str) and x_request_id.strip()
        else f"predict-{uuid.uuid4().hex[:12]}"
    )
    if not _has_predict_input(file, selected_item):
        logger.info(
            "tavily_local_guidance request_id=%s status=tavily_disabled called=False "
            "skip_reason=invalid_request duration_ms=0.0 result_count=0 "
            "trusted_source_count=0 reported_credit_usage=None",
            request_id,
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "Image file or selected_item is required."},
        )

    context_token = request_context.set_predict_request_id(request_id)
    active_count = _increment_active_predict_requests()
    logger.info(
        "predict_request_started request_id=%s active_predict_requests=%s overlapping=%s has_file=%s selected_item=%s filename=%s content_type=%s",
        request_id,
        active_count,
        active_count > 1,
        file is not None,
        bool(selected_item),
        getattr(file, "filename", None),
        getattr(file, "content_type", None),
    )
    try:
        try:
            scan_rate_limit_service.check_scan_limits(x_greenbin_client_id)
        except scan_rate_limit_service.MissingScanClientIdError:
            return JSONResponse(
                status_code=400,
                content={"error": "scan_client_id_required"},
            )
        except scan_rate_limit_service.DailyScanLimitReachedError as exc:
            return _scan_limit_response(
                "daily_scan_limit_reached",
                exc.metadata,
            )
        except scan_rate_limit_service.MonthlyScanLimitReachedError as exc:
            return _scan_limit_response(
                "monthly_scan_limit_reached",
                exc.metadata,
            )
        except scan_rate_limit_service.ScanRateLimitUnavailableError:
            return JSONResponse(
                status_code=503,
                content={"error": "scan_rate_limit_unavailable"},
            )

        # Retained as an accepted form field for API compatibility. Jurisdiction IDs
        # no longer select hard-coded local disposal rules.
        _ = jurisdiction_id
        classification = await recognize_item(file=file, selected_item=selected_item)
        confirmed_provider = _confirmed_provider_for_location(
            client_id=x_greenbin_client_id,
            city=city,
            county=county,
            state=state,
        )
        coarse_location = {
            key: normalized
            for key, value in {
                "city": city,
                "county": county,
                "state": state,
                "country": country,
            }.items()
            if isinstance(value, str) and (normalized := value.strip())
        }
        if confirmed_provider is not None:
            coarse_location["waste_provider"] = confirmed_provider["canonical_name"]
            if confirmed_provider.get("official_domain"):
                coarse_location["provider_official_domain"] = confirmed_provider["official_domain"]
        if coarse_location:
            # Only coarse jurisdiction fields are attached. Coordinates, complete
            # addresses, and other reverse-geocoder data never enter Tavily.
            classification["location"] = coarse_location
        guidance_started = perf_counter()
        try:
            response = build_prediction_response(
                classification,
            )
            recognition_details = classification.get("recognition_details")
            if isinstance(recognition_details, dict):
                normalized_details = recognition_details.get("normalized")
                if isinstance(normalized_details, dict):
                    response["recognition_details"] = {
                        "normalized": normalized_details,
                    }
            # Count only a successfully built response. The reservation rechecks
            # both limits atomically to prevent concurrent oversubscription.
            try:
                rate_limit_metadata = scan_rate_limit_service.consume_scan(
                    x_greenbin_client_id
                )
            except scan_rate_limit_service.MissingScanClientIdError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "scan_client_id_required"},
                )
            except scan_rate_limit_service.DailyScanLimitReachedError as exc:
                return _scan_limit_response(
                    "daily_scan_limit_reached",
                    exc.metadata,
                )
            except scan_rate_limit_service.MonthlyScanLimitReachedError as exc:
                return _scan_limit_response(
                    "monthly_scan_limit_reached",
                    exc.metadata,
                )
            except scan_rate_limit_service.ScanRateLimitUnavailableError:
                return JSONResponse(
                    status_code=503,
                    content={"error": "scan_rate_limit_unavailable"},
                )
            if rate_limit_metadata is not None:
                response.update(rate_limit_metadata.to_response_payload())
            response["request_id"] = request_id
            # Feedback is optional and is written only when the tester submits a
            # rating. Prediction completion never depends on feedback storage.
            _ = x_original_request_id
            return response
        finally:
            logger.info(
                "predict_timing request_id=%s stage=guidance duration_ms=%.1f",
                request_id,
                (perf_counter() - guidance_started) * 1000,
            )
    finally:
        remaining_count = _decrement_active_predict_requests()
        logger.info(
            "predict_timing request_id=%s stage=total duration_ms=%.1f active_predict_requests=%s",
            request_id,
            (perf_counter() - request_started) * 1000,
            remaining_count,
        )
        request_context.reset_predict_request_id(context_token)
