from __future__ import annotations

import re
from typing import Any


UNKNOWN_TERMS = {"", "unknown", "uncertain", "unsure", "none", "not applicable"}
IDENTITY_ASPECTS = {
    "packaging_use",
    "form_factor",
    "construction",
    "power_source",
    "contents",
}
GENERIC_LABEL_TERMS = {
    "item",
    "object",
    "household object",
    "household item",
    "container",
    "unknown container",
    "rigid container",
}
BATTERY_TERMS = ("battery", "batteries", "battery-like cell", "cylindrical cell")
ELECTRONIC_TERMS = (
    "electronic",
    "electronics",
    "phone",
    "laptop",
    "calculator",
    "remote",
    "charger",
    "powered device",
)
ORGANIC_ITEM_TERMS = (
    "banana",
    "bananas",
    "banana bunch",
    "leafy greens",
    "green leaves",
    "plant leaves",
    "food scraps",
    "produce",
)
CONTAINER_FEATURE_TERMS = (
    "pump",
    "nozzle",
    "dispensing closure",
    "bottle",
    "personal care container",
    "personal-care container",
    "cosmetic container",
)
MUG_OR_COOKWARE_TERMS = ("ceramic mug", "mug", "pot", "pressure cooker")


def _normalize(value: Any) -> str:
    normalized = str(value or "").strip().casefold().replace("_", " ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokens(value: Any) -> list[str]:
    normalized = _normalize(value)
    return normalized.split() if normalized else []


def _contains_term(value: Any, term: Any) -> bool:
    value_tokens = _tokens(value)
    term_tokens = _tokens(term)
    if not value_tokens or not term_tokens or len(term_tokens) > len(value_tokens):
        return False
    width = len(term_tokens)
    return any(
        value_tokens[index : index + width] == term_tokens
        for index in range(len(value_tokens) - width + 1)
    )


def _contains_any(value: Any, terms: tuple[str, ...]) -> bool:
    return any(_contains_term(value, term) for term in terms)


def _coerce_confidence(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _normalized_details(recognition_details: dict[str, Any]) -> dict[str, Any]:
    value = recognition_details.get("normalized")
    return value if isinstance(value, dict) else {}


def _observations(recognition_details: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = _normalized_details(recognition_details)
    value = normalized.get("visual_observations")
    if not isinstance(value, list):
        value = recognition_details.get("visual_observations")
    return [item for item in value or [] if isinstance(item, dict)]


def _known_observation_value(observation: dict[str, Any]) -> str:
    value = _normalize(observation.get("value"))
    return "" if value in UNKNOWN_TERMS else value


def _observation_value_text(observations: list[dict[str, Any]]) -> str:
    return " ".join(
        value
        for observation in observations
        if (value := _known_observation_value(observation))
    )


def _evidence_quality(observations: list[dict[str, Any]]) -> str:
    known = [item for item in observations if _known_observation_value(item)]
    identity_aspects = {
        str(item.get("aspect") or "")
        for item in known
        if str(item.get("aspect") or "") in IDENTITY_ASPECTS
    }
    if len(known) >= 3 and len(identity_aspects) >= 2:
        return "strong"
    if len(known) >= 2 or identity_aspects:
        return "partial"
    return "weak"


def _candidate_scores(
    recognition_details: dict[str, Any],
) -> tuple[float | None, float | None]:
    candidates = recognition_details.get("candidates")
    if not isinstance(candidates, list):
        return None, None
    scores = [
        score
        for candidate in candidates[:3]
        if isinstance(candidate, dict)
        and (score := _coerce_confidence(candidate.get("confidence"))) is not None
    ]
    if not scores:
        return None, None
    top_score = scores[0]
    margin = top_score - scores[1] if len(scores) > 1 else None
    return top_score, margin


def _candidate_supports(
    recognition_details: dict[str, Any], terms: tuple[str, ...], *, minimum: float
) -> bool:
    candidates = recognition_details.get("candidates")
    if not isinstance(candidates, list):
        return False
    for candidate in candidates[:3]:
        if not isinstance(candidate, dict) or not _contains_any(
            candidate.get("label"), terms
        ):
            continue
        confidence = _coerce_confidence(candidate.get("confidence"))
        if confidence is not None and confidence >= minimum:
            return True
    return False


def _suggest_broader_label(
    label_text: str,
    observation_text: str,
    recognition_details: dict[str, Any],
) -> str | None:
    if _contains_any(observation_text, BATTERY_TERMS) and _candidate_supports(
        recognition_details, BATTERY_TERMS, minimum=0.45
    ):
        return "Battery"
    if _contains_any(observation_text, ("personal care", "personal-care", "cosmetic")):
        return "Personal care container"
    if _contains_any(observation_text, CONTAINER_FEATURE_TERMS):
        return "Rigid container"
    if _contains_any(observation_text, ("stainless steel", "metal cup")) and _contains_any(
        label_text, MUG_OR_COOKWARE_TERMS
    ):
        return "Metal cup"
    return None


def _contradictions(
    label_text: str,
    material_text: str,
    observations: list[dict[str, Any]],
    recognition_details: dict[str, Any],
) -> tuple[list[str], str | None]:
    observation_text = _observation_value_text(observations)
    reasons: list[str] = []

    battery_signal = _contains_any(observation_text, BATTERY_TERMS)
    label_is_battery_or_electronic = _contains_any(
        label_text, (*BATTERY_TERMS, *ELECTRONIC_TERMS)
    )
    if battery_signal and not label_is_battery_or_electronic:
        reasons.append("unresolved_power_source_conflict")

    specific_mug_or_cookware = _contains_any(label_text, MUG_OR_COOKWARE_TERMS)
    container_signal = _contains_any(observation_text, CONTAINER_FEATURE_TERMS)
    if specific_mug_or_cookware and container_signal:
        reasons.append("specific_container_feature_conflict")

    if _contains_term(label_text, "ceramic mug") and _contains_any(
        observation_text, ("metal", "stainless steel", "plastic bottle", "rigid plastic")
    ):
        reasons.append("label_material_conflict")

    organic_label = _contains_any(label_text, ORGANIC_ITEM_TERMS)
    if organic_label and (
        _contains_any(observation_text, ("ceramic", "handled cup", "plastic body"))
        or _contains_any(material_text, ("ceramic", "plastic", "metal"))
    ):
        reasons.append("organic_identity_material_conflict")

    return list(dict.fromkeys(reasons)), _suggest_broader_label(
        label_text, observation_text, recognition_details
    )


def evaluate_open_recognition(
    recognition_details: dict[str, Any],
) -> dict[str, Any]:
    normalized = _normalized_details(recognition_details)
    label = str(
        normalized.get("normalized_item")
        or normalized.get("item_label")
        or recognition_details.get("raw_item_label")
        or ""
    ).strip()
    label_text = _normalize(label)
    material_text = _normalize(
        normalized.get("primary_material")
        or normalized.get("material_category")
        or recognition_details.get("likely_material")
    )
    observations = _observations(recognition_details)
    evidence_quality = _evidence_quality(observations)
    top_score, candidate_margin = _candidate_scores(recognition_details)
    model_status = _normalize(recognition_details.get("status")) or "unknown"
    parse_mode = _normalize(recognition_details.get("parse_mode")) or "exact"
    material_confidence = _normalize(normalized.get("material_confidence"))
    normalization_source = _normalize(normalized.get("normalization_source"))
    contradictions, suggested_label = _contradictions(
        label_text,
        material_text,
        observations,
        recognition_details,
    )

    score = 0.0
    if model_status == "confident":
        score += 0.35
    elif model_status == "uncertain":
        score += 0.2
    if top_score is not None:
        score += 0.25 * top_score
    if candidate_margin is None:
        score += 0.1
    elif candidate_margin >= 0.12:
        score += 0.1
    elif candidate_margin >= 0.06:
        score += 0.05
    if evidence_quality == "strong":
        score += 0.15
    elif evidence_quality == "partial":
        score += 0.08
    if label_text and label_text not in UNKNOWN_TERMS:
        score += 0.1
    if material_confidence == "high":
        score += 0.05
    elif material_confidence == "medium":
        score += 0.025

    reason_codes: list[str] = list(contradictions)
    blocking = bool(contradictions)
    medium_cap = False
    if not label_text or label_text in UNKNOWN_TERMS:
        reason_codes.append("missing_item_identity")
        blocking = True
    if model_status == "unknown":
        reason_codes.append("model_returned_unknown")
        blocking = True
    elif model_status == "uncertain":
        reason_codes.append("model_returned_uncertain")
        blocking = True
        medium_cap = True
    if parse_mode in {"recovered", "partial", "truncated"}:
        reason_codes.append("truncated_or_recovered_output")
        blocking = True
        medium_cap = True
    if evidence_quality == "weak":
        reason_codes.append("weak_visual_evidence")
        medium_cap = True
    if top_score is not None and top_score < 0.65:
        reason_codes.append("low_top_candidate_confidence")
        medium_cap = True
    if candidate_margin is not None and candidate_margin < 0.08:
        reason_codes.append("ambiguous_candidate_margin")
        medium_cap = True
    if material_confidence in {"", "low"}:
        reason_codes.append("low_material_certainty")
    if normalization_source == "unknown fallback":
        reason_codes.append("uncertain_normalization")
        medium_cap = True
    if label_text in GENERIC_LABEL_TERMS:
        reason_codes.append("generic_item_label")
        medium_cap = True

    if contradictions or model_status == "unknown" or not label_text:
        level = "low"
        score = min(score, 0.39)
    elif medium_cap or score < 0.72:
        level = "medium"
        score = min(score, 0.74)
    else:
        level = "high"

    agreement = (
        "contradictory"
        if contradictions
        else "supported"
        if evidence_quality == "strong"
        else "insufficient"
    )
    return {
        "level": level,
        "score": round(max(0.0, min(1.0, score)), 4),
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "evidence_quality": evidence_quality,
        "candidate_margin": (
            round(candidate_margin, 4) if candidate_margin is not None else None
        ),
        "model_confidence": top_score,
        "label_observation_agreement": agreement,
        "suggested_label": suggested_label,
        "blocking": blocking,
    }


def user_confirmed_recognition_confidence() -> dict[str, Any]:
    return {
        "level": "high",
        "score": 1.0,
        "reason_codes": ["user_confirmed_selection"],
        "evidence_quality": "user_confirmed",
        "candidate_margin": None,
        "model_confidence": None,
        "label_observation_agreement": "user_confirmed",
        "suggested_label": None,
        "blocking": False,
    }

