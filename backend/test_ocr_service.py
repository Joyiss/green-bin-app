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


def _fake_pytesseract_with_outputs(*outputs: str):
    output_iter = iter(outputs)

    def image_to_string(image, config=None):
        return next(output_iter)

    return SimpleNamespace(
        image_to_string=image_to_string,
        get_tesseract_version=lambda: "5.0.0",
        pytesseract=SimpleNamespace(tesseract_cmd="tesseract"),
    )


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

    def test_strong_battery_text_maps_to_battery(self):
        fake_runtime = _fake_pytesseract_with_outputs(
            "Duracell alkaline battery",
            "AA rechargeable pack",
        )

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["matched_label"], "Battery")
        self.assertIn("battery", result["keywords"])
        self.assertIn("duracell", result["keywords"])

    def test_aa_alone_does_not_map_to_battery(self):
        fake_runtime = _fake_pytesseract_with_outputs("AA", "")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["keywords"], ["aa"])
        self.assertIsNone(result["matched_label"])

    def test_shampoo_and_conditioner_text_maps_to_shampoo_bottle(self):
        fake_runtime = _fake_pytesseract_with_outputs("Conditioner", "Shampoo")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["matched_label"], "Shampoo bottle")

    def test_detergent_text_maps_to_detergent_bottle(self):
        fake_runtime = _fake_pytesseract_with_outputs("Laundry detergent", "")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["matched_label"], "Detergent bottle")

    def test_motor_oil_text_maps_to_motor_oil_container(self):
        fake_runtime = _fake_pytesseract_with_outputs("Synthetic motor oil", "")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["matched_label"], "Motor oil container")

    def test_oil_alone_does_not_map(self):
        fake_runtime = _fake_pytesseract_with_outputs("Oil", "")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertIn("oil", result["keywords"])
        self.assertIsNone(result["matched_label"])

    def test_paint_text_maps_to_paint_can(self):
        fake_runtime = _fake_pytesseract_with_outputs("Spray paint", "")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["matched_label"], "Paint can")

    def test_aerosol_text_maps_to_aerosol_can(self):
        fake_runtime = _fake_pytesseract_with_outputs("Aerosol can", "")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["matched_label"], "Aerosol can")

    def test_spray_alone_does_not_map(self):
        fake_runtime = _fake_pytesseract_with_outputs("spray", "")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertIn("spray", result["keywords"])
        self.assertIsNone(result["matched_label"])

    def test_generic_package_words_return_keywords_but_no_label(self):
        fake_runtime = _fake_pytesseract_with_outputs(
            "Purified drinking water plastic bottle",
            "",
        )

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(
            result["keywords"],
            ["water", "drinking", "purified", "plastic", "bottle"],
        )
        self.assertIsNone(result["matched_label"])

    def test_brand_names_alone_return_text_but_no_label(self):
        fake_runtime = _fake_pytesseract_with_outputs("Coca Cola", "Pepsi")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["text"], "coca cola pepsi")
        self.assertEqual(result["keywords"], [])
        self.assertIsNone(result["matched_label"])

    def test_unrelated_random_text_returns_no_matched_label(self):
        fake_runtime = _fake_pytesseract_with_outputs("ZXQ random token", "hello world")

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["keywords"], [])
        self.assertIsNone(result["matched_label"])

    def test_combined_variants_are_lowercased_deduped_and_truncated(self):
        repeated_text = "Battery Label"
        long_text = "Long Text " * 120
        fake_runtime = _fake_pytesseract_with_outputs(repeated_text, repeated_text)

        with patch("services.ocr_service._load_pytesseract", return_value=fake_runtime):
            result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(result["text"], result["text"].lower())
        self.assertEqual(result["text"], "battery label")

        truncating_runtime = _fake_pytesseract_with_outputs(long_text, "")
        with patch("services.ocr_service._load_pytesseract", return_value=truncating_runtime):
            truncated_result = ocr_service.extract_ocr_text(_make_image_bytes())

        self.assertEqual(truncated_result["text"], truncated_result["text"].lower())
        self.assertTrue(truncated_result["text"].startswith("long text"))
        self.assertLessEqual(len(truncated_result["text"]), 500)


if __name__ == "__main__":
    unittest.main()
