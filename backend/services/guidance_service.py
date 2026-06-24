from __future__ import annotations

import re
from typing import Any

try:
    from ..rules import get_rules
    from . import guidance_retrieval_service
except ImportError:
    from rules import get_rules
    from services import guidance_retrieval_service

UNKNOWN_CATEGORY = "Unknown"
CHECK_LOCAL_GUIDANCE_ACTION = "Check local guidance"


def _empty_guidance() -> dict[str, Any]:
    return {
        "disposal_action": None,
        "material_code": None,
        "impact_level": None,
        "summary": None,
        "steps": [],
        "guidance_source": "safe_fallback",
    }


def _open_guidance_unavailable(classification: dict[str, Any]) -> dict[str, Any]:
    recognized_material = _first_non_empty_string(
        _normalized_open_value(classification, "material"),
        _normalized_open_value(classification, "material_category"),
        _normalized_open_value(classification, "broad_category"),
        classification.get("recognized_material_category"),
        classification.get("recognized_broad_category"),
    )

    steps = []
    if recognized_material and recognized_material != UNKNOWN_CATEGORY:
        steps.append(f"Detected material category: {recognized_material}.")
    steps.append(
        "Use local guidance or scan a supported item for trusted disposal instructions."
    )

    return {
        "disposal_action": None,
        "material_code": None,
        "impact_level": "Trusted Guidance Unavailable",
        "summary": "Trusted disposal guidance is not available yet for this recognized item.",
        "steps": steps,
        "guidance_source": "safe_fallback",
    }


def _default_safe_guidance() -> dict[str, Any]:
    return {
        "disposal_action": None,
        "material_code": None,
        "impact_level": "Trusted Guidance Unavailable",
        "summary": "Trusted disposal guidance is not available yet.",
        "steps": [
            "Use local guidance or scan a supported item for trusted disposal instructions."
        ],
        "guidance_source": "safe_fallback",
    }


def _format_item_name(item: str) -> str:
    if not item:
        return ""

    words = []
    for word in item.split():
        if "-" in word:
            parts = [
                part if part.isupper() else part.capitalize()
                for part in word.split("-")
            ]
            words.append("-".join(parts))
        else:
            words.append(word if word.isupper() else word.capitalize())

    return " ".join(words)


def _serialize_candidates(candidates: list[tuple[str, float]]) -> list[dict[str, Any]]:
    return [
        {
            "label": label.title(),
            "score": round(float(score), 4),
        }
        for label, score in candidates
    ]


def _first_non_empty_string(*values: Any) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue

        normalized_value = value.strip()
        if normalized_value:
            return normalized_value

    return None


def _normalized_open_details(classification: dict[str, Any]) -> dict[str, Any]:
    recognition_details = classification.get("recognition_details")
    if not isinstance(recognition_details, dict):
        return {}

    normalized = recognition_details.get("normalized")
    if not isinstance(normalized, dict):
        return {}

    return normalized


def _normalized_open_value(classification: dict[str, Any], key: str) -> str | None:
    value = _normalized_open_details(classification).get(key)
    return _first_non_empty_string(value)


def _is_open_recognition_classification(classification: dict[str, Any]) -> bool:
    return isinstance(classification.get("recognition_details"), dict)


def _build_default_summary(
    *,
    item: str,
    category: str,
    disposal_action: str | None,
) -> str | None:
    if not disposal_action:
        return None

    formatted_item = _format_item_name(item)
    normalized_category = category.strip().lower() if isinstance(category, str) else ""
    normalized_action = disposal_action.strip().lower()

    if formatted_item and normalized_category:
        return (
            f"{formatted_item} is categorized as {normalized_category} "
            f"and should be handled through {normalized_action} guidance in your area."
        )
    if formatted_item:
        return (
            f"{formatted_item} should be handled through {normalized_action} guidance in your area."
        )
    if normalized_category:
        return (
            f"This item is categorized as {normalized_category} and should be handled "
            f"through {normalized_action} guidance in your area."
        )

    return f"Handle this item through {normalized_action} guidance in your area."


def _choose_disposal_action(chunk: dict[str, Any]) -> str | None:
    supported_actions = [
        str(action).strip()
        for action in chunk.get("disposal_actions_supported", [])
        if str(action).strip()
    ]
    actionable = [
        action for action in supported_actions if action.casefold() != CHECK_LOCAL_GUIDANCE_ACTION.casefold()
    ]

    if len(actionable) != 1:
        return None

    return actionable[0].lower()


