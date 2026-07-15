import unittest

from services.guidance_consistency_service import validate_guidance_consistency


def _classification(*, condition_flags=None, special_flags=None, trusted=None):
    classification = {
        "item": "Test item",
        "category": "Household item",
        "status": "confident",
        "recognition_details": {
            "normalized": {
                "condition_flags": condition_flags or [],
                "special_handling_flags": special_flags or [],
            }
        },
    }
    if trusted is not None:
        classification["trusted_guidance_available"] = trusted
    return classification


def _guidance(
    action,
    *,
    source="json_rag_llm_generated",
    applicable_chunk_ids=None,
    cache_hit=False,
):
    return {
        "disposal_action": action,
        "guidance_source": source,
        "guidance_metadata": {
            "applicable_chunk_ids": applicable_chunk_ids or [],
        },
        "cache_hit": cache_hit,
    }


class GuidanceConsistencyServiceTests(unittest.TestCase):
    def test_reuse_conflicting_with_explicit_condition_is_rejected(self):
        for flag in ("single_use", "contaminated", "broken"):
            with self.subTest(flag=flag):
                result = validate_guidance_consistency(
                    _classification(condition_flags=[flag]),
                    _guidance("donate/reuse"),
                )

                self.assertFalse(result["valid"])
                self.assertEqual(result["resolution"], "conditional_guidance")
                self.assertIn(
                    "reuse_conflicts_with_explicit_condition",
                    result["contradiction_codes"],
                )

    def test_intact_reusable_item_preserves_reuse(self):
        result = validate_guidance_consistency(
            _classification(condition_flags=["intact", "reusable"]),
            _guidance("donate/reuse", source="llm_general_fallback"),
        )

        self.assertTrue(result["valid"])

    def test_strong_routes_require_applicable_evidence(self):
        for action in ("recycle", "compost", "drop-off"):
            with self.subTest(action=action):
                result = validate_guidance_consistency(
                    _classification(),
                    _guidance(action),
                )

                self.assertFalse(result["valid"])
                self.assertIn(
                    "strong_action_without_applicable_evidence",
                    result["contradiction_codes"],
                )

    def test_applicable_chunk_supports_strong_route(self):
        result = validate_guidance_consistency(
            _classification(),
            _guidance("compost", applicable_chunk_ids=["compost-food-01"]),
        )

        self.assertTrue(result["valid"])

    def test_trusted_static_rules_count_as_applicable_evidence(self):
        result = validate_guidance_consistency(
            _classification(trusted=True),
            _guidance("e-waste recycling", source="legacy_rules_fallback"),
        )

        self.assertTrue(result["valid"])

    def test_conditional_retrieval_overrides_broad_static_recycling_claim(self):
        guidance = _guidance("recycle", source="legacy_rules_fallback")
        guidance["guidance_metadata"]["conditional_chunk_ids"] = ["film-01"]
        result = validate_guidance_consistency(
            _classification(trusted=True),
            guidance,
        )

        self.assertFalse(result["valid"])
        self.assertIn(
            "strong_action_without_applicable_evidence",
            result["contradiction_codes"],
        )

    def test_trash_conflicting_with_special_handling_requests_clarification(self):
        for flag in ("battery", "electronics", "chemical", "hazardous"):
            with self.subTest(flag=flag):
                result = validate_guidance_consistency(
                    _classification(special_flags=[flag]),
                    _guidance("trash", source="llm_general_fallback"),
                )

                self.assertFalse(result["valid"])
                self.assertEqual(result["resolution"], "clarification")
                self.assertIn(
                    "trash_conflicts_with_special_handling_evidence",
                    result["contradiction_codes"],
                )

    def test_cached_guidance_is_checked_against_current_condition(self):
        result = validate_guidance_consistency(
            _classification(condition_flags=["contaminated"]),
            _guidance("donate/reuse", cache_hit=True),
        )

        self.assertFalse(result["valid"])
        self.assertTrue(result["evidence"]["cache_hit"])


if __name__ == "__main__":
    unittest.main()
