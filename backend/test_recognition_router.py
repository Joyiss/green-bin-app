import io
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException, UploadFile
from PIL import Image

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
        mock_vlm.assert_not_called()
        mock_save.assert_not_called()

    def test_cache_hit_falls_back_to_item_label_when_metadata_is_missing(self):
        cached_record = {
            "item_label": "Calculator",
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
            patch("services.recognition_router.vlm_service.get_top_predictions") as mock_vlm,
        ):
            result = _run_recognize_item(file=_make_upload_file())

        self.assertEqual(result["recognition_source"], "phash_cache")
        self.assertTrue(result["cache_hit"])
        mock_build.assert_called_once_with("Calculator")
        mock_vlm.assert_not_called()

    def test_cache_miss_calls_vlm_and_saves_recognition_record(self):
        predictions = {"top_predictions": [("Calculator", 0.91)], "margin": 0.91}
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.91), ("Keyboard", 0.2)],
        }

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef"),
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
            ),
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
        mock_vlm.assert_called_once()
        mock_save.assert_called_once_with(
            phash="deadbeef",
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
                }
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

        with (
            patch("services.recognition_router.phash_service.create_phash", return_value="deadbeef") as mock_phash,
            patch(
                "services.recognition_router.cache_repository.find_nearest_phash_match",
                return_value=None,
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
        mock_logger.exception.assert_called_once_with("pHash cache lookup failed.")

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
        mock_logger.exception.assert_called_once_with("pHash cache save failed.")

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


if __name__ == "__main__":
    unittest.main()
