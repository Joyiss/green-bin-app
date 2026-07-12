import io
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from PIL import Image

from main import app
from routes.predict import predict as predict_route
from services.scan_rate_limit_service import (
    DailyScanLimitReachedError,
    ScanRateLimitMetadata,
)


def _make_image_bytes() -> bytes:
    image = Image.new("RGB", (24, 24), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class PredictRouteTests(unittest.TestCase):
    def setUp(self):
        self.clip_ready_patch = patch(
            "services.recognition_router.clip_service.is_clip_initialized",
            return_value=True,
        )
        self.clip_ready_patch.start()
        self.addCleanup(self.clip_ready_patch.stop)
        self.feedback_storage_patch = patch(
            "routes.predict.feedback_context_service.store_prediction_context",
            return_value=True,
        )
        self.feedback_storage_patch.start()
        self.addCleanup(self.feedback_storage_patch.stop)

    def test_predict_allows_missing_client_id_when_not_required(self):
        client = TestClient(app)

        with (
            patch.dict("os.environ", {"REQUIRE_SCAN_CLIENT_ID": "false"}, clear=False),
            patch("routes.predict.recognize_item", AsyncMock()) as mock_recognize,
            patch("routes.predict.build_prediction_response", return_value={"item": "Calculator"}),
        ):
            mock_recognize.return_value = {
                "item": "Calculator",
                "category": "Electronics",
                "status": "confident",
                "candidates": [],
            }
            response = client.post("/predict", data={"selected_item": "Calculator"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.pop("request_id").startswith("predict-"))
        self.assertEqual(payload, {"item": "Calculator"})
        mock_recognize.assert_called_once()

    def test_predict_requires_client_id_when_configured(self):
        client = TestClient(app)

        with (
            patch.dict("os.environ", {"REQUIRE_SCAN_CLIENT_ID": "true"}, clear=False),
            patch("routes.predict.recognize_item", AsyncMock()) as mock_recognize,
        ):
            response = client.post("/predict", data={"selected_item": "Calculator"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "scan_client_id_required"})
        mock_recognize.assert_not_called()

    def test_predict_invalid_request_does_not_consume_daily_scan(self):
        client = TestClient(app)

        with patch("routes.predict.scan_rate_limit_service.consume_daily_scan") as mock_consume:
            response = client.post("/predict")

        self.assertEqual(response.status_code, 400)
        mock_consume.assert_not_called()

    def test_predict_success_includes_scan_limit_metadata_when_available(self):
        client = TestClient(app)
        metadata = ScanRateLimitMetadata(
            daily_limit=40,
            scans_remaining=39,
            reset_at="2026-07-10T00:00:00Z",
        )

        with (
            patch("routes.predict.scan_rate_limit_service.consume_daily_scan", return_value=metadata),
            patch(
                "routes.predict.recognize_item",
                AsyncMock(
                    return_value={
                        "item": "Calculator",
                        "category": "Electronics",
                        "status": "confident",
                        "candidates": [],
                    }
                ),
            ),
            patch("routes.predict.build_prediction_response", return_value={"item": "Calculator"}),
        ):
            response = client.post(
                "/predict",
                data={"selected_item": "Calculator"},
                headers={"X-GreenBin-Client-Id": "install-123"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.pop("request_id").startswith("predict-"))
        self.assertEqual(
            payload,
            {
                "item": "Calculator",
                "daily_limit": 40,
                "scans_remaining": 39,
                "reset_at": "2026-07-10T00:00:00Z",
            },
        )

    def test_predict_rate_limit_reached_returns_429_before_recognition(self):
        client = TestClient(app)
        metadata = ScanRateLimitMetadata(
            daily_limit=40,
            scans_remaining=0,
            reset_at="2026-07-10T00:00:00Z",
        )

        with (
            patch(
                "routes.predict.scan_rate_limit_service.consume_daily_scan",
                side_effect=DailyScanLimitReachedError(metadata),
            ),
            patch("routes.predict.recognize_item", AsyncMock()) as mock_recognize,
        ):
            response = client.post(
                "/predict",
                data={"selected_item": "Calculator"},
                headers={"X-GreenBin-Client-Id": "install-123"},
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response.json(),
            {
                "error": "daily_scan_limit_reached",
                "daily_limit": 40,
                "scans_remaining": 0,
                "reset_at": "2026-07-10T00:00:00Z",
            },
        )
        mock_recognize.assert_not_called()

    def test_predict_logs_guidance_and_total_timing(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.98)],
        }
        response = {"item": "Calculator"}
        with (
            patch("routes.predict.recognize_item", AsyncMock(return_value=classification)),
            patch("routes.predict.build_prediction_response", return_value=response),
            self.assertLogs("routes.predict", level="INFO") as logs,
        ):
            result = asyncio.run(predict_route(file=None, selected_item="Calculator"))

        self.assertEqual(result, response)
        combined = "\n".join(logs.output)
        self.assertIn("stage=guidance", combined)
        self.assertIn("stage=total", combined)

    def test_predict_returns_request_id_and_stores_trusted_original_context(self):
        client = TestClient(app)
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [],
            "recognition_source": "vlm",
        }
        with (
            patch(
                "routes.predict.recognize_item",
                AsyncMock(return_value=classification),
            ),
            patch(
                "routes.predict.build_prediction_response",
                return_value={"item": "Calculator"},
            ),
            patch(
                "routes.predict.feedback_context_service.store_prediction_context",
                return_value=True,
            ) as mock_store,
        ):
            response = client.post(
                "/predict",
                data={"selected_item": "Calculator"},
                headers={"X-Request-ID": "mobile-original-1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request_id"], "mobile-original-1")
        kwargs = mock_store.call_args.kwargs
        self.assertEqual(kwargs["request_id"], "mobile-original-1")
        self.assertIsNone(kwargs["original_request_id"])

    def test_correction_request_links_original_context(self):
        client = TestClient(app)
        classification = {
            "item": "Metal Cup",
            "category": "Metal",
            "status": "confident",
            "candidates": [],
            "recognition_source": "user_confirmed_selection",
        }
        with (
            patch(
                "routes.predict.recognize_item",
                AsyncMock(return_value=classification),
            ),
            patch(
                "routes.predict.build_prediction_response",
                return_value={"item": "Metal Cup"},
            ),
            patch(
                "routes.predict.feedback_context_service.store_prediction_context",
                return_value=True,
            ) as mock_store,
        ):
            response = client.post(
                "/predict",
                data={"selected_item": "Metal Cup"},
                headers={
                    "X-Request-ID": "mobile-correction-2",
                    "X-Original-Request-ID": "mobile-original-1",
                },
            )

        self.assertEqual(response.status_code, 200)
        kwargs = mock_store.call_args.kwargs
        self.assertEqual(kwargs["request_id"], "mobile-correction-2")
        self.assertEqual(kwargs["original_request_id"], "mobile-original-1")
        self.assertEqual(kwargs["selected_item"], "Metal Cup")

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
        payload = response.json()
        self.assertTrue(payload.pop("request_id").startswith("predict-"))
        self.assertEqual(
            payload,
            {
                "item": "Calculator",
                "category": "Electronics",
                "status": "confident",
                "candidates": [
                    {
                        "label": "Calculator",
                        "selected_item": "Calculator",
                        "guidance_supported": True,
                        "score": 0.98,
                    }
                ],
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
                "guidance_metadata": {"final_generation_path": "legacy_safe_fallback"},
                "guidance_confidence": {
                    "level": "medium",
                    "score": 0.62,
                    "reason_codes": ["static_category_guidance"],
                    "source": "legacy_rules_fallback",
                    "applicability": {
                        "applicable_chunk_ids": [],
                        "conditional_chunk_ids": [],
                        "not_applicable_chunk_ids": [],
                    },
                },
                "cache_hit": True,
                "recognition_source": "phash_cache",
            },
        )

    def test_predict_accepts_real_multipart_uploads_through_recognition_flow(self):
        client = TestClient(app)

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_exact_phash_match",
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
            "recognized_broad_category": "metal",
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
                    "broad_category": "metal",
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
        payload = response.json()
        self.assertEqual(payload["item"], "Water Bottle")
        self.assertEqual(payload["status"], "confident")
        self.assertEqual(payload["disposal_action"], "check local guidance")
        self.assertEqual(payload["guidance_source"], "llm_general_fallback")
        self.assertIn("reuse", payload["summary"].casefold())
        self.assertIn("trash", payload["summary"].casefold())
        self.assertNotIn(payload["disposal_action"], {"recycle", "donate/reuse"})
        self.assertEqual(
            payload["recognition_details"]["normalized"],
            classification["recognition_details"]["normalized"],
        )

    def test_predict_exposes_normalized_nearby_search_context(self):
        client = TestClient(app)
        normalized = {
            "normalized_item": "Curtain",
            "disposal_category": "Textiles",
            "material_category": "Fabric/Textile",
        }
        classification = {
            "item": "Curtain",
            "category": "Textiles",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognition_details": {
                "status": "confident",
                "normalized": normalized,
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
        self.assertEqual(response.json()["recognition_details"]["normalized"], normalized)

    def test_predict_cleans_open_candidate_labels(self):
        client = TestClient(app)
        classification = {
            "item": "Water bottle",
            "category": "Plastic",
            "status": "confident",
            "candidates": [],
            "cache_hit": False,
            "recognition_source": "vlm_open",
            "trusted_guidance_available": False,
            "recognized_material_category": "Plastic",
            "recognized_broad_category": "plastic",
            "recognition_details": {
                "status": "confident",
                "raw_item_label": "water bottle",
                "likely_material": "plastic",
                "broad_category": "drinkware",
                "candidates": [
                    {"label": "water bottle", "confidence": 0.94},
                    {"label": "Water Bottle", "confidence": 0.88},
                    {"label": "drinking bottle", "confidence": 0.82},
                    {"label": "", "confidence": 0.7},
                    {"label": "Other", "confidence": 0.7},
                    {"name": "plastic water bottle", "score": 0.75},
                ],
                "visual_evidence": "Bottle silhouette and narrow opening visible.",
                "normalized": {
                    "item_label": "Water Bottle",
                    "material_category": "Plastic",
                    "broad_category": "plastic",
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
            response.json()["candidates"],
            [
                {
                    "label": "Plastic Water Bottle",
                    "selected_item": "Plastic water bottle",
                    "guidance_supported": True,
                    "score": 0.94,
                },
            ],
        )
        self.assertNotIn(
            "Drinking Bottle",
            [candidate["label"] for candidate in response.json()["candidates"]],
        )

    def test_predict_adds_main_item_as_fallback_candidate(self):
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
            "recognized_broad_category": "electronics",
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
            response.json()["candidates"],
            [{"label": "Cable", "selected_item": "Cable", "guidance_supported": True}],
        )

    def test_selected_item_synonym_maps_to_supported_guidance(self):
        client = TestClient(app)

        response = client.post("/predict", data={"selected_item": "drinking bottle"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"], "Plastic Water Bottle")
        self.assertEqual(response.json()["category"], "Plastic")
        self.assertEqual(response.json()["status"], "confident")
        self.assertEqual(
            response.json()["recognition_source"], "user_confirmed_selection"
        )
        self.assertNotIn("clarification", response.json())
        self.assertNotEqual(response.json()["guidance_source"], "safe_fallback")
        self.assertEqual(
            response.json()["candidates"],
            [
                {
                    "label": "Plastic Water Bottle",
                    "selected_item": "Plastic water bottle",
                    "guidance_supported": True,
                }
            ],
        )

    def test_selected_item_supported_label_still_works(self):
        client = TestClient(app)

        response = client.post("/predict", data={"selected_item": "Plastic water bottle"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"], "Plastic Water Bottle")
        self.assertEqual(response.json()["category"], "Plastic")
        self.assertEqual(response.json()["status"], "confident")
        self.assertNotEqual(response.json()["guidance_source"], "safe_fallback")

    def test_selected_item_unmapped_label_stays_unknown(self):
        client = TestClient(app)

        response = client.post("/predict", data={"selected_item": "mystery artifact"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"], "")
        self.assertEqual(response.json()["category"], "Unknown")
        self.assertEqual(response.json()["status"], "uncertain")
        self.assertTrue(response.json()["clarification"]["required"])
        self.assertIn(
            "recognition_status_unknown",
            response.json()["clarification"]["reason_codes"],
        )
        self.assertEqual(response.json()["candidates"], [])

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
            "recognized_broad_category": "household",
            "recognition_details": {
                "status": "confident",
                "raw_item_label": "pencil",
                "likely_material": "mixed material",
                "broad_category": "household",
                "normalized": {
                    "item_label": "Pencil",
                    "material_category": "Mixed Material",
                    "broad_category": "household",
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
            "recognized_broad_category": "electronics",
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
        payload = response.json()
        self.assertTrue(payload.pop("request_id").startswith("predict-"))
        self.assertEqual(
            payload,
            {
                "item": "Charging Cable",
                "category": "Electronics",
                "status": "confident",
                "candidates": [
                    {"label": "Cable", "selected_item": "Cable", "guidance_supported": True}
                ],
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
                "guidance_metadata": {"final_generation_path": "legacy_safe_fallback"},
                "guidance_confidence": {
                    "level": "medium",
                    "score": 0.62,
                    "reason_codes": ["static_category_guidance"],
                    "source": "legacy_rules_fallback",
                    "applicability": {
                        "applicable_chunk_ids": [],
                        "conditional_chunk_ids": [],
                        "not_applicable_chunk_ids": [],
                    },
                },
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
            "recognized_broad_category": "batteries",
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
                    "broad_category": "batteries",
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
        payload = response.json()
        self.assertTrue(payload.pop("request_id").startswith("predict-"))
        self.assertEqual(
            payload,
            {
                "item": "",
                "category": "Unknown",
                "status": "uncertain",
                "candidates": [],
                "disposal_action": None,
                "material_code": None,
                "impact_level": None,
                "summary": "Confirm or correct the recognized item before disposal guidance is shown.",
                "steps": [],
                "guidance_source": "recognition_clarification_required",
                "guidance_metadata": {
                    "final_generation_path": "recognition_clarification",
                    "clarification_reason_codes": ["recognition_status_unknown"],
                },
                "cache_hit": False,
                "recognition_source": "vlm_open",
                "guidance_confidence": {
                    "level": "unknown",
                    "score": 0.0,
                    "reason_codes": ["recognition_clarification_required"],
                    "source": "recognition_clarification_required",
                    "applicability": {
                        "applicable_chunk_ids": [],
                        "conditional_chunk_ids": [],
                        "not_applicable_chunk_ids": [],
                    },
                },
                "clarification": {
                    "required": True,
                    "reason_codes": ["recognition_status_unknown"],
                    "retake_recommended": True,
                    "retake_guidance": (
                        "Retake the photo with the whole item visible in brighter light, "
                        "with labels and physical features in focus."
                    ),
                    "message": (
                        "Confirm or correct the recognized item before disposal guidance is shown."
                    ),
                },
            },
        )

    def test_predict_exact_phash_cache_hit_preserves_response_shape(self):
        client = TestClient(app)
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 0,
            "metadata": (
                "{\"classification\": {\"item\": \"Calculator\", \"category\": \"Electronics\", "
                "\"status\": \"confident\", \"candidates\": [[\"Calculator\", 0.98]]}}"
            ),
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_exact_phash_match",
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
        payload = response.json()
        self.assertTrue(payload.pop("request_id").startswith("predict-"))
        self.assertEqual(
            payload,
            {
                "item": "Calculator",
                "category": "Electronics",
                "status": "confident",
                "candidates": [
                    {
                        "label": "Calculator",
                        "selected_item": "Calculator",
                        "guidance_supported": True,
                        "score": 0.98,
                    }
                ],
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
                "guidance_metadata": {"final_generation_path": "legacy_safe_fallback"},
                "guidance_confidence": {
                    "level": "medium",
                    "score": 0.62,
                    "reason_codes": ["static_category_guidance"],
                    "source": "legacy_rules_fallback",
                    "applicability": {
                        "applicable_chunk_ids": [],
                        "conditional_chunk_ids": [],
                        "not_applicable_chunk_ids": [],
                    },
                },
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
            "recognized_broad_category": "electronics",
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
                    "broad_category": "electronics",
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
            "batteries_01",
            response.json()["guidance_metadata"]["retrieved_chunk_ids"],
        )


if __name__ == "__main__":
    unittest.main()
