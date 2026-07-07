from __future__ import annotations

import io
import logging

import imagehash
from PIL import Image, ImageOps


logger = logging.getLogger(__name__)

PHASH_THRESHOLD = 6


def create_phash(image_bytes: bytes) -> str:
    with Image.open(io.BytesIO(image_bytes)) as image:
        normalized_image = ImageOps.exif_transpose(image).convert("RGB")
        return str(imagehash.phash(normalized_image))


def phash_distance(hash_a: str, hash_b: str) -> int:
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def warmup_phash() -> bool:
    """Run the production hash path once so dependency cold work happens at startup."""
    try:
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), color="black").save(buffer, format="PNG")
        create_phash(buffer.getvalue())
        logger.info("pHash startup warmup completed.")
        return True
    except Exception as exc:
        logger.warning("pHash startup warmup failed safely: %s", exc)
        return False
