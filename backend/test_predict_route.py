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
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=[0.1, 0.2],
            ),
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                return_value=[],
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

    def test_predict_open_water_bottle_without_supported_match_is_not_unidentified(self):
        client = TestClient(app)
        classification = {
            "item": "Water bottle",
            "category": "Metal",
            "status": "confident",
            "candidates": [],
            "cache_hit": False,
            "recognition_source": "vlm_open",
            "trusted_guidance_available": False,
            "recognized_material_category": "Metal",
            "recognized_broad_category": "Drinkware",
            "recognition_details": {
                "status": "confident",
                "raw_item_label": "water bottle",
                "likely_material": "metal",
                "broad_category": "drinkware",
                "candidates": [{"label": "water bottle", "confidence": 0.94}],
                "visual_evidence": "Bottle silhouette and narrow opening visible.",
                "disposal_action": "trash",
                "steps": ["do not trust this"],
                "normalized": {
                    "item_label": "Water bottle",
                    "material_category": "Metal",
                    "broad_category": "Drinkware",
                    "condition_flags": [],
                    "special_handling_flags": [],
                    "matched_supported_label": None,
                    "normalization_source": "keyword_rule",
                },
            },
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
                "item": "Water Bottle",
                "category": "Metal",
                "status": "confident",
                "candidates": [],
                "disposal_action": None,
                "material_code": None,
                "impact_level": "Trusted Guidance Unavailable",
                "steps": [
                    "Trusted disposal guidance is not available yet for this recognized item.",
                    "Detected material category: Metal.",
                    "Use local guidance or scan a supported item for trusted disposal instructions.",
                ],
                "cache_hit": False,
                "recognition_source": "vlm_open",
            },
        )

    def test_predict_open_supported_match_can_use_existing_trusted_guidance(self):
        client = TestClient(app)
        classification = {
            "item": "Charging cable",
            "category": "Electronics",
            "status": "confident",
            "candidates": [],
            "cache_hit": False,
            "recognition_source": "vlm_open",
            "trusted_guidance_available": True,
            "trusted_guidance_label": "Cable",
            "recognized_material_category": "Electronics",
            "recognized_broad_category": "Electronics",
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
                "item": "Charging Cable",
                "category": "Electronics",
                "status": "confident",
                "candidates": [],
                "disposal_action": "e-waste recycling",
                "material_code": None,
                "impact_level": "High Impact",
                "steps": [
                    "Do not place electronics in household trash.",
                    "Wipe any personal data before disposal.",
                    "Take the item to an e-waste center or retailer drop-off.",
                ],
                "cache_hit": False,
                "recognition_source": "vlm_open",
            },
        )

    def test_predict_unknown_open_result_stays_safe(self):
        client = TestClient(app)
        classification = {
            "item": "",
            "category": "Unknown",
            "status": "unknown",
            "candidates": [],
            "cache_hit": False,
            "recognition_source": "vlm_open",
            "trusted_guidance_available": False,
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
                "item": "",
                "category": "Unknown",
                "status": "unknown",
                "candidates": [],
                "disposal_action": None,
                "material_code": None,
                "impact_level": None,
                "steps": [],
                "cache_hit": False,
                "recognition_source": "vlm_open",
            },
        )

    def test_predict_near_phash_cache_hit_matches_exact_cache_response_shape(self):
        client = TestClient(app)
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 4,
            "metadata": (
                "{\"classification\": {\"item\": \"Calculator\", \"category\": \"Electronics\", "
                "\"status\": \"confident\", \"candidates\": [[\"Calculator\", 0.98]]}}"
            ),
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
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
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
