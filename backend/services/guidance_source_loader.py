from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_SOURCE_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "trusted_guidance_sources.json"
)
_GUIDANCE_SOURCE_CACHE: dict[str, list[dict[str, Any]]] = {}
_SECTION_CATEGORY_ALIASES: dict[str, list[str]] = {
    "batteries": ["batteries", "electronics/e-waste"],
    "bulky_items": ["furniture/bulky items", "mixed-material items"],
    "curbside_recycling_basics": [
        "plastic containers",
        "glass",
        "metal cans",
        "paper/cardboard",
    ],
    "electronics": ["electronics/e-waste"],
    "food_scraps_compost": ["organic waste"],
    "glass_containers": ["glass"],
    "household_hazardous_waste": ["paint/household hazardous waste"],
    "metal_containers": ["metal cans"],
    "mixed_materials": ["mixed-material items"],
    "paper_cardboard": ["paper/cardboard"],
    "plastic_bags_film": ["plastic film"],
    "plastic_containers": ["plastic containers"],
    "textiles_donation": ["textiles", "reuse/donation"],
    "yard_waste": ["organic waste"],
}
_SECTION_ITEM_ALIASES: dict[str, list[str]] = {
    "batteries": ["battery", "batteries", "rechargeable batteries", "lithium-ion batteries"],
    "electronics": ["electronics", "e-waste"],
    "plastic_bags_film": ["plastic bags", "plastic wrap"],
    "textiles_donation": ["clothing", "textiles", "old clothes"],
}
_SECTION_MATERIAL_ALIASES: dict[str, list[str]] = {
    "batteries": ["battery"],
    "electronics": ["electronics"],
    "textiles_donation": ["fabric", "textile"],
}
_LOCATION_CHECK_TOKENS = (
    "local",
    "municipal",
    "municipality",
    "county",
    "district",
    "provider",
    "program",
    "participating",
    "retail",
    "retailer",
    "store",
    "availability",
    "accepted in your area",
)


def reset_guidance_source_cache() -> None:
    _GUIDANCE_SOURCE_CACHE.clear()


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None

    normalized_value = str(value).strip()
    return normalized_value or None


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        normalized_value = value.strip()
        return [normalized_value] if normalized_value else []

    return []


def _normalize_source_url(value: Any) -> str | None:
    normalized_value = _normalize_optional_string(value)
    if normalized_value is None:
        return None

    markdown_match = re.fullmatch(r"\[[^\]]+\]\((https?://[^)]+)\)", normalized_value)
    if markdown_match:
        return markdown_match.group(1).strip()

    if normalized_value.startswith("http://") or normalized_value.startswith("https://"):
        return normalized_value

    embedded_match = re.search(r"(https?://[^\s)]+)", normalized_value)
    if embedded_match:
        return embedded_match.group(1).strip()

    return normalized_value


