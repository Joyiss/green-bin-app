import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from services import scan_rate_limit_service


class ServiceProviderRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"X-GreenBin-Client-Id": "raw-installation-id"}

    def test_client_id_is_required(self):
        response = self.client.get("/service-providers/current", params={"city": "A", "state": "B"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["error"], "client_id_required")

    @patch("routes.service_providers.service_provider_repository.current_restriction", return_value=None)
    @patch("routes.service_providers.service_provider_repository.current_provider", return_value=None)
    def test_current_is_scoped_to_hash_and_requested_location(self, current, restriction):
        response = self.client.get(
            "/service-providers/current",
            params={"city": " Atlanta ", "county": "Fulton", "state": "Georgia"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["provider"])
        self.assertEqual(
            current.call_args.kwargs["client_id_hash"],
            scan_rate_limit_service.hash_client_id("raw-installation-id"),
        )
        self.assertNotIn("raw-installation-id", str(current.call_args.kwargs))
        self.assertEqual(current.call_args.kwargs["county"], "Fulton")

    @patch("routes.service_providers.service_provider_repository.current_restriction", return_value=None)
    @patch("routes.service_providers.service_provider_repository.current_provider")
    def test_location_change_does_not_return_previous_provider(self, current, restriction):
        current.side_effect = [{"id": "old"}, None]
        first = self.client.get(
            "/service-providers/current", params={"city": "Atlanta", "state": "Georgia"},
            headers=self.headers,
        )
        second = self.client.get(
            "/service-providers/current", params={"city": "Seattle", "state": "Washington"},
            headers=self.headers,
        )
        self.assertEqual(first.json()["provider"], {"id": "old"})
        self.assertIsNone(second.json()["provider"])
        self.assertEqual(current.call_args.kwargs["city"], "Seattle")

    @patch("routes.service_providers.service_provider_verification_service.verify_provider")
    def test_cooldown_is_sanitized(self, verify):
        from services.service_provider_verification_service import ProviderCooldown
        verify.side_effect = ProviderCooldown("failed_attempts", "2026-08-17T00:00:00Z")
        response = self.client.post(
            "/service-providers/verify",
            json={"service_name": "Provider", "location": {"city": "A", "state": "B"}},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"]["cooldown_reason"], "failed_attempts")


if __name__ == "__main__":
    unittest.main()
