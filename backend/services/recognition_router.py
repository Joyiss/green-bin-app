from __future__ import annotations

import io
import json
import logging
from typing import Any

from fastapi import File, Form, HTTPException, UploadFile
from PIL import Image, ImageOps

try:
    from ..classifier import build_selected_item_prediction, classify
    from ..repositories import cache_repository
    from . import barcode_service
    from . import ocr_service
    from . import phash_service
    from .product_lookup_service import (
        get_product_by_barcode,
        map_product_to_item_label,
    )
    from . import vlm_service
    from .confidence_router import MIN_TOP_SIMILARITY, TOP_K, evaluate_clip_candidates
except ImportError:
    from classifier import build_selected_item_prediction, classify
    from repositories import cache_repository
    from services import barcode_service
    from services import ocr_service
    from services import phash_service
    from services.product_lookup_service import (
        get_product_by_barcode,
        map_product_to_item_label,
    )
    from services import vlm_service
    from services.confidence_router import MIN_TOP_SIMILARITY, TOP_K, evaluate_clip_candidates


logger = logging.getLogger(__name__)


class _ClipServiceProxy:
    def create_clip_embedding(self, image_bytes: bytes) -> list[float]:
        try:
            from ..services import clip_service as clip_service_module
        except ImportError:
            from services import clip_service as clip_service_module

        return clip_service_module.create_clip_embedding(image_bytes)


clip_service = _ClipServiceProxy()


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

    return {
        "item": item,
        "category": category,
        "status": status,
        "candidates": normalized_candidates,
    }


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

    return {
        "item": classification.get("item", ""),
        "category": classification.get("category", ""),
        "status": classification.get("status", "unknown"),
        "candidates": normalized_candidates,
    }


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


def _empty_ocr_signal() -> dict[str, Any]:
    return {
        "text": "",
        "keywords": [],
        "matched_label": None,
    }


def _is_text_heavy_ocr_signal(ocr_signal: dict[str, Any]) -> bool:
    text = ocr_signal.get("text", "")
    keywords = ocr_signal.get("keywords", [])

    return (
        isinstance(text, str)
        and len(text) >= 20
    ) or (
        isinstance(keywords, list)
        and len(keywords) >= 2
    )


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
    ocr_signal: dict[str, Any],
    clip_embedding: list[float] | None,
) -> dict[str, Any]:
    final_label = classification.get("item")
    final_status = classification.get("status")
    barcode_detected = barcode_signal.get("value") is not None
    normalized_ocr_label = _normalize_label_for_matching(ocr_signal.get("matched_label"))
    normalized_final_label = _normalize_label_for_matching(final_label)

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

    if final_status != "confident" or not _is_cacheable_item_label(final_label):
        return _build_cache_policy(
            save_record=True,
            save_clip_embedding=False,
            reason="unknown_or_uncertain_result",
        )

    if (
        normalized_ocr_label is not None
        and normalized_final_label is not None
        and normalized_ocr_label != normalized_final_label
    ):
        return _build_cache_policy(
            save_record=True,
            save_clip_embedding=False,
            reason="ocr_final_label_conflict",
        )

    return _build_cache_policy(
        save_record=True,
        save_clip_embedding=True,
        reason="normal_product_photo",
    )


def _normalize_ocr_signal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _empty_ocr_signal()

    text = value.get("text")
    keywords = value.get("keywords")
    matched_label = value.get("matched_label")

    normalized_keywords: list[str] = []
    if isinstance(keywords, list):
        normalized_keywords = [keyword for keyword in keywords if isinstance(keyword, str)]

    return {
        "text": text if isinstance(text, str) else "",
        "keywords": normalized_keywords,
        "matched_label": matched_label if isinstance(matched_label, str) else None,
    }


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
    ocr_signal: dict[str, Any],
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
        "ocr": dict(ocr_signal),
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
    signals_ocr = signals.get("ocr") if isinstance(signals, dict) else None
    signals_barcode = signals.get("barcode") if isinstance(signals, dict) else None
    signals_cache_policy = signals.get("cache_policy") if isinstance(signals, dict) else None
    barcode_detected = (
        isinstance(signals_barcode, dict)
        and signals_barcode.get("value") is not None
    )
    ocr_matched_label = (
        signals_ocr.get("matched_label")
        if isinstance(signals_ocr, dict)
        else None
    )
    cache_policy_reason = (
        signals_cache_policy.get("reason")
        if isinstance(signals_cache_policy, dict)
        else None
    )

    logger.info(
        "Recognition cache policy. save_clip_embedding=%s reason=%s barcode_detected=%s ocr_matched_label=%s final_label=%s final_status=%s",
        bool(save_clip_embedding and clip_embedding is not None),
        cache_policy_reason,
        barcode_detected,
        ocr_matched_label,
        classification.get("item"),
        classification.get("status"),
    )

    if not save_record or phash is None or not _is_cacheable_item_label(item_label):
        return

    cache_repository.save_recognition_record(
        phash=phash,
        clip_embedding=clip_embedding if save_clip_embedding else None,
        item_label=item_label,
        recognition_source=recognition_source,
        confidence=_classification_confidence(classification),
        verified=False,
        metadata={
            "classification": _classification_snapshot(classification),
            "route": route,
            "signals": signals,
        },
    )


