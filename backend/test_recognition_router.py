import io
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, UploadFile
from PIL import Image

if "imagehash" not in sys.modules:
    fake_imagehash = types.ModuleType("imagehash")
    fake_imagehash.phash = lambda image: "deadbeef"
    fake_imagehash.hex_to_hash = lambda value: 0
    sys.modules["imagehash"] = fake_imagehash

from services.recognition_router import recognize_item


def _make_upload_file() -> UploadFile:
    image = Image.new("RGB", (32, 32), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)
    return UploadFile(filename="photo.jpg", file=buffer)


def _run_recognize_item(**kwargs):
    import asyncio

    return asyncio.run(recognize_item(**kwargs))


def _no_clip_candidates_decision() -> dict:
    return {
        "use_cache": False,
        "item_label": None,
        "reason": "no_clip_candidates",
        "confidence": None,
        "top_label": None,
        "top_score": None,
        "label_agreement_count": 0,
        "evaluated_count": 0,
        "best_competing_label": None,
        "best_competing_score": None,
        "margin": None,
    }


def _strong_clip_cache_decision(label: str) -> dict:
    return {
        "use_cache": True,
        "item_label": label,
        "reason": "strong_clip_agreement",
        "confidence": 0.97,
        "top_label": label,
        "top_score": 0.97,
        "label_agreement_count": 3,
        "evaluated_count": 3,
        "best_competing_label": None,
        "best_competing_score": None,
        "margin": None,
    }


