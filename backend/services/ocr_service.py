from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps


logger = logging.getLogger(__name__)

TESSERACT_CONFIG = "--oem 3 --psm 11"
MAX_DIMENSION = 1280
MAX_TEXT_LENGTH = 500
WINDOWS_TESSERACT_PATH = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

OCR_KEYWORDS = (
    "synthetic motor oil",
    "motor oil",
    "engine oil",
    "spray paint",
    "laundry detergent",
    "hair care",
    "battery",
    "alkaline",
    "rechargeable",
    "lithium",
    "duracell",
    "energizer",
    "shampoo",
    "conditioner",
    "detergent",
    "laundry",
    "fabric",
    "softener",
    "paint",
    "aerosol",
    "spray",
    "can",
    "oil",
    "water",
    "drinking",
    "purified",
    "plastic",
    "bottle",
    "glass",
    "jar",
    "carton",
    "cardboard",
    "aa",
    "aaa",
)


def _empty_ocr_payload() -> dict[str, Any]:
    return {
        "text": "",
        "keywords": [],
        "matched_label": None,
    }


def _load_pytesseract() -> Any | None:
    try:
        import pytesseract

        logger.info("pytesseract import succeeded.")
        return pytesseract
    except Exception as exc:
        logger.info("pytesseract import failed: %s", exc)
        return None


def _configure_tesseract_cmd(pytesseract_module: Any) -> None:
    env_path = os.getenv("TESSERACT_CMD", "").strip()
    if env_path and Path(env_path).is_file():
        pytesseract_module.pytesseract.tesseract_cmd = env_path
        return

    if WINDOWS_TESSERACT_PATH.is_file():
        pytesseract_module.pytesseract.tesseract_cmd = str(WINDOWS_TESSERACT_PATH)


def _is_tesseract_available(pytesseract_module: Any) -> bool:
    try:
        pytesseract_module.get_tesseract_version()
        logger.info("Tesseract runtime is available.")
        return True
    except (Exception, SystemExit) as exc:
        logger.warning("Tesseract runtime is unavailable or invalid: %s", exc)
        return False


def clean_ocr_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    cleaned_text = " ".join(text.split()).strip().lower()
    if len(cleaned_text) > MAX_TEXT_LENGTH:
        return cleaned_text[:MAX_TEXT_LENGTH].strip()
    return cleaned_text


def _keyword_in_text(text: str, keyword: str) -> bool:
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _resize_max_dimension(image: Image.Image, max_dimension: int) -> Image.Image:
    resized_image = image.copy()
    resized_image.thumbnail((max_dimension, max_dimension))
    return resized_image


def _high_contrast_grayscale(image: Image.Image) -> Image.Image:
    grayscale_image = image.convert("L")
    return ImageEnhance.Contrast(grayscale_image).enhance(2.5)


def _build_ocr_variants(image: Image.Image) -> list[tuple[str, Image.Image]]:
    rgb_resized_1280 = _resize_max_dimension(image, MAX_DIMENSION)
    return [
        ("rgb_resized_1280", rgb_resized_1280),
        (
            "high_contrast_grayscale_resized_1280",
            _high_contrast_grayscale(rgb_resized_1280),
        ),
    ]


def _collect_text_segments(pytesseract_module: Any, image: Image.Image) -> list[str]:
    text_segments: list[str] = []
    variants = _build_ocr_variants(image)
    logger.info("OCR variants tried: %s", [variant_name for variant_name, _ in variants])

    for variant_name, variant_image in variants:
        try:
            raw_text = pytesseract_module.image_to_string(
                variant_image,
                config=TESSERACT_CONFIG,
            )
        except (Exception, SystemExit) as exc:
            logger.info("OCR variant failed. variant=%s error=%s", variant_name, exc)
            continue

        cleaned_text = clean_ocr_text(raw_text)
        if cleaned_text:
            text_segments.append(cleaned_text)

    return text_segments


def _dedupe_text_segments(segments: list[str]) -> str:
    unique_segments: list[str] = []
    seen_segments: set[str] = set()

    for segment in segments:
        normalized_segment = clean_ocr_text(segment)
        if not normalized_segment or normalized_segment in seen_segments:
            continue
        seen_segments.add(normalized_segment)
        unique_segments.append(normalized_segment)

    return clean_ocr_text(" ".join(unique_segments))


def extract_matched_keywords(text: str) -> list[str]:
    cleaned_text = clean_ocr_text(text)
    if not cleaned_text:
        return []

    return [
        keyword
        for keyword in OCR_KEYWORDS
        if _keyword_in_text(cleaned_text, keyword)
    ]


def _has_any_keyword(keywords: list[str], candidates: tuple[str, ...]) -> bool:
    keyword_set = set(keywords)
    return any(candidate in keyword_set for candidate in candidates)


def match_keyword_label(keywords: list[str]) -> str | None:
    keyword_list = [keyword for keyword in keywords if isinstance(keyword, str)]
    if not keyword_list:
        return None

    if _has_any_keyword(keyword_list, ("shampoo", "conditioner")):
        return "Shampoo bottle"

    if _has_any_keyword(keyword_list, ("laundry detergent",)):
        return "Detergent bottle"
    if "detergent" in keyword_list:
        return "Detergent bottle"

    if _has_any_keyword(keyword_list, ("synthetic motor oil", "motor oil", "engine oil")):
        return "Motor oil container"

    if "spray paint" in keyword_list:
        return "Paint can"
    if "paint" in keyword_list and "can" in keyword_list:
        return "Paint can"

    if "aerosol" in keyword_list:
        return "Aerosol can"
    if "spray" in keyword_list and "can" in keyword_list:
        return "Aerosol can"

    if "battery" in keyword_list:
        return "Battery"

    battery_context_keywords = ("alkaline", "rechargeable", "lithium", "duracell", "energizer")
    battery_size_keywords = ("aa", "aaa")
    if (
        _has_any_keyword(keyword_list, battery_context_keywords)
        and _has_any_keyword(keyword_list, battery_size_keywords)
    ):
        return "Battery"

    return None


def extract_ocr_text(image_bytes: bytes) -> dict[str, Any]:
    try:
        pytesseract_module = _load_pytesseract()
        if pytesseract_module is None:
            return _empty_ocr_payload()

        _configure_tesseract_cmd(pytesseract_module)
        if not _is_tesseract_available(pytesseract_module):
            return _empty_ocr_payload()

        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized_image = ImageOps.exif_transpose(image).convert("RGB")

        collected_segments = _collect_text_segments(pytesseract_module, normalized_image)
        combined_text = _dedupe_text_segments(collected_segments)
        keywords = extract_matched_keywords(combined_text)
        matched_label = match_keyword_label(keywords)

        logger.info(
            "OCR result. text_length=%s keywords=%s matched_label=%s preview=%s",
            len(combined_text),
            keywords,
            matched_label,
            combined_text[:120],
        )

        return {
            "text": combined_text,
            "keywords": keywords,
            "matched_label": matched_label,
        }
    except (Exception, SystemExit) as exc:
        logger.warning("OCR extraction failed safely: %s", exc)
        return _empty_ocr_payload()
