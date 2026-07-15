from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")
logger = logging.getLogger(__name__)

FetchEarth911 = Callable[[str, dict[str, Any]], Any]
CatalogMatcher = Callable[
    [str, dict[str, Any] | None, dict[str, list[str]]],
    dict[str, Any],
]

SUPPORTED_MATERIALS_TTL_SECONDS = 24 * 60 * 60
STALE_CACHE_RETRY_SECONDS = 5 * 60
DEFAULT_LLM_MODEL = "llama-3.3-70b-versatile"
DEFAULT_LLM_TIMEOUT_SECONDS = 10.0

_CACHE_LOCK = threading.Lock()
_CACHE_EXPIRES_AT = 0.0
_CACHE_MATERIALS: list[dict[str, Any]] | None = None
_CACHE_FAMILY_NAMES: dict[int, str] = {}
_CACHE_GROUPED_CATALOG: dict[str, list[str]] = {}
_CACHE_IS_STALE = False

_ALIASES: dict[str, tuple[str, ...]] = {
    "cell phone": ("Cell Phones", "Smartphones", "Telephones"),
    "cellphone": ("Cell Phones", "Smartphones", "Telephones"),
    "calculator": ("Calculators",),
    "computer mouse": ("Computer Peripherals - External",),
    "laptop computer": ("Laptop Computers",),
    "mobile phone": ("Cell Phones", "Smartphones", "Telephones"),
    "mouse": ("Computer Peripherals - External",),
    "notebook computer": ("Laptop Computers",),
    "plastic water bottle": (
        "Plastic Bottles",
        "Water Bottles",
        "Plastic Beverage Bottles",
    ),
    "smart phone": ("Smartphones", "Cell Phones"),
    "smartphone": ("Smartphones", "Cell Phones"),
    "water bottle": ("Water Bottles", "Plastic Bottles"),
}

_PLURAL_ALIAS_EXCLUDED_TERMS = {
    "electronics",
    "glass",
    "hazardous",
    "metal",
    "paper",
    "plastic",
}

_PROTECTED_TERMS = {
    "aerosol",
    "ammunition",
    "antifreeze",
    "asbestos",
    "battery",
    "batteries",
    "biohazard",
    "cell phone",
    "chemical",
    "chemicals",
    "computer",
    "electronic",
    "electronics",
    "e waste",
    "explosive",
    "hazardous",
    "laptop",
    "medical",
    "medication",
    "medicine",
    "mercury",
    "oil",
    "paint",
    "pesticide",
    "pharmaceutical",
    "phone",
    "propane",
    "solvent",
    "tablet",
}

_PROTECTED_CATEGORY_TERMS = {
    "battery",
    "chemical",
    "electronics",
    "electronic",
    "e-waste",
    "e waste",
    "hazardous",
    "medical",
    "medicine",
}

_GENERIC_PROTECTED_INPUTS = {
    "batteries",
    "battery",
    "chemicals",
    "chemical waste",
    "electronics",
    "electronic waste",
    "e waste",
    "hazardous materials",
    "hazardous waste",
    "household hazardous waste",
    "medical waste",
}

_BROAD_PROTECTED_TARGETS = {
    "batteries",
    "chemicals",
    "consumer electronics",
    "electronics",
    "electronic waste",
    "e waste",
    "hazardous materials",
    "hazardous waste",
    "household hazardous waste",
    "medical waste",
}

_ROUTING_FAMILY_NAMES: dict[str, tuple[str, ...]] = {
    "automotive": ("Automotive",),
    "batteries": ("Batteries",),
    "construction": ("Construction",),
    "electronics": ("Electronics",),
    "garden": ("Garden",),
    "glass": ("Glass",),
    "hazardous": ("Hazardous",),
    "household": ("Household",),
    "metal": ("Metal",),
    "paint": ("Paint", "Hazardous"),
    "paper": ("Paper",),
    "plastic": ("Plastic",),
}

