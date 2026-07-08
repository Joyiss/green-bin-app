from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter, File, Form, UploadFile

try:
    from ..services.guidance_service import build_prediction_response
    from ..services.recognition_router import recognize_item
except ImportError:
    from services.guidance_service import build_prediction_response
    from services.recognition_router import recognize_item

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/predict")
async def predict(
    file: UploadFile | None = File(None),
    selected_item: str | None = Form(None),
) -> dict[str, Any]:
    request_started = perf_counter()
    try:
        classification = await recognize_item(file=file, selected_item=selected_item)
        guidance_started = perf_counter()
        try:
            response = build_prediction_response(classification)
            recognition_details = classification.get("recognition_details")
            if isinstance(recognition_details, dict):
                normalized_details = recognition_details.get("normalized")
                if isinstance(normalized_details, dict):
                    response["recognition_details"] = {
                        "normalized": normalized_details,
                    }
            return response
        finally:
            logger.info(
                "predict_timing stage=guidance duration_ms=%.1f",
                (perf_counter() - guidance_started) * 1000,
            )
    finally:
        logger.info(
            "predict_timing stage=total duration_ms=%.1f",
            (perf_counter() - request_started) * 1000,
        )