def _sentences_from_text(value: str) -> list[str]:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", value.strip())
        if sentence.strip()
    ]
    return sentences


def _build_json_summary(primary_chunk: dict[str, Any]) -> str:
    content = _first_non_empty_string(primary_chunk.get("content"))
    if content:
        summary_sentences = _sentences_from_text(content)[:2]
        summary = " ".join(summary_sentences).strip()
    else:
        summary = _first_non_empty_string(primary_chunk.get("title")) or "Trusted source guidance was retrieved for this item."

    source_name = _first_non_empty_string(primary_chunk.get("source_name"))
    if source_name and source_name.casefold() == "paintcare":
        summary = (
            f"{summary} Check whether a PaintCare program or participating drop-off site "
            f"is available in your area."
        )
    elif source_name and "earth911" in source_name.casefold():
        summary = f"{summary} Verify local facility acceptance before relying on this option."
    elif primary_chunk.get("requires_location_check") is True:
        summary = f"{summary} Check local rules or program availability before relying on this guidance."

    return summary


def _build_json_steps(primary_chunk: dict[str, Any], disposal_action: str | None) -> list[str]:
    steps: list[str] = []

    if disposal_action == "recycle":
        steps.append("Recycling may be appropriate based on the retrieved source guidance.")
    elif disposal_action == "compost":
        steps.append("Composting may be appropriate where a local organics program accepts this item.")
    elif disposal_action == "drop-off":
        steps.append("Use a designated drop-off or take-back program when one is available.")
    elif disposal_action == "trash":
        steps.append("Use regular trash only when the retrieved source guidance explicitly supports that option.")
    elif disposal_action == "donate/reuse":
        steps.append("Reuse or donation may be appropriate when the item is still usable.")
    else:
        steps.append("Multiple disposal paths may apply depending on the item condition and local program rules.")

    source_name = _first_non_empty_string(primary_chunk.get("source_name"))
    if source_name and source_name.casefold() == "paintcare":
        steps.append("Check whether a PaintCare program or participating site is available in your area.")
    elif source_name and "earth911" in source_name.casefold():
        steps.append("Verify the local facility accepts this material before visiting.")
    elif primary_chunk.get("requires_location_check") is True:
        steps.append("Check local or program-specific availability before relying on this guidance.")

    limitations = primary_chunk.get("limitations") or []
    if isinstance(limitations, list) and limitations:
        steps.append(str(limitations[0]))

    return steps


def _build_json_guidance_metadata(
    retrieval_results: list[dict[str, Any]],
) -> dict[str, Any]:
    retrieved_chunk_ids: list[str] = []
    source_names: list[str] = []
    source_urls: list[str] = []
    matched_fields: dict[str, list[str]] = {}
    retrieval_scores: dict[str, float] = {}
    limitations: dict[str, list[str]] = {}
    requires_location_check = False

    for result in retrieval_results[:3]:
        chunk = result.get("chunk", {})
        chunk_id = str(result.get("chunk_id") or chunk.get("id") or "")
        if not chunk_id:
            continue

        retrieved_chunk_ids.append(chunk_id)
        source_name = _first_non_empty_string(chunk.get("source_name"))
        source_url = _first_non_empty_string(chunk.get("source_url"))
        if source_name and source_name not in source_names:
            source_names.append(source_name)
        if source_url and source_url not in source_urls:
            source_urls.append(source_url)

        matched_fields[chunk_id] = list(result.get("matched_fields") or [])
        retrieval_scores[chunk_id] = float(result.get("score") or 0.0)
        if chunk.get("limitations"):
            limitations[chunk_id] = list(chunk.get("limitations") or [])
        if result.get("requires_location_check") is True:
            requires_location_check = True

    metadata = {
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "source_names": source_names,
        "source_urls": source_urls,
        "matched_fields": matched_fields,
        "retrieval_scores": retrieval_scores,
        "requires_location_check": requires_location_check,
    }
    if limitations:
        metadata["limitations"] = limitations

    return metadata


