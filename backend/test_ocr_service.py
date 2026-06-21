import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from services import ocr_service


def _make_image_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class OcrServiceTests(unittest.TestCase):
    def test_extract_ocr_text_returns_empty_payload_when_runtime_is_unavailable(self):
        with patch("services.ocr_service._load_pytesseract", return_value=None):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(
            result,
            {
                "text": "",
                "keywords": [],
                "matched_label": None,
            },
        )

    def test_extract_ocr_text_cleans_text_and_matches_keywords(self):
        fake_runtime = SimpleNamespace(
            image_to_string=lambda image: " Duracell \nAA \nPack "
        )

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(
            result,
            {
                "text": "Duracell AA Pack",
                "keywords": ["aa", "duracell"],
                "matched_label": "Battery",
            },
        )


if __name__ == "__main__":
    unittest.main()
