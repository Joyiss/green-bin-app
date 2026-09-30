import unittest
from unittest.mock import MagicMock, patch

from repositories import guidance_repository
from services import guidance_service
from services.operational_logging import log_operation


class PrivacyLoggingTests(unittest.TestCase):
    def test_operational_log_contains_only_safe_fields_and_masks_request_id(self):
        with self.assertLogs("greenbin.operations", level="INFO") as logs:
            log_operation(
                request_id="private-request-identifier",
                route="/predict",
                stage="guidance",
                status=200,
                outcome="completed",
                duration_ms=12.3,
            )

        combined = "\n".join(logs.output)
        self.assertNotIn("private-request-identifier", combined)
        self.assertRegex(combined, r"request_id=rid-[0-9a-f]{16}")
        self.assertIn("route=/predict", combined)
        self.assertIn("stage=guidance", combined)
        self.assertIn("status=200", combined)
        self.assertIn("outcome=completed", combined)
        self.assertIn("duration_ms=12.3", combined)

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
