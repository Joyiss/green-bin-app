from __future__ import annotations

import io
import json
import logging
import os
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from fastapi import File, Form, HTTPException, UploadFile
from PIL import Image, ImageOps

try:
    from ..classifier import build_selected_item_prediction, classify
    from ..repositories import cache_repository
    from . import barcode_service
    from .open_label_normalizer import (
        normalize_open_recognition,
    )
    from . import phash_service
    from .product_lookup_service import (
        get_product_by_barcode,
        map_product_to_item_label,
    )
    from . import request_context
    from . import vlm_service
    from .recognition_reliability_service import (
        evaluate_open_recognition,
        user_confirmed_recognition_confidence,
    )
    from .confidence_router import TOP_K, evaluate_clip_candidates
    from .runtime_config import is_clip_enabled
except ImportError:
    from classifier import build_selected_item_prediction, classify
    from repositories import cache_repository
    from services import barcode_service
    from services.open_label_normalizer import (
        normalize_open_recognition,
    )
    from services import phash_service
    from services.product_lookup_service import (
        get_product_by_barcode,
        map_product_to_item_label,
    )
    from services import request_context
    from services import vlm_service
    from services.recognition_reliability_service import (
        evaluate_open_recognition,
        user_confirmed_recognition_confidence,
    )
    from services.confidence_router import TOP_K, evaluate_clip_candidates
    from services.runtime_config import is_clip_enabled


logger = logging.getLogger(__name__)


class _ClipServiceProxy:
    def is_clip_initialized(self) -> bool:
        try:
            from ..services import clip_service as clip_service_module
        except ImportError:
            from services import clip_service as clip_service_module

        return clip_service_module.is_clip_initialized()

    def create_clip_embedding(self, image_bytes: bytes) -> list[float]:
        try:
            from ..services import clip_service as clip_service_module
        except ImportError:
            from services import clip_service as clip_service_module

        return clip_service_module.create_clip_embedding(image_bytes)


clip_service = _ClipServiceProxy()

_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def _nearest_phash_lookup_enabled() -> bool:
    return os.getenv("ENABLE_NEAREST_PHASH_LOOKUP", "false").strip().casefold() in _TRUE_ENV_VALUES


@contextmanager
def _timed_stage(stage: str):
    started = perf_counter()
    try:
        yield
    finally:
        logger.info(
            "predict_timing request_id=%s stage=%s duration_ms=%.1f",
            request_context.get_predict_request_id(),
            stage,
            (perf_counter() - started) * 1000,
        )


def _parse_json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _normalize_cached_candidate(candidate: Any) -> tuple[str, float] | None:
    if isinstance(candidate, dict):
        label = candidate.get("label")
        score = candidate.get("score")
    elif isinstance(candidate, (list, tuple)) and len(candidate) == 2:
        label = candidate[0]
        score = candidate[1]
    else:
        return None

    if not isinstance(label, str):
        return None

    try:
        return (label, float(score))
    except (TypeError, ValueError):
        return None


def _normalize_cached_classification(value: Any) -> dict[str, Any] | None:
    value = _parse_json_value(value)
    if not isinstance(value, dict):
        return None

    item = value.get("item")
    category = value.get("category")
    status = value.get("status")
    candidates = value.get("candidates")

    if not isinstance(item, str) or not isinstance(category, str) or not isinstance(status, str):
        return None
    if not isinstance(candidates, list):
        return None

    normalized_candidates: list[tuple[str, float]] = []
    for candidate in candidates:
        normalized_candidate = _normalize_cached_candidate(candidate)
        if normalized_candidate is None:
            return None
        normalized_candidates.append(normalized_candidate)

    normalized_classification = {
        "item": item,
        "category": category,
        "status": status,
        "candidates": normalized_candidates,
    }

    trusted_guidance_available = value.get("trusted_guidance_available")
    if isinstance(trusted_guidance_available, bool):
        normalized_classification["trusted_guidance_available"] = (
            trusted_guidance_available
        )

    trusted_guidance_label = value.get("trusted_guidance_label")
    if trusted_guidance_label is None or isinstance(trusted_guidance_label, str):
        if trusted_guidance_label is not None:
            normalized_classification["trusted_guidance_label"] = trusted_guidance_label

    recognition_details = value.get("recognition_details")
    if isinstance(recognition_details, dict):
        existing_normalized_details = recognition_details.get("normalized")
        has_raw_vlm_fields = any(
            key in recognition_details
            for key in ("raw_item_label", "likely_material", "broad_category")
        )
        needs_current_normalization = not (
            isinstance(existing_normalized_details, dict)
            and "normalized_item" in existing_normalized_details
            and "disposal_category" in existing_normalized_details
        )
        normalized_recognition_details = (
            normalize_open_recognition(recognition_details)
            if has_raw_vlm_fields and needs_current_normalization
            else recognition_details
        )
        normalized_classification["recognition_details"] = normalized_recognition_details

        normalized_open_details = normalized_recognition_details.get("normalized")
        if isinstance(normalized_open_details, dict):
            normalized_item = str(
                normalized_open_details.get("normalized_item")
                or normalized_open_details.get("item_label")
                or ""
            ).strip()
            disposal_category = str(
                normalized_open_details.get("disposal_category") or ""
            ).strip()
            material_category = str(
                normalized_open_details.get("material_category") or ""
            ).strip()
            broad_category = str(
                normalized_open_details.get("broad_category") or ""
            ).strip()

            if _is_real_item_label(normalized_item):
                normalized_classification["item"] = normalized_item
            if disposal_category:
                normalized_classification["category"] = disposal_category
            if material_category:
                normalized_classification["recognized_material_category"] = material_category
            if broad_category:
                normalized_classification["recognized_broad_category"] = broad_category

    recognized_material_category = value.get("recognized_material_category")
    if (
        isinstance(recognized_material_category, str)
        and "recognized_material_category" not in normalized_classification
    ):
        normalized_classification["recognized_material_category"] = (
            recognized_material_category
        )

    recognized_broad_category = value.get("recognized_broad_category")
    if (
        isinstance(recognized_broad_category, str)
        and "recognized_broad_category" not in normalized_classification
    ):
        normalized_classification["recognized_broad_category"] = (
            recognized_broad_category
        )

    recognition_confidence = value.get("recognition_confidence")
    if isinstance(recognition_confidence, dict):
        normalized_classification["recognition_confidence"] = dict(
            recognition_confidence
        )

    return normalized_classification


