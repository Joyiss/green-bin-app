from __future__ import annotations

import logging
from typing import Any

try:
    from ..repositories import feedback_repository
except ImportError:
    from repositories import feedback_repository

logger = logging.getLogger(__name__)

_MAX_REASON_CODES = 24
_MAX_CHUNK_IDS = 24


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_string(value: Any, *, maximum: int = 200) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized[:maximum] if normalized else None


def _bounded_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 1:
        return None
    return number


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    values: list[str] = []
    for item in value:
        normalized = _optional_string(item, maximum=100)
        if normalized and normalized not in values:
            values.append(normalized)
        if len(values) == limit:
            break
    return values


def _flatten_reason_codes(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    flattened: list[str] = []
    for reason_codes in value.values():
        for reason in _string_list(reason_codes, limit=_MAX_REASON_CODES):
            if reason not in flattened:
                flattened.append(reason)
            if len(flattened) == _MAX_REASON_CODES:
                return flattened
    return flattened


def build_guidance_context(response: dict[str, Any]) -> dict[str, Any]:
    guidance_confidence = _record(response.get("guidance_confidence"))
    guidance_metadata = _record(response.get("guidance_metadata"))
    applicability = _record(guidance_confidence.get("applicability"))
    retrieved_chunk_ids = _string_list(
        guidance_metadata.get("retrieved_chunk_ids"),
        limit=_MAX_CHUNK_IDS,
    )
    applicable_ids = _string_list(
        guidance_metadata.get("applicable_chunk_ids")
        or applicability.get("applicable_chunk_ids"),
        limit=_MAX_CHUNK_IDS,
    )
    conditional_ids = _string_list(
        guidance_metadata.get("conditional_chunk_ids")
        or applicability.get("conditional_chunk_ids"),
        limit=_MAX_CHUNK_IDS,
    )
    not_applicable_ids = _string_list(
        guidance_metadata.get("not_applicable_chunk_ids")
        or applicability.get("not_applicable_chunk_ids"),
        limit=_MAX_CHUNK_IDS,
    )
    if not retrieved_chunk_ids:
        retrieved_chunk_ids = list(
            dict.fromkeys([*applicable_ids, *conditional_ids, *not_applicable_ids])
        )[:_MAX_CHUNK_IDS]

    return {
        "guidance_confidence_level": _optional_string(
            guidance_confidence.get("level"), maximum=20
        ),
        "guidance_confidence_score": _bounded_float(
            guidance_confidence.get("score")
        ),
        "guidance_reason_codes": _string_list(
            guidance_confidence.get("reason_codes"), limit=_MAX_REASON_CODES
        ),
        "guidance_source": _optional_string(
            response.get("guidance_source"), maximum=100
        ),
        "final_action": _optional_string(
            response.get("disposal_action"), maximum=100
        ),
        "guidance_cache_hit": guidance_metadata.get("guidance_cache_hit") is True,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "applicable_chunk_ids": applicable_ids,
        "conditional_chunk_ids": conditional_ids,
        "not_applicable_chunk_ids": not_applicable_ids,
        "retrieval_reason_codes": _flatten_reason_codes(
            guidance_metadata.get("applicability_reason_codes")
        ),
        "final_generation_path": _optional_string(
            guidance_metadata.get("final_generation_path"), maximum=100
        ),
        "consistency_guard_triggered": (
            guidance_metadata.get("consistency_guard_triggered") is True
        ),
        "consistency_reason_codes": _string_list(
            guidance_metadata.get("consistency_contradiction_codes"),
            limit=_MAX_REASON_CODES,
        ),
    }


def build_original_context(
    *,
    request_id: str,
    classification: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    recognition_confidence = _record(classification.get("recognition_confidence"))
    clarification = _record(response.get("clarification"))
    status = _optional_string(classification.get("status"), maximum=20) or "unknown"
    if status not in {"confident", "uncertain", "unknown"}:
        status = "unknown"
    confidence_level = _optional_string(
        recognition_confidence.get("level"), maximum=20
    )
    if confidence_level not in {"high", "medium", "low", "unknown"}:
        confidence_level = "unknown" if confidence_level else None

    return {
        "request_id": request_id,
        "original_prediction": (
            _optional_string(response.get("item"), maximum=200)
            or _optional_string(classification.get("item"), maximum=200)
            or "Unknown"
        ),
        "original_status": status,
        "recognition_source": _optional_string(
            classification.get("recognition_source"), maximum=100
        ),
        "recognition_confidence_level": confidence_level,
        "recognition_confidence_score": _bounded_float(
            recognition_confidence.get("score")
        ),
        "recognition_reason_codes": _string_list(
            recognition_confidence.get("reason_codes"), limit=_MAX_REASON_CODES
        ),
        "recognition_cache_hit": classification.get("cache_hit") is True,
        "clarification_required": clarification.get("required") is True,
        "clarification_reason_codes": _string_list(
            clarification.get("reason_codes"), limit=_MAX_REASON_CODES
        ),
        **build_guidance_context(response),
    }


def store_prediction_context(
    *,
    request_id: str,
    classification: dict[str, Any],
    response: dict[str, Any],
    original_request_id: str | None = None,
    selected_item: str | None = None,
) -> bool:
    if original_request_id and selected_item:
        stored = feedback_repository.attach_correction_context(
            original_request_id=original_request_id,
            correction_request_id=request_id,
            corrected_item=(
                _optional_string(response.get("item"), maximum=200)
                or _optional_string(selected_item, maximum=200)
                or "Unknown"
            ),
            guidance_context=build_guidance_context(response),
        )
        logger.info(
            "Closed-test correction context processed. request_id=%s correction_request_id=%s stored=%s",
            original_request_id,
            request_id,
            stored,
        )
        return stored

    stored = feedback_repository.store_original_context(
        build_original_context(
            request_id=request_id,
            classification=classification,
            response=response,
        )
    )
    logger.info(
        "Closed-test original context processed. request_id=%s stored=%s",
        request_id,
        stored,
    )
    return stored
