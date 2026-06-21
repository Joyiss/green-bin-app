from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.barcode_service import detect_barcode
from services.ocr_service import extract_ocr_text


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug barcode and OCR services against a local image.",
    )
    parser.add_argument("image_path", help="Path to the image file to inspect.")
    return parser.parse_args()


def _load_image_bytes(image_path: Path) -> bytes:
    return image_path.read_bytes()


def _print_image_info(image_bytes: bytes) -> None:
    with Image.open(io.BytesIO(image_bytes)) as image:
        print("Image info:")
        print(f"  original_size: {image.size}")
        print(f"  original_mode: {image.mode}")

        normalized_image = ImageOps.exif_transpose(image)
        print(f"  normalized_size: {normalized_image.size}")
        print(f"  normalized_mode: {normalized_image.mode}")


def _debug_zxingcpp() -> None:
    print("\nzxingcpp:")
    try:
        import zxingcpp
    except Exception as exc:
        print(f"  import_ok: False ({exc})")
        return

    print("  import_ok: True")
    matching_names = sorted(
        name
        for name in dir(zxingcpp)
        if "barcode" in name.lower() or "read" in name.lower()
    )
    print(f"  matching_functions: {matching_names}")


def _debug_pytesseract() -> None:
    print("\npytesseract:")
    try:
        import pytesseract
    except Exception as exc:
        print(f"  import_ok: False ({exc})")
        return

    print("  import_ok: True")
    try:
        version = pytesseract.get_tesseract_version()
    except Exception as exc:
        print(f"  tesseract_version: unavailable ({exc})")
        print("  tesseract_message: Tesseract appears to be missing or not available on PATH.")
        return

    print(f"  tesseract_version: {version}")


def _print_service_result(label: str, result: Any) -> None:
    print(f"\n{label}:")
    print(f"  {result!r}")


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

    _debug_zxingcpp()
    _debug_pytesseract()

    barcode_result = detect_barcode(image_bytes)
    ocr_result = extract_ocr_text(image_bytes)

    _print_service_result("detect_barcode(image_bytes)", barcode_result)
    _print_service_result("extract_ocr_text(image_bytes)", ocr_result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