async def recognize_item(
    file: UploadFile | None = File(None),
    selected_item: str | None = Form(None),
) -> dict[str, Any]:
    try:
        if isinstance(selected_item, str) and selected_item:
            return build_selected_item_prediction(selected_item)

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
        ocr_signal = _empty_ocr_signal()
        cache_policy = _build_cache_policy(
            save_record=True,
            save_clip_embedding=True,
            reason="normal_product_photo",
        )
        text_heavy_weak_visual_detected = False
        ocr_clip_conflict_detected = False
        ocr_affected_router_decision = False

        try:
            phash = phash_service.create_phash(image_bytes)
            logger.info("Generated pHash for upload: %s", phash)
            cached_record = cache_repository.find_nearest_phash_match(
                phash,
                phash_service.PHASH_THRESHOLD,
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
                logger.info(
                    "No usable pHash cache hit found. phash=%s continuing to barcode, OCR, CLIP, and VLM.",
                    phash,
                )
        except Exception as exc:
            logger.warning("pHash cache lookup failed: %s", exc)

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
                        ocr_signal=ocr_signal,
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
                                ocr_signal=ocr_signal,
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
                                "Skipping OCR/CLIP/VLM due to Open Food Facts barcode lookup."
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
            predictions = vlm_service.get_top_predictions(
                image,
                barcode_aware=True,
                barcode_context=barcode_context,
            )
            classification = _with_recognition_metadata(
                classify(predictions),
                cache_hit=False,
                recognition_source="vlm",
            )

            if phash is not None and not _is_cacheable_item_label(classification.get("item", "")):
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
                        recognition_source="vlm",
                        route=router_reason,
                        signals=_build_signals_metadata(
                            phash_value=phash,
                            phash_hit=phash_hit,
                            phash_distance=phash_distance,
                            barcode_signal=barcode_signal,
                            ocr_signal=ocr_signal,
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

        try:
            ocr_signal = _normalize_ocr_signal(ocr_service.extract_ocr_text(image_bytes))
        except Exception as exc:
            logger.warning("OCR extraction failed: %s", exc)
            ocr_signal = _empty_ocr_signal()

        logger.info(
            "OCR signal. text_length=%s keywords=%s matched_label=%s preview=%s",
            len(ocr_signal["text"]),
            ocr_signal["keywords"],
            ocr_signal["matched_label"],
            ocr_signal["text"][:80],
        )

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
                    clip_top_label = router_decision.get("top_label")
                    clip_top_score = _coerce_optional_float(router_decision.get("top_score"))
                    normalized_ocr_label = _normalize_label_for_matching(
                        ocr_signal.get("matched_label")
                    )
                    normalized_clip_label = _normalize_label_for_matching(clip_top_label)
                    ocr_matches_clip = (
                        normalized_ocr_label is not None
                        and normalized_ocr_label == normalized_clip_label
                    )
                    text_heavy_signal = _is_text_heavy_ocr_signal(ocr_signal)

                    if normalized_ocr_label is not None:
                        if ocr_matches_clip and clip_top_score is not None and clip_top_score >= MIN_TOP_SIMILARITY:
                            cached_classification, matched_candidate_count = (
                                _find_clip_cache_classification(clip_candidates, clip_top_label)
                            )
                            classification = cached_classification
                            recognition_source = "clip_cache"
                            cache_hit = True

                            if classification is None:
                                classification = _build_signal_classification(
                                    clip_top_label,
                                    clip_top_score,
                                )
                                recognition_source = "ocr_clip"
                                cache_hit = False

                            if classification is not None:
                                router_reason = "ocr_clip_agreement"
                                ocr_affected_router_decision = True
                                _log_router_decision("ocr_clip_agreement", router_decision)
                                signals = _build_signals_metadata(
                                    phash_value=phash,
                                    phash_hit=phash_hit,
                                    phash_distance=phash_distance,
                                    barcode_signal=barcode_signal,
                                    ocr_signal=ocr_signal,
                                    clip_candidates=clip_candidates,
                                    router_reason=router_reason,
                                    cache_policy=cache_policy,
                                )
                                try:
                                    _save_recognition_record_if_possible(
                                        phash=phash,
                                        clip_embedding=clip_embedding,
                                        classification=classification,
                                        recognition_source=recognition_source,
                                        route=router_reason,
                                        signals=signals,
                                        save_record=cache_policy["save_record"],
                                        save_clip_embedding=cache_policy["save_clip_embedding"],
                                    )
                                except Exception as exc:
                                    logger.warning("Recognition cache save failed: %s", exc)

                                logger.info(
                                    "Skipping VLM due to OCR and CLIP agreement. target_label=%s matched_candidates=%s",
                                    clip_top_label,
                                    matched_candidate_count,
                                )
                                logger.info(
                                    "OCR router impact. affected=%s router_reason=%s",
                                    ocr_affected_router_decision,
                                    router_reason,
                                )
                                return _with_recognition_metadata(
                                    classification,
                                    cache_hit=cache_hit,
                                    recognition_source=recognition_source,
                                )

                        elif normalized_clip_label is not None and not ocr_matches_clip:
                            router_reason = "ocr_clip_conflict"
                            ocr_clip_conflict_detected = True
                            ocr_affected_router_decision = True
                            cache_policy = _build_cache_policy(
                                save_record=True,
                                save_clip_embedding=False,
                                reason="ocr_clip_conflict",
                            )
                            _log_router_decision(router_reason, router_decision)
                        elif text_heavy_signal:
                            router_reason = "text_heavy_weak_visual"
                            text_heavy_weak_visual_detected = True
                            ocr_affected_router_decision = True
                            cache_policy = _build_cache_policy(
                                save_record=True,
                                save_clip_embedding=False,
                                reason="text_heavy_weak_visual",
                            )
                            _log_router_decision(router_reason, router_decision)
                        else:
                            _log_router_decision("vlm_fallback", router_decision)
                    elif text_heavy_signal:
                        router_reason = "text_heavy_weak_visual"
                        text_heavy_weak_visual_detected = True
                        ocr_affected_router_decision = True
                        cache_policy = _build_cache_policy(
                            save_record=True,
                            save_clip_embedding=False,
                            reason="text_heavy_weak_visual",
                        )
                        _log_router_decision(router_reason, router_decision)
                    elif router_decision.get("use_cache"):
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
                            logger.info(
                                "OCR router impact. affected=%s router_reason=%s",
                                ocr_affected_router_decision,
                                "clip_cache",
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
                        _log_router_decision("vlm_fallback", router_decision)

        if _is_text_heavy_ocr_signal(ocr_signal) and router_reason == "vlm_fallback":
            router_reason = "text_heavy_weak_visual"
            text_heavy_weak_visual_detected = True
            ocr_affected_router_decision = True
            cache_policy = _build_cache_policy(
                save_record=True,
                save_clip_embedding=False,
                reason="text_heavy_weak_visual",
            )
        elif text_heavy_weak_visual_detected:
            router_reason = "text_heavy_weak_visual"
        elif ocr_clip_conflict_detected:
            router_reason = "ocr_clip_conflict"

        logger.info(
            "OCR router impact. affected=%s router_reason=%s",
            ocr_affected_router_decision,
            router_reason,
        )
        logger.info("Proceeding to VLM inference after pHash, barcode, OCR, and CLIP checks.")
        predictions = vlm_service.get_top_predictions(image)
        classification = _with_recognition_metadata(
            classify(predictions),
            cache_hit=False,
            recognition_source="vlm",
        )
        cache_policy = _finalize_vlm_cache_policy(
            classification=classification,
            barcode_signal=barcode_signal,
            ocr_signal=ocr_signal,
            clip_embedding=clip_embedding,
        )

        if phash is not None and not _is_cacheable_item_label(classification.get("item", "")):
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
                    recognition_source="vlm",
                    route=router_reason,
                    signals=_build_signals_metadata(
                        phash_value=phash,
                        phash_hit=phash_hit,
                        phash_distance=phash_distance,
                        barcode_signal=barcode_signal,
                        ocr_signal=ocr_signal,
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
