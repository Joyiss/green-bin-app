import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

from repositories import scan_usage_repository
from services import scan_rate_limit_service


class ScanRateLimitServiceTests(unittest.TestCase):
    def test_scan_limits_default_to_5_daily_and_20_monthly(self):
        for invalid_value in (None, "invalid", "0", "-4"):
            env = {}
            if invalid_value is not None:
                env = {
                    "DAILY_SCAN_LIMIT": invalid_value,
                    "MONTHLY_SCAN_LIMIT": invalid_value,
                }
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(scan_rate_limit_service.get_daily_scan_limit(), 5)
                self.assertEqual(scan_rate_limit_service.get_monthly_scan_limit(), 20)

    def test_missing_client_id_preserves_existing_configuration(self):
        with patch.dict(os.environ, {"REQUIRE_SCAN_CLIENT_ID": "false"}, clear=True):
            self.assertIsNone(scan_rate_limit_service.check_scan_limits(None))
            self.assertIsNone(scan_rate_limit_service.consume_scan(None))
        with patch.dict(os.environ, {"REQUIRE_SCAN_CLIENT_ID": "true"}, clear=True):
            with self.assertRaises(scan_rate_limit_service.MissingScanClientIdError):
                scan_rate_limit_service.check_scan_limits(None)

    def test_preflight_rejects_daily_limit(self):
        usage = scan_usage_repository.ScanUsageSnapshot(daily_count=5, monthly_count=11)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("services.scan_rate_limit_service._today_utc", return_value=date(2026, 7, 9)),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.get_scan_usage",
                return_value=usage,
            ),
        ):
            with self.assertRaises(
                scan_rate_limit_service.DailyScanLimitReachedError
            ) as context:
                scan_rate_limit_service.check_scan_limits("install-123")
        self.assertEqual(context.exception.metadata.daily_scans_remaining, 0)
        self.assertEqual(context.exception.metadata.monthly_scans_remaining, 9)
        self.assertEqual(context.exception.metadata.daily_reset_at, "2026-07-10T00:00:00Z")

    def test_preflight_rejects_monthly_limit(self):
        usage = scan_usage_repository.ScanUsageSnapshot(daily_count=2, monthly_count=20)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("services.scan_rate_limit_service._today_utc", return_value=date(2026, 7, 9)),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.get_scan_usage",
                return_value=usage,
            ),
        ):
            with self.assertRaises(
                scan_rate_limit_service.MonthlyScanLimitReachedError
            ) as context:
                scan_rate_limit_service.check_scan_limits("install-123")
        self.assertEqual(context.exception.metadata.daily_scans_remaining, 3)
        self.assertEqual(context.exception.metadata.monthly_scans_remaining, 0)
        self.assertEqual(context.exception.metadata.monthly_reset_at, "2026-08-01T00:00:00Z")

    def test_accepted_scan_returns_both_remaining_counts(self):
        reservation = scan_usage_repository.ScanUsageReservation(
            allowed=True,
            daily_count=3,
            monthly_count=14,
            limit_period=None,
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("services.scan_rate_limit_service._today_utc", return_value=date(2026, 7, 9)),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.reserve_scan_usage",
                return_value=reservation,
            ),
        ):
            metadata = scan_rate_limit_service.consume_scan("install-123")
        self.assertEqual(metadata.daily_scans_remaining, 2)
        self.assertEqual(metadata.monthly_scans_remaining, 6)

    def test_daily_and_monthly_resets_follow_utc_boundaries(self):
        metadata = scan_rate_limit_service._metadata_for_counts(
            daily_count=0,
            monthly_count=0,
            daily_limit=5,
            monthly_limit=20,
            usage_date=date(2026, 12, 31),
        )
        self.assertEqual(metadata.daily_reset_at, "2027-01-01T00:00:00Z")
        self.assertEqual(metadata.monthly_reset_at, "2027-01-01T00:00:00Z")

    def test_concurrent_requests_accept_only_one_last_available_scan(self):
        lock = threading.Lock()
        counts = {"daily": 4, "monthly": 19}

        def reserve_once(**_kwargs):
            with lock:
                if counts["daily"] >= 5:
                    return scan_usage_repository.ScanUsageReservation(
                        False, counts["daily"], counts["monthly"], "daily"
                    )
                counts["daily"] += 1
                counts["monthly"] += 1
                return scan_usage_repository.ScanUsageReservation(
                    True, counts["daily"], counts["monthly"], None
                )

        def consume():
            try:
                scan_rate_limit_service.consume_scan("install-123")
                return "accepted"
            except scan_rate_limit_service.DailyScanLimitReachedError:
                return "rejected"

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "services.scan_rate_limit_service.scan_usage_repository.reserve_scan_usage",
                side_effect=reserve_once,
            ),
            ThreadPoolExecutor(max_workers=8) as executor,
        ):
            results = list(executor.map(lambda _index: consume(), range(8)))
        self.assertEqual(results.count("accepted"), 1)
        self.assertEqual(results.count("rejected"), 7)
        self.assertEqual(counts, {"daily": 5, "monthly": 20})


if __name__ == "__main__":
    unittest.main()
