from __future__ import annotations

import argparse
import io
import os
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageOps


BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.ocr_service import clean_ocr_text, extract_matched_keywords, match_keyword_label


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare pytesseract and EasyOCR on a local image.",
    )
    parser.add_argument("image_path", help="Path to the image file to inspect.")
    parser.add_argument(
        "--provider",
        choices=("tesseract", "easyocr", "both"),
        default="both",
        help="Which OCR provider(s) to run. Default: both.",
    )
    return parser.parse_args()


def _load_image_bytes(image_path: Path) -> bytes:
    return image_path.read_bytes()


def _open_rgb_image(image_bytes: bytes) -> Image.Image:
    with Image.open(io.BytesIO(image_bytes)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _resize_max_dimension(image: Image.Image, max_dimension: int) -> Image.Image:
    resized_image = image.copy()
    resized_image.thumbnail((max_dimension, max_dimension))
    return resized_image


def _threshold_image(image: Image.Image, threshold: int = 170) -> Image.Image:
    grayscale_image = image.convert("L")
    return grayscale_image.point(lambda pixel: 255 if pixel >= threshold else 0, mode="1")


def _build_tesseract_variants(image: Image.Image) -> list[tuple[str, Image.Image]]:
    rgb_resized_1280 = _resize_max_dimension(image, 1280)
    grayscale_resized_1280 = rgb_resized_1280.convert("L")
    high_contrast_grayscale = ImageEnhance.Contrast(grayscale_resized_1280).enhance(2.5)
    thresholded_image = _threshold_image(grayscale_resized_1280)

    return [
        ("rgb_resized_1280", rgb_resized_1280),
        ("grayscale_resized_1280", grayscale_resized_1280),
        ("high_contrast_grayscale", high_contrast_grayscale),
        ("thresholded_black_white", thresholded_image),
    ]


def _build_easyocr_variants(image: Image.Image) -> list[tuple[str, Image.Image]]:
    return [
        ("resized_1280", _resize_max_dimension(image, 1280)),
        ("resized_1024", _resize_max_dimension(image, 1024)),
    ]


def _text_preview(text: str, limit: int = 160) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _configure_tesseract_cmd(pytesseract_module: Any) -> None:
    env_path = os.getenv("TESSERACT_CMD")
    default_windows_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

    if env_path and Path(env_path).is_file():
        pytesseract_module.pytesseract.tesseract_cmd = env_path
        return

    if default_windows_path.is_file():
        pytesseract_module.pytesseract.tesseract_cmd = str(default_windows_path)


def _print_image_info(image_bytes: bytes) -> None:
    with Image.open(io.BytesIO(image_bytes)) as image:
        normalized_image = ImageOps.exif_transpose(image)
        print("Image info:")
        print(f"  original_size: {image.size}")
        print(f"  original_mode: {image.mode}")
        print(f"  normalized_size: {normalized_image.size}")
        print(f"  normalized_mode: {normalized_image.mode}")


def _analyze_text(text: str) -> tuple[str, list[str], str | None]:
    cleaned_text = clean_ocr_text(text)
    keywords = extract_matched_keywords(cleaned_text)
    matched_label = match_keyword_label(keywords)
    return cleaned_text, keywords, matched_label


def _print_text_analysis(text: str) -> None:
    cleaned_text, keywords, matched_label = _analyze_text(text)
    print(f"    text_preview: {_text_preview(cleaned_text)!r}")
    print(f"    keywords: {keywords}")
    print(f"    matched_label: {matched_label}")


def _run_tesseract_variant(
    pytesseract_module: Any,
    image: Image.Image,
    *,
    variant_name: str,
    config: str,
) -> None:
    started_at = time.perf_counter()
    try:
        raw_text = pytesseract_module.image_to_string(image, config=config)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"  variant: {variant_name}")
        print(f"    config: {config}")
        print(f"    ocr_ok: False ({exc})")
        print(f"    elapsed_ms: {elapsed_ms:.1f}")
        return

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    print(f"  variant: {variant_name}")
    print(f"    config: {config}")
    print(f"    elapsed_ms: {elapsed_ms:.1f}")
    _print_text_analysis(raw_text)


