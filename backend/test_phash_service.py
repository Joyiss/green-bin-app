import unittest
import io
from pathlib import Path

from PIL import Image, ImageDraw

from services.phash_service import PHASH_THRESHOLD, create_phash, phash_distance


FIXTURE_DIR = (
    Path(__file__).resolve().parent
    / "experiments"
    / "semantic-cache"
    / "images"
    / "phash_test"
)


def _fixture_bytes(filename: str) -> bytes:
    return (FIXTURE_DIR / filename).read_bytes()


def _make_rotated_exif_duplicate_bytes() -> tuple[bytes, bytes]:
    base_image = Image.new("RGB", (80, 50), color="white")
    draw = ImageDraw.Draw(base_image)
    draw.rectangle((5, 5, 30, 40), fill="black")
    draw.rectangle((45, 10, 70, 20), fill="red")
    draw.rectangle((55, 30, 75, 45), fill="blue")

    original_buffer = io.BytesIO()
    base_image.save(original_buffer, format="JPEG")

    rotated_image = base_image.transpose(Image.Transpose.ROTATE_90)
    rotated_exif = Image.Exif()
    rotated_exif[274] = 6

    rotated_buffer = io.BytesIO()
    rotated_image.save(rotated_buffer, format="JPEG", exif=rotated_exif)

    return original_buffer.getvalue(), rotated_buffer.getvalue()


class PHashServiceTests(unittest.TestCase):
    def test_create_phash_returns_stable_hex_string(self):
        image_bytes = _fixture_bytes("org_calculator.jpg")

        first_hash = create_phash(image_bytes)
        second_hash = create_phash(image_bytes)

        self.assertEqual(first_hash, second_hash)
        self.assertEqual(len(first_hash), 16)
        int(first_hash, 16)

    def test_create_phash_handles_exif_rotated_duplicate(self):
        original_bytes, rotated_bytes = _make_rotated_exif_duplicate_bytes()
        original_hash = create_phash(original_bytes)
        rotated_hash = create_phash(rotated_bytes)

        self.assertLessEqual(
            phash_distance(original_hash, rotated_hash),
            PHASH_THRESHOLD,
        )

    def test_phash_distance_is_symmetric_for_known_pairs(self):
        original_hash = create_phash(_fixture_bytes("org_calculator.jpg"))
        copy_hash = create_phash(_fixture_bytes("copy_calculator.jpg"))
        remote_hash = create_phash(_fixture_bytes("remote.jpg"))

        close_distance = phash_distance(original_hash, copy_hash)
        reverse_close_distance = phash_distance(copy_hash, original_hash)
        far_distance = phash_distance(original_hash, remote_hash)

        self.assertEqual(close_distance, reverse_close_distance)
        self.assertLessEqual(close_distance, PHASH_THRESHOLD)
        self.assertGreater(far_distance, PHASH_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
