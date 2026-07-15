from __future__ import annotations

import logging
import threading
import uuid
from time import perf_counter
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

try:
    from ..services import feedback_context_service, request_context, scan_rate_limit_service
    from ..services.guidance_service import build_prediction_response
    from ..services.recognition_router import recognize_item
except ImportError:
    from services import feedback_context_service, request_context, scan_rate_limit_service
    from services.guidance_service import build_prediction_response
    from services.recognition_router import recognize_item

router = APIRouter()
logger = logging.getLogger(__name__)
_ACTIVE_PREDICT_REQUESTS = 0
_ACTIVE_PREDICT_REQUESTS_LOCK = threading.Lock()


def _increment_active_predict_requests() -> int:
    global _ACTIVE_PREDICT_REQUESTS
    with _ACTIVE_PREDICT_REQUESTS_LOCK:
        _ACTIVE_PREDICT_REQUESTS += 1
        return _ACTIVE_PREDICT_REQUESTS


def _decrement_active_predict_requests() -> int:
    global _ACTIVE_PREDICT_REQUESTS
    with _ACTIVE_PREDICT_REQUESTS_LOCK:
        _ACTIVE_PREDICT_REQUESTS = max(0, _ACTIVE_PREDICT_REQUESTS - 1)
        return _ACTIVE_PREDICT_REQUESTS


def _has_predict_input(file: UploadFile | None, selected_item: str | None) -> bool:
    return file is not None or (isinstance(selected_item, str) and bool(selected_item.strip()))


@router.post("/predict")
async def predict(
    file: UploadFile | None = File(None),
    selected_item: str | None = Form(None),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_original_request_id: str | None = Header(None, alias="X-Original-Request-ID"),
    x_greenbin_client_id: str | None = Header(None, alias="X-GreenBin-Client-Id"),
) -> Any:
    request_started = perf_counter()
    request_id = (
        x_request_id.strip()
        if isinstance(x_request_id, str) and x_request_id.strip()
        else f"predict-{uuid.uuid4().hex[:12]}"
    )
    if not _has_predict_input(file, selected_item):
        raise HTTPException(
            status_code=400,
            detail={"error": "Image file or selected_item is required."},
        )

    context_token = request_context.set_predict_request_id(request_id)
    active_count = _increment_active_predict_requests()
    logger.info(
        "predict_request_started request_id=%s active_predict_requests=%s overlapping=%s has_file=%s selected_item=%s filename=%s content_type=%s",
        request_id,
        active_count,
        active_count > 1,
        file is not None,
        bool(selected_item),
        getattr(file, "filename", None),
        getattr(file, "content_type", None),
    )
    try:
        try:
            rate_limit_metadata = scan_rate_limit_service.consume_daily_scan(
                x_greenbin_client_id
            )
        except scan_rate_limit_service.MissingScanClientIdError:
            return JSONResponse(
                status_code=400,
                content={"error": "scan_client_id_required"},
            )
        except scan_rate_limit_service.DailyScanLimitReachedError as exc:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "daily_scan_limit_reached",
                    **exc.metadata.to_response_payload(),
                },
            )
        except scan_rate_limit_service.ScanRateLimitUnavailableError:
            return JSONResponse(
                status_code=503,
                content={"error": "scan_rate_limit_unavailable"},
            )

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
            if rate_limit_metadata is not None:
                response.update(rate_limit_metadata.to_response_payload())
            response["request_id"] = request_id
            original_request_id = (
                x_original_request_id.strip()
                if isinstance(x_original_request_id, str)
                and x_original_request_id.strip()
                and len(x_original_request_id.strip()) <= 96
                else None
            )
            feedback_context_service.store_prediction_context(
                request_id=request_id,
                classification=classification,
                response=response,
                original_request_id=original_request_id,
                selected_item=selected_item,
            )
            return response
        finally:
            logger.info(
                "predict_timing request_id=%s stage=guidance duration_ms=%.1f",
                request_id,
                (perf_counter() - guidance_started) * 1000,
            )
    finally:
        remaining_count = _decrement_active_predict_requests()
        logger.info(
            "predict_timing request_id=%s stage=total duration_ms=%.1f active_predict_requests=%s",
            request_id,
            (perf_counter() - request_started) * 1000,
            remaining_count,
        )
        request_context.reset_predict_request_id(context_token)
