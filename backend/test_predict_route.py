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
        ), patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=None,
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
                "summary": "Calculator is categorized as electronics and should be handled through e-waste recycling guidance in your area.",
                "steps": [
                    "Do not place electronics in household trash.",
                    "Wipe any personal data before disposal.",
                    "Take the item to an e-waste center or retailer drop-off.",
                ],
                "guidance_source": "legacy_rules_fallback",
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
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ),
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
        ), patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
        ), patch(
            "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
            return_value={"guidance": None, "failure_reason": "llm_disabled"},
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
                "summary": "Trusted disposal guidance is not available yet for this recognized item.",
                "steps": [
                    "Detected material category: Metal.",
                    "Use local guidance or scan a supported item for trusted disposal instructions.",
                ],
                "guidance_source": "safe_fallback",
                "cache_hit": False,
                "recognition_source": "vlm_open",
            },
        )

    def test_predict_low_risk_open_item_can_use_deterministic_low_risk_fallback(self):
        client = TestClient(app)
        classification = {
            "item": "Pencil",
            "category": "Mixed Material",
            "status": "confident",
            "candidates": [],
            "cache_hit": False,
            "recognition_source": "vlm_open",
            "trusted_guidance_available": False,
            "recognized_material_category": "Mixed Material",
            "recognized_broad_category": "Household item",
            "recognition_details": {
                "status": "confident",
                "raw_item_label": "pencil",
                "likely_material": "mixed material",
                "broad_category": "household item",
                "normalized": {
                    "item_label": "Pencil",
                    "material_category": "Mixed Material",
                    "broad_category": "Household item",
                    "condition_flags": [],
                    "special_handling_flags": [],
                    "matched_supported_label": None,
                },
            },
        }

        with patch(
            "routes.predict.recognize_item",
            AsyncMock(return_value=classification),
        ), patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
        ), patch(
            "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
            return_value={"guidance": None, "failure_reason": "missing_summary"},
        ):
            response = client.post(
                "/predict",
                files={"file": ("photo.jpg", _make_image_bytes(), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["guidance_source"], "llm_general_fallback")
        self.assertEqual(response.json()["disposal_action"], "check local guidance")
        self.assertIn("pencil", response.json()["summary"].lower())
        self.assertEqual(
            response.json()["guidance_metadata"]["llm_fallback_reason"],
            "missing_summary",
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
        ), patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
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
                "summary": "Charging Cable is categorized as electronics and should be handled through e-waste recycling guidance in your area.",
                "steps": [
                    "Do not place electronics in household trash.",
                    "Wipe any personal data before disposal.",
                    "Take the item to an e-waste center or retailer drop-off.",
                ],
                "guidance_source": "legacy_rules_fallback",
                "cache_hit": False,
                "recognition_source": "vlm_open",
            },
        )

    def test_predict_open_high_risk_item_without_chunks_stays_non_prescriptive(self):
        client = TestClient(app)
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
            "cache_hit": False,
            "recognition_source": "vlm_open",
            "trusted_guidance_available": False,
            "recognized_material_category": "Battery",
            "recognized_broad_category": "Batteries",
            "recognition_details": {
                "status": "confident",
                "raw_item_label": "battery",
                "likely_material": "battery",
                "broad_category": "batteries",
                "candidates": [{"label": "battery", "confidence": 0.96}],
                "visual_evidence": "Cylindrical battery visible.",
                "normalized": {
                    "item_label": "Battery",
                    "material_category": "Battery",
                    "broad_category": "Batteries",
                    "condition_flags": ["requires_dropoff", "hazardous"],
                    "special_handling_flags": ["battery", "dropoff_recommended"],
                    "matched_supported_label": None,
                    "normalization_source": "keyword_rule",
                },
            },
        }

        with patch(
            "routes.predict.recognize_item",
            AsyncMock(return_value=classification),
        ), patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
        ):
            response = client.post(
                "/predict",
                files={"file": ("photo.jpg", _make_image_bytes(), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["guidance_source"], "safe_fallback")
        self.assertIsNone(response.json()["disposal_action"])
        self.assertEqual(
            response.json()["summary"],
            "Trusted disposal guidance is not available yet for this recognized item.",
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
                "summary": None,
                "steps": [],
                "guidance_source": "safe_fallback",
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
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ),
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
                "summary": "Calculator is categorized as electronics and should be handled through e-waste recycling guidance in your area.",
                "steps": [
                    "Do not place electronics in household trash.",
                    "Wipe any personal data before disposal.",
                    "Take the item to an e-waste center or retailer drop-off.",
                ],
                "guidance_source": "legacy_rules_fallback",
                "cache_hit": True,
                "recognition_source": "phash_cache",
            },
        )
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_predict_can_return_direct_json_guidance_with_metadata(self):
        client = TestClient(app)
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
            "cache_hit": False,
            "recognition_source": "vlm",
        }
        retrieval_result = {
            "chunk": {
                "id": "battery-guidance",
                "title": "Battery Drop-off Guidance",
                "source_name": "Call2Recycle",
                "source_url": "https://www.call2recycle.org/",
                "requires_location_check": True,
                "disposal_actions_supported": ["Drop-off"],
                "warnings": ["Do not place rechargeable batteries in curbside recycling."],
                "limitations": ["Program availability varies by location."],
                "content": "Rechargeable batteries should go to a designated battery drop-off program. Tape exposed terminals before transport.",
            },
            "chunk_id": "battery-guidance",
            "score": 8.25,
            "matched_fields": ["item_label_exact"],
            "requires_location_check": True,
        }

        with patch(
            "routes.predict.recognize_item",
            AsyncMock(return_value=classification),
        ), patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[retrieval_result],
        ), patch(
            "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
            return_value={"guidance": None, "failure_reason": "llm_disabled"},
        ):
            response = client.post(
                "/predict",
                files={"file": ("photo.jpg", _make_image_bytes(), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["guidance_source"], "json_rag_direct_generated")
        self.assertEqual(response.json()["disposal_action"], "drop-off")
        self.assertIn("guidance_metadata", response.json())
        self.assertEqual(
            response.json()["guidance_metadata"]["retrieved_chunk_ids"],
            ["battery-guidance"],
        )
        self.assertEqual(
            response.json()["warnings"],
            ["Do not place rechargeable batteries in curbside recycling."],
        )

    def test_predict_open_battery_without_gemini_uses_json_guidance(self):
        client = TestClient(app)
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
            "cache_hit": False,
            "recognition_source": "vlm_open",
            "trusted_guidance_available": False,
            "recognized_material_category": "Battery",
            "recognized_broad_category": "Electronics",
            "recognition_details": {
                "status": "confident",
                "raw_item_label": "battery",
                "likely_material": "battery",
                "broad_category": "electronics",
                "candidates": [{"label": "battery", "confidence": 0.96}],
                "visual_evidence": "Battery silhouette visible.",
                "normalized": {
                    "item_label": "Battery",
                    "material_category": "Battery",
                    "broad_category": "Electronics",
                    "condition_flags": [],
                    "special_handling_flags": ["battery", "dropoff_recommended"],
                    "matched_supported_label": None,
                    "normalization_source": "keyword_rule",
                },
            },
        }

        with patch(
            "routes.predict.recognize_item",
            AsyncMock(return_value=classification),
        ), patch(
            "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
            return_value={"guidance": None, "failure_reason": "ENABLE_LLM_GUIDANCE_false"},
        ):
            response = client.post(
                "/predict",
                files={"file": ("photo.jpg", _make_image_bytes(), "image/jpeg")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["guidance_source"], "json_rag_direct_generated")
        self.assertEqual(response.json()["disposal_action"], "drop-off")
        self.assertIn(
            "call2recycle_national_batteries",
            response.json()["guidance_metadata"]["retrieved_chunk_ids"],
        )


if __name__ == "__main__":
    unittest.main()
