import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from repositories import feedback_repository


class FeedbackRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.payload = {
            "request_id": "mobile-original-1",
            "item_name": "Composition Book",
            "location": "Los Angeles, California",
            "guidance": {
                "action": "Recycle",
                "steps": [{"title": "Keep it clean and dry"}],
            },
            "rating": "negative",
            "reasons": ["local_information_inaccurate"],
            "details": "The local rule changed.",
        }

    def test_successful_feedback_uses_scan_feedback_payload(self):
        with patch(
            "routes.feedback.feedback_repository.upsert_scan_feedback",
            side_effect=lambda payload: payload,
        ) as upsert:
            response = self.client.put("/feedback/mobile-original-1", json=self.payload)

        self.assertEqual(response.status_code, 200)
        stored = upsert.call_args.args[0]
        self.assertEqual(stored["request_id"], "mobile-original-1")
        self.assertEqual(stored["rating"], "negative")
        self.assertIn("submitted_at", stored)
        self.assertEqual(set(stored), {
            "request_id", "item_name", "location", "guidance", "rating",
            "reasons", "details", "submitted_at",
        })

    def test_updating_previous_feedback_uses_same_request_id(self):
        stored_payloads = []
        with patch(
            "routes.feedback.feedback_repository.upsert_scan_feedback",
            side_effect=lambda payload: stored_payloads.append(payload) or payload,
        ):
            first = self.client.put("/feedback/mobile-original-1", json=self.payload)
            second = self.client.put(
                "/feedback/mobile-original-1",
                json={**self.payload, "rating": "positive", "reasons": ["other"]},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual([row["request_id"] for row in stored_payloads], [
            "mobile-original-1", "mobile-original-1",
        ])
        self.assertEqual(stored_payloads[1]["rating"], "positive")
        self.assertEqual(stored_payloads[1]["reasons"], [])
        self.assertIsNone(stored_payloads[1]["details"])

    def test_missing_or_mismatched_request_id_is_controlled(self):
        missing_path = self.client.put("/feedback/", json=self.payload)
        missing_body = self.client.put(
            "/feedback/mobile-original-1",
            json={key: value for key, value in self.payload.items() if key != "request_id"},
        )
        mismatch = self.client.put(
            "/feedback/mobile-original-1",
            json={**self.payload, "request_id": "another-request"},
        )

        self.assertEqual(missing_path.status_code, 404)
        self.assertEqual(missing_body.status_code, 422)
        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(mismatch.json()["detail"]["error"], "request_id_mismatch")

    def test_database_failure_returns_controlled_response(self):
        with patch(
            "routes.feedback.feedback_repository.upsert_scan_feedback",
            side_effect=feedback_repository.FeedbackRepositoryUnavailable,
        ):
            response = self.client.put("/feedback/mobile-original-1", json=self.payload)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["error"], "feedback_unavailable")

    def test_legacy_scan_feedback_path_uses_same_handler(self):
        with patch(
            "routes.feedback.feedback_repository.upsert_scan_feedback",
            return_value={"request_id": "mobile-original-1"},
        ) as upsert:
            response = self.client.put(
                "/scan-feedback/mobile-original-1",
                json=self.payload,
            )

        self.assertEqual(response.status_code, 200)
        upsert.assert_called_once()


if __name__ == "__main__":
    unittest.main()
