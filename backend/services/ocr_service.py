from __future__ import annotations

import io
import re
from typing import Any

from PIL import Image, ImageOps


OCR_KEYWORDS = {
    "battery": "Battery",
    "aa": "Battery",
    "aaa": "Battery",
    "alkaline": "Battery",
    "duracell": "Battery",
    "energizer": "Battery",
    "shampoo": "Shampoo bottle",
    "conditioner": "Shampoo bottle",
    "detergent": "Detergent bottle",
    "laundry": "Detergent bottle",
    "motor oil": "Motor oil container",
    "paint": "Paint can",
}


def _empty_ocr_payload() -> dict[str, Any]:
    return {
        "text": "",
        "keywords": [],
        "matched_label": None,
    }


def _load_pytesseract() -> Any | None:
    try:
        import pytesseract

        return pytesseract
    except Exception:
        return None


def clean_ocr_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    return " ".join(text.split())


def _keyword_in_text(text: str, keyword: str) -> bool:
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def extract_matched_keywords(text: str) -> list[str]:
    cleaned_text = clean_ocr_text(text)
    if not cleaned_text:
        return []

    return [
        keyword
        for keyword in OCR_KEYWORDS
        if _keyword_in_text(cleaned_text, keyword)
    ]


def match_keyword_label(keywords: list[str]) -> str | None:
    for keyword in keywords:
        matched_label = OCR_KEYWORDS.get(keyword)
        if matched_label is not None:
            return matched_label

    return None


def extract_ocr_text(image_bytes: bytes) -> dict[str, Any]:
    try:
        pytesseract_module = _load_pytesseract()
        if pytesseract_module is None:
            return _empty_ocr_payload()

        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized_image = ImageOps.exif_transpose(image).convert("RGB")
            raw_text = pytesseract_module.image_to_string(normalized_image)

        cleaned_text = clean_ocr_text(raw_text)
        keywords = extract_matched_keywords(cleaned_text)
        return {
            "text": cleaned_text,
            "keywords": keywords,
            "matched_label": match_keyword_label(keywords),
        }
    except Exception:
        return _empty_ocr_payload()
