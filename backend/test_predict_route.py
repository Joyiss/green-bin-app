import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from main import app


def _make_image_bytes() -> bytes:
    image = Image.new("RGB", (24, 24), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class PredictRouteTests(unittest.TestCase):
    def test_predict_preserves_existing_shape_and_includes_cache_metadata(self):
        client = TestClient(app)
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.98)],
            "cache_hit": True,
            "recognition_source": "phash_cache",
        }

        with patch(
            "routes.predict.recognize_item",
            AsyncMock(return_value=classification),
        ):
            response = client.post(
                "/predict",
                files={"file": ("photo.jpg", _make_image_bytes(), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "item": "Calculator",
                "category": "Electronics",
                "status": "confident",
                "candidates": [{"label": "Calculator", "score": 0.98}],
                "disposal_action": "e-waste recycling",
                "material_code": None,
                "impact_level": "High Impact",
                "steps": [
                    "Do not place electronics in household trash.",
                    "Wipe any personal data before disposal.",
                    "Take the item to an e-waste center or retailer drop-off.",
                ],
                "cache_hit": True,
                "recognition_source": "phash_cache",
            },
        )

    def test_predict_accepts_real_multipart_uploads_through_recognition_flow(self):
        client = TestClient(app)

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.98)], "margin": 0.98},
            ),
            patch(
                "services.recognition_router.classify",
                return_value={
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [("Calculator", 0.98)],
                },
            ),
            patch("services.recognition_router.cache_repository.save_recognition_record"),
        ):
            response = client.post(
                "/predict",
                files={"file": ("photo.jpg", _make_image_bytes(), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"], "Calculator")
        self.assertEqual(response.json()["recognition_source"], "vlm")
        self.assertFalse(response.json()["cache_hit"])


if __name__ == "__main__":
    unittest.main()
