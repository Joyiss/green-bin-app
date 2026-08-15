import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from repositories import scan_usage_repository


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self.data = data
        self.filters = []

    def select(self, columns):
        self.columns = columns
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def lt(self, column, value):
        self.filters.append(("lt", column, value))
        return self

    def execute(self):
        return _Response(self.data)


class _Client:
    def __init__(self, *, table_data=None, rpc_data=None):
        self.table_query = _Query(table_data or [])
        self.rpc_query = _Query(rpc_data or [])
        self.rpc_call = None

    def table(self, name):
        self.table_name = name
        return self.table_query

    def rpc(self, name, params):
        self.rpc_call = (name, params)
        return self.rpc_query


class ScanUsageRepositoryTests(unittest.TestCase):
    def test_usage_snapshot_uses_only_the_current_utc_month(self):
        client = _Client(
            table_data=[
                {"usage_date": "2026-07-01", "scan_count": 5},
                {"usage_date": "2026-07-09", "scan_count": 3},
            ]
        )
        with patch(
            "repositories.scan_usage_repository._get_supabase_client",
            return_value=client,
        ):
            usage = scan_usage_repository.get_scan_usage(
                client_id_hash="hashed-client",
                usage_date=date(2026, 7, 9),
            )

        self.assertEqual(usage.daily_count, 3)
        self.assertEqual(usage.monthly_count, 8)
        self.assertEqual(client.table_name, "scan_usage_daily")
        self.assertIn(("gte", "usage_date", "2026-07-01"), client.table_query.filters)
        self.assertIn(("lt", "usage_date", "2026-08-01"), client.table_query.filters)

    def test_atomic_reservation_passes_both_limits_to_database(self):
        client = _Client(
            rpc_data=[
                {
                    "allowed": True,
                    "limit_period": None,
                    "daily_count": 2,
                    "monthly_count": 7,
                }
            ]
        )
        with patch(
            "repositories.scan_usage_repository._get_supabase_client",
            return_value=client,
        ):
            reservation = scan_usage_repository.reserve_scan_usage(
                client_id_hash="hashed-client",
                usage_date=date(2026, 7, 9),
                daily_limit=5,
                monthly_limit=20,
            )

        self.assertTrue(reservation.allowed)
        self.assertEqual(reservation.daily_count, 2)
        self.assertEqual(reservation.monthly_count, 7)
        self.assertEqual(
            client.rpc_call,
            (
                "reserve_scan_usage",
                {
                    "p_client_id_hash": "hashed-client",
                    "p_daily_limit": 5,
                    "p_monthly_limit": 20,
                    "p_now": "2026-07-09T00:00:00+00:00",
                },
            ),
        )

    def test_database_reservation_serializes_concurrent_user_requests(self):
        migration = (
            Path(__file__).parent / "migrations" / "006_scan_usage_limits.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("pg_advisory_xact_lock", migration)
        self.assertIn("v_daily_count >= p_daily_limit", migration)
        self.assertIn("v_monthly_count >= p_monthly_limit", migration)
        self.assertIn("scan_count = scan_count + 1", migration)


if __name__ == "__main__":
    unittest.main()
