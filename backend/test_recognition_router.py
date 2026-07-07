import asyncio
import io
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from PIL import Image

from services.recognition_router import _build_cached_classification, recognize_item


def _make_image_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _make_upload_file(contents: bytes | None = None) -> UploadFile:
    return UploadFile(filename="photo.jpg", file=io.BytesIO(contents or _make_image_bytes()))


def _run_recognize_item(**kwargs):
    return asyncio.run(recognize_item(**kwargs))


def _classification(item: str = "Calculator") -> dict:
    return {
        "item": item,
        "category": "Electronics",
        "status": "confident",
        "candidates": [(item, 0.91)],
    }


def _clip_decision(*, use_cache: bool, label: str | None = None) -> dict:
    return {
        "use_cache": use_cache,
        "item_label": label,
        "reason": "strong_clip_agreement" if use_cache else "no_clip_candidates",
        "confidence": 0.97 if use_cache else None,
        "top_label": label,
        "top_score": 0.97 if use_cache else None,
        "label_agreement_count": 3 if use_cache else 0,
        "evaluated_count": 3 if use_cache else 0,
        "best_competing_label": None,
        "best_competing_score": None,
        "margin": None,
    }


class RecognitionRouterTests(unittest.TestCase):
    def setUp(self):
        self.exact_phash_patch = patch(
            "services.recognition_router.cache_repository.find_exact_phash_match",
            return_value=None,
        )
        self.exact_phash_patch.start()
        self.addCleanup(self.exact_phash_patch.stop)
        self.phash_env_patch = patch.dict(
            os.environ,
            {"ENABLE_NEAREST_PHASH_LOOKUP": "false"},
        )
        self.phash_env_patch.start()
        self.addCleanup(self.phash_env_patch.stop)

    def test_selected_item_bypasses_recognition_flow(self):
        with patch("services.recognition_router.phash_service.create_phash") as mock_phash:
            result = _run_recognize_item(selected_item="Calculator")

        self.assertEqual(result["item"], "Calculator")
        mock_phash.assert_not_called()

    def test_invalid_image_returns_http_400(self):
        with self.assertRaises(HTTPException) as context:
            _run_recognize_item(file=_make_upload_file(b"not an image"))
        self.assertEqual(context.exception.status_code, 400)

    def test_phash_hit_short_circuits_later_recognition(self):
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 0,
            "metadata": {"classification": _classification()},
        }
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_exact_phash_match",
                return_value=cached_record,
            ),
            patch("services.recognition_router.barcode_service.detect_barcode") as mock_barcode,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            with self.assertLogs("services.recognition_router", level="INFO") as logs:
                result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "phash_cache")
        self.assertTrue(result["cache_hit"])
        mock_barcode.assert_not_called()
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()
        combined = "\n".join(logs.output)
        self.assertIn("stage=phash_compute", combined)
        self.assertIn("stage=phash_exact_lookup", combined)
        self.assertIn("stage=phash_total", combined)

    def test_known_barcode_short_circuits_clip_and_vlm(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch("services.recognition_router.cache_repository.find_nearest_phash_match", return_value=None),
            patch(
                "services.recognition_router.barcode_service.detect_barcode",
                return_value={"barcode_value": "9780399578694", "barcode_type": "EAN_13"},
            ),
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            with self.assertLogs("services.recognition_router", level="INFO") as logs:
                result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Book")
        self.assertEqual(result["recognition_source"], "barcode")
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()
        self.assertIsNone(mock_save.call_args.kwargs["clip_embedding"])

    def test_open_food_facts_mapping_short_circuits_clip_and_vlm(self):
        product = {
            "product_name": "Spring Water",
            "brand": "Acme",
            "category": "Waters",
            "packaging": "Plastic bottle",
            "source": "open_food_facts",
        }
        mapping = {"item_label": "Plastic water bottle", "confidence": 0.85}
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch("services.recognition_router.cache_repository.find_nearest_phash_match", return_value=None),
            patch(
                "services.recognition_router.barcode_service.detect_barcode",
                return_value={"barcode_value": "0123456789012", "barcode_type": "EAN_13"},
            ),
            patch("services.recognition_router.get_product_by_barcode", return_value=product),
            patch("services.recognition_router.map_product_to_item_label", return_value=mapping),
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
            patch("services.recognition_router.cache_repository.save_recognition_record"),
        ):
            with self.assertLogs("services.recognition_router", level="INFO") as logs:
                result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "open_food_facts")
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_unknown_barcode_uses_barcode_aware_vlm_without_clip(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch("services.recognition_router.cache_repository.find_nearest_phash_match", return_value=None),
            patch(
                "services.recognition_router.barcode_service.detect_barcode",
                return_value={"barcode_value": "999999999999", "barcode_type": "EAN_13"},
            ),
            patch("services.recognition_router.get_product_by_barcode", return_value=None),
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.91)], "margin": 0.91},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=_classification()),
            patch("services.recognition_router.cache_repository.save_recognition_record"),
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        mock_clip.assert_not_called()
        mock_vlm.assert_called_once_with(
            unittest.mock.ANY,
            barcode_aware=True,
            barcode_context=None,
        )

    def test_cold_clip_skips_embedding_and_continues_to_vlm(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch("services.recognition_router.cache_repository.find_nearest_phash_match") as mock_nearest,
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch("services.recognition_router.clip_service.is_clip_initialized", return_value=False),
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.cache_repository.find_similar_embeddings") as mock_search,
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.91)], "margin": 0.91},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=_classification()),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            with self.assertLogs("services.recognition_router", level="INFO") as logs:
                result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        mock_clip.assert_not_called()
        mock_search.assert_not_called()
        mock_nearest.assert_not_called()
        mock_vlm.assert_called_once()
        self.assertIsNone(mock_save.call_args.kwargs["clip_embedding"])
        self.assertTrue(any("stage=clip" in message and "skipped=true" in message for message in logs.output))
        self.assertTrue(any("nearest lookup skipped" in message for message in logs.output))

    def test_nearest_phash_lookup_runs_only_when_enabled(self):
        near_record = {
            "item_label": "Calculator",
            "phash_distance": 3,
            "metadata": {"classification": _classification()},
        }
        with (
            patch.dict(os.environ, {"ENABLE_NEAREST_PHASH_LOOKUP": "true"}),
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=near_record,
            ) as mock_nearest,
            patch("services.recognition_router.barcode_service.detect_barcode") as mock_barcode,
        ):
            with self.assertLogs("services.recognition_router", level="INFO") as logs:
                result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "phash_cache")
        mock_nearest.assert_called_once_with(
            "deadbeef",
            6,
            check_exact=False,
        )
        mock_barcode.assert_not_called()
        self.assertTrue(any("stage=phash_nearest_lookup" in message for message in logs.output))

    def test_ready_clip_cache_hit_skips_vlm(self):
        clip_record = {
            "id": "clip-1",
            "item_label": "Calculator",
            "similarity": 0.97,
            "confidence": 0.91,
            "verified": True,
            "metadata": {"classification": _classification()},
        }
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch("services.recognition_router.cache_repository.find_nearest_phash_match", return_value=None),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch("services.recognition_router.clip_service.is_clip_initialized", return_value=True),
            patch("services.recognition_router.clip_service.create_clip_embedding", return_value=[0.1, 0.2]),
            patch("services.recognition_router.cache_repository.find_similar_embeddings", return_value=[clip_record]),
            patch("services.recognition_router.evaluate_clip_candidates", return_value=_clip_decision(use_cache=True, label="Calculator")),
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "clip_cache")
        self.assertTrue(result["cache_hit"])
        mock_vlm.assert_not_called()

    def test_ready_clip_miss_runs_vlm_and_saves_embedding(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch("services.recognition_router.cache_repository.find_nearest_phash_match", return_value=None),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch("services.recognition_router.clip_service.is_clip_initialized", return_value=True),
            patch("services.recognition_router.clip_service.create_clip_embedding", return_value=[0.1, 0.2]),
            patch("services.recognition_router.cache_repository.find_similar_embeddings", return_value=[]),
            patch("services.recognition_router.evaluate_clip_candidates", return_value=_clip_decision(use_cache=False)),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.91)], "margin": 0.91},
            ),
            patch("services.recognition_router.classify", return_value=_classification()),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        self.assertEqual(mock_save.call_args.kwargs["clip_embedding"], [0.1, 0.2])
        self.assertNotIn("ocr", mock_save.call_args.kwargs["metadata"]["signals"])

    def test_legacy_cache_record_with_ocr_metadata_remains_readable(self):
        record = {
            "item_label": "Calculator",
            "metadata": {
                "classification": _classification(),
                "signals": {
                    "ocr": {"text": "battery", "matched_label": "Battery"},
                    "cache_policy": {"save_clip_embedding": True},
                },
            },
        }

        classification = _build_cached_classification(record)

        self.assertIsNotNone(classification)
        self.assertEqual(classification["item"], "Calculator")

    def test_stage_timing_logs_use_flexible_identifiers(self):
        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch("services.recognition_router.cache_repository.find_nearest_phash_match", return_value=None),
            patch("services.recognition_router.barcode_service.detect_barcode", return_value=None),
            patch("services.recognition_router.clip_service.is_clip_initialized", return_value=False),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.91)], "margin": 0.91},
            ),
            patch("services.recognition_router.classify", return_value=_classification()),
            patch("services.recognition_router.cache_repository.save_recognition_record"),
        ):
            with self.assertLogs("services.recognition_router", level="INFO") as logs:
                _run_recognize_item(file=_make_upload_file())

        combined = "\n".join(logs.output)
        for stage in ("phash_compute", "phash_exact_lookup", "phash_total", "barcode", "vlm"):
            self.assertIn(f"stage={stage}", combined)
        self.assertNotIn("stage=phash_nearest_lookup", combined)


if __name__ == "__main__":
    unittest.main()
