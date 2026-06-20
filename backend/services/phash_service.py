from __future__ import annotations

import io

import imagehash
from PIL import Image, ImageOps


PHASH_THRESHOLD = 6


def create_phash(image_bytes: bytes) -> str:
    with Image.open(io.BytesIO(image_bytes)) as image:
        normalized_image = ImageOps.exif_transpose(image).convert("RGB")
        return str(imagehash.phash(normalized_image))


def phash_distance(hash_a: str, hash_b: str) -> int:
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)