_ROUTING_CATEGORY_VALUES = set(_ROUTING_FAMILY_NAMES) | {"unknown", "unsupported"}

_ROUTING_ALIAS_MAP: dict[str, str] = {
    "appliances": "household",
    "automobile": "automotive",
    "automotive": "automotive",
    "batteries": "batteries",
    "battery": "batteries",
    "battery waste": "batteries",
    "cardboard": "paper",
    "chemical": "hazardous",
    "chemicals": "hazardous",
    "construction": "construction",
    "construction and demolition": "construction",
    "demolition": "construction",
    "e waste": "electronics",
    "e-waste": "electronics",
    "electronic": "electronics",
    "electronic device": "electronics",
    "electronics": "electronics",
    "fabric/textile": "household",
    "garden": "garden",
    "glass": "glass",
    "hazardous": "hazardous",
    "hazardous household item": "hazardous",
    "hazardous waste": "hazardous",
    "household": "household",
    "household item": "household",
    "metal": "metal",
    "paint": "paint",
    "paper": "paper",
    "paper product": "paper",
    "plastic": "plastic",
    "textile": "household",
    "textiles": "household",
    "unknown": "unknown",
    "unsupported": "unsupported",
}


def reset_supported_materials_cache_for_tests() -> None:
    global _CACHE_EXPIRES_AT, _CACHE_MATERIALS, _CACHE_FAMILY_NAMES
    global _CACHE_GROUPED_CATALOG, _CACHE_IS_STALE
    with _CACHE_LOCK:
        _CACHE_EXPIRES_AT = 0.0
        _CACHE_MATERIALS = None
        _CACHE_FAMILY_NAMES = {}
        _CACHE_GROUPED_CATALOG = {}
        _CACHE_IS_STALE = False


def normalize_material_label(value: str) -> str:
    normalized = value.strip().casefold()
    normalized = normalized.replace("&", " and ")
    normalized = normalized.replace("/", " ")
    normalized = normalized.replace("_", " ")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\b(a|an|the)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _cache_time(now: float | int | None) -> float:
    return time.time() if now is None else float(now)


