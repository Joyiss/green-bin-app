from __future__ import annotations

import io
import json
import logging
from typing import Any

from fastapi import File, Form, HTTPException, UploadFile
from PIL import Image

try:
    from ..classifier import build_selected_item_prediction, classify
    from ..repositories import cache_repository
    from . import clip_service
    from . import vlm_service
    from . import phash_service
except ImportError:
    from classifier import build_selected_item_prediction, classify
    from repositories import cache_repository
    from services import clip_service
    from services import vlm_service
    from services import phash_service


logger = logging.getLogger(__name__)


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
    if (
        not isinstance(first_candidate, (list, tuple))
        or len(first_candidate) != 2
    ):
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


def _clip_shadow_candidates_summary(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for candidate in candidates[:3]:
        similarity = candidate.get("similarity")
        confidence = candidate.get("confidence")
        try:
            normalized_similarity = float(similarity) if similarity is not None else None
        except (TypeError, ValueError):
            normalized_similarity = None
        try:
            normalized_confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            normalized_confidence = None

        summary.append(
            {
                "id": candidate.get("id"),
                "item_label": candidate.get("item_label"),
                "similarity": normalized_similarity,
                "confidence": normalized_confidence,
                "verified": bool(candidate.get("verified")),
            }
        )

    return summary


def _format_clip_shadow_candidates(candidates: list[dict[str, Any]]) -> str:
    formatted_candidates: list[str] = []
    for candidate in candidates:
        label = candidate.get("item_label") or "unknown"
        similarity = candidate.get("similarity")
        if isinstance(similarity, (int, float)):
            formatted_candidates.append(f"{label} ({float(similarity):.4f})")
        else:
            formatted_candidates.append(str(label))
    return ", ".join(formatted_candidates)


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
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": "Invalid image file."}) from exc

        phash: str | None = None
        clip_embedding: list[float] | None = None
        clip_shadow_candidates: list[dict[str, Any]] = []
        try:
            phash = phash_service.create_phash(image_bytes)
            logger.info("Generated pHash for upload: %s", phash)
            cached_record = cache_repository.find_nearest_phash_match(
                phash,
                phash_service.PHASH_THRESHOLD,
            )
            if cached_record is not None:
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
                    logger.info(
                        "Skipping VLM due to usable pHash cache hit. phash=%s best_distance=%s",
                        phash,
                        cached_record.get("phash_distance"),
                    )
                    logger.info(
                        "pHash cache hit final classification. item=%s status=%s category=%s",
                        cached_classification.get("item"),
                        cached_classification.get("status"),
                        cached_classification.get("category"),
                    )
                    return _with_recognition_metadata(
                        cached_classification,
                        cache_hit=True,
                        recognition_source="phash_cache",
                    )
                logger.info(
                    "Found pHash cache match, but cached row was unusable. phash=%s best_distance=%s",
                    phash,
                    cached_record.get("phash_distance"),
                )
            else:
                logger.info(
                    "No usable pHash cache hit found. phash=%s continuing to CLIP shadow search and VLM.",
                    phash,
                )
        except Exception as exc:
            logger.warning("pHash cache lookup failed: %s", exc)

        if phash is not None:
            try:
                clip_embedding = clip_service.create_clip_embedding(image_bytes)
                logger.info(
                    "Generated CLIP embedding for shadow search. dimensions=%s",
                    len(clip_embedding),
                )
            except clip_service.ClipServiceError as exc:
                logger.warning("CLIP embedding generation failed: %s", exc)
            except Exception as exc:
                logger.warning("CLIP embedding generation failed: %s", exc)

        if clip_embedding is not None:
            try:
                similar_records = cache_repository.find_similar_embeddings(clip_embedding)
                clip_shadow_candidates = _clip_shadow_candidates_summary(similar_records)
                logger.info(
                    "CLIP shadow search executed. candidate_count=%s",
                    len(similar_records),
                )
                if clip_shadow_candidates:
                    logger.info(
                        "Top CLIP shadow candidates: %s",
                        _format_clip_shadow_candidates(clip_shadow_candidates),
                    )
            except Exception as exc:
                logger.warning("CLIP vector search failed: %s", exc)

        logger.info("Proceeding to VLM inference after cache checks.")
        predictions = vlm_service.get_top_predictions(image)
        classification = _with_recognition_metadata(
            classify(predictions),
            cache_hit=False,
            recognition_source="vlm",
        )

        item_label_to_save = classification.get("item", "")

        if phash is not None and _is_cacheable_item_label(item_label_to_save):
            try:
                metadata = {
                    "classification": _classification_snapshot(classification),
                }
                if clip_shadow_candidates:
                    metadata["clip_shadow_candidates"] = clip_shadow_candidates

                cache_repository.save_recognition_record(
                    phash=phash,
                    clip_embedding=clip_embedding,
                    item_label=item_label_to_save,
                    recognition_source="vlm",
                    confidence=_classification_confidence(classification),
                    verified=False,
                    metadata=metadata,
                )
            except Exception as exc:
                logger.warning("Recognition cache save failed: %s", exc)
        elif phash is not None:
            logger.info(
                "Skipping recognition cache save because classification item_label was blank or unknown. item=%s status=%s category=%s",
                classification.get("item"),
                classification.get("status"),
                classification.get("category"),
            )

        return classification
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail={"error": "Model inference failed."}) from exc