def _recover_confident_cached_classification(label: Any) -> dict[str, Any] | None:
    if not isinstance(label, str) or not label.strip():
        return None

    recovered_classification = build_selected_item_prediction(label)
    if recovered_classification.get("status") != "confident":
        return None

    return recovered_classification


def _is_real_item_label(label: Any) -> bool:
    if not isinstance(label, str):
        return False

    normalized_label = label.strip()
    if not normalized_label:
        return False
    if normalized_label.lower() == "unknown":
        return False

    return True


def _is_usable_cached_classification(classification: dict[str, Any]) -> bool:
    status = classification.get("status")
    item = classification.get("item")
    category = classification.get("category")
    trusted_guidance_available = classification.get("trusted_guidance_available")

    if status != "confident" or not _is_real_item_label(item):
        return False

    if trusted_guidance_available is False:
        return True

    return (
        status == "confident"
        and _is_real_item_label(item)
        and isinstance(category, str)
        and category != "Unknown"
    )


def _is_cacheable_item_label(label: Any) -> bool:
    if not _is_real_item_label(label):
        return False

    rebuilt_classification = build_selected_item_prediction(label)
    return rebuilt_classification.get("status") == "confident"


def _build_cached_classification(record: dict[str, Any]) -> dict[str, Any] | None:
    metadata = _parse_json_value(record.get("metadata"))
    item_label = record.get("item_label")

    if isinstance(metadata, dict):
        candidate_classification_values = []
        if "classification" in metadata:
            candidate_classification_values.append(metadata.get("classification"))
        candidate_classification_values.append(metadata)

        for candidate_value in candidate_classification_values:
            cached_classification = _normalize_cached_classification(candidate_value)
            if cached_classification is None:
                continue
            if _is_usable_cached_classification(cached_classification):
                return cached_classification

        for candidate_label in (
            item_label,
            metadata.get("item"),
            metadata.get("item_label"),
        ):
            recovered_classification = _recover_confident_cached_classification(candidate_label)
            if recovered_classification is not None:
                return recovered_classification

    recovered_from_item_label = _recover_confident_cached_classification(item_label)
    if recovered_from_item_label is not None:
        return recovered_from_item_label

    return None


def _classification_confidence(classification: dict[str, Any]) -> float | None:
    recognition_confidence = classification.get("recognition_confidence")
    if isinstance(recognition_confidence, dict):
        try:
            score = recognition_confidence.get("score")
            if score is not None:
                return float(score)
        except (TypeError, ValueError):
            pass

    candidates = classification.get("candidates", [])
    if classification.get("status") not in {"confident", "uncertain"}:
        return None
    if not candidates:
        return None

    first_candidate = candidates[0]
    if not isinstance(first_candidate, (list, tuple)) or len(first_candidate) != 2:
        return None

    try:
        return float(first_candidate[1])
    except (TypeError, ValueError):
        return None


def _classification_snapshot(classification: dict[str, Any]) -> dict[str, Any]:
    normalized_candidates: list[list[Any]] = []
    for candidate in classification.get("candidates", []):
        if not isinstance(candidate, (list, tuple)) or len(candidate) != 2:
            continue
        normalized_candidates.append([candidate[0], float(candidate[1])])

    snapshot = {
        "item": classification.get("item", ""),
        "category": classification.get("category", ""),
        "status": classification.get("status", "unknown"),
        "candidates": normalized_candidates,
    }

    for key in (
        "trusted_guidance_available",
        "trusted_guidance_label",
        "recognition_details",
        "recognized_material_category",
        "recognized_broad_category",
        "recognition_confidence",
    ):
        if key in classification:
            snapshot[key] = classification.get(key)

    return snapshot


def _with_recognition_metadata(
    classification: dict[str, Any],
    *,
    cache_hit: bool,
    recognition_source: str,
) -> dict[str, Any]:
    return {
        **classification,
        "cache_hit": cache_hit,
        "recognition_source": recognition_source,
    }


def _get_normalized_open_recognition_details(
    prediction_result: dict[str, Any],
) -> dict[str, Any] | None:
    recognition_details = prediction_result.get("recognition_details")
    if not isinstance(recognition_details, dict):
        return None

    normalized = recognition_details.get("normalized")
    if (
        isinstance(normalized, dict)
        and "normalized_item" in normalized
        and "disposal_category" in normalized
        and "original_vlm_broad_category" in normalized
        and "original_vlm_likely_material" in normalized
        and "visual_observations" in normalized
    ):
        if "vlm_mode" in recognition_details:
            return recognition_details
        return {
            **recognition_details,
            "vlm_mode": "open",
        }

    normalized_recognition_details = normalize_open_recognition(recognition_details)
    if "vlm_mode" not in normalized_recognition_details:
        normalized_recognition_details = {
            **normalized_recognition_details,
            "vlm_mode": "open",
        }

    return normalized_recognition_details


