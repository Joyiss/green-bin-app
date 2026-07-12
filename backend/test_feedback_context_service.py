import unittest
from unittest.mock import patch

from services import feedback_context_service


class FeedbackContextServiceTests(unittest.TestCase):
    def test_original_context_is_allowlisted_and_excludes_raw_model_data(self):
        classification = {
            "item": "Plastic bottle",
            "status": "confident",
            "recognition_source": "vlm_open",
            "cache_hit": False,
            "recognition_confidence": {
                "level": "medium",
                "score": 0.71,
                "reason_codes": ["unknown_resin"],
            },
            "recognition_details": {
                "raw_output": "raw model output must not survive",
                "visual_observations": [{"aspect": "construction"}],
            },
        }
        response = {
            "item": "Plastic Bottle",
            "disposal_action": "trash",
            "guidance_source": "llm_general_fallback",
            "clarification": None,
            "guidance_confidence": {
                "level": "medium",
                "score": 0.64,
                "reason_codes": ["practical_low_risk_fallback"],
                "applicability": {"conditional_chunk_ids": ["plastic-1"]},
            },
            "guidance_metadata": {
                "retrieved_chunk_ids": ["plastic-1"],
                "conditional_chunk_ids": ["plastic-1"],
                "applicability_reason_codes": {
                    "plastic-1": ["local_acceptance_unknown"]
                },
                "final_generation_path": "general_fallback",
                "consistency_guard_triggered": True,
                "consistency_contradiction_codes": [
                    "strong_action_without_applicable_evidence"
                ],
            },
        }

        context = feedback_context_service.build_original_context(
            request_id="mobile-123-1",
            classification=classification,
            response=response,
        )

        self.assertEqual(context["request_id"], "mobile-123-1")
        self.assertEqual(context["original_prediction"], "Plastic Bottle")
        self.assertEqual(context["recognition_reason_codes"], ["unknown_resin"])
        self.assertEqual(context["conditional_chunk_ids"], ["plastic-1"])
        self.assertTrue(context["consistency_guard_triggered"])
        rendered = repr(context)
        self.assertNotIn("raw model output", rendered)
        self.assertNotIn("visual_observations", rendered)
        self.assertNotIn("location", rendered)
        self.assertNotIn("image", rendered)

    def test_correction_updates_only_correction_and_guidance_context(self):
        with patch(
            "services.feedback_context_service.feedback_repository.attach_correction_context",
            return_value=True,
        ) as mock_attach:
            stored = feedback_context_service.store_prediction_context(
                request_id="mobile-correction-2",
                original_request_id="mobile-original-1",
                selected_item="Metal cup",
                classification={"item": "Metal cup", "status": "confident"},
                response={
                    "item": "Metal Cup",
                    "disposal_action": "donate/reuse",
                    "guidance_source": "llm_general_fallback",
                    "guidance_confidence": {
                        "level": "medium",
                        "score": 0.64,
                        "reason_codes": [],
                    },
                },
            )

        self.assertTrue(stored)
        kwargs = mock_attach.call_args.kwargs
        self.assertEqual(kwargs["original_request_id"], "mobile-original-1")
        self.assertEqual(kwargs["correction_request_id"], "mobile-correction-2")
        self.assertEqual(kwargs["corrected_item"], "Metal Cup")
        self.assertNotIn("original_prediction", kwargs["guidance_context"])


if __name__ == "__main__":
    unittest.main()