class RecognitionRouterTests(unittest.TestCase):
    def test_known_barcode_short_circuits_before_ocr_clip_and_vlm(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.barcode_service.detect_barcode",
                return_value={
                    "barcode_value": "9780399578694",
                    "barcode_type": "EAN_13",
                },
            ),
            patch("services.recognition_router.ocr_service.extract_ocr_text") as mock_ocr,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
            patch(
                "services.recognition_router.cache_repository.save_recognition_record"
            ) as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Book")
        self.assertEqual(result["category"], "Paper")
        self.assertEqual(result["recognition_source"], "barcode")
        self.assertFalse(result["cache_hit"])
        mock_ocr.assert_not_called()
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()
        self.assertIsNone(mock_save.call_args.kwargs["clip_embedding"])
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["cache_policy"],
            {
                "save_record": True,
                "save_clip_embedding": False,
                "reason": "known_barcode",
            },
        )

    def test_unknown_barcode_blocks_clip_fast_path_and_falls_back_to_vlm(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.88)],
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.barcode_service.detect_barcode",
                return_value={
                    "barcode_value": "999999999999",
                    "barcode_type": "EAN_13",
                },
            ),
            patch(
                "services.recognition_router.get_product_by_barcode",
                return_value=None,
            ),
            patch("services.recognition_router.ocr_service.extract_ocr_text") as mock_ocr,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.88)], "margin": 0.88},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch(
                "services.recognition_router.cache_repository.save_recognition_record"
            ) as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        mock_ocr.assert_not_called()
        mock_clip.assert_not_called()
        mock_vlm.assert_called_once_with(
            unittest.mock.ANY,
            barcode_aware=True,
            barcode_context=None,
        )
        mock_vlm.assert_called_once()
        self.assertIsNone(mock_save.call_args.kwargs["clip_embedding"])
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["route"],
            "unknown_barcode_vlm_fallback",
        )
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["cache_policy"],
            {
                "save_record": True,
                "save_clip_embedding": False,
                "reason": "unknown_barcode_vlm_fallback",
            },
        )
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["barcode"]["product_lookup"],
            {
                "found": False,
                "mapped": False,
                "source": "open_food_facts",
                "product_name": None,
                "brand": None,
                "category": None,
                "packaging": None,
            },
        )

    def test_open_food_facts_mapped_barcode_skips_vlm_and_saves_without_clip_embedding(self):
        product = {
            "barcode_value": "0123456789012",
            "product_name": "Spring Water",
            "brand": "Acme",
            "category": "Waters",
            "packaging": "Plastic bottle",
            "quantity": "500 ml",
            "source": "open_food_facts",
            "raw_categories": ["en:waters"],
            "raw_packaging_tags": ["en:plastic-bottle"],
        }
        product_mapping = {
            "item_label": "Plastic water bottle",
            "confidence": 0.85,
            "reason": "open_food_facts_keyword_match",
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.barcode_service.detect_barcode",
                return_value={
                    "barcode_value": "0123456789012",
                    "barcode_type": "EAN_13",
                },
            ),
            patch(
                "services.recognition_router.get_product_by_barcode",
                return_value=product,
            ),
            patch(
                "services.recognition_router.map_product_to_item_label",
                return_value=product_mapping,
            ),
            patch("services.recognition_router.ocr_service.extract_ocr_text") as mock_ocr,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
            patch(
                "services.recognition_router.cache_repository.save_recognition_record"
            ) as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Plastic water bottle")
        self.assertEqual(result["recognition_source"], "open_food_facts")
        self.assertFalse(result["cache_hit"])
        mock_ocr.assert_not_called()
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()
        self.assertIsNone(mock_save.call_args.kwargs["clip_embedding"])
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["route"],
            "open_food_facts_barcode_lookup",
        )
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["barcode"]["product_lookup"],
            {
                "found": True,
                "mapped": True,
                "source": "open_food_facts",
                "product_name": "Spring Water",
                "brand": "Acme",
                "category": "Waters",
                "packaging": "Plastic bottle",
            },
        )

    def test_open_food_facts_unmapped_product_uses_barcode_aware_vlm_and_saves_without_clip_embedding(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.88)],
        }
        product = {
            "barcode_value": "1111111111111",
            "product_name": "Mystery Snack",
            "brand": "Acme",
            "category": "Snacks",
            "packaging": "Wrapper",
            "quantity": "40 g",
            "source": "open_food_facts",
            "raw_categories": ["en:snacks"],
            "raw_packaging_tags": ["en:wrapper"],
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.barcode_service.detect_barcode",
                return_value={
                    "barcode_value": "1111111111111",
                    "barcode_type": "EAN_13",
                },
            ),
            patch(
                "services.recognition_router.get_product_by_barcode",
                return_value=product,
            ),
            patch(
                "services.recognition_router.map_product_to_item_label",
                return_value=None,
            ),
            patch("services.recognition_router.ocr_service.extract_ocr_text") as mock_ocr,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.88)], "margin": 0.88},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch(
                "services.recognition_router.cache_repository.save_recognition_record"
            ) as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        mock_ocr.assert_not_called()
        mock_clip.assert_not_called()
        mock_vlm.assert_called_once_with(
            unittest.mock.ANY,
            barcode_aware=True,
            barcode_context={
                "barcode_value": "1111111111111",
                "product_name": "Mystery Snack",
                "brand": "Acme",
                "category": "Snacks",
                "packaging": "Wrapper",
            },
        )
        self.assertIsNone(mock_save.call_args.kwargs["clip_embedding"])
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["route"],
            "barcode_product_context_vlm_fallback",
        )
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["barcode"]["product_lookup"],
            {
                "found": True,
                "mapped": False,
                "source": "open_food_facts",
                "product_name": "Mystery Snack",
                "brand": "Acme",
                "category": "Snacks",
                "packaging": "Wrapper",
            },
        )

    def test_barcode_aware_vlm_fallback_can_return_unknown_without_saving_record(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.barcode_service.detect_barcode",
                return_value={
                    "barcode_value": "999999999999",
                    "barcode_type": "EAN_13",
                },
            ),
            patch(
                "services.recognition_router.get_product_by_barcode",
                return_value=None,
            ),
            patch("services.recognition_router.ocr_service.extract_ocr_text") as mock_ocr,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [], "margin": 0.0},
            ) as mock_vlm,
            patch(
                "services.recognition_router.cache_repository.save_recognition_record"
            ) as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["item"], "")
        self.assertEqual(result["recognition_source"], "vlm")
        mock_ocr.assert_not_called()
        mock_clip.assert_not_called()
        mock_vlm.assert_called_once_with(
            unittest.mock.ANY,
            barcode_aware=True,
            barcode_context=None,
        )
        mock_save.assert_not_called()

    def test_phash_exact_duplicate_of_unsafe_cached_record_still_returns_early(self):
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 0,
            "metadata": {
                "classification": {
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [["Calculator", 1.0]],
                },
                "signals": {
                    "cache_policy": {
                        "save_record": True,
                        "save_clip_embedding": False,
                        "reason": "unknown_barcode",
                    }
                },
            },
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode") as mock_barcode,
            patch("services.recognition_router.ocr_service.extract_ocr_text") as mock_ocr,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "phash_cache")
        self.assertTrue(result["cache_hit"])
        mock_barcode.assert_not_called()
        mock_ocr.assert_not_called()
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_phash_near_match_of_unsafe_cached_record_continues_full_flow(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.91)],
        }
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 3,
            "metadata": {
                "classification": {
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [["Calculator", 1.0]],
                },
                "signals": {
                    "cache_policy": {
                        "save_record": True,
                        "save_clip_embedding": False,
                        "reason": "text_heavy_weak_visual",
                    }
                },
            },
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None) as mock_barcode,
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={"text": "", "keywords": [], "matched_label": None},
            ) as mock_ocr,
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=[0.1, 0.2],
            ) as mock_clip,
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                return_value=[],
            ),
            patch(
                "services.recognition_router.evaluate_clip_candidates",
                return_value=_no_clip_candidates_decision(),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.91)], "margin": 0.91},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        mock_barcode.assert_called_once()
        mock_ocr.assert_called_once()
        mock_clip.assert_called_once()
        mock_vlm.assert_called_once()
        self.assertEqual(mock_save.call_args.kwargs["clip_embedding"], [0.1, 0.2])
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["cache_policy"]["reason"],
            "normal_product_photo",
        )

    def test_no_barcode_noisy_ocr_and_confident_vlm_result_saves_clip_embedding(self):
        classification = {
            "item": "Monitor",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Monitor", 0.93)],
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={
                    "text": "model display hdmi energy star serial input monitor office screen setup",
                    "keywords": ["display", "monitor", "office"],
                    "matched_label": None,
                },
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
                "services.recognition_router.evaluate_clip_candidates",
                return_value=_no_clip_candidates_decision(),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Monitor", 0.93)], "margin": 0.93},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        mock_vlm.assert_called_once()
        self.assertEqual(mock_save.call_args.kwargs["clip_embedding"], [0.1, 0.2])
        self.assertEqual(mock_save.call_args.kwargs["metadata"]["route"], "text_heavy_weak_visual")
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["cache_policy"],
            {
                "save_record": True,
                "save_clip_embedding": True,
                "reason": "normal_product_photo",
            },
        )

    def test_ocr_clip_conflict_disables_clip_embedding_persistence(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.83)],
        }
        clip_candidates = [
            {
                "id": "clip-1",
                "item_label": "Calculator",
                "similarity": 0.95,
                "confidence": 0.8,
                "verified": True,
                "recognition_source": "vlm",
                "metadata": {"source": "cached-neighbor"},
            }
        ]

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={
                    "text": "battery label closeup",
                    "keywords": ["battery"],
                    "matched_label": "Battery",
                },
            ),
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=[0.1, 0.2],
            ),
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                return_value=clip_candidates,
            ),
            patch(
                "services.recognition_router.evaluate_clip_candidates",
                return_value=_strong_clip_cache_decision("Calculator"),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.83)], "margin": 0.83},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        mock_vlm.assert_called_once()
        self.assertIsNone(mock_save.call_args.kwargs["clip_embedding"])
        self.assertEqual(mock_save.call_args.kwargs["metadata"]["route"], "ocr_clip_conflict")
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["cache_policy"],
            {
                "save_record": True,
                "save_clip_embedding": False,
                "reason": "ocr_final_label_conflict",
            },
        )

    def test_ocr_clip_agreement_is_allowed_and_saves_lightweight_candidates(self):
        clip_candidates = [
            {
                "id": "clip-1",
                "item_label": "Calculator",
                "similarity": 0.92,
                "confidence": 0.85,
                "verified": True,
                "recognition_source": "vlm",
                "metadata": {"source": "cached-neighbor"},
            }
        ]
        router_decision = {
            "use_cache": False,
            "item_label": None,
            "reason": "weak_label_agreement",
            "confidence": 0.92,
            "top_label": "Calculator",
            "top_score": 0.92,
            "label_agreement_count": 1,
            "evaluated_count": 1,
            "best_competing_label": None,
            "best_competing_score": None,
            "margin": None,
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={
                    "text": "calc",
                    "keywords": ["calculator"],
                    "matched_label": "Calculator",
                },
            ),
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=[0.1, 0.2],
            ),
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                return_value=clip_candidates,
            ),
            patch(
                "services.recognition_router.evaluate_clip_candidates",
                return_value=router_decision,
            ),
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "clip_cache")
        self.assertTrue(result["cache_hit"])
        mock_vlm.assert_not_called()
        self.assertEqual(mock_save.call_args.kwargs["clip_embedding"], [0.1, 0.2])
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["cache_policy"],
            {
                "save_record": True,
                "save_clip_embedding": True,
                "reason": "normal_product_photo",
            },
        )
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["clip_candidates"],
            [
                {
                    "id": "clip-1",
                    "item_label": "Calculator",
                    "similarity": 0.92,
                    "confidence": 0.85,
                    "verified": True,
                    "recognition_source": "vlm",
                }
            ],
        )
        self.assertNotIn(
            "metadata",
            mock_save.call_args.kwargs["metadata"]["signals"]["clip_candidates"][0],
        )

    def test_normal_product_photo_keeps_clip_embedding(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.91)],
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={"text": "", "keywords": [], "matched_label": None},
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
                "services.recognition_router.evaluate_clip_candidates",
                return_value=_no_clip_candidates_decision(),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.91)], "margin": 0.91},
            ),
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        self.assertEqual(mock_save.call_args.kwargs["clip_embedding"], [0.1, 0.2])
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["signals"]["cache_policy"],
            {
                "save_record": True,
                "save_clip_embedding": True,
                "reason": "normal_product_photo",
            },
        )

    def test_uncertain_or_unknown_result_does_not_save_clip_embedding(self):
        classification = {
            "item": "Unknown",
            "category": "Unknown",
            "status": "unknown",
            "candidates": [("Unknown", 0.42)],
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={"text": "blurred object", "keywords": [], "matched_label": None},
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
                "services.recognition_router.evaluate_clip_candidates",
                return_value=_no_clip_candidates_decision(),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Unknown", 0.42)], "margin": 0.05},
            ),
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["status"], "unknown")
        self.assertFalse(mock_save.called)

    def test_selected_item_bypasses_recognition_flow(self):
        manual_classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [],
        }

        with (
            patch(
                "services.recognition_router.build_selected_item_prediction",
                return_value=manual_classification,
            ) as mock_build,
            patch("services.recognition_router.phash_service.create_phash") as mock_phash,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            result = _run_recognize_item(selected_item="Calculator")

        self.assertEqual(result, manual_classification)
        mock_build.assert_called_once_with("Calculator")
        mock_phash.assert_not_called()
        mock_vlm.assert_not_called()

    def test_invalid_image_returns_http_400(self):
        invalid_file = UploadFile(filename="broken.jpg", file=io.BytesIO(b"not-an-image"))

        with self.assertRaises(HTTPException) as context:
            _run_recognize_item(file=invalid_file)

        self.assertEqual(context.exception.status_code, 400)

    def test_valid_upload_reads_bytes_once_and_reuses_them(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.91)],
        }
        upload_file = _make_upload_file()
        original_read = upload_file.read
        upload_file.read = AsyncMock(wraps=original_read)
        expected_bytes = upload_file.file.getvalue()

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef") as mock_phash,
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None) as mock_barcode,
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={"text": "", "keywords": [], "matched_label": None},
            ) as mock_ocr,
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=[0.1, 0.2],
            ) as mock_clip,
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                return_value=[],
            ),
            patch(
                "services.recognition_router.evaluate_clip_candidates",
                return_value=_no_clip_candidates_decision(),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.91)], "margin": 0.91},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record"),
        ):
            result = _run_recognize_item(file=upload_file)

        self.assertEqual(result["item"], "Calculator")
        upload_file.read.assert_awaited_once()
        mock_phash.assert_called_once_with(expected_bytes)
        mock_barcode.assert_called_once_with(expected_bytes)
        mock_ocr.assert_called_once_with(expected_bytes)
        mock_clip.assert_called_once_with(expected_bytes)
        mock_vlm.assert_called_once()

    def test_open_mode_confident_water_bottle_without_supported_match_becomes_final_classification(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={"text": "", "keywords": [], "matched_label": None},
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
                "services.recognition_router.evaluate_clip_candidates",
                return_value=_no_clip_candidates_decision(),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={
                    "top_predictions": [],
                    "margin": 0.0,
                    "recognition_details": {
                        "status": "confident",
                        "raw_item_label": "water bottle",
                        "likely_material": "metal",
                        "broad_category": "drinkware",
                        "candidates": [{"label": "water bottle", "confidence": 0.93}],
                        "visual_evidence": "Bottle body and narrow opening are visible.",
                        "raw_output": '{"status":"confident"}',
                        "disposal_action": "recycle",
                        "steps": ["ignore this"],
                    },
                },
            ),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Water bottle")
        self.assertEqual(result["category"], "Metal")
        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["recognition_source"], "vlm_open")
        self.assertFalse(result["trusted_guidance_available"])
        self.assertIsNone(result["trusted_guidance_label"])
        self.assertIn("recognition_details", result)
        self.assertEqual(result["recognition_details"]["raw_item_label"], "water bottle")
        self.assertEqual(result["recognition_details"]["likely_material"], "metal")
        self.assertEqual(result["recognition_details"]["broad_category"], "drinkware")
        self.assertEqual(result["recognition_details"]["disposal_action"], "recycle")
        self.assertEqual(
            result["recognition_details"]["normalized"]["item_label"],
            "Water bottle",
        )
        self.assertEqual(
            result["recognition_details"]["normalized"]["material_category"],
            "Metal",
        )
        self.assertEqual(
            result["recognition_details"]["normalized"]["broad_category"],
            "Drinkware",
        )
        self.assertIsNone(
            result["recognition_details"]["normalized"]["matched_supported_label"]
        )
        self.assertEqual(mock_save.call_args.kwargs["item_label"], "Water bottle")
        self.assertEqual(mock_save.call_args.kwargs["recognition_source"], "vlm_open")
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["recognition_details"]["raw_item_label"],
            "water bottle",
        )
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["recognition_details"]["normalized"]["item_label"],
            "Water bottle",
        )
        self.assertEqual(
            mock_save.call_args.kwargs["metadata"]["recognition_details"]["normalized"]["material_category"],
            "Metal",
        )
        self.assertEqual(mock_save.call_args.kwargs["metadata"]["vlm_mode"], "open")

    def test_open_mode_supported_match_uses_trusted_guidance_category(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={"text": "", "keywords": [], "matched_label": None},
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
                "services.recognition_router.evaluate_clip_candidates",
                return_value=_no_clip_candidates_decision(),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={
                    "top_predictions": [],
                    "margin": 0.0,
                    "recognition_details": {
                        "status": "confident",
                        "raw_item_label": "iphone charging cable",
                        "likely_material": "electronics",
                        "broad_category": "electronics",
                        "candidates": [{"label": "Charging cable", "confidence": 0.95}],
                        "visual_evidence": "Cable connector and charging cord.",
                        "raw_output": '{"status":"confident"}',
                        "normalized": {
                            "item_label": "Charging cable",
                            "material_category": "Electronics",
                            "broad_category": "Electronics",
                            "condition_flags": [],
                            "special_handling_flags": ["electronics", "dropoff_recommended"],
                            "matched_supported_label": "Cable",
                            "normalization_source": "exact_alias",
                        },
                    },
                },
            ),
            patch("services.recognition_router.cache_repository.save_recognition_record"),
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Charging cable")
        self.assertEqual(result["category"], "Electronics")
        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["recognition_source"], "vlm_open")
        self.assertTrue(result["trusted_guidance_available"])
        self.assertEqual(result["trusted_guidance_label"], "Cable")

    def test_unknown_open_mode_output_does_not_crash(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch(
                "services.recognition_router.ocr_service.extract_ocr_text",
                return_value={"text": "", "keywords": [], "matched_label": None},
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
                "services.recognition_router.evaluate_clip_candidates",
                return_value=_no_clip_candidates_decision(),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={
                    "top_predictions": [],
                    "margin": 0.0,
                    "recognition_details": {
                        "status": "unknown",
                        "raw_item_label": "",
                        "likely_material": "",
                        "broad_category": "",
                        "candidates": [],
                        "visual_evidence": "",
                        "raw_output": '{"status":"unknown"}',
                        "normalized": {
                            "item_label": "Unknown",
                            "material_category": "Unknown",
                            "broad_category": "Unknown",
                            "condition_flags": [],
                            "special_handling_flags": [],
                            "matched_supported_label": None,
                            "normalization_source": "unknown_fallback",
                        },
                    },
                },
            ),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["recognition_source"], "vlm_open")
        self.assertIn("recognition_details", result)
        mock_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
