import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import _env_flag, app, start_clip_warmup, warmup_phash_and_cache
from materials import MATERIAL_LABELS


class MaterialLabelsEndpointTests(unittest.TestCase):
    def test_material_labels_returns_supported_inventory(self):
        client = TestClient(app)

        response = client.get("/material_labels")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"labels": MATERIAL_LABELS})


class ClipWarmupStartupTests(unittest.TestCase):
    def test_warmup_flag_defaults_true_and_handles_values(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(_env_flag("ENABLE_CLIP_WARMUP", default=True))
        for value in ("1", "true", "YES", "on"):
            with patch.dict("os.environ", {"ENABLE_CLIP_WARMUP": value}, clear=True):
                self.assertTrue(_env_flag("ENABLE_CLIP_WARMUP", default=True))
        for value in ("0", "false", "NO", "off"):
            with patch.dict("os.environ", {"ENABLE_CLIP_WARMUP": value}, clear=True):
                self.assertFalse(_env_flag("ENABLE_CLIP_WARMUP", default=True))
        with patch.dict("os.environ", {"ENABLE_CLIP_WARMUP": "invalid"}, clear=True):
            self.assertTrue(_env_flag("ENABLE_CLIP_WARMUP", default=True))

    def test_startup_schedules_warmup_when_enabled(self):
        with (
            patch.dict("os.environ", {"ENABLE_CLIP_WARMUP": "true"}, clear=True),
            patch("main.clip_service.start_background_warmup") as mock_start,
        ):
            start_clip_warmup()
        mock_start.assert_called_once_with()

    def test_startup_skips_warmup_when_disabled(self):
        with (
            patch.dict("os.environ", {"ENABLE_CLIP_WARMUP": "false"}, clear=True),
            patch("main.clip_service.start_background_warmup") as mock_start,
        ):
            start_clip_warmup()
        mock_start.assert_not_called()


class PHashWarmupStartupTests(unittest.TestCase):
    def test_startup_warms_phash_then_exact_cache_lookup(self):
        call_order = []
        with (
            patch(
                "main.phash_service.warmup_phash",
                side_effect=lambda: call_order.append("phash"),
            ) as mock_phash,
            patch(
                "main.cache_repository.warmup_exact_phash_lookup",
                side_effect=lambda: call_order.append("cache"),
            ) as mock_cache,
        ):
            warmup_phash_and_cache()

        mock_phash.assert_called_once_with()
        mock_cache.assert_called_once_with()
        self.assertEqual(call_order, ["phash", "cache"])


if __name__ == "__main__":
    unittest.main()