def _normalize_applies_to(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        value = {}

    return {
        "item_labels": _normalize_string_list(value.get("item_labels")),
        "materials": _normalize_string_list(value.get("materials")),
        "categories": _normalize_string_list(value.get("categories")),
        "condition_flags": _normalize_string_list(value.get("condition_flags")),
    }


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped_values: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized_value = str(value).strip()
        if not normalized_value:
            continue

        dedupe_key = normalized_value.casefold()
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        deduped_values.append(normalized_value)

    return deduped_values


def _normalize_section_label(value: Any) -> str | None:
    normalized_value = _normalize_optional_string(value)
    if normalized_value is None:
        return None

    return normalized_value.replace("_", " ")


def _normalize_entry_scope(
    raw_chunk: dict[str, Any],
    decision_signals: dict[str, Any],
) -> tuple[str | None, bool, bool]:
    explicit_location_scope = _normalize_optional_string(raw_chunk.get("location_scope"))
    if explicit_location_scope is not None:
        return (
            explicit_location_scope,
            bool(raw_chunk.get("generalizable", False)),
            bool(raw_chunk.get("requires_location_check", False)),
        )

    scope = _normalize_optional_string(raw_chunk.get("scope")) or "us_general"
    source_text = " ".join(
        filter(
            None,
            [
                _normalize_optional_string(raw_chunk.get("source_claim")),
                _normalize_optional_string(raw_chunk.get("source_excerpt")),
                " ".join(_normalize_string_list(raw_chunk.get("limitations"))),
            ],
        )
    ).casefold()
    text_implies_location_check = any(
        token in source_text for token in _LOCATION_CHECK_TOKENS
    )

    requires_location_check = (
        text_implies_location_check
        or bool(decision_signals.get("supports_recycling"))
        or bool(decision_signals.get("supports_composting"))
        or bool(decision_signals.get("supports_donation_or_reuse"))
        or bool(decision_signals.get("requires_dropoff"))
        or bool(decision_signals.get("requires_household_hazardous_waste"))
    )

    if scope == "program_limited":
        return ("program_states_only", False, True)
    if scope == "national_dropoff":
        return ("national", True, True)

    return ("national", True, requires_location_check)


def _build_entry_applies_to(raw_chunk: dict[str, Any]) -> dict[str, list[str]]:
    raw_applies_to = raw_chunk.get("applies_to")
    if not isinstance(raw_applies_to, dict):
        return _normalize_applies_to(raw_applies_to)

    if any(
        key in raw_applies_to
        for key in ("item_labels", "categories", "condition_flags")
    ):
        return _normalize_applies_to(raw_applies_to)

    section = _normalize_optional_string(raw_chunk.get("section")) or ""
    decision_signals = raw_chunk.get("decision_signals")
    if not isinstance(decision_signals, dict):
        decision_signals = {}

    item_labels = _dedupe_strings(
        [
            *_normalize_string_list(raw_applies_to.get("item_examples")),
            *(_SECTION_ITEM_ALIASES.get(section, [])),
        ]
    )
    materials = _dedupe_strings(
        [
            *_normalize_string_list(raw_applies_to.get("materials")),
            *(_SECTION_MATERIAL_ALIASES.get(section, [])),
        ]
    )
    categories = _dedupe_strings(
        [
            *(_SECTION_CATEGORY_ALIASES.get(section, [])),
            *(
                [_normalize_section_label(section)]
                if _normalize_section_label(section) is not None
                else []
            ),
        ]
    )
    condition_flags = _normalize_string_list(raw_applies_to.get("conditions"))

    if decision_signals.get("requires_dropoff"):
        condition_flags.extend(["requires_dropoff", "dropoff_recommended"])
    if decision_signals.get("requires_household_hazardous_waste"):
        condition_flags.extend(["hazardous", "special_handling"])
    if decision_signals.get("avoid_curbside_recycling"):
        condition_flags.append("check_local_rules")
    if section == "batteries":
        condition_flags.append("battery")
    if section == "electronics":
        condition_flags.extend(["electronics", "e_waste"])

    return {
        "item_labels": _dedupe_strings(item_labels),
        "materials": _dedupe_strings(materials),
        "categories": _dedupe_strings(categories),
        "condition_flags": _dedupe_strings(condition_flags),
    }


def _build_entry_content(raw_chunk: dict[str, Any]) -> str | None:
    explicit_content = _normalize_optional_string(raw_chunk.get("content"))
    if explicit_content is not None:
        return explicit_content

    claim = _normalize_optional_string(raw_chunk.get("source_claim"))
    excerpt = _normalize_optional_string(raw_chunk.get("source_excerpt"))
    section = _normalize_section_label(raw_chunk.get("section"))

    content_parts: list[str] = []
    if claim is not None:
        content_parts.append(claim)
    if excerpt is not None and excerpt != claim:
        content_parts.append(f"Source excerpt: {excerpt}")
    if section is not None:
        content_parts.append(f"Guidance section: {section}.")

    if not content_parts:
        return None

    return " ".join(content_parts)


def _build_entry_disposal_actions(raw_chunk: dict[str, Any]) -> list[str]:
    explicit_actions = _normalize_string_list(raw_chunk.get("disposal_actions_supported"))
    if explicit_actions:
        return explicit_actions

    decision_signals = raw_chunk.get("decision_signals")
    if not isinstance(decision_signals, dict):
        decision_signals = {}

    actions: list[str] = []
    if decision_signals.get("supports_donation_or_reuse"):
        actions.append("Donate/reuse")
    elif decision_signals.get("requires_household_hazardous_waste") or decision_signals.get(
        "requires_dropoff"
    ):
        actions.append("Drop-off")
    elif decision_signals.get("supports_recycling"):
        actions.append("Recycle")
    elif decision_signals.get("supports_composting"):
        actions.append("Compost")
    elif decision_signals.get("supports_trash"):
        actions.append("Trash")

    location_scope, _, requires_location_check = _normalize_entry_scope(
        raw_chunk,
        decision_signals,
    )
    if requires_location_check or location_scope == "program_states_only":
        actions.append("Check local guidance")

    return _dedupe_strings(actions)


def _build_entry_warnings(raw_chunk: dict[str, Any]) -> list[str]:
    explicit_warnings = _normalize_string_list(raw_chunk.get("warnings"))
    if explicit_warnings:
        return explicit_warnings

    decision_signals = raw_chunk.get("decision_signals")
    if not isinstance(decision_signals, dict):
        decision_signals = {}

    warnings: list[str] = []
    if decision_signals.get("avoid_curbside_recycling"):
        warnings.append(
            "Do not place this item in curbside recycling unless your local program explicitly accepts it."
        )
    if decision_signals.get("avoid_trash"):
        warnings.append("Do not place this item in household trash.")
    if decision_signals.get("requires_household_hazardous_waste"):
        warnings.append(
            "Use an approved household hazardous waste or special handling drop-off option."
        )

    return warnings


def _normalize_chunk(raw_chunk: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw_chunk, dict):
        return None

    source_payload = raw_chunk.get("source")
    if not isinstance(source_payload, dict):
        source_payload = {}

    decision_signals = raw_chunk.get("decision_signals")
    if not isinstance(decision_signals, dict):
        decision_signals = {}

    location_scope, generalizable, requires_location_check = _normalize_entry_scope(
        raw_chunk,
        decision_signals,
    )
    source_name = (
        _normalize_optional_string(raw_chunk.get("source_name"))
        or _normalize_optional_string(source_payload.get("organization"))
        or _normalize_optional_string(source_payload.get("name"))
    )
    title = (
        _normalize_optional_string(raw_chunk.get("title"))
        or _normalize_optional_string(source_payload.get("name"))
        or _normalize_section_label(raw_chunk.get("section"))
    )

    normalized_chunk = {
        "id": _normalize_optional_string(raw_chunk.get("id")) or f"chunk-{index}",
        "title": title,
        "section": _normalize_optional_string(raw_chunk.get("section")),
        "source_name": source_name,
        "source_url": _normalize_source_url(
            raw_chunk.get("source_url") or source_payload.get("url")
        ),
        "source_type": _normalize_optional_string(
            raw_chunk.get("source_type") or source_payload.get("source_type")
        ),
        "location_scope": location_scope,
        "generalizable": generalizable,
        "requires_location_check": requires_location_check,
        "applies_to": _build_entry_applies_to(raw_chunk),
        "content": _build_entry_content(raw_chunk),
        "disposal_actions_supported": _build_entry_disposal_actions(raw_chunk),
        "warnings": _build_entry_warnings(raw_chunk),
        "limitations": _normalize_string_list(raw_chunk.get("limitations")),
        "confidence": _normalize_optional_string(raw_chunk.get("confidence")),
        "verified": bool(raw_chunk.get("verified", False))
        or _normalize_optional_string(raw_chunk.get("confidence")) == "high",
        "source_grounded": bool(raw_chunk.get("source_grounded", True)),
        "human_reviewed": bool(raw_chunk.get("human_reviewed", False)),
        "review_status": _normalize_optional_string(raw_chunk.get("review_status"))
        or "generated_from_sources",
    }

    source_excerpt = _normalize_optional_string(raw_chunk.get("source_excerpt"))
    if source_excerpt is not None:
        normalized_chunk["source_excerpt"] = source_excerpt

    source_claim = _normalize_optional_string(raw_chunk.get("source_claim"))
    if source_claim is not None:
        normalized_chunk["source_claim"] = source_claim

    if decision_signals:
        normalized_chunk["decision_signals"] = decision_signals

    original_scope = _normalize_optional_string(raw_chunk.get("scope"))
    if original_scope is not None:
        normalized_chunk["original_scope"] = original_scope

    return normalized_chunk


def _extract_raw_chunks(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        entries = payload.get("entries")
        if isinstance(entries, list):
            return entries
        chunks = payload.get("chunks")
        if isinstance(chunks, list):
            return chunks
    return []


def load_trusted_guidance_chunks(
    *,
    force_reload: bool = False,
    file_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    resolved_path = Path(file_path) if file_path is not None else _DEFAULT_SOURCE_FILE
    cache_key = str(resolved_path.resolve())

    if not force_reload and cache_key in _GUIDANCE_SOURCE_CACHE:
        return list(_GUIDANCE_SOURCE_CACHE[cache_key])

    try:
        raw_text = resolved_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Trusted guidance source file was not found: %s", resolved_path)
        _GUIDANCE_SOURCE_CACHE[cache_key] = []
        return []
    except OSError as exc:
        logger.warning(
            "Trusted guidance source file could not be read: %s error=%s",
            resolved_path,
            exc,
        )
        _GUIDANCE_SOURCE_CACHE[cache_key] = []
        return []

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Trusted guidance source file contained malformed JSON: %s error=%s",
            resolved_path,
            exc,
        )
        _GUIDANCE_SOURCE_CACHE[cache_key] = []
        return []

    normalized_chunks: list[dict[str, Any]] = []
    for index, raw_chunk in enumerate(_extract_raw_chunks(payload), start=1):
        normalized_chunk = _normalize_chunk(raw_chunk, index)
        if normalized_chunk is not None:
            normalized_chunks.append(normalized_chunk)

    _GUIDANCE_SOURCE_CACHE[cache_key] = normalized_chunks
    return list(normalized_chunks)
