from __future__ import annotations

import io
from typing import Any

from fastapi import File, Form, HTTPException, UploadFile
from PIL import Image

try:
    from ..classifier import build_selected_item_prediction, classify
    from . import vlm_service
except ImportError:
    from classifier import build_selected_item_prediction, classify
    from services import vlm_service


async def recognize_item(
    file: UploadFile | None = File(None),
    selected_item: str | None = Form(None),
) -> dict[str, Any]:
    try:
        if selected_item:
            return build_selected_item_prediction(selected_item)

        if file is None:
            raise HTTPException(status_code=400, detail={"error": "Image file is required."})

        image_bytes = await file.read()

        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": "Invalid image file."}) from exc

        predictions = vlm_service.get_top_predictions(image)
        return classify(predictions)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail={"error": "Model inference failed."}) from exc
