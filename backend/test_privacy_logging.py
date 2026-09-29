import unittest
from unittest.mock import MagicMock, patch

from repositories import guidance_repository
from services import guidance_service


class PrivacyLoggingTests(unittest.TestCase):
    def test_failed_guidance_lookup_does_not_log_item_or_exception_text(self):
        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = RuntimeError(
            "Private item name"
        )
        with (
            patch.object(guidance_repository, "_get_supabase_client", return_value=client),
            self.assertLogs("repositories.guidance_repository", level="WARNING") as logs,
        ):
            self.assertIsNone(guidance_repository.get_guidance_by_item_label_key("Private item name"))
        self.assertNotIn("Private item name", "\n".join(logs.output))

    def test_failed_retrieval_does_not_log_item_or_exception_text(self):
        with (
            patch.object(
                guidance_service.guidance_retrieval_service,
                "retrieve_guidance_chunks",
                side_effect=RuntimeError("Private item name"),
            ),
            self.assertLogs("services.guidance_service", level="WARNING") as logs,
        ):
            self.assertEqual(
                guidance_service._lookup_json_guidance(
                    {}, retrieval_inputs={"item_label": "Private item name"}
                ),
                [],
            )
        self.assertNotIn("Private item name", "\n".join(logs.output))
