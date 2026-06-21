from __future__ import annotations

import io
import logging
from typing import Any

from PIL import Image, ImageOps


logger = logging.getLogger(__name__)


KNOWN_BARCODES = {
    "9780399578694": {
        "item_label": "Book",
        "confidence": 1.0,
    }
}


def _load_zxingcpp() -> Any | None:
    try:
        import zxingcpp

        logger.info("zxingcpp import succeeded.")
        return zxingcpp
    except Exception as exc:
        logger.info("zxingcpp import failed: %s", exc)
        return None


def _extract_barcode_value(result: Any) -> str | None:
    for attribute_name in ("text", "value"):
        value = getattr(result, attribute_name, None)
        if isinstance(value, bytes):
            try:
                value = value.decode("utf-8")
            except Exception:
                value = None
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _extract_barcode_type(result: Any) -> str | None:
    barcode_type = getattr(result, "format", None)
    if barcode_type is None:
        barcode_type = getattr(result, "barcode_format", None)

    if isinstance(barcode_type, str) and barcode_type.strip():
        return barcode_type.strip()

    type_name = getattr(barcode_type, "name", None)
    if isinstance(type_name, str) and type_name.strip():
        return type_name.strip()

    return None


def _read_barcodes(zxingcpp_module: Any, image: Image.Image) -> list[Any]:
    read_many = getattr(zxingcpp_module, "read_barcodes", None)
    if callable(read_many):
        results = read_many(image)
        if isinstance(results, list):
            return results
        if results is None:
            return []
        return list(results)

    read_one = getattr(zxingcpp_module, "read_barcode", None)
    if callable(read_one):
        result = read_one(image)
        return [result] if result is not None else []

    return []


def detect_barcode(image_bytes: bytes) -> dict[str, str] | None:
    try:
        zxingcpp_module = _load_zxingcpp()
        if zxingcpp_module is None:
            return None

        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized_image = ImageOps.exif_transpose(image).convert("RGB")
            logger.info(
                "Barcode detection image prepared. size=%s mode=%s",
                normalized_image.size,
                normalized_image.mode,
            )
            barcodes = _read_barcodes(zxingcpp_module, normalized_image)
            logger.info("Barcode detection returned %s result(s).", len(barcodes))

        if not barcodes:
            return None

        first_barcode = barcodes[0]
        barcode_value = _extract_barcode_value(first_barcode)
        if not barcode_value:
            return None

        return {
            "barcode_value": barcode_value,
            "barcode_type": _extract_barcode_type(first_barcode) or "Unknown",
        }
    except Exception:
        logger.exception("Barcode detection failed.")
        return None


def match_known_barcode(barcode_value: str) -> dict[str, Any] | None:
    return KNOWN_BARCODES.get(barcode_value)
