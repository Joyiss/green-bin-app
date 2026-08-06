import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from repositories import feedback_repository


class FeedbackRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.context = {
            "request_id": "mobile-original-1",
            "correction_request_id": "mobile-correction-2",
            "corrected_item": "Metal Cup",
        }

    def test_item_thumbs_down_is_recorded_without_correction(self):
        with (
            patch(
                "routes.feedback.feedback_repository.get_feedback_context",
                return_value=self.context,
            ),
            patch(
                "routes.feedback.feedback_repository.update_user_feedback",
                return_value=self.context,
            ) as mock_update,
        ):
            response = self.client.put(
                "/feedback/mobile-original-1",
                json={"item_correct": False},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request_id"], "mobile-original-1")
        mock_update.assert_called_once_with(
            "mobile-original-1", {"item_correct": False}
        )

    def test_completed_correction_must_match_trusted_context(self):
        with patch(
            "routes.feedback.feedback_repository.get_feedback_context",
            return_value=self.context,
        ), patch(
            "routes.feedback.feedback_repository.get_correction_context",
            return_value={
                "request_id": "mobile-correction-2",
                "original_request_id": "mobile-original-1",
                "corrected_item": "Metal Cup",
            },
        ), patch(
            "routes.feedback.feedback_repository.update_user_feedback",
            return_value=self.context,
        ) as mock_update:
            accepted = self.client.put(
                "/feedback/mobile-original-1",
                json={
                    "item_correct": False,
                    "prediction_changed": True,
                    "corrected_item": "Metal Cup",
                    "correction_request_id": "mobile-correction-2",
                },
            )
            rejected = self.client.put(
                "/feedback/mobile-original-1",
                json={
                    "prediction_changed": True,
                    "corrected_item": "Plastic Cup",
                    "correction_request_id": "mobile-correction-2",
                },
            )

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(mock_update.call_count, 1)

    def test_diagnostic_and_private_fields_are_rejected(self):
        response = self.client.put(
            "/feedback/mobile-original-1",
            json={
                "item_correct": False,
                "recognition_confidence": {"level": "low"},
                "photo": "base64",
                "location": {"lat": 1, "lon": 2},
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_unknown_correction_request_is_rejected(self):
        with (
            patch(
                "routes.feedback.feedback_repository.get_feedback_context",
                return_value=self.context,
            ),
            patch(
                "routes.feedback.feedback_repository.get_correction_context",
                side_effect=feedback_repository.FeedbackContextNotFound,
            ),
            patch(
                "routes.feedback.feedback_repository.update_user_feedback",
            ) as mock_update,
        ):
            response = self.client.put(
                "/feedback/mobile-original-1",
                json={
                    "prediction_changed": True,
                    "corrected_item": "Metal Cup",
                    "correction_request_id": "unknown-correction",
                },
            )

        self.assertEqual(response.status_code, 409)
        mock_update.assert_not_called()

    def test_unavailable_storage_returns_retryable_error(self):
        with patch(
            "routes.feedback.feedback_repository.get_feedback_context",
            side_effect=feedback_repository.FeedbackRepositoryUnavailable,
        ):
            response = self.client.put(
                "/feedback/mobile-original-1",
                json={"guidance_helpful": True},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["error"], "feedback_unavailable")

    def test_scan_feedback_upserts_complete_negative_submission(self):
        stored = {}

        def capture(payload):
            stored.update(payload)
            return payload

        with patch(
            "routes.feedback.feedback_repository.upsert_scan_feedback",
            side_effect=capture,
        ):
            response = self.client.put(
                "/scan-feedback/mobile-original-1",
                json={
                    "request_id": "mobile-original-1",
                    "item_name": "Composition Book",
                    "location": "Los Angeles, California",
                    "guidance": {
                        "action": "Recycle",
                        "steps": [{"title": "Keep it clean and dry"}],
                        "references": [{"title": "LA Sanitation"}],
                    },
                    "rating": "negative",
                    "reasons": [
                        "item_identified_incorrectly",
                        "local_information_inaccurate",
                    ],
                    "details": "The blue-bin rule changed.",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(stored["request_id"], "mobile-original-1")
        self.assertEqual(stored["rating"], "negative")
        self.assertEqual(len(stored["reasons"]), 2)
        self.assertEqual(stored["guidance"]["references"][0]["title"], "LA Sanitation")
        self.assertIn("submitted_at", stored)

    def test_positive_scan_feedback_forces_empty_reasons_and_null_details(self):
        with patch(
            "routes.feedback.feedback_repository.upsert_scan_feedback",
            return_value={"request_id": "mobile-original-1"},
        ) as upsert:
            response = self.client.put(
                "/scan-feedback/mobile-original-1",
                json={
                    "request_id": "mobile-original-1",
                    "item_name": "Composition Book",
                    "location": None,
                    "guidance": {"action": "Recycle"},
                    "rating": "positive",
                    "reasons": ["other"],
                    "details": "This must not be retained.",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = upsert.call_args.args[0]
        self.assertEqual(payload["reasons"], [])
        self.assertIsNone(payload["details"])

    def test_scan_feedback_rejects_request_id_mismatch_and_unknown_reason(self):
        base_payload = {
            "request_id": "different-request",
            "item_name": "Book",
            "location": None,
            "guidance": {"action": "Recycle"},
            "rating": "negative",
            "reasons": [],
            "details": None,
        }
        mismatch = self.client.put(
            "/scan-feedback/mobile-original-1",
            json=base_payload,
        )
        unknown_reason = self.client.put(
            "/scan-feedback/mobile-original-1",
            json={
                **base_payload,
                "request_id": "mobile-original-1",
                "reasons": ["made_up_reason"],
            },
        )

        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(unknown_reason.status_code, 422)


if __name__ == "__main__":
    unittest.main()
