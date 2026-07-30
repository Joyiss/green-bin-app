from __future__ import annotations

import logging
import re
from time import perf_counter
from typing import Any

try:
    from ..materials import resolve_material_label
    from ..rules import get_rules
    from . import guidance_cache_service, guidance_consistency_service, guidance_llm_service, guidance_retrieval_service, local_guidance_matcher, request_context, tavily_local_guidance_service
    from .guidance_key_service import normalize_guidance_phrase
    from .recognition_clarification_service import evaluate_clarification
except ImportError:
    from materials import resolve_material_label
    from rules import get_rules
    from services import guidance_cache_service, guidance_consistency_service, guidance_llm_service, guidance_retrieval_service, local_guidance_matcher, request_context, tavily_local_guidance_service
    from services.guidance_key_service import normalize_guidance_phrase
    from services.recognition_clarification_service import evaluate_clarification

logger = logging.getLogger(__name__)

UNKNOWN_CATEGORY = "Unknown"
CHECK_LOCAL_GUIDANCE_ACTION = "Check local guidance"
_HIGH_RISK_KEYWORDS = {
    "battery",
    "batteries",
    "rechargeable battery",
    "lithium ion",
    "paint",
    "stain",
    "solvent",
    "electronics",
    "electronic waste",
    "e waste",
    "e-waste",
    "circuit board",
    "phone",
    "laptop",
    "monitor",
    "tv",
    "charger",
    "aerosol",
    "motor oil",
    "oil filter",
    "gasoline",
    "fuel",
    "propane",
    "pressurized can",
    "fluorescent",
    "fluorescent bulb",
    "cfl",
    "mercury bulb",
    "chemical",
    "cleaner",
    "bleach",
    "pesticide",
    "medicine",
    "medication",
    "medical waste",
    "biohazard",
    "sharp",
    "sharps",
    "needle",
    "syringe",
    "hazardous",
    "hazardous waste",
    "special handling",
}
_HIGH_RISK_FLAGS = {
    "battery",
    "hazardous",
    "electronics",
    "special_handling",
    "regulated",
    "requires_dropoff",
}
_CAUTION_KEYWORDS = {
    "food soiled paper",
    "food soiled cardboard",
    "greasy pizza box",
    "thermal receipt",
    "receipt paper",
    "laminated paper",
    "wax coated paper",
    "waxed cardboard",
    "shredded paper",
    "broken glass",
    "mirror glass",
    "ceramic shards",
    "treated wood",
    "painted wood",
    "pressure treated wood",
    "sharp metal",
    "unknown liquid container",
    "dirty",
    "oily",
    "moldy",
    "chemically contaminated",
    "medical contaminated",
    "bodily fluids",
}
_LOW_RISK_ALLOW_GROUPS = {
    "allowed_paper_stationery": {
        "paper",
        "paper product",
        "sheet music",
        "music sheet",
        "printed paper",
        "notebook paper",
        "loose paper",
        "stationery",
        "envelope",
        "folder",
        "worksheet",
        "book",
        "notebook",
        "clean cardboard",
        "pencil",
        "pen",
        "eraser",
        "ruler",
    },
    "allowed_textile_soft_goods": {
        "curtain",
        "fabric",
        "textile",
        "clothing",
        "shirt",
        "pants",
        "towel",
        "blanket",
        "backpack",
        "bag",
        "shoes",
    },
    "allowed_reusable_household": {
        "ceramic mug",
        "cup",
        "plate",
        "bowl",
        "glass cup",
        "water bottle",
        "metal water bottle",
        "thermoflask",
        "insulated bottle",
        "reusable container",
        "lunch box",
    },
    "allowed_simple_household_objects": {
        "plastic toy",
        "rubber duck",
        "toy",
        "wooden toy",
        "wooden spoon",
        "plastic spoon",
        "hanger",
        "basket",
        "storage bin",
        "decoration",
        "household item",
    },
    "allowed_simple_material": {
        "clean paper",
        "clean cardboard",
        "untreated wood",
        "simple plastic",
        "hard plastic",
        "fabric",
        "textile",
        "ceramic",
        "non broken glass",
        "simple metal",
        "paper",
        "cardboard",
        "wood",
        "plastic",
        "metal",
        "glass",
    },
    "allowed_single_use_packaging": {
        "wrapper",
        "single use",
        "single-use",
        "product container",
        "personal care container",
        "cosmetic container",
        "food packaging",
    },
    "allowed_organic_material": {
        "organic",
        "organic food",
        "organic fruit",
        "organic plant material",
        "produce",
        "food scraps",
        "fruit scraps",
        "vegetable scraps",
        "leaves",
        "leafy material",
        "yard waste",
    },
    "allowed_durable_reusable": {
        "reusable",
        "appears reusable",
        "appears intact",
        "utensil",
        "stainless steel",
        "metal cup",
    },
}
_LOW_RISK_DROP_OFF_ONLY_TERMS = {
    "textile",
    "clothing",
    "backpack",
    "bag",
    "shoes",
    "curtain",
    "fabric",
}
_LLM_SKIP_REASONS = {
    "llm_disabled",
    "ENABLE_LLM_GUIDANCE_false",
    "provider_not_groq",
    "missing_GROQ_API_KEY",
    "no_chunks",
}


def _log_guidance_timing(stage: str, started: float, **fields: Any) -> None:
    request_id = request_context.get_predict_request_id()
    if request_id is not None and "request_id" not in fields:
        fields = {"request_id": request_id, **fields}
    field_text = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info(
        "guidance_timing stage=%s duration_ms=%.1f %s",
        stage,
        (perf_counter() - started) * 1000,
        field_text,
    )
_COMMON_LOW_RISK_WARNING = (
    "Do not place this item in curbside recycling unless your local program accepts it."
)


def _empty_guidance() -> dict[str, Any]:
    return {
        "disposal_action": None,
        "material_code": None,
        "impact_level": None,
        "summary": None,
        "steps": [],
        "guidance_source": "safe_fallback",
    }


def _clarification_guidance(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "disposal_action": None,
        "material_code": None,
        "impact_level": None,
        "summary": decision.get("message"),
        "steps": [],
        "guidance_source": "recognition_clarification_required",
        "guidance_metadata": {
            "final_generation_path": "recognition_clarification",
            "clarification_reason_codes": list(decision.get("reason_codes") or []),
        },
    }


def _consistency_guard_metadata(
    validation: dict[str, Any], guidance: dict[str, Any]
) -> dict[str, Any]:
    return {
        "consistency_guard_triggered": True,
        "consistency_contradiction_codes": list(
            validation.get("contradiction_codes") or []
        ),
        "consistency_resolution": validation.get("resolution"),
        "rejected_disposal_action": guidance.get("disposal_action"),
        "rejected_guidance_source": guidance.get("guidance_source"),
        "rejected_cache_hit": guidance.get("cache_hit") is True,
    }


def _consistency_clarification_decision(
    validation: dict[str, Any],
) -> dict[str, Any]:
    reason_codes = [
        "guidance_consistency_guard",
        *list(validation.get("contradiction_codes") or []),
    ]
    return {
        "required": True,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "retake_recommended": True,
        "retake_guidance": (
            "Retake the photo with the whole item visible in brighter light, with labels and safety-relevant features in focus."
        ),
        "message": (
            "Confirm this item before disposal guidance because battery, electronic, chemical, or hazardous evidence conflicts with ordinary trash guidance."
        ),
        "safety_relevant": True,
    }


def _first_non_empty_string(*values: Any) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue

        normalized_value = value.strip()
        if normalized_value:
            return normalized_value

    return None


def _merge_guidance_metadata(*metadata_values: Any) -> dict[str, Any]:
    merged_metadata: dict[str, Any] = {}
    for metadata in metadata_values:
        if not isinstance(metadata, dict):
            continue
        merged_metadata.update(metadata)
    return merged_metadata


