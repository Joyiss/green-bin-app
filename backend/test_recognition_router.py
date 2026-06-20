import io
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException, UploadFile
from PIL import Image

from services import clip_service
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


class RecognitionRouterTests(unittest.TestCase):
    def test_cache_hit_skips_vlm_and_returns_cached_classification(self):
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 0,
            "metadata": {
                "classification": {
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [["Calculator", 1.0]],
                }
            },
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(
            result,
            {
                "item": "Calculator",
                "category": "Electronics",
                "status": "confident",
                "candidates": [("Calculator", 1.0)],
                "cache_hit": True,
                "recognition_source": "phash_cache",
            },
        )
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()
        mock_save.assert_not_called()

    def test_near_cache_hit_returns_same_shape_as_exact_cache_hit(self):
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 4,
            "metadata": {
                "classification": {
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [["Calculator", 1.0]],
                }
            },
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
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(
            result,
            {
                "item": "Calculator",
                "category": "Electronics",
                "status": "confident",
                "candidates": [("Calculator", 1.0)],
                "cache_hit": True,
                "recognition_source": "phash_cache",
            },
        )
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_near_cache_hit_works_with_json_string_metadata(self):
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 4,
            "metadata": (
                "{\"classification\": {\"item\": \"Calculator\", \"category\": \"Electronics\", "
                "\"status\": \"confident\", \"candidates\": [{\"label\": \"Calculator\", \"score\": 1.0}]}}"
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
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["candidates"], [("Calculator", 1.0)])
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["recognition_source"], "phash_cache")
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_exact_cache_hit_with_json_string_metadata_returns_cached_item_not_unknown(self):
        cached_record = {
            "id": "record-exact-json",
            "item_label": "Calculator",
            "phash_distance": 0,
            "metadata": (
                "{\"classification\": {\"item\": \"Calculator\", \"category\": \"Electronics\", "
                "\"status\": \"confident\", \"candidates\": [{\"label\": \"Calculator\", \"score\": 1.0}]}}"
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
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["category"], "Electronics")
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["recognition_source"], "phash_cache")
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_cache_hit_falls_back_to_item_label_when_metadata_is_missing(self):
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 4,
            "metadata": {"classification": {"status": "confident"}},
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch(
                "services.recognition_router.build_selected_item_prediction",
                return_value={
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [],
                },
            ) as mock_build,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "phash_cache")
        self.assertTrue(result["cache_hit"])
        mock_build.assert_called_once_with("Calculator")
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_exact_cache_hit_with_malformed_metadata_and_valid_item_label_returns_normal_result(self):
        cached_record = {
            "id": "record-exact-fallback",
            "item_label": "Calculator",
            "phash_distance": 0,
            "metadata": "{\"classification\": {\"status\": \"unknown\", \"candidates\": []}}",
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch(
                "services.recognition_router.build_selected_item_prediction",
                return_value={
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [],
                },
            ) as mock_build,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["category"], "Electronics")
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["recognition_source"], "phash_cache")
        mock_build.assert_called_once_with("Calculator")
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_near_cache_hit_falls_back_to_item_label_when_metadata_is_malformed(self):
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 4,
            "metadata": "{\"classification\": {\"status\": \"confident\", \"candidates\": [1, 2]}}",
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch(
                "services.recognition_router.build_selected_item_prediction",
                return_value={
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [],
                },
            ) as mock_build,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["recognition_source"], "phash_cache")
        mock_build.assert_called_once_with("Calculator")
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_cache_hit_falls_back_to_item_label_when_metadata_is_structurally_valid_but_unusable(self):
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 4,
            "metadata": {
                "classification": {
                    "item": "",
                    "category": "Unknown",
                    "status": "unknown",
                    "candidates": [],
                }
            },
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch(
                "services.recognition_router.build_selected_item_prediction",
                return_value={
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [],
                },
            ) as mock_build,
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        self.assertEqual(result["status"], "confident")
        self.assertTrue(result["cache_hit"])
        mock_build.assert_called_once_with("Calculator")
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_cache_hit_supports_top_level_metadata_classification_shape(self):
        cached_record = {
            "item_label": "Calculator",
            "phash_distance": 4,
            "metadata": {
                "item": "Calculator",
                "category": "Electronics",
                "status": "confident",
                "candidates": [{"label": "Calculator", "score": 1.0}],
            },
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
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["candidates"], [("Calculator", 1.0)])
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["recognition_source"], "phash_cache")
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_unusable_cache_row_falls_through_to_vlm(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.88)],
        }
        cached_record = {
            "item_label": None,
            "phash_distance": 4,
            "metadata": "{\"classification\": {\"status\": \"confident\", \"candidates\": [1, 2]}}",
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=[0.1, 0.2],
            ) as mock_clip,
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                return_value=[],
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.88)], "margin": 0.88},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record"),
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        self.assertFalse(result["cache_hit"])
        mock_clip.assert_called_once()
        mock_vlm.assert_called_once()

    def test_empty_item_label_and_unknown_cached_classification_falls_through_to_vlm(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.88)],
        }
        cached_record = {
            "id": "record-empty-unknown",
            "item_label": "",
            "phash_distance": 0,
            "metadata": {
                "classification": {
                    "item": "",
                    "category": "Unknown",
                    "status": "unknown",
                    "candidates": [],
                }
            },
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=cached_record,
            ),
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=[0.1, 0.2],
            ) as mock_clip,
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                return_value=[],
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.88)], "margin": 0.88},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record"),
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        self.assertEqual(result["recognition_source"], "vlm")
        self.assertFalse(result["cache_hit"])
        mock_clip.assert_called_once()
        mock_vlm.assert_called_once()

    def test_cache_miss_runs_clip_shadow_search_and_still_saves_vlm_result(self):
        predictions = {"top_predictions": [("Calculator", 0.91)], "margin": 0.91}
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.91), ("Keyboard", 0.2)],
        }
        clip_embedding = [0.1, 0.2, 0.3]
        clip_candidates = [
            {"id": "shadow-1", "item_label": "Keyboard", "similarity": 0.97, "confidence": 0.7, "verified": True},
            {"id": "shadow-2", "item_label": "Mouse", "similarity": 0.92, "confidence": 0.4, "verified": False},
            {"id": "shadow-3", "item_label": "Monitor", "similarity": 0.9, "confidence": None, "verified": True},
            {"id": "shadow-4", "item_label": "Cable", "similarity": 0.88, "confidence": 0.2, "verified": False},
        ]

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=clip_embedding,
            ) as mock_clip,
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                return_value=clip_candidates,
            ) as mock_search,
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value=predictions,
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch(
                "services.recognition_router.cache_repository.save_recognition_record"
            ) as mock_save,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["recognition_source"], "vlm")
        self.assertEqual(result["item"], "Calculator")
        mock_clip.assert_called_once()
        mock_search.assert_called_once_with(clip_embedding)
        mock_vlm.assert_called_once()
        mock_save.assert_called_once_with(
            phash="deadbeef",
            clip_embedding=clip_embedding,
            item_label="Calculator",
            recognition_source="vlm",
            confidence=0.91,
            verified=False,
            metadata={
                "classification": {
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [["Calculator", 0.91], ["Keyboard", 0.2]],
                },
                "clip_shadow_candidates": [
                    {"id": "shadow-1", "item_label": "Keyboard", "similarity": 0.97, "confidence": 0.7, "verified": True},
                    {"id": "shadow-2", "item_label": "Mouse", "similarity": 0.92, "confidence": 0.4, "verified": False},
                    {"id": "shadow-3", "item_label": "Monitor", "similarity": 0.9, "confidence": None, "verified": True},
                ],
            },
        )

    def test_valid_upload_reads_bytes_once_and_reuses_them(self):
        predictions = {"top_predictions": [("Calculator", 0.91)], "margin": 0.91}
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
        clip_embedding = [0.1, 0.2]

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef") as mock_phash,
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=clip_embedding,
            ) as mock_clip,
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                return_value=[],
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value=predictions,
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record"),
        ):
            result = _run_recognize_item(file=upload_file)

        self.assertEqual(result["item"], "Calculator")
        upload_file.read.assert_awaited_once()
        mock_phash.assert_called_once_with(expected_bytes)
        mock_clip.assert_called_once_with(expected_bytes)
        mock_vlm.assert_called_once()

    def test_cache_lookup_failure_logs_and_continues_with_vlm(self):
        classification = {
            "item": "",
            "category": "Unknown",
            "status": "unknown",
            "candidates": [],
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                side_effect=RuntimeError("lookup failed"),
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
                return_value={"top_predictions": [], "margin": 0.0},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record"),
            patch("services.recognition_router.logger") as mock_logger,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "vlm")
        mock_vlm.assert_called_once()
        mock_logger.warning.assert_any_call("pHash cache lookup failed: %s", unittest.mock.ANY)

    def test_clip_generation_failure_still_returns_vlm_prediction_and_saves_without_embedding(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.83)],
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                side_effect=clip_service.ClipServiceError("model unavailable"),
            ),
            patch("services.recognition_router.cache_repository.find_similar_embeddings") as mock_search,
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.83)], "margin": 0.83},
            ),
            patch("services.recognition_router.classify", return_value=classification),
            patch(
                "services.recognition_router.cache_repository.save_recognition_record"
            ) as mock_save,
            patch("services.recognition_router.logger") as mock_logger,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        self.assertFalse(result["cache_hit"])
        mock_search.assert_not_called()
        mock_save.assert_called_once_with(
            phash="deadbeef",
            clip_embedding=None,
            item_label="Calculator",
            recognition_source="vlm",
            confidence=0.83,
            verified=False,
            metadata={
                "classification": {
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [["Calculator", 0.83]],
                }
            },
        )
        mock_logger.warning.assert_any_call(
            "CLIP embedding generation failed: %s",
            unittest.mock.ANY,
        )

    def test_clip_vector_search_failure_still_returns_vlm_prediction(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.83)],
        }
        clip_embedding = [0.1, 0.2]

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
            patch(
                "services.recognition_router.clip_service.create_clip_embedding",
                return_value=clip_embedding,
            ),
            patch(
                "services.recognition_router.cache_repository.find_similar_embeddings",
                side_effect=RuntimeError("vector search failed"),
            ),
            patch(
                "services.recognition_router.vlm_service.get_top_predictions",
                return_value={"top_predictions": [("Calculator", 0.83)], "margin": 0.83},
            ) as mock_vlm,
            patch("services.recognition_router.classify", return_value=classification),
            patch(
                "services.recognition_router.cache_repository.save_recognition_record"
            ) as mock_save,
            patch("services.recognition_router.logger") as mock_logger,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        mock_vlm.assert_called_once()
        mock_save.assert_called_once_with(
            phash="deadbeef",
            clip_embedding=clip_embedding,
            item_label="Calculator",
            recognition_source="vlm",
            confidence=0.83,
            verified=False,
            metadata={
                "classification": {
                    "item": "Calculator",
                    "category": "Electronics",
                    "status": "confident",
                    "candidates": [["Calculator", 0.83]],
                }
            },
        )
        mock_logger.warning.assert_any_call(
            "CLIP vector search failed: %s",
            unittest.mock.ANY,
        )

    def test_cache_save_failure_logs_and_still_returns_prediction(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.83)],
        }

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
                return_value={"top_predictions": [("Calculator", 0.83)], "margin": 0.83},
            ),
            patch("services.recognition_router.classify", return_value=classification),
            patch(
                "services.recognition_router.cache_repository.save_recognition_record",
                side_effect=RuntimeError("save failed"),
            ),
            patch("services.recognition_router.logger") as mock_logger,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["item"], "Calculator")
        self.assertFalse(result["cache_hit"])
        mock_logger.warning.assert_any_call(
            "Recognition cache save failed: %s",
            unittest.mock.ANY,
        )

    def test_cache_save_skips_blank_or_unknown_item_labels(self):
        classification = {
            "item": "",
            "category": "Unknown",
            "status": "unknown",
            "candidates": [],
        }

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
                return_value={"top_predictions": [], "margin": 0.0},
            ),
            patch("services.recognition_router.classify", return_value=classification),
            patch("services.recognition_router.cache_repository.save_recognition_record") as mock_save,
            patch("services.recognition_router.logger") as mock_logger,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["cache_hit"])
        mock_save.assert_not_called()
        mock_logger.info.assert_any_call(
            "Skipping recognition cache save because classification item_label was blank or unknown. item=%s status=%s category=%s",
            "",
            "unknown",
            "Unknown",
        )

    def test_selected_item_bypasses_phash_and_vlm(self):
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
            patch("services.recognition_router.clip_service.create_clip_embedding") as mock_clip,
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            result = _run_recognize_item(selected_item="Calculator")

        self.assertEqual(result, manual_classification)
        mock_build.assert_called_once_with("Calculator")
        mock_phash.assert_not_called()
        mock_clip.assert_not_called()
        mock_vlm.assert_not_called()

    def test_invalid_image_returns_http_400(self):
        invalid_file = UploadFile(filename="broken.jpg", file=io.BytesIO(b"not-an-image"))

        with self.assertRaises(HTTPException) as context:
            _run_recognize_item(file=invalid_file)

        self.assertEqual(context.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