def _normalize_open_prediction_result(prediction_result: dict[str, Any]) -> dict[str, Any]:
    normalized_recognition_details = _get_normalized_open_recognition_details(
        prediction_result
    )
    if normalized_recognition_details is None:
        return prediction_result

    return {
        **prediction_result,
        "recognition_details": normalized_recognition_details,
    }


def _attach_recognition_details(
    classification: dict[str, Any],
    prediction_result: dict[str, Any],
) -> dict[str, Any]:
    normalized_recognition_details = _get_normalized_open_recognition_details(
        prediction_result
    )
    if normalized_recognition_details is None:
        return classification

    return {
        **classification,
        "recognition_details": normalized_recognition_details,
    }


def _prediction_contains_open_recognition(prediction_result: dict[str, Any]) -> bool:
    recognition_details = prediction_result.get("recognition_details")
    return isinstance(recognition_details, dict)


def _open_vlm_recognition_source(prediction_result: dict[str, Any]) -> str:
    return "vlm_open" if _prediction_contains_open_recognition(prediction_result) else "vlm"


def _build_open_vlm_classification(
    prediction_result: dict[str, Any],
) -> dict[str, Any] | None:
    recognition_details = _get_normalized_open_recognition_details(prediction_result)
    if recognition_details is None:
        return None

    normalized = recognition_details.get("normalized")
    if not isinstance(normalized, dict):
        return None

    normalized_item_label = str(
        normalized.get("normalized_item") or normalized.get("item_label") or ""
    ).strip()
    reliability = evaluate_open_recognition(recognition_details)
    suggested_label = reliability.get("suggested_label")
    final_item_label = (
        str(suggested_label).strip()
        if isinstance(suggested_label, str) and suggested_label.strip()
        else normalized_item_label
    )
    model_status = str(recognition_details.get("status") or "unknown").strip().casefold()
    if model_status == "unknown" or not _is_real_item_label(final_item_label):
        final_status = "unknown"
    elif reliability.get("blocking") is True or model_status == "uncertain":
        final_status = "uncertain"
    else:
        final_status = "confident"

    matched_supported_label = normalized.get("matched_supported_label")
    disposal_category = str(
        normalized.get("disposal_category") or ""
    ).strip() or "Unknown"
    material_category = str(
        normalized.get("material_category") or ""
    ).strip() or "Unknown"
    broad_category = str(
        normalized.get("broad_category") or ""
    ).strip() or "Unknown"
    if (
        final_status == "confident"
        and isinstance(matched_supported_label, str)
        and matched_supported_label.strip()
    ):
        trusted_classification = build_selected_item_prediction(matched_supported_label)
        if trusted_classification.get("status") == "confident":
            return {
                "item": final_item_label,
                "category": disposal_category,
                "status": "confident",
                "candidates": [],
                "trusted_guidance_available": True,
                "trusted_guidance_label": matched_supported_label,
                "recognized_material_category": material_category,
                "recognized_broad_category": broad_category,
                "recognition_confidence": reliability,
            }

    return {
        "item": final_item_label,
        "category": disposal_category,
        "status": final_status,
        "candidates": [],
        "trusted_guidance_available": False,
        "trusted_guidance_label": None,
        "recognized_material_category": material_category,
        "recognized_broad_category": broad_category,
        "recognition_confidence": reliability,
    }


def _build_vlm_classification(prediction_result: dict[str, Any]) -> dict[str, Any]:
    open_classification = _build_open_vlm_classification(prediction_result)
    if open_classification is not None:
        return open_classification

    return classify(prediction_result)


def _should_cache_open_vlm_classification(
    classification: dict[str, Any],
) -> bool:
    if classification.get("status") != "confident":
        return False
    recognition_confidence = classification.get("recognition_confidence")
    if (
        isinstance(recognition_confidence, dict)
        and recognition_confidence.get("level") != "high"
    ):
        return False
    if not _is_real_item_label(classification.get("item")):
        return False
    return True


def _log_final_classification(classification: dict[str, Any]) -> None:
    safe_fallback_guidance_used = (
        classification.get("status") == "confident"
        and classification.get("trusted_guidance_available") is False
    )
    recognition_confidence = classification.get("recognition_confidence")
    logger.info(
        "Final classification built. item=%s status=%s category=%s material_category=%s recognition_source=%s recognition_level=%s recognition_reasons=%s safe_fallback_guidance=%s",
        classification.get("item"),
        classification.get("status"),
        classification.get("category"),
        classification.get("recognized_material_category"),
        classification.get("recognition_source"),
        recognition_confidence.get("level") if isinstance(recognition_confidence, dict) else None,
        recognition_confidence.get("reason_codes") if isinstance(recognition_confidence, dict) else None,
        safe_fallback_guidance_used,
    )


def _coerce_optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_label_for_matching(label: Any) -> str | None:
    if not isinstance(label, str):
        return None

    normalized_label = label.strip()
    if not normalized_label:
        return None

    return normalized_label.casefold()