def _with_metadata(
    guidance: dict[str, Any],
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(extra_metadata, dict) or not extra_metadata:
        return guidance

    existing_metadata = guidance.get("guidance_metadata")
    guidance["guidance_metadata"] = _merge_guidance_metadata(
        existing_metadata,
        extra_metadata,
    )
    return guidance


_TAVILY_ELIGIBILITY_SKIP_REASONS = {
    "recognition_not_confident",
    "clarification_required",
    "item_not_specific",
    "missing_location",
    "trusted_manual_rule",
}
_LOCAL_GUIDANCE_UNAVAILABLE_MESSAGE = (
    "Verified local guidance is temporarily unavailable. "
    "Here is general disposal guidance for this item."
)
_LOCAL_GUIDANCE_CONFIRM_RULES_MESSAGE = (
    "Verified local guidance is temporarily unavailable. "
    "Confirm local rules before acting. "
    "Here is general disposal guidance for this item."
)


def _attach_tavily_outcome(
    guidance: dict[str, Any],
    outcome: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(outcome, dict):
        return guidance
    status = _first_non_empty_string(outcome.get("status"))
    skip_reason = _first_non_empty_string(outcome.get("skip_reason"))
    if status is None:
        return guidance

    if (
        outcome.get("called") is not True
        and skip_reason in _TAVILY_ELIGIBILITY_SKIP_REASONS
    ):
        return guidance

    metadata = {
        "local_guidance_status": status,
        "tavily_called": outcome.get("called") is True,
        "tavily_result_count": int(outcome.get("result_count") or 0),
        "tavily_trusted_source_count": int(
            outcome.get("trusted_source_count") or 0
        ),
    }
    credits = outcome.get("credits")
    if isinstance(credits, int) and credits >= 0:
        metadata["tavily_reported_credit_usage"] = credits
    sources = outcome.get("sources")
    if isinstance(sources, list) and sources:
        metadata["trusted_local_sources"] = [
            {
                key: source.get(key)
                for key in (
                    "title",
                    "organization",
                    "url",
                    "trusted",
                    "local",
                    "status",
                    "trust_level",
                )
            }
            for source in sources
            if isinstance(source, dict)
        ]

    if status == "tavily_verified_local" and _guidance_uses_verified_local_source(
        guidance
    ):
        guidance["impact_level"] = "Verified Local Guidance"
    else:
        metadata["guidance_fallback_status"] = "general_fallback"
        fallback_message = (
            _LOCAL_GUIDANCE_CONFIRM_RULES_MESSAGE
            if status == "tavily_official_supporting"
            else _LOCAL_GUIDANCE_UNAVAILABLE_MESSAGE
        )
        summary = _first_non_empty_string(guidance.get("summary"))
        guidance["summary"] = (
            f"{fallback_message} {summary}"
            if summary and fallback_message not in summary
            else summary or fallback_message
        )

    return _with_metadata(guidance, metadata)


def _guidance_uses_verified_local_source(guidance: dict[str, Any]) -> bool:
    metadata = guidance.get("guidance_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    if metadata.get("requires_location_check") is True:
        return False
    if guidance.get("guidance_source") != "json_rag_llm_generated":
        return False
    source_ids = {
        str(value)
        for value in (
            metadata.get("retrieved_chunk_ids")
            or metadata.get("sources_used")
            or []
        )
        if value
    }
    applicable_ids = {
        str(value) for value in metadata.get("applicable_chunk_ids") or [] if value
    }
    candidate_ids = source_ids & applicable_ids if source_ids else applicable_ids
    if not candidate_ids:
        return False

    matched_fields = metadata.get("matched_fields")
    matched_fields = matched_fields if isinstance(matched_fields, dict) else {}
    applicability = metadata.get("applicability_by_chunk")
    applicability = applicability if isinstance(applicability, dict) else {}
    local_tokens = {
        "location_exact",
        "city_exact",
        "county_exact",
        "provider_exact",
        "statewide",
        "statewide_rule",
    }
    for chunk_id in candidate_ids:
        if applicability.get(chunk_id) != "applicable":
            continue
        fields = {
            str(field)
            for field in (
                matched_fields.get(chunk_id)
                if isinstance(matched_fields.get(chunk_id), list)
                else []
            )
        }
        if fields & local_tokens:
            return True

    return any(
        isinstance(source, dict)
        and source.get("local") is True
        and str(source.get("trust_level") or "") == "LOCAL_PRIMARY"
        for source in metadata.get("trusted_local_sources") or []
    )


def _local_web_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "local_guidance_status",
        "guidance_fallback_status",
        "tavily_called",
        "tavily_result_count",
        "tavily_trusted_source_count",
        "tavily_reported_credit_usage",
        "trusted_local_sources",
    )
    return {
        key: metadata[key]
        for key in keys
        if key in metadata and metadata[key] not in (None, [], {})
    }


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


def _normalized_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized_values: list[str] = []
    for item in value:
        normalized_item = normalize_guidance_phrase(item)
        if normalized_item:
            normalized_values.append(normalized_item.replace(" ", "_"))
    return normalized_values


def _visual_observations(classification: dict[str, Any]) -> list[dict[str, Any]]:
    recognition_details = classification.get("recognition_details")
    normalized_details = _normalized_open_details(classification)
    raw_observations = normalized_details.get("visual_observations")
    if not isinstance(raw_observations, list) and isinstance(recognition_details, dict):
        raw_observations = recognition_details.get("visual_observations")
    if not isinstance(raw_observations, list):
        return []

    observations: list[dict[str, Any]] = []
    for raw_observation in raw_observations:
        if not isinstance(raw_observation, dict):
            continue
        aspect = _first_non_empty_string(raw_observation.get("aspect"))
        value = _first_non_empty_string(raw_observation.get("value"))
        if aspect is None or value is None:
            continue
        evidence = _first_non_empty_string(raw_observation.get("evidence")) or ""
        confidence_value = raw_observation.get("confidence")
        confidence: float | None = None
        try:
            if confidence_value is not None:
                confidence = max(0.0, min(1.0, float(confidence_value)))
        except (TypeError, ValueError):
            confidence = None
        observations.append(
            {
                "aspect": aspect,
                "value": value,
                "confidence": confidence,
                "evidence": evidence,
            }
        )
    return observations


def _visual_observation_text_values(observations: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for observation in observations:
        for key in ("aspect", "value", "evidence"):
            normalized = _first_non_empty_string(observation.get(key))
            if normalized and normalized.casefold() != UNKNOWN_CATEGORY.casefold():
                values.append(normalized)
    return values


def _visual_observation_flags(observations: list[dict[str, Any]]) -> list[str]:
    normalized_text = " ".join(
        normalize_guidance_phrase(value) or ""
        for value in _visual_observation_text_values(observations)
    )
    flags: list[str] = []
    flag_patterns = (
        ("food_soiled", ("food residue", "crumb", "greasy", "soiled", "food soiled")),
        ("contaminated", ("contaminated", "dirty", "residue", "stained")),
        ("empty", ("empty",)),
        ("opened", ("open", "opened", "unsealed")),
        ("broken", ("broken", "cracked", "shattered", "damaged")),
        ("wet", ("wet", "damp", "soaked")),
        ("single_use", ("single use", "single-use", "disposable")),
        ("reusable", ("reusable", "durable", "refillable")),
        ("battery", ("battery compartment", "battery powered", "battery visible")),
        ("recycling_mark_visible", ("recycling mark", "recycling symbol", "resin code")),
    )
    for flag, patterns in flag_patterns:
        if any(pattern in normalized_text for pattern in patterns):
            flags.append(flag)
    return _candidate_values(flags)


def _combined_visual_evidence(classification: dict[str, Any]) -> str | None:
    recognition_details = classification.get("recognition_details")
    observations = _visual_observations(classification)
    values = _candidate_values(
        recognition_details.get("visual_evidence") if isinstance(recognition_details, dict) else None,
        _visual_observation_text_values(observations),
    )
    return "; ".join(values) if values else None


def _candidate_values(*values: Any) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for value in values:
        if isinstance(value, list):
            candidate_source = value
        else:
            candidate_source = [value]

        for candidate in candidate_source:
            if not isinstance(candidate, str):
                continue

            normalized_candidate = candidate.strip()
            if not normalized_candidate:
                continue
            if normalized_candidate.casefold() == UNKNOWN_CATEGORY.casefold():
                continue

            dedupe_key = normalized_candidate.casefold()
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            candidates.append(normalized_candidate)

    return candidates


def _format_log_list(values: list[Any]) -> str:
    return "[" + ", ".join(str(value) for value in values) + "]"


def _log_resolution_started(
    classification: dict[str, Any],
    retrieval_inputs: dict[str, Any],
) -> None:
    logger.info(
        "Guidance resolution started. item=%s category=%s material=%s recognition_source=%s open_normalized=%s lookup_item=%s lookup_material=%s lookup_category=%s observation_count=%s",
        classification.get("item"),
        classification.get("category"),
        _first_non_empty_string(
            _normalized_open_value(classification, "material"),
            _normalized_open_value(classification, "material_category"),
            classification.get("recognized_material_category"),
        ),
        classification.get("recognition_source"),
        _is_open_recognition_classification(classification),
        retrieval_inputs.get("item_label"),
        retrieval_inputs.get("material"),
        retrieval_inputs.get("category"),
        len(retrieval_inputs.get("visual_observations") or []),
    )


def _log_retrieval_complete(retrieval_results: list[dict[str, Any]]) -> None:
    top_chunks: list[str] = []
    source_names: list[str] = []
    matched_fields: list[str] = []
    applicability: list[str] = []

    for result in retrieval_results[:3]:
        chunk = result.get("chunk", {})
        chunk_id = _first_non_empty_string(result.get("chunk_id"), chunk.get("id")) or "unknown"
        score = round(float(result.get("score") or 0.0), 4)
        top_chunks.append(f"{chunk_id}:{score}")

        source_name = _first_non_empty_string(chunk.get("source_name"))
        if source_name and source_name not in source_names:
            source_names.append(source_name)

        result_fields = list(result.get("matched_fields") or [])
        if result_fields:
            matched_fields.append(f"{chunk_id}={'|'.join(str(field) for field in result_fields)}")
        applicability.append(
            f"{chunk_id}={result.get('applicability') or 'applicable'}"
        )

    logger.info(
        "Guidance retrieval complete. count=%s top_chunks=%s sources=%s matched_fields=%s applicability=%s",
        len(retrieval_results),
        _format_log_list(top_chunks),
        _format_log_list(source_names),
        _format_log_list(matched_fields),
        _format_log_list(applicability),
    )


def _log_guidance_selected(
    guidance: dict[str, Any],
    *,
    chunk_ids: list[str] | None = None,
    requires_location_check: bool | None = None,
    reason: str | None = None,
    item: str | None = None,
    category: str | None = None,
    low_risk_eligible: bool | None = None,
    reason_codes: list[str] | None = None,
) -> None:
    log_parts = [f"source={guidance.get('guidance_source')}"]
    if chunk_ids is not None:
        log_parts.append(f"chunks={_format_log_list(chunk_ids)}")
    if guidance.get("disposal_action") is not None:
        log_parts.append(f"disposal_action={guidance.get('disposal_action')}")
    else:
        log_parts.append("disposal_action=None")
    if requires_location_check is not None:
        log_parts.append(f"requires_location_check={requires_location_check}")
    if item:
        log_parts.append(f"item={item}")
    if category:
        log_parts.append(f"category={category}")
    if low_risk_eligible is not None:
        log_parts.append(f"low_risk_eligible={low_risk_eligible}")
    if reason:
        log_parts.append(f"reason={reason}")
    if reason_codes is not None:
        log_parts.append(f"reason_codes={_format_log_list(reason_codes)}")

    logger.info("Guidance selected. %s", " ".join(log_parts))


def _is_open_recognition_classification(classification: dict[str, Any]) -> bool:
    return isinstance(classification.get("recognition_details"), dict)


def _general_fallback_guidance(
    classification: dict[str, Any] | None = None,
    *,
    reason: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = _first_non_empty_string(
        classification.get("item") if isinstance(classification, dict) else None
    )
    recognized_material = _first_non_empty_string(
        _normalized_open_value(classification, "material") if isinstance(classification, dict) else None,
        _normalized_open_value(classification, "material_category") if isinstance(classification, dict) else None,
        classification.get("recognized_material_category") if isinstance(classification, dict) else None,
        classification.get("category") if isinstance(classification, dict) else None,
    )

    subject = f"the {item.lower()}" if item else "this item"
    steps = [
        f"Keep {subject} out of curbside recycling unless your local program explicitly accepts it.",
        "Check your city, county, or waste-provider disposal guidance before choosing recycling, compost, hazardous-waste, or drop-off options.",
        "If no verified local option is available, follow local trash guidance or ask your waste provider.",
    ]
    if recognized_material and recognized_material != UNKNOWN_CATEGORY:
        steps.append(
            f"Use the detected material/category only as context: {recognized_material}."
        )

    guidance = {
        "disposal_action": "check local guidance",
        "material_code": None,
        "impact_level": "Low Confidence Guidance",
        "summary": (
            f"Verified local guidance is unavailable for {subject}, so use conservative general disposal guidance."
        ),
        "steps": steps,
        "guidance_source": "safe_fallback",
        "warnings": [_COMMON_LOW_RISK_WARNING],
        "guidance_metadata": {
            "final_generation_path": "general_fallback",
            "guidance_fallback_status": "general_fallback",
            "fallback_reason": reason or "no_usable_source_grounded_guidance",
            "confidence": "low",
            "source_names": [],
            "source_urls": [],
            "retrieved_chunk_ids": [],
            "requires_location_check": True,
        },
    }
    return _with_metadata(guidance, extra_metadata)


def _open_guidance_unavailable(
    classification: dict[str, Any],
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _general_fallback_guidance(
        classification,
        reason="open_guidance_unavailable",
        extra_metadata=extra_metadata,
    )


def _default_safe_guidance(
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _general_fallback_guidance(
        None,
        reason="default_safe_fallback",
        extra_metadata=extra_metadata,
    )


def _normalized_phrase(value: Any) -> str:
    normalized_value = normalize_guidance_phrase(value)
    return normalized_value or ""


def _contains_any_phrase(haystack: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in haystack for phrase in phrases)


def _deterministic_low_risk_group(
    classification: dict[str, Any],
    low_risk_evaluation: dict[str, Any],
) -> str:
    reason = _first_non_empty_string(low_risk_evaluation.get("reason")) or ""
    item_text = _normalized_phrase(classification.get("item"))
    material_text = _normalized_phrase(
        _first_non_empty_string(
            _normalized_open_value(classification, "material"),
            _normalized_open_value(classification, "material_category"),
            classification.get("recognized_material_category"),
            classification.get("category"),
        )
    )
    normalized_details = _normalized_open_details(classification)
    condition_flags = {
        _normalized_phrase(value).replace(" ", "_")
        for value in normalized_details.get("condition_flags") or []
        if _normalized_phrase(value)
    }
    observation_values = " ".join(
        _normalized_phrase(observation.get("value"))
        for observation in _visual_observations(classification)
        if isinstance(observation, dict)
    )
    context_text = " ".join([item_text, material_text, observation_values])

    if any(term in context_text for term in ("organic", "produce", "food scrap", "leaves", "leafy", "yard waste")):
        return "organic_material"
    if "paper" in material_text and any(
        term in item_text for term in ("plate", "cup", "food tray", "takeout")
    ):
        return "paper_food_service_item"
    if (
        "single_use" in condition_flags
        or any(term in context_text for term in ("single use", "single-use", "wrapper"))
        or (
            any(
                term in f"{item_text} {observation_values}"
                for term in ("product container", "personal care", "cosmetic")
            )
            and "reusable" not in condition_flags
        )
    ):
        return "single_use_packaging"

    if reason == "allowed_paper_stationery":
        return "paper_stationery"
    if reason == "allowed_textile_soft_goods":
        return "textile_soft_goods"
    if reason == "allowed_reusable_household":
        return "durable_reusable_object"
    if reason == "allowed_simple_household_objects":
        if _contains_any_phrase(item_text, ("toy", "rubik", "duck", "container", "bottle")):
            return "durable_reusable_object"
    if reason == "allowed_durable_reusable":
        return "durable_reusable_object"
    if _contains_any_phrase(item_text, ("container", "bin", "basket", "storage", "bottle", "mug", "cup", "bowl", "plate", "lunch box")):
        return "durable_reusable_object"
    if _contains_any_phrase(material_text, ("paper", "cardboard")):
        return "paper_stationery"
    if _contains_any_phrase(material_text, ("textile", "fabric", "cloth")):
        return "textile_soft_goods"
    if "plastic" in material_text:
        return "simple_plastic_object"
    if _contains_any_phrase(material_text, ("metal", "glass", "ceramic")):
        return "simple_metal_glass_ceramic_object"
    if "wood" in material_text:
        return "simple_wood_object"
    return "durable_reusable_object"


def _deterministic_low_risk_guidance(
    classification: dict[str, Any],
    *,
    low_risk_evaluation: dict[str, Any],
    failure_reason: str | None,
) -> dict[str, Any]:
    formatted_item = _format_item_name(
        _first_non_empty_string(classification.get("item")) or "This item"
    )
    item_text = _normalized_phrase(classification.get("item"))
    material_text = _normalized_phrase(
        _first_non_empty_string(
            _normalized_open_value(classification, "material"),
            _normalized_open_value(classification, "material_category"),
            classification.get("recognized_material_category"),
            classification.get("category"),
        )
    )
    group = _deterministic_low_risk_group(classification, low_risk_evaluation)
    disposal_action: str | None = None
    summary: str
    steps: list[str]

    observation_values = " ".join(
        _normalized_phrase(observation.get("value"))
        for observation in _visual_observations(classification)
        if isinstance(observation, dict)
    )
    normalized_condition_flags = {
        _normalized_phrase(value).replace(" ", "_")
        for value in _normalized_open_details(classification).get("condition_flags") or []
        if _normalized_phrase(value)
    }
    reusable_confirmed = bool(
        normalized_condition_flags & {"intact", "reusable", "appears_clean"}
    ) or "appears reusable" in observation_values

    if group == "organic_material":
        appears_edible = any(
            term in observation_values for term in ("appears edible", "edible", "loose produce")
        ) and not any(term in item_text for term in ("scrap", "peel", "spoiled"))
        if appears_edible:
            disposal_action = "donate/reuse"
            summary = (
                f"Use, eat, or share the {formatted_item.lower()} while it is still edible; compost it if it becomes food scraps."
            )
            steps = [
                f"Use the {formatted_item.lower()} for food, or share it while it is still good to eat.",
                "If it is no longer edible, remove non-organic packaging and compost the food scraps where accepted.",
                "Use household trash only when food-scrap or compost options are unavailable.",
            ]
        else:
            disposal_action = "compost"
            summary = (
                f"Compost or mulch the {formatted_item.lower()} where that organic route is available."
            )
            steps = [
                "Remove plastic ties, labels, or other non-organic pieces.",
                f"Compost the {formatted_item.lower()}, use it as mulch when appropriate, or place it in yard-waste collection.",
                "Use household trash only if no organics or yard-waste route is available.",
            ]
    elif group == "single_use_packaging":
        disposal_action = "trash"
        summary = (
            f"Put the {formatted_item.lower()} in household trash unless an eligibility marking and your local program confirm another route."
        )
        steps = [
            "Empty any remaining contents without dismantling the package.",
            f"Place the {formatted_item.lower()} in household trash.",
            "Use recycling or film drop-off only when this exact construction is eligible and locally accepted.",
        ]
    elif group == "paper_food_service_item":
        disposal_action = "trash"
        summary = (
            f"Put the {formatted_item.lower()} in household trash because its coating and local paper acceptance are not confirmed."
        )
        steps = [
            f"Place the {formatted_item.lower()} in household trash even if it appears clean.",
            "Do not treat cleanliness alone as proof that coated or mixed paper is recyclable.",
            "Use paper recycling only if the construction and local program acceptance are confirmed.",
        ]
    elif group == "paper_stationery":
        disposal_action = "check local guidance"
        if "pencil" in item_text:
            summary = (
                f"Try to use or donate the {formatted_item.lower()} if it is still usable; "
                "otherwise follow local trash guidance for small used pencil pieces."
            )
            steps = [
                f"Use the {formatted_item.lower()} until it is finished, or donate unused pencils if they are still usable.",
                "Do not assume pencils belong in curbside recycling because they often contain mixed materials.",
                "If it is too small, broken, or not reusable, follow local trash guidance.",
            ]
        else:
            summary = (
                f"If the {formatted_item.lower()} is clean and dry, check whether your local program accepts this type of paper."
            )
            steps = [
                f"Reuse or donate the {formatted_item.lower()} if someone can still use it.",
                "If it is clean and dry, check local paper recycling rules before placing it in recycling.",
                "Remove obvious non-paper attachments when possible, or follow local trash guidance if it is not accepted.",
            ]
    elif group == "textile_soft_goods":
        disposal_action = "donate/reuse"
        summary = (
            f"Reuse, repair, or donate the {formatted_item.lower()} if it is still usable; otherwise check local textile options before throwing it away."
        )
        steps = [
            f"Donate, reuse, or repair the {formatted_item.lower()} if it is still clean and functional.",
            "Check local textile recycling, donation, or reuse drop-off options before disposal.",
            "If no local textile option is available, follow local trash guidance.",
        ]
    elif group == "durable_reusable_object":
        if reusable_confirmed:
            disposal_action = "donate/reuse"
            summary = (
                f"Keep using or donate the {formatted_item.lower()} because it appears intact and reusable."
            )
            steps = [
                f"Keep using the {formatted_item.lower()} if it still works for its intended purpose.",
                "Clean it if needed, then donate or share it while it remains usable.",
                "Use household trash only if it is no longer functional and no realistic material recovery option exists.",
            ]
        else:
            disposal_action = "check local guidance"
            summary = (
                f"Reuse the {formatted_item.lower()} if it is intact; if it is not reusable, use household trash unless a local program accepts its construction."
            )
            steps = [
                f"Check whether the {formatted_item.lower()} is intact, clean, and still functional before discarding it.",
                "Reuse or donate it only if another person can realistically use it as-is.",
                "If it is not reusable, use household trash unless a local program confirms another route.",
            ]
    elif group == "simple_plastic_object":
        disposal_action = (
            "donate/reuse"
            if _contains_any_phrase(item_text, ("toy", "container", "basket", "bin"))
            else "check local guidance"
        )
        if "container" in item_text:
            summary = (
                f"Reuse the {formatted_item.lower()} if it is clean and functional; otherwise check local rules before recycling or throwing it away."
            )
            steps = [
                "Reuse it for storage if it is clean and safe to keep.",
                "Check local recycling rules or drop-off options for this type of plastic container.",
                "If your local program does not accept it, follow local trash guidance.",
            ]
        else:
            summary = (
                f"If the {formatted_item.lower()} is still usable, reuse or donate it; otherwise check local rules for this type of plastic before disposal."
            )
            steps = [
                f"Keep using the {formatted_item.lower()} or donate it if it is still functional.",
                "Do not assume mixed or rigid plastic items are accepted in curbside recycling.",
                "If local reuse, recycling, or drop-off options are not available, follow local trash guidance.",
            ]
    elif group == "simple_metal_glass_ceramic_object":
        disposal_action = "donate/reuse" if reusable_confirmed else "check local guidance"
        summary = (
            f"Reuse or donate the {formatted_item.lower()} if it is visibly intact and usable; otherwise use trash or a confirmed local material route."
        )
        steps = [
            f"Keep using the {formatted_item.lower()} or donate it only if it is functional and unbroken.",
            f"Use recycling or drop-off for {material_text or 'this material'} only when the construction and local acceptance are confirmed.",
            "If it is not reusable and no confirmed material route exists, place it in household trash.",
        ]
    elif group == "simple_wood_object":
        disposal_action = "donate/reuse"
        summary = (
            f"Reuse, repair, or donate the {formatted_item.lower()} if it is still usable; otherwise check local wood disposal options before throwing it away."
        )
        steps = [
            f"Keep using the {formatted_item.lower()} or donate it if it is still functional.",
            "Do not assume small wooden household items belong in curbside recycling.",
            "If local reuse or drop-off options are not available, follow local trash guidance.",
        ]
    else:
        disposal_action = "donate/reuse"
        if "container" in item_text:
            summary = (
                f"Reuse the {formatted_item.lower()} if it is clean and functional; otherwise check local rules before recycling or throwing it away."
            )
            steps = [
                "Reuse it for storage if it is clean and safe to keep.",
                "Check local recycling rules or drop-off options for this type of plastic container.",
                "If your local program does not accept it, follow local trash guidance.",
            ]
        elif _contains_any_phrase(item_text, ("rubik", "toy", "duck")):
            summary = (
                f"Reuse or donate the {formatted_item.lower()} if it still works; if it is broken, check local options before throwing it away."
            )
            steps = [
                f"Keep using the {formatted_item.lower()}, repair it, or donate it if it is clean and functional.",
                "Do not assume mixed plastic toys are accepted in curbside recycling.",
                "If no reuse, donation, or local drop-off option is available, follow local trash guidance.",
            ]
        else:
            summary = (
                f"Reuse the {formatted_item.lower()} if it is still usable; otherwise check local recycling or drop-off options before disposal."
            )
            steps = [
                f"Keep using the {formatted_item.lower()}, repair it, or donate it if it is still functional.",
                "Check local recycling or drop-off rules that apply to this item or material.",
                "If no reuse or local recovery option is available, follow local trash guidance.",
            ]

    guidance = {
        "disposal_action": disposal_action,
        "material_code": None,
        "impact_level": "Low Confidence Guidance",
        "summary": summary,
        "steps": steps,
        "warnings": [_COMMON_LOW_RISK_WARNING],
        "guidance_source": "llm_general_fallback",
        "guidance_metadata": {
            "llm_mode": "general_safe_fallback",
            "confidence": "medium",
            "sources_used": [],
            "llm_fallback_reason": failure_reason,
            "deterministic_fallback_used": True,
            "low_risk_reason": low_risk_evaluation.get("reason"),
            "matched_terms": list(low_risk_evaluation.get("matched_terms") or []),
            "fallback_group": group,
            "claims_used": [],
            "source_excerpts": [],
            "source_names": [],
            "source_urls": [],
            "limitations": [],
            "why_this_action": "This is a compact low-confidence fallback because no trusted chunks were retrieved.",
            "retrieved_chunk_ids": [],
        },
    }
    return guidance


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


RESPONSE_CANDIDATE_LIMIT = 5


def _candidate_label(value: Any) -> str | None:
    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        for key in ("label", "name", "item_label", "raw_item_label"):
            label = value.get(key)
            if isinstance(label, str):
                return label
        return None

    if isinstance(value, (list, tuple)) and value:
        return _candidate_label(value[0])

    return None


def _candidate_score(value: Any) -> float | None:
    score: Any = None

    if isinstance(value, dict):
        for key in ("score", "confidence", "similarity"):
            if value.get(key) is not None:
                score = value.get(key)
                break
    elif isinstance(value, (list, tuple)) and len(value) > 1:
        score = value[1]

    if score is None:
        return None

    try:
        return round(float(score), 4)
    except (TypeError, ValueError):
        return None


def _is_usable_candidate_label(label: str) -> bool:
    normalized_label = label.strip().casefold()
    return normalized_label not in {
        "",
        "unknown",
        "other",
        "unidentified",
        "unidentified item",
        "unknown item",
    }


def _supported_candidate_label(value: Any) -> str | None:
    label = _candidate_label(value)
    if not isinstance(label, str) or not _is_usable_candidate_label(label):
        return None

    return resolve_material_label(label)


def _append_response_candidate(
    candidates: list[dict[str, Any]],
    seen_labels: set[str],
    value: Any,
) -> None:
    canonical_label = _supported_candidate_label(value)
    if canonical_label is None:
        return

    formatted_label = _format_item_name(canonical_label)
    dedupe_key = canonical_label.casefold()
    score = _candidate_score(value)

    for candidate in candidates:
        if str(candidate.get("selected_item") or candidate["label"]).casefold() == dedupe_key:
            if score is not None and "score" not in candidate:
                candidate["score"] = score
            return

    if dedupe_key in seen_labels:
        return

    seen_labels.add(dedupe_key)
    candidate: dict[str, Any] = {
        "label": formatted_label,
        "selected_item": canonical_label,
        "guidance_supported": True,
    }
    if score is not None:
        candidate["score"] = score
    candidates.append(candidate)


def _open_recognition_details(classification: dict[str, Any]) -> dict[str, Any]:
    recognition_details = classification.get("recognition_details")
    if not isinstance(recognition_details, dict):
        return {}

    return recognition_details


def _normalized_open_candidate_sources(
    classification: dict[str, Any],
) -> list[Any]:
    recognition_details = _open_recognition_details(classification)
    normalized_details = recognition_details.get("normalized")
    if isinstance(normalized_details, dict):
        return [normalized_details.get("item_label")]

    return []


def _raw_open_candidate_sources(classification: dict[str, Any]) -> list[Any]:
    recognition_details = _open_recognition_details(classification)
    sources: list[Any] = []

    recognition_candidates = recognition_details.get("candidates")
    if isinstance(recognition_candidates, list):
        sources.extend(recognition_candidates)

    sources.append(recognition_details.get("raw_item_label"))
    return sources


def _matched_supported_label(classification: dict[str, Any]) -> Any:
    recognition_details = _open_recognition_details(classification)
    normalized_details = recognition_details.get("normalized")
    if not isinstance(normalized_details, dict):
        return None

    return normalized_details.get("matched_supported_label")


def _classification_candidate_sources(classification: dict[str, Any]) -> list[Any]:
    raw_classification_candidates = classification.get("candidates")
    if isinstance(raw_classification_candidates, list):
        return raw_classification_candidates

    return []


def _build_response_candidates(classification: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_labels: set[str] = set()

    source_groups = [
        [classification.get("trusted_guidance_label")],
        [_matched_supported_label(classification)],
        _normalized_open_candidate_sources(classification),
        _classification_candidate_sources(classification),
        _raw_open_candidate_sources(classification),
        [classification.get("item")],
    ]

    for sources in source_groups:
        for source in sources:
            _append_response_candidate(candidates, seen_labels, source)
            if len(candidates) == RESPONSE_CANDIDATE_LIMIT:
                return candidates

    return candidates


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
        action
        for action in supported_actions
        if action.casefold() != CHECK_LOCAL_GUIDANCE_ACTION.casefold()
    ]

    if len(actionable) != 1:
        return None

    normalized_action = actionable[0].strip().lower().replace("drop off", "drop-off")
    return normalized_action


def _sentences_from_text(value: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", value.strip())
        if sentence.strip()
    ]


def _json_item_phrase(recognized_item: str | None) -> str:
    item = _first_non_empty_string(recognized_item)
    return item.casefold() if item else "item"


def _build_json_summary(primary_chunk: dict[str, Any], disposal_action: str | None, recognized_item: str | None) -> str:
    item_phrase = _json_item_phrase(recognized_item)
    if disposal_action == "recycle":
        summary = f"Recycle the {item_phrase} if the retrieved source supports it."
    elif disposal_action == "drop-off":
        summary = f"Use drop-off guidance for the {item_phrase}."
    elif disposal_action == "compost":
        summary = f"Compost the {item_phrase} only if accepted locally."
    elif disposal_action == "trash":
        summary = f"Trash the {item_phrase} only if the source allows it."
    elif disposal_action == "donate/reuse":
        summary = f"Reuse or donate the {item_phrase} if still usable."
    else:
        summary = f"Follow retrieved guidance for the {item_phrase}."

    if primary_chunk.get("requires_location_check") is True:
        return f"{summary.rstrip('.')} Check local acceptance first."
    return summary


def _build_json_steps(
    primary_chunk: dict[str, Any],
    disposal_action: str | None,
    recognized_item: str | None,
) -> list[str]:
    item_phrase = _json_item_phrase(recognized_item)
    chunk_text = " ".join(
        filter(
            None,
            [
                _first_non_empty_string(primary_chunk.get("content")),
                _first_non_empty_string(primary_chunk.get("source_claim")),
                _first_non_empty_string(primary_chunk.get("source_excerpt")),
                " ".join(str(value).strip() for value in (primary_chunk.get("warnings") or []) if str(value).strip()),
                " ".join(str(value).strip() for value in (primary_chunk.get("limitations") or []) if str(value).strip()),
            ],
        )
    ).casefold()

    steps: list[str] = []
    if "food scraps" in chunk_text or "greasy" in chunk_text or "residue" in chunk_text:
        steps.append("Remove food scraps before recycling.")
    elif "tape" in chunk_text and "terminal" in chunk_text:
        steps.append("Tape exposed terminals before transport.")
    elif "remove hardcover" in chunk_text or "hardcover cover" in chunk_text:
        steps.append("Remove hardcover covers before recycling.")
    elif "flatten" in chunk_text:
        steps.append(f"Flatten the {item_phrase} before recycling.")
    elif "clean and dry" in chunk_text:
        steps.append(f"Keep the {item_phrase} clean and dry.")
    elif disposal_action == "drop-off":
        steps.append(f"Keep the {item_phrase} together for drop-off.")

    if primary_chunk.get("requires_location_check") is True:
        steps.append("Check local program acceptance before relying on it.")

    if disposal_action == "recycle":
        steps.append("Recycle it only through the supported route.")
    elif disposal_action == "drop-off":
        steps.append(f"Use drop-off for the {item_phrase}.")
    elif disposal_action == "compost":
        steps.append("Compost it only if accepted locally.")
    elif disposal_action == "trash":
        steps.append("Use trash only if the retrieved guidance allows it.")
    elif disposal_action == "donate/reuse":
        steps.append(f"Donate the {item_phrase} if still usable.")
    else:
        steps.append("Follow the limits shown in More Details.")

    limitations = primary_chunk.get("limitations") or []
    if isinstance(limitations, list) and limitations:
        first_limitation = str(limitations[0]).strip()
        if first_limitation and len(steps) < 3:
            steps.append(first_limitation.rstrip(".") + ".")

    if len(steps) < 2:
        steps.append("Review the retrieved limits in More Details.")
    return steps[:3]


def _build_json_guidance_metadata(
    retrieval_results: list[dict[str, Any]],
) -> dict[str, Any]:
    retrieved_chunk_ids: list[str] = []
    source_names: list[str] = []
    source_urls: list[str] = []
    source_excerpts: list[str] = []
    claims_used: list[str] = []
    matched_fields: dict[str, list[str]] = {}
    retrieval_scores: dict[str, float] = {}
    limitations: list[str] = []
    requires_location_check = False
    applicability_by_chunk: dict[str, str] = {}
    applicability_reason_codes: dict[str, list[str]] = {}
    source_conditions: dict[str, dict[str, list[str]]] = {}
    trusted_local_sources: list[dict[str, Any]] = []

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
        source_excerpt = _first_non_empty_string(chunk.get("source_excerpt"))
        if source_excerpt and source_excerpt not in source_excerpts:
            source_excerpts.append(source_excerpt)
        source_claim = _first_non_empty_string(chunk.get("source_claim"))
        if source_claim and source_claim not in claims_used:
            claims_used.append(source_claim)

        matched_fields[chunk_id] = list(result.get("matched_fields") or [])
        retrieval_scores[chunk_id] = float(result.get("score") or 0.0)
        applicability_by_chunk[chunk_id] = str(
            result.get("applicability") or "applicable"
        )
        applicability_reason_codes[chunk_id] = list(
            result.get("applicability_reason_codes") or []
        )
        if isinstance(result.get("source_conditions"), dict):
            source_conditions[chunk_id] = result["source_conditions"]
        source_metadata = chunk.get("source_metadata")
        if isinstance(source_metadata, dict):
            safe_source_metadata = {
                key: source_metadata.get(key)
                for key in (
                    "title",
                    "organization",
                    "url",
                    "trusted",
                    "local",
                    "status",
                )
            }
            if safe_source_metadata not in trusted_local_sources:
                trusted_local_sources.append(safe_source_metadata)
        for limitation in list(chunk.get("limitations") or []):
            normalized_limitation = str(limitation).strip()
            if normalized_limitation and normalized_limitation not in limitations:
                limitations.append(normalized_limitation)
        if result.get("requires_location_check") is True:
            requires_location_check = True

    metadata = {
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "source_names": source_names,
        "source_urls": source_urls,
        "source_excerpts": source_excerpts,
        "claims_used": claims_used,
        "matched_fields": matched_fields,
        "retrieval_scores": retrieval_scores,
        "applicability_by_chunk": applicability_by_chunk,
        "applicability_reason_codes": applicability_reason_codes,
        "source_conditions": source_conditions,
        "applicable_chunk_ids": [
            chunk_id
            for chunk_id, status in applicability_by_chunk.items()
            if status == "applicable"
        ],
        "conditional_chunk_ids": [
            chunk_id
            for chunk_id, status in applicability_by_chunk.items()
            if status == "conditional"
        ],
        "not_applicable_chunk_ids": [
            chunk_id
            for chunk_id, status in applicability_by_chunk.items()
            if status == "not_applicable"
        ],
        "requires_location_check": requires_location_check,
        "limitations": limitations,
        "why_this_action": (
            "The selected action matches the strongest retrieved source evidence."
            if retrieved_chunk_ids
            else "No source evidence was retrieved."
        ),
    }
    if trusted_local_sources:
        metadata["trusted_local_sources"] = trusted_local_sources

    return metadata


def _retrieval_applicability(result: dict[str, Any]) -> str:
    status = str(result.get("applicability") or "applicable")
    return status if status in {"applicable", "conditional", "not_applicable"} else "conditional"


def _build_retrieval_applicability_metadata(
    retrieval_results: list[dict[str, Any]],
) -> dict[str, Any]:
    applicability_by_chunk: dict[str, str] = {}
    applicability_reason_codes: dict[str, list[str]] = {}
    for result in retrieval_results:
        chunk = result.get("chunk")
        chunk = chunk if isinstance(chunk, dict) else {}
        chunk_id = _first_non_empty_string(result.get("chunk_id"), chunk.get("id"))
        if chunk_id is None:
            continue
        applicability_by_chunk[chunk_id] = _retrieval_applicability(result)
        applicability_reason_codes[chunk_id] = list(
            result.get("applicability_reason_codes") or []
        )
    return {
        "applicability_by_chunk": applicability_by_chunk,
        "applicability_reason_codes": applicability_reason_codes,
        "applicable_chunk_ids": [
            chunk_id
            for chunk_id, status in applicability_by_chunk.items()
            if status == "applicable"
        ],
        "conditional_chunk_ids": [
            chunk_id
            for chunk_id, status in applicability_by_chunk.items()
            if status == "conditional"
        ],
        "not_applicable_chunk_ids": [
            chunk_id
            for chunk_id, status in applicability_by_chunk.items()
            if status == "not_applicable"
        ],
    }


def _attach_retrieval_applicability(
    guidance: dict[str, Any],
    retrieval_results: list[dict[str, Any]],
) -> dict[str, Any]:
    if not retrieval_results:
        return guidance
    guidance["guidance_metadata"] = _merge_guidance_metadata(
        _build_retrieval_applicability_metadata(retrieval_results),
        guidance.get("guidance_metadata"),
    )
    return guidance


def _usable_retrieval_results(
    retrieval_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        result
        for result in retrieval_results
        if _retrieval_applicability(result) != "not_applicable"
    ]


def _applicable_retrieval_results(
    retrieval_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        result
        for result in retrieval_results
        if _retrieval_applicability(result) == "applicable"
    ]


def _guidance_from_json_retrieval(
    retrieval_results: list[dict[str, Any]],
    *,
    extra_metadata: dict[str, Any] | None = None,
    recognized_item: str | None = None,
    material: str | None = None,
    broad_category: str | None = None,
    condition_flags: list[str] | None = None,
    special_flags: list[str] | None = None,
    visual_evidence: str | None = None,
    visual_observations: list[dict[str, Any]] | None = None,
    candidates: list[str] | None = None,
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

    steps = _build_json_steps(primary_chunk, disposal_action, recognized_item)
    candidate_payload = {
        "disposal_action": disposal_action,
        "material_code": None,
        "impact_level": (
            "Check Local Guidance"
            if primary_chunk.get("requires_location_check") is True
            else "Source-Grounded Guidance"
        ),
        "summary": _build_json_summary(primary_chunk, disposal_action, recognized_item),
        "steps": steps,
        "warnings": warnings,
        "confidence": "medium",
        "sources_used": [
            result.get("chunk_id")
            for result in retrieval_results[:3]
            if isinstance(result.get("chunk_id"), str) and result.get("chunk_id")
        ],
    }
    validated_payload, validation_errors = guidance_llm_service.validate_mobile_guidance_output(
        candidate_payload,
        mode="source_grounded",
        recognized_item=recognized_item,
        normalized_item_label=recognized_item,
        material=material,
        broad_category=broad_category,
        condition_flags=list(condition_flags or []),
        special_flags=list(special_flags or []),
        visual_evidence=visual_evidence,
        visual_observations=list(visual_observations or []),
        candidates=list(candidates or []),
        allowed_actions={
            action
            for result in retrieval_results[:3]
            for action in (
                str(value).strip().lower().replace("drop off", "drop-off")
                for value in (result.get("chunk", {}).get("disposal_actions_supported", []) or [])
                if str(value).strip()
            )
        },
        chunks=[result.get("chunk", {}) for result in retrieval_results[:3] if isinstance(result.get("chunk"), dict)],
    )
    if validated_payload is None:
        logger.info(
            "Direct JSON guidance contract fallback used. item=%s validation_errors=%s",
            recognized_item,
            validation_errors,
        )
        validated_payload = {
            **candidate_payload,
            "steps": steps,
        }

    guidance = {
        "disposal_action": validated_payload["disposal_action"],
        "material_code": validated_payload["material_code"],
        "impact_level": validated_payload["impact_level"],
        "summary": validated_payload["summary"],
        "steps": validated_payload["steps"],
        "guidance_source": "json_rag_direct_generated",
        "guidance_metadata": _merge_guidance_metadata(
            _build_json_guidance_metadata(retrieval_results),
            guidance_llm_service._contract_metadata_values(),
            {
                "final_generation_path": "direct_rag_fallback",
                "confidence": "medium",
            },
            extra_metadata,
        ),
    }
    if validated_payload["warnings"]:
        guidance["warnings"] = validated_payload["warnings"]

    return guidance


def _build_guidance_confidence(
    guidance: dict[str, Any],
    classification: dict[str, Any],
    clarification_decision: dict[str, Any],
) -> dict[str, Any]:
    metadata = guidance.get("guidance_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    applicable_ids = list(metadata.get("applicable_chunk_ids") or [])
    applicable_local_rule_ids = list(
        metadata.get("applicable_local_rule_ids") or []
    )
    conditional_ids = list(metadata.get("conditional_chunk_ids") or [])
    not_applicable_ids = list(metadata.get("not_applicable_chunk_ids") or [])
    source = str(guidance.get("guidance_source") or "unknown")
    action = _normalized_phrase(guidance.get("disposal_action"))
    reason_codes: list[str] = []

    if clarification_decision.get("required") is True:
        level = "unknown"
        score = 0.0
        reason_codes.append("recognition_clarification_required")
    elif not action:
        level = "low"
        score = 0.25
        reason_codes.append("no_disposal_action_selected")
    elif source == "local_rules" and applicable_local_rule_ids:
        local_applicability = str(
            metadata.get("local_rule_applicability") or ""
        ).casefold()
        if local_applicability == "applicable":
            level = "high"
            score = 0.94
            reason_codes.append("approved_local_rule")
        elif local_applicability == "conditional":
            level = "medium"
            score = 0.7
            reason_codes.append("local_rule_condition_unresolved")
        else:
            level = "high"
            score = 0.9
            reason_codes.append("explicit_local_exclusion")
    elif source == "json_rag_llm_generated" and applicable_ids:
        if metadata.get("requires_location_check") is True:
            level = "medium"
            score = 0.72
            reason_codes.append("local_acceptance_still_varies")
        elif metadata.get("deterministic_fallback_used") is True:
            level = "medium"
            score = 0.68
            reason_codes.append("deterministic_source_fallback")
        else:
            level = "high"
            score = 0.9
            reason_codes.append("applicable_source_evidence")
    elif source == "json_rag_llm_generated":
        level = "medium" if action in {"trash", "check local guidance"} else "low"
        score = 0.6 if level == "medium" else 0.4
        reason_codes.append("conditional_source_practical_fallback")
    elif source == "json_rag_direct_generated":
        level = "medium" if applicable_ids else "low"
        score = 0.66 if applicable_ids else 0.42
        reason_codes.append(
            "direct_rag_with_applicable_evidence"
            if applicable_ids
            else "direct_rag_without_applicable_evidence"
        )
    elif source in {"general_fallback", "safe_fallback"}:
        level = "low"
        score = 0.35
        reason_codes.append("general_fallback")
    elif source == "llm_general_fallback":
        recognition = classification.get("recognition_confidence")
        recognition_level = (
            str(recognition.get("level") or "").casefold()
            if isinstance(recognition, dict)
            else ""
        )
        level = "medium" if recognition_level in {"high", "medium"} else "low"
        score = 0.64 if level == "medium" else 0.45
        reason_codes.append("practical_low_risk_fallback")
    elif source == "legacy_rules_fallback":
        level = "medium"
        score = 0.62
        reason_codes.append("static_category_guidance")
    else:
        level = "low"
        score = 0.35
        reason_codes.append("limited_guidance_evidence")

    if conditional_ids:
        reason_codes.append("conditional_retrieval_context")
    if metadata.get("requires_location_check") is True:
        reason_codes.append("local_variation")
    if guidance.get("cache_hit") is True:
        reason_codes.append("condition_matched_cache_hit")

    applicability = {
        "applicable_chunk_ids": applicable_ids,
        "conditional_chunk_ids": conditional_ids,
        "not_applicable_chunk_ids": not_applicable_ids,
    }
    if applicable_local_rule_ids:
        applicability["applicable_local_rule_ids"] = applicable_local_rule_ids

    return {
        "level": level,
        "score": round(score, 3),
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "source": source,
        "applicability": applicability,
    }


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
        "guidance_metadata": {"final_generation_path": "legacy_safe_fallback"},
    }


def _build_retrieval_inputs(classification: dict[str, Any]) -> dict[str, Any]:
    if _is_open_recognition_classification(classification):
        recognition_details = classification.get("recognition_details")
        visual_observations = _visual_observations(classification)
        recognition_candidates = []
        if isinstance(recognition_details, dict):
            recognition_candidates = [
                candidate.get("label")
                for candidate in recognition_details.get("candidates", [])
                if isinstance(candidate, dict)
            ]

        item_candidates = _candidate_values(
            classification.get("item"),
            _normalized_open_value(classification, "item_label"),
            recognition_details.get("raw_item_label") if isinstance(recognition_details, dict) else None,
            recognition_candidates,
        )
        material_candidates = _candidate_values(
            _normalized_open_value(classification, "material_category"),
            classification.get("recognized_material_category"),
            _normalized_open_value(classification, "material"),
            recognition_details.get("likely_material") if isinstance(recognition_details, dict) else None,
        )
        category_candidates = _candidate_values(
            _normalized_open_value(classification, "disposal_category"),
            classification.get("category"),
            _normalized_open_value(classification, "broad_category"),
            classification.get("recognized_broad_category"),
            recognition_details.get("broad_category") if isinstance(recognition_details, dict) else None,
            classification.get("trusted_guidance_label"),
            _normalized_open_details(classification).get("matched_supported_label"),
        )
        condition_flags = _candidate_values(
            _normalized_open_details(classification).get("condition_flags", []),
            _normalized_open_details(classification).get("special_handling_flags", []),
            _normalized_open_details(classification).get("special_flags", []),
            _visual_observation_flags(visual_observations),
        )
        special_flags = _candidate_values(
            _normalized_open_details(classification).get("special_handling_flags", []),
            _normalized_open_details(classification).get("special_flags", []),
        )
        condition_flags.extend(_derived_guidance_context_flags(classification))
        condition_flags = _candidate_values(condition_flags)
        visual_evidence = _combined_visual_evidence(classification)

        return {
            "item_label": item_candidates[0] if item_candidates else None,
            "material": material_candidates[0] if material_candidates else None,
            "category": category_candidates[0] if category_candidates else None,
            "item_candidates": item_candidates,
            "material_candidates": material_candidates,
            "category_candidates": category_candidates,
            "condition_flags": condition_flags,
            "special_flags": special_flags,
            "visual_evidence": visual_evidence,
            "visual_observations": visual_observations,
            "primary_material": _first_non_empty_string(
                _normalized_open_value(classification, "primary_material"),
                material_candidates[0] if material_candidates else None,
            ),
            "material_confidence": _first_non_empty_string(
                _normalized_open_value(classification, "material_confidence")
            ),
            "specific_context_required": bool(visual_observations),
            "location": classification.get("location"),
        }

    item_candidates = _candidate_values(classification.get("item"))
    material_candidates = _candidate_values(classification.get("category"))
    category_candidates = _candidate_values(classification.get("category"))
    return {
        "item_label": item_candidates[0] if item_candidates else None,
        "material": material_candidates[0] if material_candidates else None,
        "category": category_candidates[0] if category_candidates else None,
        "item_candidates": item_candidates,
        "material_candidates": material_candidates,
        "category_candidates": category_candidates,
        "condition_flags": [],
        "special_flags": [],
        "visual_evidence": None,
        "visual_observations": [],
        "primary_material": material_candidates[0] if material_candidates else None,
        "material_confidence": None,
        "specific_context_required": False,
        "location": classification.get("location"),
    }


def _lookup_json_guidance(
    classification: dict[str, Any],
    *,
    retrieval_inputs: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if retrieval_inputs is None:
        retrieval_inputs = _build_retrieval_inputs(classification)
    try:
        return guidance_retrieval_service.retrieve_guidance_chunks(**retrieval_inputs) or []
    except Exception:
        logger.exception(
            "Guidance retrieval failed. lookup_item=%s lookup_material=%s lookup_category=%s",
            retrieval_inputs.get("item_label"),
            retrieval_inputs.get("material"),
            retrieval_inputs.get("category"),
        )
        return []


def _build_llm_context(classification: dict[str, Any]) -> dict[str, Any]:
    recognition_details = classification.get("recognition_details")
    candidate_labels: list[str] = []
    if isinstance(recognition_details, dict):
        candidate_labels = [
            label
            for label in (
                candidate.get("label")
                for candidate in recognition_details.get("candidates", [])
                if isinstance(candidate, dict)
            )
            if isinstance(label, str) and label.strip()
        ]

    normalized_details = _normalized_open_details(classification)
    visual_observations = _visual_observations(classification)
    return {
        "recognized_item": _first_non_empty_string(classification.get("item")),
        "normalized_item_label": _first_non_empty_string(
            normalized_details.get("item_label"),
            classification.get("trusted_guidance_label"),
            classification.get("item"),
        ),
        "material": _first_non_empty_string(
            normalized_details.get("material"),
            normalized_details.get("material_category"),
            classification.get("recognized_material_category"),
            classification.get("category"),
        ),
        "broad_category": _first_non_empty_string(
            normalized_details.get("disposal_category"),
            classification.get("category"),
            normalized_details.get("broad_category"),
            classification.get("recognized_broad_category"),
        ),
        "condition_flags": _open_condition_flags(classification),
        "special_flags": _candidate_values(
            _normalized_string_list(normalized_details.get("special_handling_flags")),
            _normalized_string_list(normalized_details.get("special_flags")),
            _visual_observation_flags(visual_observations),
        ),
        "visual_evidence": _combined_visual_evidence(classification),
        "visual_observations": visual_observations,
        "candidates": _candidate_values(
            candidate_labels,
            classification.get("trusted_guidance_label"),
            normalized_details.get("matched_supported_label"),
        ),
        "location": classification.get("location"),
    }


def _normalize_open_text_fields(classification: dict[str, Any]) -> list[str]:
    normalized_details = _normalized_open_details(classification)
    raw_values = [
        classification.get("item"),
        normalized_details.get("item_label"),
        normalized_details.get("material"),
        normalized_details.get("material_category"),
        normalized_details.get("disposal_category"),
        normalized_details.get("broad_category"),
        classification.get("recognized_material_category"),
        classification.get("recognized_broad_category"),
        *_visual_observation_text_values(_visual_observations(classification)),
    ]

    normalized_values: list[str] = []
    for value in raw_values:
        normalized_value = normalize_guidance_phrase(value)
        if normalized_value:
            normalized_values.append(normalized_value)
    return normalized_values


def _derived_guidance_context_flags(classification: dict[str, Any]) -> list[str]:
    normalized_text = " ".join(_normalize_open_text_fields(classification))
    derived_flags: list[str] = []

    if "battery" in normalized_text:
        derived_flags.extend(
            ["battery", "requires_dropoff", "hazardous", "dropoff_recommended"]
        )

    if (
        "electronics/e-waste" in normalized_text
        or "electronics e waste" in normalized_text
        or "electronics" in normalized_text
    ):
        derived_flags.extend(["electronics", "requires_dropoff"])

    if "paint" in normalized_text or "chemical" in normalized_text:
        derived_flags.extend(["hazardous", "requires_dropoff"])

    if any(
        keyword in normalized_text
        for keyword in (
            "aerosol",
            "motor oil",
            "fluorescent",
            "medicine",
            "medication",
            "sharps",
            "needle",
            "syringe",
        )
    ):
        derived_flags.extend(["hazardous", "special_handling"])

    return _candidate_values(derived_flags)


def _open_special_handling_flags(classification: dict[str, Any]) -> list[str]:
    return _normalized_string_list(
        _normalized_open_details(classification).get("special_handling_flags")
    )


def _open_condition_flags(classification: dict[str, Any]) -> list[str]:
    visual_observations = _visual_observations(classification)
    return _candidate_values(
        _normalized_open_details(classification).get("condition_flags", []),
        _normalized_open_details(classification).get("special_handling_flags", []),
        _normalized_open_details(classification).get("special_flags", []),
        _visual_observation_flags(visual_observations),
        _derived_guidance_context_flags(classification),
    )


def _find_matching_terms(normalized_text: str, terms: set[str]) -> list[str]:
    text_tokens = normalized_text.split()
    matched_terms: list[str] = []
    for term in sorted(terms):
        term_tokens = (_normalized_phrase(term) or "").split()
        if not term_tokens or len(term_tokens) > len(text_tokens):
            continue
        width = len(term_tokens)
        if any(
            text_tokens[index : index + width] == term_tokens
            for index in range(len(text_tokens) - width + 1)
        ):
            matched_terms.append(term)
    return matched_terms


def _build_low_risk_decision_context(classification: dict[str, Any]) -> dict[str, Any]:
    recognition_details = classification.get("recognition_details")
    normalized_details = _normalized_open_details(classification)
    visual_observations = _visual_observations(classification)
    values = _candidate_values(
        classification.get("item"),
        classification.get("category"),
        classification.get("recognized_material_category"),
        classification.get("recognized_broad_category"),
        normalized_details.get("item_label"),
        normalized_details.get("material"),
        normalized_details.get("material_category"),
        normalized_details.get("broad_category"),
        recognition_details.get("raw_item_label") if isinstance(recognition_details, dict) else None,
        recognition_details.get("broad_category") if isinstance(recognition_details, dict) else None,
        _visual_observation_text_values(visual_observations),
    )
    flags = _open_condition_flags(classification)
    normalized_values = [
        normalize_guidance_phrase(value)
        for value in values
        if normalize_guidance_phrase(value)
    ]
    normalized_flags = [
        flag.replace("_", " ")
        for flag in flags
        if isinstance(flag, str) and flag.strip()
    ]
    decision_text = " ".join(normalized_values + normalized_flags)
    return {
        "decision_text": decision_text,
        "values": normalized_values,
        "flags": flags,
    }


def _evaluate_low_risk_open_item(classification: dict[str, Any]) -> dict[str, Any]:
    item = _first_non_empty_string(classification.get("item")) or ""
    if not _is_open_recognition_classification(classification):
        result = {"eligible": False, "reason": "not_open_recognition", "matched_terms": []}
        logger.info(
            "Low-risk eligibility evaluated. item=%s eligible=%s reason=%s matched_terms=%s",
            item,
            result["eligible"],
            result["reason"],
            _format_log_list(result["matched_terms"]),
        )
        return result

    if classification.get("trusted_guidance_available") is not False:
        result = {"eligible": False, "reason": "trusted_guidance_supported_path", "matched_terms": []}
        logger.info(
            "Low-risk eligibility evaluated. item=%s eligible=%s reason=%s matched_terms=%s",
            item,
            result["eligible"],
            result["reason"],
            _format_log_list(result["matched_terms"]),
        )
        return result

    context = _build_low_risk_decision_context(classification)
    decision_text = context["decision_text"]
    flags = set(context["flags"])
    allow_matches: list[str] = []
    allow_reason: str | None = None
    for reason, terms in _LOW_RISK_ALLOW_GROUPS.items():
        matched_terms = _find_matching_terms(decision_text, terms)
        if matched_terms:
            allow_matches = matched_terms
            allow_reason = reason
            break

    high_risk_matches = _find_matching_terms(decision_text, _HIGH_RISK_KEYWORDS)
    if high_risk_matches:
        result = {
            "eligible": False,
            "reason": "blocked_high_risk",
            "matched_terms": high_risk_matches,
        }
    else:
        blocking_flags = sorted(flag for flag in flags if flag in _HIGH_RISK_FLAGS)
        if blocking_flags:
            result = {
                "eligible": False,
                "reason": "blocked_high_risk_flags",
                "matched_terms": blocking_flags,
            }
        elif "dropoff_recommended" in flags and not any(
            term in _LOW_RISK_DROP_OFF_ONLY_TERMS for term in allow_matches
        ):
            result = {
                "eligible": False,
                "reason": "blocked_special_handling_flag",
                "matched_terms": ["dropoff_recommended"],
            }
        else:
            caution_matches = _find_matching_terms(decision_text, _CAUTION_KEYWORDS)
            if caution_matches:
                result = {
                    "eligible": False,
                    "reason": "blocked_caution_specific_rules",
                    "matched_terms": caution_matches,
                }
            elif allow_reason is not None:
                result = {
                    "eligible": True,
                    "reason": allow_reason,
                    "matched_terms": allow_matches,
                }
            else:
                result = {
                    "eligible": False,
                    "reason": "default_unknown_safe_fallback",
                    "matched_terms": [],
                }

    logger.info(
        "Low-risk eligibility evaluated. item=%s eligible=%s reason=%s matched_terms=%s",
        item,
        result["eligible"],
        result["reason"],
        _format_log_list(result["matched_terms"]),
    )
    return result


def _legacy_rules_allowed(classification: dict[str, Any]) -> bool:
    if not _is_open_recognition_classification(classification):
        return True

    return classification.get("trusted_guidance_available") is True


def _resolve_guidance(
    classification: dict[str, Any],
    *,
    clarification_decision: dict[str, Any] | None = None,
    jurisdiction_id: str | None = None,
) -> dict[str, Any]:
    decision = clarification_decision or evaluate_clarification(classification)
    if decision.get("required") is True:
        tavily_local_guidance_service.log_tavily_skip(
            "tavily_disabled",
            "clarification_required",
        )
        guidance = _clarification_guidance(decision)
        _log_guidance_selected(
            guidance,
            reason="recognition_clarification_required",
            item=_first_non_empty_string(classification.get("item")),
            category=_first_non_empty_string(classification.get("category")),
            reason_codes=list(decision.get("reason_codes") or []),
        )
        return guidance

    local_result = local_guidance_matcher.match_local_guidance(
        classification,
        jurisdiction_id,
    )
    local_guidance = local_result.get("guidance")
    if isinstance(local_guidance, dict):
        tavily_local_guidance_service.log_tavily_skip(
            "manual_local_rule",
            "trusted_manual_rule",
        )
        local_guidance = _with_metadata(
            local_guidance,
            {
                "local_guidance_status": "manual_local_rule",
                "tavily_called": False,
                "tavily_skip_reason": "trusted_manual_rule",
            },
        )
        _log_guidance_selected(
            local_guidance,
            item=_first_non_empty_string(classification.get("item")),
            category=_first_non_empty_string(classification.get("category")),
            reason=f"local_rule_{local_result.get('status')}",
        )
        return local_guidance

    tavily_outcome = tavily_local_guidance_service.search_local_guidance(
        classification,
        clarification_required=decision.get("required") is True,
        manual_rule_applied=False,
    )
    tavily_retrieval_results = tavily_outcome.get("retrieval_results")
    tavily_retrieval_results = (
        tavily_retrieval_results
        if isinstance(tavily_retrieval_results, list)
        else []
    )
    retrieval_inputs = _build_retrieval_inputs(classification)
    _log_resolution_started(classification, retrieval_inputs)
    retrieval_started = perf_counter()
    retrieval_results = [
        *tavily_retrieval_results,
        *_lookup_json_guidance(
            classification,
            retrieval_inputs=retrieval_inputs,
        ),
    ]
    _log_guidance_timing(
        "retrieval",
        retrieval_started,
        result_count=len(retrieval_results),
        item=retrieval_inputs.get("item_label"),
        category=retrieval_inputs.get("category"),
    )
    _log_retrieval_complete(retrieval_results)
    llm_context = _build_llm_context(classification)
    source_results = _usable_retrieval_results(retrieval_results)
    applicable_results = _applicable_retrieval_results(source_results)
    has_dynamic_tavily_sources = any(
        isinstance(result.get("chunk"), dict)
        and result["chunk"].get("dynamic_source") == "tavily"
        for result in source_results
    )

    if source_results:
        cache_context_started = perf_counter()
        cache_context = (
            None
            if has_dynamic_tavily_sources
            else guidance_cache_service.build_source_grounded_cache_context(
                classification=classification,
                retrieval_inputs=retrieval_inputs,
                retrieval_results=source_results,
                llm_context=llm_context,
                jurisdiction_id=jurisdiction_id,
                local_rules_version=local_result.get("rules_version"),
            )
        )
        _log_guidance_timing(
            "cache_context",
            cache_context_started,
            retrieved_chunk_count=len(source_results),
            cache_key_present=bool(cache_context.get("cache_key")) if cache_context else False,
        )
        cache_lookup_started = perf_counter()
        cached_guidance = guidance_cache_service.get_cached_source_grounded_guidance(
            cache_context
        )
        _log_guidance_timing(
            "cache_lookup",
            cache_lookup_started,
            hit=isinstance(cached_guidance, dict),
        )
        if isinstance(cached_guidance, dict):
            _log_guidance_selected(
                cached_guidance,
                chunk_ids=cached_guidance.get("guidance_metadata", {}).get(
                    "retrieved_chunk_ids"
                ),
                requires_location_check=bool(
                    cached_guidance.get("guidance_metadata", {}).get(
                        "requires_location_check"
                    )
                ),
                reason="guidance_cache_hit",
            )
            return _attach_tavily_outcome(cached_guidance, tavily_outcome)

        llm_started = perf_counter()
        llm_result = guidance_llm_service.try_generate_source_grounded_guidance(
            **llm_context,
            retrieval_results=source_results,
        )
        _log_guidance_timing(
            "llm_source_grounded",
            llm_started,
            guidance_returned=isinstance(llm_result.get("guidance"), dict),
            failure_reason=llm_result.get("failure_reason"),
        )
        llm_guidance = llm_result.get("guidance")
        if isinstance(llm_guidance, dict):
            llm_metadata = llm_guidance.get("guidance_metadata")
            llm_metadata = llm_metadata if isinstance(llm_metadata, dict) else {}
            used_chunk_ids = {
                str(chunk_id)
                for chunk_id in (
                    llm_metadata.get("retrieved_chunk_ids")
                    or llm_metadata.get("sources_used")
                    or []
                )
                if chunk_id
            }
            metadata_results = (
                [
                    result
                    for result in source_results
                    if str(result.get("chunk_id") or "") in used_chunk_ids
                ]
                if used_chunk_ids
                else []
            ) or source_results
            llm_guidance["guidance_metadata"] = _merge_guidance_metadata(
                _build_json_guidance_metadata(metadata_results),
                llm_metadata,
                _build_retrieval_applicability_metadata(metadata_results),
            )
            _log_guidance_selected(
                llm_guidance,
                chunk_ids=llm_guidance["guidance_metadata"].get("retrieved_chunk_ids"),
                requires_location_check=bool(
                    llm_guidance["guidance_metadata"].get("requires_location_check")
                ),
            )
            cache_write_started = perf_counter()
            guidance_cache_service.write_source_grounded_guidance_if_cacheable(
                classification=classification,
                guidance=llm_guidance,
                cache_context=cache_context,
                retrieval_inputs=retrieval_inputs,
                retrieval_results=source_results,
                llm_context=llm_context,
            )
            _log_guidance_timing("cache_write", cache_write_started, attempted=True)
            return _attach_tavily_outcome(llm_guidance, tavily_outcome)

        llm_fallback_reason = _first_non_empty_string(llm_result.get("failure_reason"))
        if llm_fallback_reason in _LLM_SKIP_REASONS:
            logger.info("LLM guidance skipped. reason=%s", llm_fallback_reason)
        elif llm_fallback_reason:
            logger.info(
                "LLM guidance unavailable. reason=%s fallback=%s",
                llm_fallback_reason,
                "general_fallback",
            )
        guidance = _general_fallback_guidance(
            classification,
            reason=llm_fallback_reason or "source_grounded_llm_unavailable",
            extra_metadata=_build_retrieval_applicability_metadata(source_results),
        )
        _log_guidance_selected(
            guidance,
            item=_first_non_empty_string(classification.get("item")),
            category=_first_non_empty_string(classification.get("category")),
            reason="source_grounded_llm_unavailable",
        )
        return _attach_tavily_outcome(guidance, tavily_outcome)

    logger.info(
        "Source-grounded guidance unavailable. reason=%s conditional_chunks=%s not_applicable_chunks=%s",
        "no_usable_sources",
        len([result for result in source_results if _retrieval_applicability(result) == "conditional"]),
        len(retrieval_results) - len(source_results),
    )
    guidance = _general_fallback_guidance(
        classification,
        reason="no_usable_sources",
        extra_metadata=_build_retrieval_applicability_metadata(retrieval_results),
    )
    _log_guidance_selected(
        guidance,
        item=_first_non_empty_string(classification.get("item")),
        category=_first_non_empty_string(classification.get("category")),
        reason="no_usable_sources",
    )
    return _attach_tavily_outcome(guidance, tavily_outcome)


def _apply_final_consistency_guard(
    classification: dict[str, Any],
    guidance: dict[str, Any],
    clarification_decision: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    validation = guidance_consistency_service.validate_guidance_consistency(
        classification,
        guidance,
    )
    if validation.get("valid") is True:
        return guidance, clarification_decision

    contradiction_codes = list(validation.get("contradiction_codes") or [])
    logger.warning(
        "Guidance consistency contradiction prevented. item=%s action=%s source=%s cache_hit=%s contradictions=%s resolution=%s",
        classification.get("item"),
        guidance.get("disposal_action"),
        guidance.get("guidance_source"),
        guidance.get("cache_hit") is True,
        _format_log_list(contradiction_codes),
        validation.get("resolution"),
    )
    guard_metadata = _consistency_guard_metadata(validation, guidance)

    if (
        validation.get("resolution") == "clarification"
        or "trash_conflicts_with_special_handling_evidence" in contradiction_codes
    ):
        decision = _consistency_clarification_decision(validation)
        replacement = _clarification_guidance(decision)
        original_metadata = guidance.get("guidance_metadata")
        original_metadata = (
            original_metadata if isinstance(original_metadata, dict) else {}
        )
        replacement["guidance_metadata"] = _merge_guidance_metadata(
            replacement.get("guidance_metadata"),
            _local_web_metadata(original_metadata),
            guard_metadata,
        )
        return replacement, decision

    if any(
        code
        in {
            "reuse_conflicts_with_explicit_condition",
            "strong_action_without_applicable_evidence",
        }
        for code in contradiction_codes
    ):
        original_metadata = guidance.get("guidance_metadata")
        original_metadata = (
            original_metadata if isinstance(original_metadata, dict) else {}
        )
        replacement = _general_fallback_guidance(
            classification,
            reason="consistency_guard",
            extra_metadata=_merge_guidance_metadata(
                {
                    "applicability_by_chunk": original_metadata.get(
                        "applicability_by_chunk", {}
                    ),
                    "applicability_reason_codes": original_metadata.get(
                        "applicability_reason_codes", {}
                    ),
                    "applicable_chunk_ids": list(
                        original_metadata.get("applicable_chunk_ids") or []
                    ),
                    "conditional_chunk_ids": list(
                        original_metadata.get("conditional_chunk_ids") or []
                    ),
                    "not_applicable_chunk_ids": list(
                        original_metadata.get("not_applicable_chunk_ids") or []
                    ),
                },
                _local_web_metadata(original_metadata),
                guard_metadata,
            ),
        )
        return replacement, clarification_decision

    original_metadata = guidance.get("guidance_metadata")
    original_metadata = original_metadata if isinstance(original_metadata, dict) else {}
    guidance["guidance_metadata"] = _merge_guidance_metadata(
        original_metadata,
        guard_metadata,
        {"consistency_guard_non_blocking": True},
    )
    return guidance, clarification_decision


def build_prediction_response(
    classification: dict[str, Any],
    *,
    jurisdiction_id: str | None = None,
) -> dict[str, Any]:
    clarification_decision = evaluate_clarification(classification)
    guidance = _resolve_guidance(
        classification,
        clarification_decision=clarification_decision,
        jurisdiction_id=jurisdiction_id,
    )
    guidance, clarification_decision = _apply_final_consistency_guard(
        classification,
        guidance,
        clarification_decision,
    )

    guidance_metadata = guidance.get("guidance_metadata")
    if not isinstance(guidance_metadata, dict):
        guidance_metadata = {}
    if "final_generation_path" not in guidance_metadata:
        source = guidance.get("guidance_source")
        if source == "json_rag_direct_generated":
            final_path = "direct_rag_fallback"
        elif guidance_metadata.get("deterministic_fallback_used") is True:
            final_path = "deterministic_fallback"
        elif source == "local_rules":
            final_path = "local_rules"
        elif source in {"safe_fallback", "legacy_rules_fallback"}:
            final_path = "legacy_safe_fallback"
        else:
            final_path = "original_llm"
        guidance_metadata["final_generation_path"] = final_path
    guidance["guidance_metadata"] = guidance_metadata

    response = {
        "item": _format_item_name(str(classification.get("item") or "")),
        "category": classification.get("category", UNKNOWN_CATEGORY),
        "status": (
            "uncertain"
            if clarification_decision.get("required") is True
            else classification.get("status", "unknown")
        ),
        "candidates": _build_response_candidates(classification),
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

    if isinstance(guidance_metadata, dict) and guidance_metadata:
        response["guidance_metadata"] = guidance_metadata

    local_guidance = guidance.get("local_guidance")
    if isinstance(local_guidance, dict):
        response["jurisdiction_id"] = jurisdiction_id
        response["local_guidance"] = local_guidance

    response["guidance_confidence"] = _build_guidance_confidence(
        guidance,
        classification,
        clarification_decision,
    )

    if "cache_hit" in classification or "cache_hit" in guidance:
        response["cache_hit"] = bool(
            classification.get("cache_hit") or guidance.get("cache_hit")
        )
    if "recognition_source" in classification:
        response["recognition_source"] = classification["recognition_source"]
    if isinstance(classification.get("recognition_confidence"), dict):
        response["recognition_confidence"] = classification[
            "recognition_confidence"
        ]
    if clarification_decision.get("required") is True:
        response["clarification"] = {
            "required": True,
            "reason_codes": list(
                clarification_decision.get("reason_codes") or []
            ),
            "retake_recommended": bool(
                clarification_decision.get("retake_recommended")
            ),
            "retake_guidance": clarification_decision.get("retake_guidance"),
            "message": clarification_decision.get("message"),
        }

    logger.info(
        "Guidance resolution finished. source=%s item=%s disposal_action=%s steps_count=%s",
        response["guidance_source"],
        response["item"],
        response["disposal_action"],
        len(response["steps"]),
    )

    return response
