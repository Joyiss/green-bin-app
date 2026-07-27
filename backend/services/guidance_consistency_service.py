from __future__ import annotations

import re
from typing import Any


_INCOMPATIBLE_REUSE_FLAGS = {"broken", "contaminated", "food_soiled", "single_use"}
_SPECIAL_HANDLING_FLAGS = {
    "battery",
    "chemical",
    "electronics",
    "hazardous",
    "special_handling",
}
_STRONG_EVIDENCE_ACTIONS = {
    "compost",
    "drop off",
    "household hazardous waste",
    "recycle",
}


def _normalize(value: Any) -> str:
    normalized = str(value or "").strip().casefold().replace("_", " ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalized_flags(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        normalized.replace(" ", "_")
        for item in value
        if (normalized := _normalize(item))
    }


def _normalized_details(classification: dict[str, Any]) -> dict[str, Any]:
    recognition_details = classification.get("recognition_details")
    if not isinstance(recognition_details, dict):
        return {}
    normalized = recognition_details.get("normalized")
    return normalized if isinstance(normalized, dict) else {}


def _condition_flags(classification: dict[str, Any]) -> set[str]:
    normalized = _normalized_details(classification)
    return _normalized_flags(normalized.get("condition_flags"))


def _special_flags(classification: dict[str, Any]) -> set[str]:
    normalized = _normalized_details(classification)
    return _normalized_flags(
        normalized.get("special_handling_flags") or normalized.get("special_flags")
    )


def _applicable_chunk_ids(guidance: dict[str, Any]) -> list[str]:
    metadata = guidance.get("guidance_metadata")
    if not isinstance(metadata, dict):
        return []
    value = metadata.get("applicable_chunk_ids")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _applicable_local_rule_ids(guidance: dict[str, Any]) -> list[str]:
    metadata = guidance.get("guidance_metadata")
    if not isinstance(metadata, dict):
        return []
    value = metadata.get("applicable_local_rule_ids")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _trusted_static_guidance(
    classification: dict[str, Any], guidance: dict[str, Any]
) -> bool:
    if guidance.get("guidance_source") != "legacy_rules_fallback":
        return False
    category = _normalize(classification.get("category"))
    if not category or category == "unknown":
        return False
    if classification.get("trusted_guidance_available") is False:
        return False
    metadata = guidance.get("guidance_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    if metadata.get("conditional_chunk_ids") or metadata.get(
        "not_applicable_chunk_ids"
    ):
        return False
    return True


def _requires_applicable_evidence(action: str) -> bool:
    return action in _STRONG_EVIDENCE_ACTIONS or action.endswith(" recycling")


def validate_guidance_consistency(
    classification: dict[str, Any], guidance: dict[str, Any]
) -> dict[str, Any]:
    action = _normalize(guidance.get("disposal_action"))
    condition_flags = _condition_flags(classification)
    special_flags = _special_flags(classification)
    applicable_chunk_ids = _applicable_chunk_ids(guidance)
    applicable_local_rule_ids = _applicable_local_rule_ids(guidance)
    contradictions: list[str] = []
    resolution = "conditional_guidance"

    if action == "donate reuse" and condition_flags & _INCOMPATIBLE_REUSE_FLAGS:
        contradictions.append("reuse_conflicts_with_explicit_condition")

    if (
        _requires_applicable_evidence(action)
        and not applicable_chunk_ids
        and not applicable_local_rule_ids
        and not _trusted_static_guidance(classification, guidance)
    ):
        contradictions.append("strong_action_without_applicable_evidence")

    unresolved_special_handling = special_flags & _SPECIAL_HANDLING_FLAGS
    if action == "trash" and unresolved_special_handling:
        contradictions.append("trash_conflicts_with_special_handling_evidence")
        resolution = "clarification"

    return {
        "valid": not contradictions,
        "contradiction_codes": contradictions,
        "resolution": resolution if contradictions else None,
        "evidence": {
            "condition_flags": sorted(condition_flags & _INCOMPATIBLE_REUSE_FLAGS),
            "special_handling_flags": sorted(unresolved_special_handling),
            "applicable_chunk_ids": applicable_chunk_ids,
            "applicable_local_rule_ids": applicable_local_rule_ids,
            "guidance_source": guidance.get("guidance_source"),
            "cache_hit": guidance.get("cache_hit") is True,
        },
    }