def _result_to_list(result: Any) -> list[Any]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        values = list(result.values())
        return values if values else [result]
    return []


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _material_search_names(record: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("description", "description_legacy", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    return names


def _normalize_material(record: dict[str, Any]) -> dict[str, Any] | None:
    description = str(record.get("description") or "").strip()
    material_id = _coerce_int(record.get("material_id"))
    if not description or material_id is None:
        return None

    family_ids = [
        family_id
        for value in (record.get("family_ids") or [])
        if (family_id := _coerce_int(value)) is not None
    ]
    normalized_names = sorted(
        {
            normalize_material_label(name)
            for name in _material_search_names(record)
            if normalize_material_label(name)
        }
    )
    return {
        "description": description,
        "material_id": material_id,
        "normalized_name": normalize_material_label(description),
        "normalized_names": normalized_names,
        "description_legacy": record.get("description_legacy"),
        "family_ids": family_ids,
        "url": record.get("url"),
        "image": record.get("image"),
        "long_description": record.get("long_description"),
        "raw": record,
    }


def _normalize_family_names(result: Any) -> dict[int, str]:
    family_names: dict[int, str] = {}
    for record in _result_to_list(result):
        if not isinstance(record, dict):
            continue
        family_id = _coerce_int(record.get("family_id"))
        description = str(record.get("description") or "").strip()
        if family_id is not None and description:
            family_names[family_id] = description
    return family_names


def _group_material_catalog(
    materials: list[dict[str, Any]],
    family_names: dict[int, str],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for material in materials:
        family_name = next(
            (
                family_names[family_id]
                for family_id in material.get("family_ids", [])
                if family_id in family_names
            ),
            "Other supported materials",
        )
        grouped.setdefault(family_name, []).append(str(material["description"]))
    return {
        family_name: sorted(names, key=str.casefold)
        for family_name, names in sorted(grouped.items(), key=lambda item: item[0].casefold())
    }


def get_supported_materials(
    fetch_earth911: FetchEarth911,
    now: float | int | None = None,
) -> list[dict[str, Any]]:
    global _CACHE_EXPIRES_AT, _CACHE_MATERIALS, _CACHE_FAMILY_NAMES
    global _CACHE_GROUPED_CATALOG, _CACHE_IS_STALE

    current_time = _cache_time(now)
    with _CACHE_LOCK:
        if _CACHE_MATERIALS is not None and current_time < _CACHE_EXPIRES_AT:
            return _CACHE_MATERIALS

        try:
            raw_materials = fetch_earth911("earth911.getMaterials", {})
            materials = [
                material
                for item in _result_to_list(raw_materials)
                if isinstance(item, dict)
                for material in [_normalize_material(item)]
                if material is not None
            ]
            if not materials:
                raise ValueError("Earth911 getMaterials returned no usable materials.")
        except Exception as exc:
            if _CACHE_MATERIALS is None:
                raise
            _CACHE_IS_STALE = True
            _CACHE_EXPIRES_AT = current_time + STALE_CACHE_RETRY_SECONDS
            logger.warning(
                "Earth911 material catalog refresh failed; serving stale cache. error_class=%s retry_seconds=%s",
                exc.__class__.__name__,
                STALE_CACHE_RETRY_SECONDS,
            )
            return _CACHE_MATERIALS

        family_names = _CACHE_FAMILY_NAMES
        try:
            refreshed_family_names = _normalize_family_names(
                fetch_earth911("earth911.getFamilies", {})
            )
            if refreshed_family_names:
                family_names = refreshed_family_names
        except Exception as exc:
            logger.warning(
                "Earth911 family catalog refresh failed; using existing family metadata. error_class=%s",
                exc.__class__.__name__,
            )

        _CACHE_MATERIALS = materials
        _CACHE_FAMILY_NAMES = family_names
        _CACHE_GROUPED_CATALOG = _group_material_catalog(materials, family_names)
        _CACHE_EXPIRES_AT = current_time + SUPPORTED_MATERIALS_TTL_SECONDS
        _CACHE_IS_STALE = False
        return _CACHE_MATERIALS


def get_grouped_material_catalog() -> dict[str, list[str]]:
    return {name: list(materials) for name, materials in _CACHE_GROUPED_CATALOG.items()}


def _material_index(materials: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for material in materials:
        for name in material.get("normalized_names", []):
            index.setdefault(str(name), material)
    return index


def _last_word_variants(word: str) -> set[str]:
    if not word or word in _PLURAL_ALIAS_EXCLUDED_TERMS:
        return set()

    variants: set[str] = set()
    if len(word) > 3 and word.endswith("ies"):
        variants.add(f"{word[:-3]}y")
    elif len(word) > 3 and word.endswith(("ches", "shes", "xes", "zes")):
        variants.add(word[:-2])
    elif len(word) > 3 and word.endswith("es") and not word.endswith(("ses", "ss")):
        variants.add(word[:-2])
    elif len(word) > 2 and word.endswith("s") and not word.endswith(("ss", "us")):
        variants.add(word[:-1])

    if word.endswith("y") and len(word) > 2 and word[-2] not in "aeiou":
        variants.add(f"{word[:-1]}ies")
    elif word.endswith(("ch", "sh", "x", "z")):
        variants.add(f"{word}es")
    elif not word.endswith(("s", "ss", "us")):
        variants.add(f"{word}s")

    variants.discard(word)
    return variants


def _plural_alias_variants(normalized_name: str) -> set[str]:
    words = normalized_name.split()
    if not words:
        return set()

    variants: set[str] = set()
    for variant in _last_word_variants(words[-1]):
        variants.add(" ".join([*words[:-1], variant]))
    return variants


def _material_plural_alias_index(
    materials: list[dict[str, Any]],
    exact_index: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    alias_index: dict[str, dict[str, Any]] = {}
    ambiguous_aliases: set[str] = set()

    for material in materials:
        for name in material.get("normalized_names", []):
            normalized_name = str(name)
            for alias in _plural_alias_variants(normalized_name):
                if alias in exact_index:
                    continue
                existing = alias_index.get(alias)
                if existing is not None and existing is not material:
                    ambiguous_aliases.add(alias)
                    continue
                alias_index[alias] = material

    for alias in ambiguous_aliases:
        alias_index.pop(alias, None)
    return alias_index


def _catalog_by_exact_description(
    materials: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {str(material["description"]): material for material in materials}


def _recognition_text(recognition_details: dict[str, Any] | None) -> str:
    if not recognition_details:
        return ""
    parts: list[str] = []
    for key in ("broad_category", "disposal_category", "category", "material_category", "likely_material"):
        value = recognition_details.get(key)
        if isinstance(value, str):
            parts.append(value)
    normalized = recognition_details.get("normalized")
    if isinstance(normalized, dict):
        for key in ("broad_category", "disposal_category", "item_label", "material_category", "likely_material"):
            value = normalized.get(key)
            if isinstance(value, str):
                parts.append(value)
    return " ".join(parts)


def _routing_category_from_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = normalize_material_label(value)
    if not normalized:
        return None
    if normalized in _ROUTING_CATEGORY_VALUES:
        return normalized
    mapped = _ROUTING_ALIAS_MAP.get(normalized)
    if mapped:
        return mapped
    if any(term in normalized for term in ("keyboard", "computer mouse", "calculator", "phone charger", "charger", "charging cable", "cable", "cord", "usb", "laptop", "computer", "monitor", "printer", "television", "tablet", "smartphone", "cell phone", "phone", "remote", "headphone", "earbud")):
        return "electronics"
    if any(term in normalized for term in ("battery", "batteries", "lithium", "alkaline", "rechargeable", "vape")):
        return "batteries"
    if "paint" in normalized:
        return "paint"
    if any(term in normalized for term in ("propane", "motor oil", "medication", "medicine", "chemical", "aerosol", "cleaning spray", "light bulb", "medical")):
        return "hazardous"
    if any(term in normalized for term in ("cardboard", "pizza box", "paper", "newspaper", "magazine", "book", "envelope")):
        return "paper"
    if "glass" in normalized:
        return "glass"
    if any(term in normalized for term in ("plastic", "pet", "pete")):
        return "plastic"
    if any(term in normalized for term in ("metal", "aluminum", "aluminium", "steel")):
        return "metal"
    if any(term in normalized for term in ("automotive", "vehicle", "tire")):
        return "automotive"
    if any(term in normalized for term in ("construction", "demolition", "drywall", "asphalt", "concrete")):
        return "construction"
    if any(term in normalized for term in ("garden", "yard", "lawn", "leaves", "branches", "grass")):
        return "garden"
    return None


def _recognition_detail_value(
    recognition_details: dict[str, Any] | None,
    key: str,
) -> Any:
    if not recognition_details:
        return None
    normalized = recognition_details.get("normalized")
    if isinstance(normalized, dict) and normalized.get(key) is not None:
        return normalized.get(key)
    return recognition_details.get(key)


def _resolve_routing_category(
    label: str,
    recognition_details: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    label_category = _routing_category_from_text(label)
    if label_category is not None:
        return label_category, "item_label"

    broad_category = _routing_category_from_text(
        _recognition_detail_value(recognition_details, "broad_category")
    )
    if broad_category is not None:
        return broad_category, "broad_category"

    for key in ("disposal_category", "category"):
        category = _routing_category_from_text(_recognition_detail_value(recognition_details, key))
        if category is not None:
            return category, key

    detail_text = _recognition_text(recognition_details)
    risky_category = _routing_category_from_text(detail_text)
    if risky_category in {"batteries", "hazardous", "paint", "electronics"}:
        return risky_category, "risky_signal"

    for key in ("material_category", "likely_material"):
        category = _routing_category_from_text(_recognition_detail_value(recognition_details, key))
        if category is not None:
            return category, key

    return None, None


def _filter_grouped_catalog_for_routing(
    grouped_catalog: dict[str, list[str]],
    routing_category: str | None,
) -> tuple[dict[str, list[str]], str | None]:
    if routing_category == "unsupported":
        return {}, "unsupported"
    if routing_category in {None, "unknown"}:
        return grouped_catalog, None

    family_names = _ROUTING_FAMILY_NAMES.get(routing_category)
    if not family_names:
        return grouped_catalog, None

    filtered: dict[str, list[str]] = {}
    normalized_family_names = {normalize_material_label(name) for name in family_names}
    for family_name, material_names in grouped_catalog.items():
        if normalize_material_label(family_name) in normalized_family_names:
            filtered[family_name] = list(material_names)

    return (filtered or grouped_catalog), ",".join(family_names)


def _has_protected_signal(label: str, recognition_details: dict[str, Any] | None) -> bool:
    normalized_label = normalize_material_label(label)
    detail_text = normalize_material_label(_recognition_text(recognition_details))
    padded_label = f" {normalized_label} "
    padded_details = f" {detail_text} "
    if any(f" {term} " in padded_label for term in _PROTECTED_TERMS):
        return True
    return any(f" {term} " in padded_details for term in _PROTECTED_CATEGORY_TERMS)


def _is_specific_protected_input(
    label: str,
    recognition_details: dict[str, Any] | None,
) -> bool:
    if not _has_protected_signal(label, recognition_details):
        return False
    return normalize_material_label(label) not in _GENERIC_PROTECTED_INPUTS


def _is_broad_protected_target(material: dict[str, Any] | None) -> bool:
    if material is None:
        return False
    return normalize_material_label(str(material.get("description") or "")) in _BROAD_PROTECTED_TARGETS


def _find_alias_match(
    normalized_label: str,
    index: dict[str, dict[str, Any]],
    generated_alias_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    for target in _ALIASES.get(normalized_label, ()):
        material = index.get(normalize_material_label(target))
        if material is not None:
            return material
    if generated_alias_index is not None:
        return generated_alias_index.get(normalized_label)
    return None


def _env_truthy(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() in {"1", "true", "yes", "on"}


def _parse_llm_timeout() -> float:
    try:
        timeout = float(os.getenv("GUIDANCE_LLM_TIMEOUT", DEFAULT_LLM_TIMEOUT_SECONDS))
    except ValueError:
        return DEFAULT_LLM_TIMEOUT_SECONDS
    return timeout if math.isfinite(timeout) and timeout > 0 else DEFAULT_LLM_TIMEOUT_SECONDS


def _llm_settings() -> dict[str, Any]:
    return {
        "enabled": _env_truthy(os.getenv("ENABLE_EARTH911_LLM_MATCHING")),
        "provider": str(os.getenv("GUIDANCE_LLM_PROVIDER") or "").strip().casefold(),
        "model": str(os.getenv("GUIDANCE_LLM_MODEL") or DEFAULT_LLM_MODEL).strip(),
        "api_key": str(os.getenv("GROQ_API_KEY") or "").strip(),
        "timeout_seconds": _parse_llm_timeout(),
    }


def _catalog_prompt(grouped_catalog: dict[str, list[str]]) -> str:
    sections: list[str] = []
    for family_name, material_names in grouped_catalog.items():
        entries = "\n".join(f"- {name}" for name in material_names)
        sections.append(f"## {family_name}\n{entries}")
    return "\n\n".join(sections)


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    start = raw_text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in LLM response.")
    parsed, _ = json.JSONDecoder().raw_decode(raw_text[start:])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object.")
    return parsed


def _extract_groq_text(payload: Any) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("choices"), list):
        raise ValueError("Groq response did not contain choices.")
    for choice in payload["choices"]:
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            continue
        content = choice["message"].get("content")
        if isinstance(content, str) and content.strip():
            return content
    raise ValueError("Groq response did not contain message content.")


def _default_catalog_matcher(
    label: str,
    recognition_details: dict[str, Any] | None,
    grouped_catalog: dict[str, list[str]],
) -> dict[str, Any]:
    settings = _llm_settings()
    if not settings["enabled"]:
        return {
            "selection": "unsupported",
            "confidence": "low",
            "reason": "Earth911 LLM matching is disabled.",
            "failure_reason": "llm_disabled",
        }
    if settings["provider"] != "groq":
        return {
            "selection": "unsupported",
            "confidence": "low",
            "reason": "The configured LLM provider is unavailable for catalog matching.",
            "failure_reason": "provider_not_groq",
        }
    if not settings["api_key"]:
        return {
            "selection": "unsupported",
            "confidence": "low",
            "reason": "The Groq API key is not configured.",
            "failure_reason": "missing_groq_api_key",
        }

    prompt = f"""You are a controlled Earth911 catalog matcher.
Choose exactly one material name copied verbatim from the catalog below, or choose \"unsupported\".
Do not invent or rewrite material names. Do not provide disposal or recycling guidance.
For hazardous, battery, medical, chemical, or electronics items, choose only a specific material.
If the item is ambiguous, the catalog has only a broad risky category, or confidence is not high, choose unsupported.

Recognized item: {label}
Recognition details: {json.dumps(recognition_details or {}, ensure_ascii=True, sort_keys=True)}

Return one JSON object only:
{{"selection":"Exact Earth911 Description or unsupported","confidence":"high or low","reason":"short explanation"}}

Earth911 supported-material catalog:
{_catalog_prompt(grouped_catalog)}
"""
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        timeout=settings["timeout_seconds"],
    )
    response.raise_for_status()
    return _extract_json_object(_extract_groq_text(response.json()))


def _clean_debug_reason(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized:
        return None
    return normalized[:240]


def _catalog_candidates_for_selection(
    selection: str,
    materials: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[str]:
    normalized_selection = normalize_material_label(selection)
    if not normalized_selection:
        return []

    terms = [
        term
        for term in normalized_selection.split()
        if len(term) >= 3 and term not in {"and", "for", "the", "with"}
    ]
    candidates: list[str] = []
    seen: set[str] = set()
    for material in materials:
        description = str(material.get("description") or "").strip()
        if not description:
            continue
        normalized_description = material.get("normalized_description") or normalize_material_label(description)
        if (
            normalized_selection in normalized_description
            or normalized_description in normalized_selection
            or any(term in normalized_description for term in terms)
        ):
            if description not in seen:
                candidates.append(description)
                seen.add(description)
        if len(candidates) >= limit:
            break
    return candidates


def _resolution(
    *,
    original_label: str,
    normalized_label: str,
    match_type: str,
    material: dict[str, Any] | None,
    protected: bool,
    protected_specific: bool,
    llm_confidence: str | None = None,
    llm_reason: str | None = None,
    llm_selection: str | None = None,
    catalog_selection_candidates: list[str] | None = None,
    routing_category: str | None = None,
    routing_category_source: str | None = None,
    catalog_family_filter: str | None = None,
    validation_failure_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "original_label": original_label,
        "normalized_label": normalized_label,
        "resolved_material_label": material.get("description") if material else None,
        "matched_material_name": material.get("description") if material else None,
        "material_id": material.get("material_id") if material else None,
        "match_type": match_type,
        "confidence": 1.0 if material else 0.0,
        "llm_confidence": llm_confidence,
        "llm_reason": llm_reason,
        "llm_selection": llm_selection,
        "catalog_selection_candidates": catalog_selection_candidates or [],
        "routing_category": routing_category,
        "routing_category_source": routing_category_source,
        "catalog_family_filter": catalog_family_filter,
        "validation_failure_reason": validation_failure_reason,
        "protected_item": protected,
        "protected_item_specific": protected_specific,
        "stale_catalog_used": _CACHE_IS_STALE,
        "search_skipped": material is None,
    }


def resolve_earth911_material(
    label: str,
    recognition_details: dict[str, Any] | None,
    fetch_earth911: FetchEarth911,
    catalog_matcher: CatalogMatcher | None = None,
) -> dict[str, Any]:
    original_label = label
    normalized_label = normalize_material_label(label)
    protected = _has_protected_signal(label, recognition_details)
    protected_specific = _is_specific_protected_input(label, recognition_details)
    routing_category, routing_category_source = _resolve_routing_category(
        label,
        recognition_details,
    )

    def result(
        match_type: str,
        material: dict[str, Any] | None,
        **debug: Any,
    ) -> dict[str, Any]:
        return _resolution(
            original_label=original_label,
            normalized_label=normalized_label,
            match_type=match_type,
            material=material,
            protected=protected,
            protected_specific=protected_specific,
            routing_category=routing_category,
            routing_category_source=routing_category_source,
            **debug,
        )

    if not normalized_label:
        return result("none", None, validation_failure_reason="empty_label")

    materials = get_supported_materials(fetch_earth911)
    index = _material_index(materials)
    generated_alias_index = _material_plural_alias_index(materials, index)

    exact_match = index.get(normalized_label)
    if exact_match is not None:
        if protected_specific and _is_broad_protected_target(exact_match):
            return result("none", None, validation_failure_reason="broad_protected_target")
        return result("exact", exact_match)

    alias_match = _find_alias_match(normalized_label, index, generated_alias_index)
    if alias_match is not None:
        if protected_specific and _is_broad_protected_target(alias_match):
            return result("none", None, validation_failure_reason="broad_protected_target")
        return result("alias", alias_match)

    matcher = catalog_matcher or _default_catalog_matcher
    grouped_catalog, catalog_family_filter = _filter_grouped_catalog_for_routing(
        get_grouped_material_catalog(),
        routing_category,
    )
    if routing_category == "unsupported":
        return result(
            "none",
            None,
            catalog_family_filter=catalog_family_filter,
            validation_failure_reason="routing_category_unsupported",
        )
    try:
        llm_output = matcher(label, recognition_details, grouped_catalog)
    except requests.Timeout:
        return result("none", None, validation_failure_reason="llm_timeout")
    except requests.RequestException:
        return result("none", None, validation_failure_reason="llm_request_error")
    except (ValueError, json.JSONDecodeError, TypeError):
        return result("none", None, validation_failure_reason="invalid_llm_response")

    if not isinstance(llm_output, dict):
        return result("none", None, validation_failure_reason="invalid_llm_response")

    selection = str(llm_output.get("selection") or "").strip()
    llm_confidence = str(llm_output.get("confidence") or "").strip().casefold()
    llm_reason = _clean_debug_reason(llm_output.get("reason"))
    failure_reason = _clean_debug_reason(llm_output.get("failure_reason"))
    debug = {
        "llm_confidence": llm_confidence or None,
        "llm_reason": llm_reason,
        "llm_selection": selection or None,
        "catalog_family_filter": catalog_family_filter,
    }
    if failure_reason:
        return result("none", None, validation_failure_reason=failure_reason, **debug)
    if selection.casefold() == "unsupported":
        return result("none", None, validation_failure_reason="llm_unsupported", **debug)
    if llm_confidence != "high":
        return result("none", None, validation_failure_reason="llm_low_confidence", **debug)

    selected_material = _catalog_by_exact_description(materials).get(selection)
    if selected_material is None:
        return result(
            "none",
            None,
            validation_failure_reason="invalid_catalog_selection",
            catalog_selection_candidates=_catalog_candidates_for_selection(selection, materials),
            **debug,
        )
    if protected_specific and _is_broad_protected_target(selected_material):
        return result("none", None, validation_failure_reason="broad_protected_target", **debug)
    return result("llm", selected_material, **debug)
