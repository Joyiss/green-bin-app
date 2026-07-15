import unittest
from unittest.mock import patch

from services.guidance_service import build_prediction_response


def _open_classification(*, condition_flags=None, special_flags=None):
    return {
        "item": "Opened Food Wrapper",
        "category": "Plastic",
        "status": "confident",
        "candidates": [],
        "trusted_guidance_available": False,
        "recognition_confidence": {
            "level": "high",
            "score": 0.94,
            "reason_codes": [],
            "blocking": False,
        },
        "recognition_details": {
            "raw_item_label": "opened food wrapper",
            "normalized": {
                "item_label": "Opened Food Wrapper",
                "material_category": "Plastic",
                "broad_category": "plastic",
                "condition_flags": condition_flags or [],
                "special_handling_flags": special_flags or [],
                "visual_observations": [
                    {
                        "aspect": "packaging_use",
                        "value": "single-use food wrapper",
                        "confidence": 0.95,
                        "evidence": "A torn wrapper is visible.",
                    }
                ],
            },
        },
    }


def _guidance(action, *, source="json_rag_llm_generated", cache_hit=False):
    return {
        "disposal_action": action,
        "material_code": None,
        "impact_level": None,
        "summary": f"Use {action}.",
        "steps": [f"Use {action} for this item.", "Finish disposal safely."],
        "guidance_source": source,
        "guidance_metadata": {
            "applicable_chunk_ids": [],
            "conditional_chunk_ids": ["conditional-01"],
        },
        "cache_hit": cache_hit,
    }


class GuidanceConsistencyIntegrationTests(unittest.TestCase):
    def test_incompatible_reuse_uses_existing_low_risk_fallback(self):
        classification = _open_classification(condition_flags=["single_use"])

        with patch(
            "services.guidance_service._resolve_guidance",
            return_value=_guidance("donate/reuse"),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["disposal_action"], "trash")
        self.assertEqual(response["guidance_source"], "llm_general_fallback")
        self.assertTrue(
            response["guidance_metadata"]["consistency_guard_triggered"]
        )
        self.assertIn(
            "reuse_conflicts_with_explicit_condition",
            response["guidance_metadata"]["consistency_contradiction_codes"],
        )

    def test_unsupported_strong_route_is_withheld_without_replacement_claim(self):
        classification = _open_classification(condition_flags=["single_use"])

        with patch(
            "services.guidance_service._resolve_guidance",
            return_value=_guidance("recycle"),
        ):
            response = build_prediction_response(classification)

        self.assertIsNone(response["disposal_action"])
        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertIn(
            "strong_action_without_applicable_evidence",
            response["guidance_metadata"]["consistency_contradiction_codes"],
        )

    def test_cached_reuse_conflict_is_rechecked_against_current_condition(self):
        classification = _open_classification(condition_flags=["contaminated"])

        with patch(
            "services.guidance_service._resolve_guidance",
            return_value=_guidance(
                "donate/reuse",
                source="json_rag_llm_generated",
                cache_hit=True,
            ),
        ):
            response = build_prediction_response(classification)

        self.assertNotEqual(response["disposal_action"], "donate/reuse")
        self.assertTrue(response["guidance_metadata"]["rejected_cache_hit"])

    def test_trash_with_special_handling_evidence_requests_clarification(self):
        classification = _open_classification(special_flags=["battery"])
        classification["recognition_source"] = "user_confirmed_selection"

        with patch(
            "services.guidance_service._resolve_guidance",
            return_value=_guidance("trash", source="llm_general_fallback"),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["status"], "uncertain")
        self.assertIsNone(response["disposal_action"])
        self.assertTrue(response["clarification"]["required"])
        self.assertIn(
            "trash_conflicts_with_special_handling_evidence",
            response["clarification"]["reason_codes"],
        )


if __name__ == "__main__":
    unittest.main()
