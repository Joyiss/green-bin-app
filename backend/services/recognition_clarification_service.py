from __future__ import annotations

import re
from typing import Any


SAFETY_REASON_CODES = {
    "unresolved_power_source_conflict",
    "unresolved_battery_identity",
    "unresolved_electronics_identity",
    "unresolved_hazardous_identity",
}
ELECTRONIC_TERMS = (
    "electronic",
    "electronics",
    "calculator",
    "charger",
    "computer",
    "earbud",
    "headphone",
    "keyboard",
    "laptop",
    "phone",
    "remote",
    "tablet",
)


def _normalize(value: Any) -> str:
    normalized = str(value or "").strip().casefold().replace("_", " ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_term(value: Any, term: Any) -> bool:
    value_tokens = _normalize(value).split()
    term_tokens = _normalize(term).split()
    if not value_tokens or not term_tokens or len(term_tokens) > len(value_tokens):
        return False
    width = len(term_tokens)
    return any(
        value_tokens[index : index + width] == term_tokens
        for index in range(len(value_tokens) - width + 1)
    )


def _contains_any(value: Any, terms: tuple[str, ...]) -> bool:
    return any(_contains_term(value, term) for term in terms)


def _normalized_details(classification: dict[str, Any]) -> dict[str, Any]:
    recognition_details = classification.get("recognition_details")
    if not isinstance(recognition_details, dict):
        return {}
    normalized = recognition_details.get("normalized")
    return normalized if isinstance(normalized, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safety_ambiguity_reasons(classification: dict[str, Any]) -> list[str]:
    normalized = _normalized_details(classification)
    special_flags = {
        _normalize(flag).replace(" ", "_")
        for flag in _string_list(
            normalized.get("special_handling_flags")
            or normalized.get("special_flags")
        )
    }
    label_context = " ".join(
        str(value or "")
        for value in (
            classification.get("item"),
            classification.get("category"),
            normalized.get("item_label"),
            normalized.get("disposal_category"),
            normalized.get("broad_category"),
        )
    )
    reasons: list[str] = []
    if "battery" in special_flags and not _contains_any(
        label_context, ("battery", "batteries")
    ):
        reasons.append("unresolved_battery_identity")
    if "electronics" in special_flags and not _contains_any(
        label_context, ELECTRONIC_TERMS
    ):
        reasons.append("unresolved_electronics_identity")
    if "hazardous" in special_flags and not _contains_any(
        label_context,
        (
            "hazardous",
            "paint",
            "chemical",
            "aerosol",
            "propane",
            "motor oil",
            "needle",
            "syringe",
            "sharp",
            "sharps",
        ),
    ):
        reasons.append("unresolved_hazardous_identity")
    return reasons


def evaluate_clarification(classification: dict[str, Any]) -> dict[str, Any]:
    recognition_source = _normalize(classification.get("recognition_source"))
    if recognition_source == "user confirmed selection":
        return {
            "required": False,
            "reason_codes": [],
            "retake_recommended": False,
            "retake_guidance": None,
            "message": None,
            "safety_relevant": False,
        }

    confidence = classification.get("recognition_confidence")
    confidence = confidence if isinstance(confidence, dict) else {}
    level = _normalize(confidence.get("level"))
    reason_codes = _string_list(confidence.get("reason_codes"))
    safety_reasons = _safety_ambiguity_reasons(classification)
    reason_codes.extend(
        reason for reason in safety_reasons if reason not in reason_codes
    )
    status = _normalize(classification.get("status")) or "unknown"

    required = bool(confidence.get("blocking"))
    if level == "low":
        required = True
        if "low_recognition_confidence" not in reason_codes:
            reason_codes.append("low_recognition_confidence")
    if status in {"uncertain", "unknown"}:
        required = True
        status_reason = f"recognition_status_{status}"
        if status_reason not in reason_codes:
            reason_codes.append(status_reason)
    if safety_reasons:
        required = True

    if not required:
        return {
            "required": False,
            "reason_codes": [],
            "retake_recommended": False,
            "retake_guidance": None,
            "message": None,
            "safety_relevant": False,
        }

    safety_relevant = bool(SAFETY_REASON_CODES & set(reason_codes))
    message = (
        "Confirm this item before disposal guidance because the image may contain a battery, electronic, or hazardous item."
        if safety_relevant
        else "Confirm or correct the recognized item before disposal guidance is shown."
    )
    return {
        "required": True,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "retake_recommended": True,
        "retake_guidance": (
            "Retake the photo with the whole item visible in brighter light, with labels and physical features in focus."
        ),
        "message": message,
        "safety_relevant": safety_relevant,
    }