def _guidance_from_json_retrieval(
    retrieval_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not retrieval_results:
        return None

    primary_result = retrieval_results[0]
    primary_chunk = primary_result.get("chunk")
    if not isinstance(primary_chunk, dict):
        return None

    disposal_action = _choose_disposal_action(primary_chunk)
    warnings: list[str] = []
    for result in retrieval_results[:3]:
        chunk = result.get("chunk", {})
        for warning in chunk.get("warnings") or []:
            normalized_warning = str(warning).strip()
            if normalized_warning and normalized_warning not in warnings:
                warnings.append(normalized_warning)

    guidance = {
        "disposal_action": disposal_action,
        "material_code": None,
        "impact_level": (
            "Check Local Guidance"
            if primary_chunk.get("requires_location_check") is True
            else "Source-Grounded Guidance"
        ),
        "summary": _build_json_summary(primary_chunk),
        "steps": _build_json_steps(primary_chunk, disposal_action),
        "guidance_source": "json_rag_direct_generated",
        "guidance_metadata": _build_json_guidance_metadata(retrieval_results),
    }
    if warnings:
        guidance["warnings"] = warnings

    return guidance


def _guidance_from_legacy_rules(
    classification: dict[str, Any],
) -> dict[str, Any] | None:
    category = classification.get("category")
    if not isinstance(category, str) or not category.strip() or category == UNKNOWN_CATEGORY:
        return None

    legacy_guidance = get_rules(category)
    if not isinstance(legacy_guidance, dict):
        return None

    disposal_action = legacy_guidance.get("disposal_action")
    return {
        "disposal_action": disposal_action,
        "material_code": legacy_guidance.get("material_code"),
        "impact_level": legacy_guidance.get("impact_level"),
        "summary": _build_default_summary(
            item=str(classification.get("item") or ""),
            category=category,
            disposal_action=disposal_action,
        ),
        "steps": legacy_guidance.get("steps") or [],
        "guidance_source": "legacy_rules_fallback",
    }


def _build_retrieval_inputs(classification: dict[str, Any]) -> dict[str, Any]:
    if _is_open_recognition_classification(classification):
        return {
            "item_label": _first_non_empty_string(
                _normalized_open_value(classification, "item_label"),
                classification.get("trusted_guidance_label"),
                classification.get("item"),
            ),
            "material": _first_non_empty_string(
                _normalized_open_value(classification, "material"),
                _normalized_open_value(classification, "material_category"),
                classification.get("recognized_material_category"),
            ),
            "category": _first_non_empty_string(
                _normalized_open_value(classification, "broad_category"),
                classification.get("recognized_broad_category"),
                classification.get("category"),
            ),
            "condition_flags": _normalized_open_details(classification).get(
                "condition_flags", []
            ),
            "location": classification.get("location"),
        }

    return {
        "item_label": _first_non_empty_string(classification.get("item")),
        "material": _first_non_empty_string(classification.get("category")),
        "category": _first_non_empty_string(classification.get("category")),
        "condition_flags": [],
        "location": classification.get("location"),
    }


def _lookup_json_guidance(classification: dict[str, Any]) -> list[dict[str, Any]]:
    retrieval_inputs = _build_retrieval_inputs(classification)
    try:
        return guidance_retrieval_service.retrieve_guidance_chunks(**retrieval_inputs)
    except Exception:
        return []


def _resolve_guidance(classification: dict[str, Any]) -> dict[str, Any]:
    if classification.get("status") != "confident":
        return _empty_guidance()

    json_guidance = _guidance_from_json_retrieval(_lookup_json_guidance(classification))
    if json_guidance is not None:
        return json_guidance

    legacy_guidance = _guidance_from_legacy_rules(classification)
    if legacy_guidance is not None:
        return legacy_guidance

    if _is_open_recognition_classification(classification):
        return _open_guidance_unavailable(classification)

    return _default_safe_guidance()


def build_prediction_response(classification: dict[str, Any]) -> dict[str, Any]:
    guidance = _resolve_guidance(classification)

    response = {
        "item": _format_item_name(str(classification.get("item") or "")),
        "category": classification.get("category", UNKNOWN_CATEGORY),
        "status": classification.get("status", "unknown"),
        "candidates": _serialize_candidates(classification.get("candidates", [])),
        "disposal_action": guidance["disposal_action"],
        "material_code": guidance["material_code"],
        "impact_level": guidance["impact_level"],
        "summary": guidance["summary"],
        "steps": guidance["steps"],
        "guidance_source": guidance["guidance_source"],
    }

    warnings = guidance.get("warnings")
    if isinstance(warnings, list) and warnings:
        response["warnings"] = warnings

    guidance_metadata = guidance.get("guidance_metadata")
    if isinstance(guidance_metadata, dict) and guidance_metadata:
        response["guidance_metadata"] = guidance_metadata

    if "cache_hit" in classification:
        response["cache_hit"] = bool(classification["cache_hit"])
    if "recognition_source" in classification:
        response["recognition_source"] = classification["recognition_source"]

    return response
