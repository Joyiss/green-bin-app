import unittest
from unittest.mock import patch

import requests
from fastapi.testclient import TestClient

from main import _env_flag, app, start_clip_warmup, warmup_phash_and_cache
from materials import MATERIAL_LABELS
from services.runtime_config import is_clip_enabled


class MaterialLabelsEndpointTests(unittest.TestCase):
    def test_material_labels_returns_supported_inventory(self):
        client = TestClient(app)

        response = client.get("/material_labels")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"labels": MATERIAL_LABELS})


class NearbyLocationsEndpointTests(unittest.TestCase):
    def test_legacy_local_rule_parameters_are_accepted_but_do_not_filter_results(self):
        client = TestClient(app)
        resolution = {
            "material_id": 20,
            "resolved_material_label": "Laptop",
            "search_skipped": False,
        }
        locations = [
            {"id": "tolbert", "name": "Tolbert Street Center"},
            {"id": "other", "name": "Another Electronics Site"},
        ]
        with (
            patch("main.resolve_earth911_material", return_value=resolution),
            patch("main._search_locations_for_material", return_value=locations),
        ):
            response = client.get(
                "/nearby_locations",
                params={
                    "item": "Laptop",
                    "lat": 34.2,
                    "lon": -84.1,
                    "jurisdiction_id": "forsyth_county_ga",
                    "local_rule_id": "fc_electronics",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["locations"], locations)

    def test_nearby_locations_uses_resolved_supported_material(self):
        client = TestClient(app)
        resolution = {
            "original_label": "computer mouse",
            "normalized_label": "computer mouse",
            "resolved_material_label": "Mouse",
            "matched_material_name": "Mouse",
            "material_id": 20,
            "match_type": "alias",
            "confidence": 0.98,
            "search_skipped": False,
        }
        locations = [
            {
                "id": "loc-1",
                "type": "Recycling Site",
                "name": "Drop-off Center",
                "address": "1 Main St",
                "status": "Open",
                "distance": "1.2 mi",
            }
        ]

        with (
            patch("main.resolve_earth911_material", return_value=resolution) as mock_resolve,
            patch("main._search_locations_for_material", return_value=locations) as mock_search,
        ):
            response = client.get(
                "/nearby_locations",
                params={
                    "item": "Mouse",
                    "normalized_item": "computer mouse",
                    "broad_category": "electronics",
                    "disposal_category": "Electronics",
                    "material_category": "Electronics",
                    "lat": 40.0,
                    "lon": -75.0,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["material_id"], 20)
        self.assertEqual(payload["reason"], None)
        self.assertFalse(payload["earth911_search_skipped"])
        self.assertEqual(payload["material_resolution"], resolution)
        self.assertEqual(payload["locations"], locations)
        mock_resolve.assert_called_once()
        self.assertEqual(mock_resolve.call_args.args[0], "computer mouse")
        self.assertEqual(
            mock_resolve.call_args.args[1],
            {
                "broad_category": "electronics",
                "disposal_category": "Electronics",
                "material_category": "Electronics",
            },
        )
        mock_search.assert_called_once_with(40.0, -75.0, 20)

    def test_nearby_locations_skips_search_for_unsupported_material(self):
        client = TestClient(app)
        resolution = {
            "original_label": "ceramic mug",
            "normalized_label": "ceramic mug",
            "resolved_material_label": None,
            "matched_material_name": None,
            "material_id": None,
            "match_type": "none",
            "confidence": 0.0,
            "search_skipped": True,
        }

        with (
            patch("main.resolve_earth911_material", return_value=resolution) as mock_resolve,
            patch("main._search_locations_for_material") as mock_search,
        ):
            response = client.get(
                "/nearby_locations",
                params={
                    "item": "Ceramic mug",
                    "normalized_item": "ceramic mug",
                    "lat": 40.0,
                    "lon": -75.0,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["material_id"], None)
        self.assertEqual(payload["locations"], [])
        self.assertEqual(payload["reason"], "unsupported_material")
        self.assertTrue(payload["earth911_search_skipped"])
        self.assertEqual(payload["material_resolution"], resolution)
        mock_resolve.assert_called_once()
        mock_search.assert_not_called()

    def test_earth911_failure_does_not_disclose_query_credentials(self):
        client = TestClient(app)
        private_value = "private-earth911-key"
        failure = requests.RequestException(
            f"https://api.earth911.com/search?api_key={private_value}",
        )

        with (
            patch("main.EARTH911_API_KEY", private_value),
            patch("main.EARTH911_SESSION.get", side_effect=failure),
        ):
            response = client.get("/get_material_id", params={"item": "battery"})

        self.assertEqual(response.status_code, 502)
        self.assertNotIn(private_value, response.text)
        self.assertEqual(
            response.json(),
            {"detail": {"error": "Nearby location service is unavailable."}},
        )

    def test_nearby_unexpected_failure_does_not_disclose_exception_text(self):
        client = TestClient(app)
        private_value = "private-backend-detail"

        with patch(
            "main.resolve_earth911_material",
            side_effect=RuntimeError(private_value),
        ):
            response = client.get(
                "/nearby_locations",
                params={"item": "battery", "lat": 40.0, "lon": -75.0},
            )

        self.assertEqual(response.status_code, 500)
        self.assertNotIn(private_value, response.text)
        self.assertEqual(
            response.json(),
            {"error": "Unable to load nearby locations right now."},
        )


class ClipWarmupStartupTests(unittest.TestCase):
    def test_clip_flag_defaults_true_and_handles_values(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(is_clip_enabled())
            self.assertTrue(_env_flag("ENABLE_CLIP", default=True))
        for value in ("1", "true", "YES", "on"):
            with patch.dict("os.environ", {"ENABLE_CLIP": value}, clear=True):
                self.assertTrue(_env_flag("ENABLE_CLIP", default=True))
        for value in ("0", "false", "NO", "off"):
            with patch.dict("os.environ", {"ENABLE_CLIP": value}, clear=True):
                self.assertFalse(_env_flag("ENABLE_CLIP", default=True))
        with patch.dict("os.environ", {"ENABLE_CLIP": "invalid"}, clear=True):
            self.assertTrue(_env_flag("ENABLE_CLIP", default=True))

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
            patch.dict("os.environ", {"ENABLE_CLIP": "true", "ENABLE_CLIP_WARMUP": "true"}, clear=True),
            patch("services.clip_service.start_background_warmup") as mock_start,
        ):
            start_clip_warmup()
        mock_start.assert_called_once_with()

    def test_startup_skips_warmup_when_clip_disabled(self):
        with patch.dict("os.environ", {"ENABLE_CLIP": "false"}, clear=True):
            with self.assertLogs("main", level="INFO") as logs:
                start_clip_warmup()

        combined = "\n".join(logs.output)
        self.assertIn("CLIP feature enabled=False", combined)
        self.assertIn("reason=clip_disabled", combined)

    def test_startup_skips_warmup_when_warmup_disabled(self):
        with (
            patch.dict("os.environ", {"ENABLE_CLIP": "true", "ENABLE_CLIP_WARMUP": "false"}, clear=True),
            patch("services.clip_service.start_background_warmup") as mock_start,
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