def _try_pytesseract(image_bytes: bytes) -> None:
    print("\npytesseract:")

    try:
        import pytesseract
    except Exception as exc:
        print(f"  import_ok: False ({exc})")
        return

    print("  import_ok: True")

    _configure_tesseract_cmd(pytesseract)
    print(f"  tesseract_cmd: {pytesseract.pytesseract.tesseract_cmd}")

    try:
        version = pytesseract.get_tesseract_version()
    except Exception as exc:
        print("  runtime_available: False")
        print(f"  tesseract_message: Tesseract is missing or not available on PATH ({exc})")
        return

    print("  runtime_available: True")
    print(f"  tesseract_version: {version}")

    try:
        rgb_image = _open_rgb_image(image_bytes)
        variants = _build_tesseract_variants(rgb_image)
    except Exception as exc:
        print(f"  variant_prep_ok: False ({exc})")
        return

    configs = [
        "--oem 3 --psm 6",
        "--oem 3 --psm 11",
    ]

    for variant_name, variant_image in variants:
        for config in configs:
            _run_tesseract_variant(
                pytesseract,
                variant_image,
                variant_name=variant_name,
                config=config,
            )


def _run_easyocr_variant(reader: Any, image: Image.Image) -> tuple[float, str] | tuple[float, None]:
    started_at = time.perf_counter()
    import numpy as np

    lines = reader.readtext(np.array(image), detail=0)
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    raw_text = " ".join(str(line) for line in lines if str(line).strip())
    return elapsed_ms, raw_text


def _print_easyocr_run(name: str, elapsed_ms: float, text: str) -> None:
    print(f"  {name}_elapsed_ms: {elapsed_ms:.1f}")
    _print_text_analysis(text)


def _try_easyocr(image_bytes: bytes) -> None:
    print("\nEasyOCR:")
    print("  note: EasyOCR may download model weights the first time it runs.")

    try:
        import easyocr
    except Exception as exc:
        print(f"  import_ok: False ({exc})")
        return

    print("  import_ok: True")

    reader_started_at = time.perf_counter()
    try:
        reader = easyocr.Reader(["en"], gpu=False)
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - reader_started_at) * 1000
        print(f"  reader_init_ok: False ({exc})")
        print(f"  reader_init_ms: {elapsed_ms:.1f}")
        return

    reader_init_ms = (time.perf_counter() - reader_started_at) * 1000
    print(f"  reader_init_ms: {reader_init_ms:.1f}")

    try:
        rgb_image = _open_rgb_image(image_bytes)
        variants = _build_easyocr_variants(rgb_image)
    except Exception as exc:
        print(f"  variant_prep_ok: False ({exc})")
        return

    for variant_name, variant_image in variants:
        print(f"  variant: {variant_name}")
        try:
            first_run_elapsed_ms, first_run_text = _run_easyocr_variant(reader, variant_image)
            print(f"    first_run_elapsed_ms: {first_run_elapsed_ms:.1f}")
            cleaned_text, keywords, matched_label = _analyze_text(first_run_text)
            print(f"    text_preview: {_text_preview(cleaned_text)!r}")
            print(f"    keywords: {keywords}")
            print(f"    matched_label: {matched_label}")

            second_run_elapsed_ms, second_run_text = _run_easyocr_variant(reader, variant_image)
            print(f"    second_run_elapsed_ms: {second_run_elapsed_ms:.1f}")
            cleaned_text, keywords, matched_label = _analyze_text(second_run_text)
            print(f"    second_text_preview: {_text_preview(cleaned_text)!r}")
            print(f"    second_keywords: {keywords}")
            print(f"    second_matched_label: {matched_label}")
        except Exception as exc:
            print(f"    ocr_ok: False ({exc})")


def main() -> int:
    args = _parse_args()
    image_path = Path(args.image_path).expanduser().resolve()

    if not image_path.is_file():
        print(f"Image not found: {image_path}")
        return 1

    print(f"Image path: {image_path}")
    image_bytes = _load_image_bytes(image_path)
    print(f"Image bytes: {len(image_bytes)}")

    try:
        _print_image_info(image_bytes)
    except Exception as exc:
        print(f"Failed to open image with PIL: {exc}")
        return 1

    if args.provider in {"tesseract", "both"}:
        _try_pytesseract(image_bytes)

    if args.provider in {"easyocr", "both"}:
        _try_easyocr(image_bytes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
