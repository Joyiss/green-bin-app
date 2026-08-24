import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from repositories import feedback_repository


class FeedbackRepositoryTests(unittest.TestCase):
    def setUp(self):
        feedback_repository._SUPABASE_CLIENT = None
        self.env_patch = patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "service-role-key",
            },
            clear=True,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(setattr, feedback_repository, "_SUPABASE_CLIENT", None)

    def test_scan_feedback_upserts_by_request_id(self):
        payload = {
            "request_id": "mobile-1",
            "item_name": "Bottle",
            "location": None,
            "guidance": {"action": "Recycle"},
            "rating": "positive",
            "reasons": [],
            "details": None,
            "submitted_at": "2026-08-24T00:00:00+00:00",
        }
        upsert = Mock()
        upsert.execute.return_value = SimpleNamespace(data=[payload])
        table = Mock()
        table.upsert.return_value = upsert
        client = Mock()
        client.table.return_value = table

        with patch(
            "repositories.feedback_repository.create_client", return_value=client
        ):
            row = feedback_repository.upsert_scan_feedback(payload)

        self.assertEqual(row["request_id"], "mobile-1")
        client.table.assert_called_once_with("scan_feedback")
        table.upsert.assert_called_once_with(payload, on_conflict="request_id")

    def test_database_error_is_normalized(self):
        table = Mock()
        table.upsert.side_effect = RuntimeError("permanent schema error")
        client = Mock()
        client.table.return_value = table
        with patch(
            "repositories.feedback_repository.create_client", return_value=client
        ):
            with self.assertRaises(feedback_repository.FeedbackRepositoryUnavailable):
                feedback_repository.upsert_scan_feedback({"request_id": "mobile-1"})

    def test_service_role_specific_environment_variable_is_supported(self):
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "preferred-service-role-key",
                "SUPABASE_KEY": "fallback-key",
            },
            clear=True,
        ), patch(
            "repositories.feedback_repository.create_client",
            return_value=Mock(),
        ) as create:
            feedback_repository._get_supabase_client()

        create.assert_called_once_with(
            "https://example.supabase.co", "preferred-service-role-key"
        )


if __name__ == "__main__":
    unittest.main()