def _shape_clip_router_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shaped_candidates: list[dict[str, Any]] = []
    for candidate in candidates[:TOP_K]:
        shaped_candidates.append(
            {
                "id": candidate.get("id"),
                "item_label": candidate.get("item_label"),
                "similarity": _coerce_optional_float(candidate.get("similarity")),
                "confidence": _coerce_optional_float(candidate.get("confidence")),
                "verified": bool(candidate.get("verified")),
                "recognition_source": candidate.get("recognition_source"),
                "metadata": _parse_json_value(candidate.get("metadata")),
            }
        )

    return shaped_candidates


def _format_clip_candidates(candidates: list[dict[str, Any]]) -> str:
    formatted_candidates: list[str] = []
    for candidate in candidates:
        label = candidate.get("item_label") or "unknown"
        similarity = candidate.get("similarity")
        if isinstance(similarity, (int, float)):
            formatted_candidates.append(f"{label} ({float(similarity):.4f})")
        else:
            formatted_candidates.append(str(label))
    return ", ".join(formatted_candidates)


def _lightweight_clip_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lightweight_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        lightweight_candidate = {
            "id": candidate.get("id"),
            "item_label": candidate.get("item_label"),
            "similarity": candidate.get("similarity"),
            "confidence": candidate.get("confidence"),
            "verified": candidate.get("verified"),
        }
        if candidate.get("recognition_source") is not None:
            lightweight_candidate["recognition_source"] = candidate.get("recognition_source")
        lightweight_candidates.append(lightweight_candidate)

    return lightweight_candidates


def _cached_record_disables_near_match_reuse(record: dict[str, Any]) -> bool:
    metadata = _parse_json_value(record.get("metadata"))
    if not isinstance(metadata, dict):
        return False

    signals = metadata.get("signals")
    if not isinstance(signals, dict):
        return False

    cache_policy = signals.get("cache_policy")
    if not isinstance(cache_policy, dict):
        return False

    return cache_policy.get("save_clip_embedding") is False


def _log_router_decision(route: str, decision: dict[str, Any]) -> None:
    logger.info(
        "CLIP confidence router decision. route=%s reason=%s top_label=%s top_score=%s "
        "label_agreement_count=%s evaluated_count=%s best_competing_label=%s "
        "best_competing_score=%s margin=%s",
        route,
        decision.get("reason"),
        decision.get("top_label"),
        decision.get("top_score"),
        decision.get("label_agreement_count"),
        decision.get("evaluated_count"),
        decision.get("best_competing_label"),
        decision.get("best_competing_score"),
        decision.get("margin"),
    )


def _find_clip_cache_classification(
    candidates: list[dict[str, Any]],
    target_label: Any,
) -> tuple[dict[str, Any] | None, int]:
    normalized_target_label = _normalize_label_for_matching(target_label)
    if normalized_target_label is None:
        return None, 0

    matched_candidate_count = 0
    for candidate in candidates:
        if _normalize_label_for_matching(candidate.get("item_label")) != normalized_target_label:
            continue

        matched_candidate_count += 1
        cached_classification = _build_cached_classification(candidate)
        if cached_classification is not None:
            return cached_classification, matched_candidate_count

    return None, matched_candidate_count


def _empty_barcode_signal() -> dict[str, Any]:
    return {
        "value": None,
        "type": None,
        "matched": False,
        "product_lookup": None,
    }


def _empty_product_lookup_signal() -> dict[str, Any]:
    return {
        "found": False,
        "mapped": False,
        "source": "open_food_facts",
        "product_name": None,
        "brand": None,
        "category": None,
        "packaging": None,
    }


