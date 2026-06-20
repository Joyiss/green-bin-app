from __future__ import annotations

import io
import logging
from typing import Any

from fastapi import File, Form, HTTPException, UploadFile
from PIL import Image

try:
    from ..classifier import build_selected_item_prediction, classify
    from ..repositories import cache_repository
    from . import vlm_service
    from . import phash_service
except ImportError:
    from classifier import build_selected_item_prediction, classify
    from repositories import cache_repository
    from services import vlm_service
    from services import phash_service


logger = logging.getLogger(__name__)


def _normalize_cached_classification(value: Any) -> dict[str, Any] | None:
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
        if (
            not isinstance(candidate, (list, tuple))
            or len(candidate) != 2
            or not isinstance(candidate[0], str)
        ):
            return None
        try:
            normalized_candidates.append((candidate[0], float(candidate[1])))
        except (TypeError, ValueError):
            return None

    return {
        "item": item,
        "category": category,
        "status": status,
        "candidates": normalized_candidates,
    }


def _build_cached_classification(record: dict[str, Any]) -> dict[str, Any] | None:
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        cached_classification = _normalize_cached_classification(metadata.get("classification"))
        if cached_classification is not None:
            return cached_classification

    item_label = record.get("item_label")
    if isinstance(item_label, str) and item_label.strip():
        return build_selected_item_prediction(item_label)

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
        try:
            phash = phash_service.create_phash(image_bytes)
            logger.warning("[TEMP pHash] generated upload pHash=%s", phash)
            cached_record = cache_repository.find_nearest_phash_match(
                phash,
                phash_service.PHASH_THRESHOLD,
            )
            if cached_record is not None:
                cached_classification = _build_cached_classification(cached_record)
                if cached_classification is not None:
                    logger.warning(
                        "[TEMP pHash] cache hit: best_distance=%s within_threshold=%s vlm_skipped=%s",
                        cached_record.get("phash_distance"),
                        True,
                        True,
                    )
                    return _with_recognition_metadata(
                        cached_classification,
                        cache_hit=True,
                        recognition_source="phash_cache",
                    )
                logger.warning(
                    "[TEMP pHash] cache match unusable: best_distance=%s within_threshold=%s vlm_skipped=%s",
                    cached_record.get("phash_distance"),
                    True,
                    False,
                )
            else:
                logger.warning(
                    "[TEMP pHash] cache miss: within_threshold=%s vlm_skipped=%s",
                    False,
                    False,
                )
        except Exception:
            logger.exception("pHash cache lookup failed.")

        logger.warning("[TEMP pHash] proceeding to VLM inference after cache path.")
        predictions = vlm_service.get_top_predictions(image)
        classification = _with_recognition_metadata(
            classify(predictions),
            cache_hit=False,
            recognition_source="vlm",
        )

        if phash is not None:
            try:
                cache_repository.save_recognition_record(
                    phash=phash,
                    item_label=classification.get("item", ""),
                    recognition_source="vlm",
                    confidence=_classification_confidence(classification),
                    verified=False,
                    metadata={
                        "classification": _classification_snapshot(classification),
                    },
                )
            except Exception:
                logger.exception("pHash cache save failed.")

        return classification
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail={"error": "Model inference failed."}) from exc
