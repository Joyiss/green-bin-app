import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from services import barcode_service


def _make_image_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class BarcodeServiceTests(unittest.TestCase):
    def test_detect_barcode_returns_none_when_runtime_is_unavailable(self):
        with patch("services.barcode_service._load_zxingcpp", return_value=None):
            result = barcode_service.detect_barcode(_make_image_bytes())

        self.assertIsNone(result)

    def test_detect_barcode_returns_value_and_type(self):
        fake_runtime = SimpleNamespace(
            read_barcodes=lambda image: [
                SimpleNamespace(
                    text="012345678905",
                    format=SimpleNamespace(name="EAN_13"),
                )
            ]
        )

        with patch("services.barcode_service._load_zxingcpp", return_value=fake_runtime):
            result = barcode_service.detect_barcode(_make_image_bytes())

        self.assertEqual(
            result,
            {
                "barcode_value": "012345678905",
                "barcode_type": "EAN_13",
            },
        )

    def test_match_known_barcode_returns_local_mapping(self):
        self.assertEqual(
            barcode_service.match_known_barcode("9780399578694"),
            {
                "item_label": "Book",
                "confidence": 1.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