def _build_product_lookup_signal(product: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(product, dict):
        return _empty_product_lookup_signal()

    return {
        "found": True,
        "mapped": False,
        "source": str(product.get("source") or "open_food_facts"),
        "product_name": product.get("product_name"),
        "brand": product.get("brand"),
        "category": product.get("category"),
        "packaging": product.get("packaging"),
    }


def _build_cache_policy(
    *,
    save_record: bool,
    save_clip_embedding: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "save_record": save_record,
        "save_clip_embedding": save_clip_embedding,
        "reason": reason,
    }


def _finalize_vlm_cache_policy(
    *,
    classification: dict[str, Any],
    barcode_signal: dict[str, Any],
    clip_embedding: list[float] | None,
) -> dict[str, Any]:
    final_label = classification.get("item")
    final_status = classification.get("status")
    barcode_detected = barcode_signal.get("value") is not None

    if barcode_detected:
        return _build_cache_policy(
            save_record=True,
            save_clip_embedding=False,
            reason="barcode_detected",
        )

    if clip_embedding is None:
        return _build_cache_policy(
            save_record=True,
            save_clip_embedding=False,
            reason="clip_embedding_unavailable",
        )

    if final_status != "confident":
        return _build_cache_policy(
            save_record=True,
            save_clip_embedding=False,
            reason="unknown_or_uncertain_result",
        )

    if not _is_real_item_label(final_label):
        return _build_cache_policy(
            save_record=True,
            save_clip_embedding=False,
            reason="confident_result_missing_item_label",
        )

    recognition_confidence = classification.get("recognition_confidence")
    if (
        isinstance(recognition_confidence, dict)
        and recognition_confidence.get("level") != "high"
    ):
        return _build_cache_policy(
            save_record=True,
            save_clip_embedding=False,
            reason="recognition_not_high_confidence",
        )

    is_open_classification = isinstance(classification.get("recognition_details"), dict)
    if not _is_cacheable_item_label(final_label) and not is_open_classification:
        return _build_cache_policy(
            save_record=True,
            save_clip_embedding=False,
            reason="confident_label_not_cacheable",
        )

    return _build_cache_policy(
        save_record=True,
        save_clip_embedding=True,
        reason="normal_product_photo",
    )


def _build_signal_classification(label: Any, confidence: float | None = None) -> dict[str, Any] | None:
    classification = _recover_confident_cached_classification(label)
    if classification is None:
        return None

    if confidence is None:
        return classification

    return {
        **classification,
        "candidates": [(classification["item"], float(confidence))],
    }


def _build_signals_metadata(
    *,
    phash_value: str | None,
    phash_hit: bool,
    phash_distance: Any,
    barcode_signal: dict[str, Any],
    clip_candidates: list[dict[str, Any]],
    router_reason: str,
    cache_policy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "phash": {
            "value": phash_value,
            "hit": phash_hit,
            "distance": phash_distance,
        },
        "barcode": dict(barcode_signal),
        "clip_candidates": _lightweight_clip_candidates(clip_candidates),
        "router_reason": router_reason,
        "cache_policy": dict(cache_policy),
    }


def _save_recognition_record_if_possible(
    *,
    phash: str | None,
    clip_embedding: list[float] | None,
    classification: dict[str, Any],
    recognition_source: str,
    route: str,
    signals: dict[str, Any],
    save_record: bool,
    save_clip_embedding: bool,
) -> None:
    item_label = classification.get("item", "")
    trusted_guidance_available = classification.get("trusted_guidance_available")
    signals_barcode = signals.get("barcode") if isinstance(signals, dict) else None
    signals_cache_policy = signals.get("cache_policy") if isinstance(signals, dict) else None
    barcode_detected = (
        isinstance(signals_barcode, dict)
        and signals_barcode.get("value") is not None
    )
    cache_policy_reason = (
        signals_cache_policy.get("reason")
        if isinstance(signals_cache_policy, dict)
        else None
    )

    logger.info(
        "Recognition cache policy. save_clip_embedding=%s reason=%s barcode_detected=%s final_label=%s final_status=%s",
        bool(save_clip_embedding and clip_embedding is not None),
        cache_policy_reason,
        barcode_detected,
        classification.get("item"),
        classification.get("status"),
    )

    is_open_confident_cacheable = (
        trusted_guidance_available is False
        and classification.get("status") == "confident"
        and (
            not isinstance(classification.get("recognition_confidence"), dict)
            or classification["recognition_confidence"].get("level") == "high"
        )
        and _is_real_item_label(item_label)
    )

    if (
        not save_record
        or phash is None
        or (
            not _is_cacheable_item_label(item_label)
            and not is_open_confident_cacheable
        )
    ):
        return

    recognition_details = classification.get("recognition_details")
    metadata = {
        "classification": _classification_snapshot(classification),
        "route": route,
        "signals": signals,
    }
    if isinstance(recognition_details, dict):
        metadata["recognition_details"] = recognition_details
        metadata["vlm_mode"] = recognition_details.get("vlm_mode", "open")

    cache_repository.save_recognition_record(
        phash=phash,
        clip_embedding=clip_embedding if save_clip_embedding else None,
        item_label=item_label,
        recognition_source=recognition_source,
        confidence=_classification_confidence(classification),
        verified=False,
        metadata=metadata,
    )


async def recognize_item(
    file: UploadFile | None = File(None),
    selected_item: str | None = Form(None),
) -> dict[str, Any]:
    try:
        if isinstance(selected_item, str) and selected_item:
            selected_classification = build_selected_item_prediction(selected_item)
            if selected_classification.get("status") == "confident":
                return {
                    **selected_classification,
                    "recognition_confidence": user_confirmed_recognition_confidence(),
                    "recognition_source": "user_confirmed_selection",
                }
            return selected_classification

        if file is None:
            raise HTTPException(status_code=400, detail={"error": "Image file is required."})

        image_bytes = await file.read()

        try:
            with Image.open(io.BytesIO(image_bytes)) as uploaded_image:
                image = uploaded_image.convert("RGB")
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": "Invalid image file."}) from exc

        phash: str | None = None
        phash_hit = False
        phash_distance: Any = None
        clip_embedding: list[float] | None = None
        clip_candidates: list[dict[str, Any]] = []
        router_decision: dict[str, Any] | None = None
        router_reason = "vlm_fallback"
        barcode_signal = _empty_barcode_signal()
        cache_policy = _build_cache_policy(
            save_record=True,
            save_clip_embedding=True,
            reason="normal_product_photo",
        )
        phash_total_started = perf_counter()
        try:
            with _timed_stage("phash_compute"):
                phash = phash_service.create_phash(image_bytes)
            logger.info("Generated pHash for upload: %s", phash)
            with _timed_stage("phash_exact_lookup"):
                cached_record = cache_repository.find_exact_phash_match(phash)
            if cached_record is None:
                if _nearest_phash_lookup_enabled():
                    with _timed_stage("phash_nearest_lookup"):
                        cached_record = cache_repository.find_nearest_phash_match(
                            phash,
                            phash_service.PHASH_THRESHOLD,
                            check_exact=False,
                        )
                else:
                    logger.info(
                        "pHash nearest lookup skipped. reason=disabled_by_default"
                    )
            if cached_record is not None:
                phash_distance = cached_record.get("phash_distance")
                parsed_metadata = _parse_json_value(cached_record.get("metadata"))
                logger.info(
                    "pHash cache reconstruction input. row_id=%s item_label=%s metadata_type=%s classification_snapshot_found=%s",
                    cached_record.get("id"),
                    cached_record.get("item_label"),
                    type(parsed_metadata).__name__ if parsed_metadata is not None else "NoneType",
                    isinstance(parsed_metadata, dict) and parsed_metadata.get("classification") is not None,
                )
                cached_classification = _build_cached_classification(cached_record)
                logger.info(
                    "pHash cache reconstruction output. classification=%s",
                    cached_classification,
                )
                if cached_classification is not None:
                    phash_hit = True
                    unsafe_near_match = (
                        phash_distance != 0
                        and _cached_record_disables_near_match_reuse(cached_record)
                    )
                    if not unsafe_near_match:
                        router_reason = "phash_cache_hit"
                        logger.info(
                            "Skipping later recognition due to usable pHash cache hit. phash=%s best_distance=%s",
                            phash,
                            phash_distance,
                        )
                        logger.info(
                            "predict_timing request_id=%s stage=phash_total duration_ms=%.1f",
                            request_context.get_predict_request_id(),
                            (perf_counter() - phash_total_started) * 1000,
                        )
                        return _with_recognition_metadata(
                            cached_classification,
                            cache_hit=True,
                            recognition_source="phash_cache",
                        )
                    logger.info(
                        "Unsafe pHash near-match found, continuing full recognition. phash=%s best_distance=%s",
                        phash,
                        phash_distance,
                    )
                else:
                    logger.info(
                        "Found pHash cache match, but cached row was unusable. phash=%s best_distance=%s",
                        phash,
                        phash_distance,
                    )
            else:
                next_stages = (
                    "barcode, CLIP, and VLM"
                    if is_clip_enabled()
                    else "barcode and VLM"
                )
                logger.info(
                    "No usable pHash cache hit found. phash=%s continuing to %s.",
                    phash,
                    next_stages,
                )
        except Exception as exc:
            logger.warning("pHash cache lookup failed: %s", exc)

        logger.info(
            "predict_timing request_id=%s stage=phash_total duration_ms=%.1f",
            request_context.get_predict_request_id(),
            (perf_counter() - phash_total_started) * 1000,
        )

        barcode_started = perf_counter()
        try:
            with Image.open(io.BytesIO(image_bytes)) as barcode_debug_image:
                normalized_barcode_debug_image = ImageOps.exif_transpose(barcode_debug_image)
                logger.info(
                    "Barcode preflight. image_byte_length=%s original_size=%s original_mode=%s normalized_size=%s normalized_mode=%s",
                    len(image_bytes),
                    barcode_debug_image.size,
                    barcode_debug_image.mode,
                    normalized_barcode_debug_image.size,
                    normalized_barcode_debug_image.mode,
                )
            detected_barcode = barcode_service.detect_barcode(image_bytes)
        except Exception as exc:
            logger.warning("Barcode detection failed: %s", exc)
            detected_barcode = None

        logger.info(
            "Barcode detect_barcode returned a result: %s",
            detected_barcode is not None,
        )

        if isinstance(detected_barcode, dict):
            barcode_value = detected_barcode.get("barcode_value")
            barcode_type = detected_barcode.get("barcode_type")
            if isinstance(barcode_value, str) and barcode_value:
                barcode_signal["value"] = barcode_value
            if isinstance(barcode_type, str) and barcode_type:
                barcode_signal["type"] = barcode_type

            known_barcode_match = barcode_service.match_known_barcode(barcode_signal["value"])
            if known_barcode_match is not None:
                barcode_signal["matched"] = True
                router_reason = "known_barcode"
                cache_policy = _build_cache_policy(
                    save_record=True,
                    save_clip_embedding=False,
                    reason="known_barcode",
                )
                classification = _build_signal_classification(
                    known_barcode_match.get("item_label"),
                    _coerce_optional_float(known_barcode_match.get("confidence")) or 1.0,
                )
                if classification is not None:
                    signals = _build_signals_metadata(
                        phash_value=phash,
                        phash_hit=phash_hit,
                        phash_distance=phash_distance,
                        barcode_signal=barcode_signal,
                        clip_candidates=clip_candidates,
                        router_reason=router_reason,
                        cache_policy=cache_policy,
                    )
                    try:
                        _save_recognition_record_if_possible(
                            phash=phash,
                            clip_embedding=None,
                            classification=classification,
                            recognition_source="barcode",
                            route=router_reason,
                            signals=signals,
                            save_record=cache_policy["save_record"],
                            save_clip_embedding=cache_policy["save_clip_embedding"],
                        )
                    except Exception as exc:
                        logger.warning("Recognition cache save failed: %s", exc)

                    logger.info(
                        "predict_timing request_id=%s stage=barcode duration_ms=%.1f",
                        request_context.get_predict_request_id(),
                        (perf_counter() - barcode_started) * 1000,
                    )
                    return _with_recognition_metadata(
                        classification,
                        cache_hit=False,
                        recognition_source="barcode",
                    )

            if barcode_signal["value"] is not None:
                logger.info(
                    "Open Food Facts lookup started. barcode=%s",
                    barcode_signal["value"],
                )
                product = get_product_by_barcode(barcode_signal["value"])
                barcode_signal["product_lookup"] = _build_product_lookup_signal(product)
                logger.info(
                    "Open Food Facts lookup result. found=%s product_name=%s brand=%s category=%s packaging=%s",
                    product is not None,
                    barcode_signal["product_lookup"]["product_name"],
                    barcode_signal["product_lookup"]["brand"],
                    barcode_signal["product_lookup"]["category"],
                    barcode_signal["product_lookup"]["packaging"],
                )

                if product is not None:
                    product_mapping = map_product_to_item_label(product)
                    if product_mapping is not None:
                        barcode_signal["matched"] = True
                        if isinstance(barcode_signal.get("product_lookup"), dict):
                            barcode_signal["product_lookup"]["mapped"] = True
                        router_reason = "open_food_facts_barcode_lookup"
                        logger.info(
                            "Open Food Facts mapping result. mapped=True item_label=%s",
                            product_mapping.get("item_label"),
                        )
                        cache_policy = _build_cache_policy(
                            save_record=True,
                            save_clip_embedding=False,
                            reason=router_reason,
                        )
                        classification = _build_signal_classification(
                            product_mapping.get("item_label"),
                            _coerce_optional_float(product_mapping.get("confidence")) or 0.85,
                        )
                        if classification is not None:
                            signals = _build_signals_metadata(
                                phash_value=phash,
                                phash_hit=phash_hit,
                                phash_distance=phash_distance,
                                barcode_signal=barcode_signal,
                                clip_candidates=clip_candidates,
                                router_reason=router_reason,
                                cache_policy=cache_policy,
                            )
                            try:
                                _save_recognition_record_if_possible(
                                    phash=phash,
                                    clip_embedding=None,
                                    classification=classification,
                                    recognition_source="open_food_facts",
                                    route=router_reason,
                                    signals=signals,
                                    save_record=cache_policy["save_record"],
                                    save_clip_embedding=cache_policy["save_clip_embedding"],
                                )
                            except Exception as exc:
                                logger.warning("Recognition cache save failed: %s", exc)

                            logger.info(
                                "Skipping CLIP/VLM due to Open Food Facts barcode lookup."
                            )
                            logger.info(
                                "predict_timing request_id=%s stage=barcode duration_ms=%.1f",
                                request_context.get_predict_request_id(),
                                (perf_counter() - barcode_started) * 1000,
                            )
                            return _with_recognition_metadata(
                                classification,
                                cache_hit=False,
                                recognition_source="open_food_facts",
                            )

                    logger.info(
                        "Open Food Facts mapping result. mapped=False item_label=None"
                    )
                    logger.info(
                        "Falling back to VLM because Open Food Facts product could not be mapped. reason=%s product_name=%s brand=%s category=%s packaging=%s",
                        "barcode_product_context_vlm_fallback",
                        barcode_signal["product_lookup"]["product_name"],
                        barcode_signal["product_lookup"]["brand"],
                        barcode_signal["product_lookup"]["category"],
                        barcode_signal["product_lookup"]["packaging"],
                    )
                    router_reason = "barcode_product_context_vlm_fallback"
                else:
                    logger.info(
                        "Falling back to VLM because Open Food Facts returned no product. reason=%s barcode=%s",
                        "unknown_barcode_vlm_fallback",
                        barcode_signal["value"],
                    )
                    router_reason = "unknown_barcode_vlm_fallback"

        logger.info(
            "Barcode signal. detected=%s value=%s type=%s matched=%s",
            barcode_signal["value"] is not None,
            barcode_signal["value"],
            barcode_signal["type"],
            barcode_signal["matched"],
        )

        logger.info(
            "predict_timing request_id=%s stage=barcode duration_ms=%.1f",
            request_context.get_predict_request_id(),
            (perf_counter() - barcode_started) * 1000,
        )

        if barcode_signal["value"] is not None and not barcode_signal["matched"]:
            cache_policy = _build_cache_policy(
                save_record=True,
                save_clip_embedding=False,
                reason=router_reason,
            )
            logger.info(
                "Proceeding to barcode-aware VLM fallback after barcode detection. reason=%s",
                router_reason,
            )
            barcode_context = None
            if router_reason == "barcode_product_context_vlm_fallback":
                barcode_context = {
                    "barcode_value": barcode_signal.get("value"),
                    "product_name": barcode_signal["product_lookup"].get("product_name"),
                    "brand": barcode_signal["product_lookup"].get("brand"),
                    "category": barcode_signal["product_lookup"].get("category"),
                    "packaging": barcode_signal["product_lookup"].get("packaging"),
                }
            with _timed_stage("vlm"):
                raw_predictions = vlm_service.get_top_predictions(
                    image,
                    barcode_aware=True,
                    barcode_context=barcode_context,
                )
                normalization_started = perf_counter()
                predictions = _normalize_open_prediction_result(raw_predictions)
                recognition_source = _open_vlm_recognition_source(predictions)
                classification = _with_recognition_metadata(
                    _attach_recognition_details(_build_vlm_classification(predictions), predictions),
                    cache_hit=False,
                    recognition_source=recognition_source,
                )
                logger.info(
                    "predict_timing request_id=%s stage=vlm_result_normalization duration_ms=%.1f recognition_source=%s status=%s item=%s",
                    request_context.get_predict_request_id(),
                    (perf_counter() - normalization_started) * 1000,
                    recognition_source,
                    classification.get("status"),
                    classification.get("item"),
                )
                _log_final_classification(classification)

            should_cache_open_result = recognition_source == "vlm_open" and _should_cache_open_vlm_classification(
                classification,
            )
            if phash is not None and not (
                _is_cacheable_item_label(classification.get("item", ""))
                or should_cache_open_result
            ):
                logger.info(
                    "Skipping recognition cache save because classification item_label was blank or unknown. item=%s status=%s category=%s",
                    classification.get("item"),
                    classification.get("status"),
                    classification.get("category"),
                )
            else:
                try:
                    _save_recognition_record_if_possible(
                        phash=phash,
                        clip_embedding=None,
                        classification=classification,
                        recognition_source=recognition_source,
                        route=router_reason,
                        signals=_build_signals_metadata(
                            phash_value=phash,
                            phash_hit=phash_hit,
                            phash_distance=phash_distance,
                            barcode_signal=barcode_signal,
                            clip_candidates=clip_candidates,
                            router_reason=router_reason,
                            cache_policy=cache_policy,
                        ),
                        save_record=cache_policy["save_record"],
                        save_clip_embedding=cache_policy["save_clip_embedding"],
                    )
                except Exception as exc:
                    logger.warning("Recognition cache save failed: %s", exc)

            return classification

        clip_enabled = is_clip_enabled()
        logger.info("CLIP feature enabled=%s", clip_enabled)
        if not clip_enabled:
            logger.info("predict_stage stage=clip skipped=true reason=clip_disabled")
        elif clip_service.is_clip_initialized():
            with _timed_stage("clip"):
                try:
                    clip_embedding = clip_service.create_clip_embedding(image_bytes)
                    logger.info(
                        "Generated CLIP embedding for cache search. dimensions=%s",
                        len(clip_embedding),
                    )
                except Exception as exc:
                    logger.warning("CLIP embedding generation failed: %s", exc)

                if clip_embedding is not None:
                    try:
                        similar_records = cache_repository.find_similar_embeddings(
                            clip_embedding,
                            limit=TOP_K,
                        )
                        clip_candidates = _shape_clip_router_candidates(similar_records)
                        logger.info(
                            "CLIP cache search executed. candidate_count=%s",
                            len(similar_records),
                        )
                        if clip_candidates:
                            logger.info(
                                "Top CLIP cache candidates: %s",
                                _format_clip_candidates(clip_candidates),
                            )
                    except Exception as exc:
                        logger.warning("CLIP vector search failed: %s", exc)
                    else:
                        try:
                            router_decision = evaluate_clip_candidates(clip_candidates)
                        except Exception as exc:
                            logger.warning("CLIP confidence router failed: %s", exc)
                        else:
                            if router_decision.get("use_cache"):
                                target_label = (
                                    router_decision.get("item_label")
                                    or router_decision.get("top_label")
                                )
                                cached_classification, matched_candidate_count = (
                                    _find_clip_cache_classification(clip_candidates, target_label)
                                )
                                if cached_classification is not None:
                                    _log_router_decision("clip_cache", router_decision)
                                    logger.info(
                                        "Skipping VLM due to strong CLIP cache agreement. target_label=%s matched_candidates=%s",
                                        target_label,
                                        matched_candidate_count,
                                    )
                                    return _with_recognition_metadata(
                                        cached_classification,
                                        cache_hit=True,
                                        recognition_source="clip_cache",
                                    )

                                logger.info(
                                    "CLIP cache candidate could not be reconstructed into a usable classification. target_label=%s matched_candidates=%s",
                                    target_label,
                                    matched_candidate_count,
                                )
                            _log_router_decision("vlm_fallback", router_decision)
        else:
            logger.info("predict_stage stage=clip skipped=true reason=model_not_ready")

        logger.info("Proceeding to VLM inference after pHash, barcode, and CLIP checks.")
        with _timed_stage("vlm"):
            raw_predictions = vlm_service.get_top_predictions(image)
            normalization_started = perf_counter()
            predictions = _normalize_open_prediction_result(raw_predictions)
            recognition_source = _open_vlm_recognition_source(predictions)
            classification = _with_recognition_metadata(
                _attach_recognition_details(_build_vlm_classification(predictions), predictions),
                cache_hit=False,
                recognition_source=recognition_source,
            )
            logger.info(
                "predict_timing request_id=%s stage=vlm_result_normalization duration_ms=%.1f recognition_source=%s status=%s item=%s",
                request_context.get_predict_request_id(),
                (perf_counter() - normalization_started) * 1000,
                recognition_source,
                classification.get("status"),
                classification.get("item"),
            )
            _log_final_classification(classification)
        cache_policy = _finalize_vlm_cache_policy(
            classification=classification,
            barcode_signal=barcode_signal,
            clip_embedding=clip_embedding,
        )

        should_cache_open_result = recognition_source == "vlm_open" and _should_cache_open_vlm_classification(
            classification,
        )
        if phash is not None and not (
            _is_cacheable_item_label(classification.get("item", ""))
            or should_cache_open_result
        ):
            logger.info(
                "Skipping recognition cache save because classification item_label was blank or unknown. item=%s status=%s category=%s",
                classification.get("item"),
                classification.get("status"),
                classification.get("category"),
            )
        else:
            try:
                _save_recognition_record_if_possible(
                    phash=phash,
                    clip_embedding=clip_embedding,
                    classification=classification,
                    recognition_source=recognition_source,
                    route=router_reason,
                    signals=_build_signals_metadata(
                        phash_value=phash,
                        phash_hit=phash_hit,
                        phash_distance=phash_distance,
                        barcode_signal=barcode_signal,
                        clip_candidates=clip_candidates,
                        router_reason=router_reason,
                        cache_policy=cache_policy,
                    ),
                    save_record=cache_policy["save_record"],
                    save_clip_embedding=cache_policy["save_clip_embedding"],
                )
            except Exception as exc:
                logger.warning("Recognition cache save failed: %s", exc)

        return classification
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail={"error": "Model inference failed."}) from exc
