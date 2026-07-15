import os
import unittest
from datetime import date
from unittest.mock import patch

from services import scan_rate_limit_service
from repositories import scan_usage_repository


class ScanRateLimitServiceTests(unittest.TestCase):
    def test_daily_scan_limit_defaults_to_40_for_missing_or_invalid_values(self):
        for env in (
            {},
            {"DAILY_SCAN_LIMIT": "invalid"},
            {"DAILY_SCAN_LIMIT": "0"},
            {"DAILY_SCAN_LIMIT": "-4"},
        ):
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(scan_rate_limit_service.get_daily_scan_limit(), 40)

    def test_require_scan_client_id_defaults_false(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(scan_rate_limit_service.require_scan_client_id())
        with patch.dict(os.environ, {"REQUIRE_SCAN_CLIENT_ID": "true"}, clear=True):
            self.assertTrue(scan_rate_limit_service.require_scan_client_id())

    def test_missing_client_id_is_allowed_when_not_required(self):
        with (
            patch.dict(os.environ, {"REQUIRE_SCAN_CLIENT_ID": "false"}, clear=True),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.increment_daily_scan_usage"
            ) as mock_increment,
        ):
            self.assertIsNone(scan_rate_limit_service.consume_daily_scan(None))

        mock_increment.assert_not_called()

    def test_missing_client_id_raises_when_required(self):
        with patch.dict(os.environ, {"REQUIRE_SCAN_CLIENT_ID": "true"}, clear=True):
            with self.assertRaises(scan_rate_limit_service.MissingScanClientIdError):
                scan_rate_limit_service.consume_daily_scan(None)

    def test_first_valid_request_under_limit_hashes_client_and_returns_metadata(self):
        usage_date = date(2026, 7, 9)
        with (
            patch.dict(
                os.environ,
                {"REQUIRE_SCAN_CLIENT_ID": "true", "DAILY_SCAN_LIMIT": "40"},
                clear=True,
            ),
            patch("services.scan_rate_limit_service._today_utc", return_value=usage_date),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.increment_daily_scan_usage",
                return_value=1,
            ) as mock_increment,
        ):
            metadata = scan_rate_limit_service.consume_daily_scan("install-123")

        self.assertEqual(metadata.daily_limit, 40)
        self.assertEqual(metadata.scans_remaining, 39)
        self.assertEqual(metadata.reset_at, "2026-07-10T00:00:00Z")
        mock_increment.assert_called_once_with(
            client_id_hash=scan_rate_limit_service.hash_client_id("install-123"),
            usage_date=usage_date,
            daily_limit=40,
        )
        self.assertNotEqual(
            mock_increment.call_args.kwargs["client_id_hash"],
            "install-123",
        )

    def test_request_with_scans_remaining_returns_remaining_count(self):
        with (
            patch.dict(os.environ, {"DAILY_SCAN_LIMIT": "40"}, clear=True),
            patch("services.scan_rate_limit_service._today_utc", return_value=date(2026, 7, 9)),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.increment_daily_scan_usage",
                return_value=17,
            ),
        ):
            metadata = scan_rate_limit_service.consume_daily_scan("install-123")

        self.assertEqual(metadata.scans_remaining, 23)

    def test_request_at_limit_raises_with_429_metadata(self):
        with (
            patch.dict(os.environ, {"DAILY_SCAN_LIMIT": "40"}, clear=True),
            patch("services.scan_rate_limit_service._today_utc", return_value=date(2026, 7, 9)),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.increment_daily_scan_usage",
                side_effect=scan_usage_repository.ScanUsageLimitReachedError,
            ),
        ):
            with self.assertRaises(scan_rate_limit_service.DailyScanLimitReachedError) as context:
                scan_rate_limit_service.consume_daily_scan("install-123")

        self.assertEqual(context.exception.metadata.daily_limit, 40)
        self.assertEqual(context.exception.metadata.scans_remaining, 0)
        self.assertEqual(context.exception.metadata.reset_at, "2026-07-10T00:00:00Z")

    def test_usage_tracking_failure_fails_closed_only_when_client_id_required(self):
        with (
            patch.dict(os.environ, {"REQUIRE_SCAN_CLIENT_ID": "false"}, clear=True),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.increment_daily_scan_usage",
                side_effect=scan_usage_repository.ScanUsageRepositoryError("network down"),
            ),
        ):
            self.assertIsNone(scan_rate_limit_service.consume_daily_scan("install-123"))

        with (
            patch.dict(os.environ, {"REQUIRE_SCAN_CLIENT_ID": "true"}, clear=True),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.increment_daily_scan_usage",
                side_effect=scan_usage_repository.ScanUsageRepositoryError("network down"),
            ),
        ):
            with self.assertRaises(scan_rate_limit_service.ScanRateLimitUnavailableError):
                scan_rate_limit_service.consume_daily_scan("install-123")


if __name__ == "__main__":
    unittest.main()
