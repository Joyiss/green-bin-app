from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, UploadFile

try:
    from ..services.guidance_service import build_prediction_response
    from ..services.recognition_router import recognize_item
except ImportError:
    from services.guidance_service import build_prediction_response
    from services.recognition_router import recognize_item

router = APIRouter()


@router.post("/predict")
async def predict(
    file: UploadFile | None = File(None),
    selected_item: str | None = Form(None),
) -> dict[str, Any]:
    classification = await recognize_item(file=file, selected_item=selected_item)
    return build_prediction_response(classification)
