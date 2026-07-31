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
    def test_condition_keywords_do_not_replace_generated_guidance(self):
        classification = _open_classification(condition_flags=["single_use"])

        with patch(
            "services.guidance_service._resolve_guidance",
            return_value=_guidance("donate/reuse"),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["disposal_action"], "donate/reuse")
        self.assertEqual(response["guidance_source"], "json_rag_llm_generated")
        self.assertNotIn("consistency_guard_triggered", response["guidance_metadata"])

    def test_valid_allowed_route_is_not_replaced_by_consistency_layer(self):
        classification = _open_classification(condition_flags=["single_use"])

        with patch(
            "services.guidance_service._resolve_guidance",
            return_value=_guidance("recycle"),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["disposal_action"], "recycle")
        self.assertEqual(response["guidance_source"], "json_rag_llm_generated")

    def test_cached_guidance_is_not_semantically_rewritten(self):
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

        self.assertEqual(response["disposal_action"], "donate/reuse")
        self.assertTrue(response["cache_hit"])

    def test_special_handling_keywords_do_not_create_late_clarification(self):
        classification = _open_classification(special_flags=["battery"])
        classification["recognition_source"] = "user_confirmed_selection"

        with patch(
            "services.guidance_service._resolve_guidance",
            return_value=_guidance("trash", source="llm_general_fallback"),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["status"], "confident")
        self.assertEqual(response["disposal_action"], "trash")
        self.assertNotIn("clarification", response)


if __name__ == "__main__":
    unittest.main()
