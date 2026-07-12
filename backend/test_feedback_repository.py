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
                "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
            },
            clear=True,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(setattr, feedback_repository, "_SUPABASE_CLIENT", None)

    def test_original_context_upserts_by_request_id(self):
        payload = {
            "request_id": "mobile-1",
            "original_prediction": "Bottle",
            "original_status": "confident",
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
            self.assertTrue(feedback_repository.store_original_context(payload))

        table.upsert.assert_called_once_with(payload, on_conflict="request_id")

    def test_user_feedback_updates_only_supplied_fields(self):
        update = Mock()
        eq = Mock()
        eq.execute.return_value = SimpleNamespace(data=[{"request_id": "mobile-1"}])
        update.eq.return_value = eq
        table = Mock()
        table.update.return_value = update
        client = Mock()
        client.table.return_value = table

        with patch(
            "repositories.feedback_repository.create_client", return_value=client
        ):
            row = feedback_repository.update_user_feedback(
                "mobile-1", {"item_correct": False}
            )

        self.assertEqual(row["request_id"], "mobile-1")
        table.update.assert_called_once_with({"item_correct": False})
        update.eq.assert_called_once_with("request_id", "mobile-1")

    def test_correction_context_is_stored_separately_from_original(self):
        payload = {
            "request_id": "mobile-correction-2",
            "original_request_id": "mobile-original-1",
            "corrected_item": "Metal Cup",
            "guidance_source": "llm_general_fallback",
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
            stored = feedback_repository.attach_correction_context(
                original_request_id="mobile-original-1",
                correction_request_id="mobile-correction-2",
                corrected_item="Metal Cup",
                guidance_context={"guidance_source": "llm_general_fallback"},
            )

        self.assertTrue(stored)
        client.table.assert_called_once_with("closed_test_correction_context")
        table.upsert.assert_called_once_with(payload, on_conflict="request_id")

    def test_feedback_repository_requires_service_role_key(self):
        with patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": ""}, clear=False):
            with self.assertRaises(feedback_repository.FeedbackRepositoryUnavailable):
                feedback_repository.get_feedback_context("mobile-1")


if __name__ == "__main__":
    unittest.main()
