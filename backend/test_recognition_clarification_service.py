import unittest

from services.recognition_clarification_service import evaluate_clarification


def _classification(**overrides):
    classification = {
        "item": "Rigid Container",
        "category": "Plastic",
        "status": "confident",
        "candidates": [],
        "recognition_source": "vlm_open",
        "recognition_confidence": {
            "level": "medium",
            "score": 0.7,
            "reason_codes": ["generic_item_label"],
            "blocking": False,
        },
        "recognition_details": {
            "normalized": {
                "item_label": "Rigid Container",
                "disposal_category": "Plastic",
                "broad_category": "plastic",
                "special_handling_flags": [],
            }
        },
    }
    classification.update(overrides)
    return classification


class RecognitionClarificationTests(unittest.TestCase):
    def test_blocking_container_contradiction_requires_clarification(self):
        result = evaluate_clarification(
            _classification(
                item="Personal care container",
                status="uncertain",
                recognition_confidence={
                    "level": "low",
                    "score": 0.39,
                    "reason_codes": ["specific_container_feature_conflict"],
                    "blocking": True,
                },
            )
        )

        self.assertTrue(result["required"])
        self.assertIn("specific_container_feature_conflict", result["reason_codes"])
        self.assertTrue(result["retake_recommended"])

    def test_weak_battery_signal_requires_safety_clarification(self):
        classification = _classification(
            item="Metal cylinder",
            recognition_details={
                "normalized": {
                    "item_label": "Metal cylinder",
                    "disposal_category": "Metal",
                    "broad_category": "metal",
                    "special_handling_flags": ["battery", "dropoff_recommended"],
                }
            },
        )

        result = evaluate_clarification(classification)

        self.assertTrue(result["required"])
        self.assertTrue(result["safety_relevant"])
        self.assertIn("unresolved_battery_identity", result["reason_codes"])

    def test_weak_electronics_signal_requires_safety_clarification(self):
        classification = _classification(
            item="Plastic household object",
            recognition_details={
                "normalized": {
                    "item_label": "Plastic household object",
                    "disposal_category": "Household item",
                    "broad_category": "household",
                    "special_handling_flags": ["electronics", "dropoff_recommended"],
                }
            },
        )

        result = evaluate_clarification(classification)

        self.assertTrue(result["required"])
        self.assertTrue(result["safety_relevant"])
        self.assertIn("unresolved_electronics_identity", result["reason_codes"])

    def test_nonblocking_medium_confidence_does_not_require_clarification(self):
        result = evaluate_clarification(_classification())

        self.assertFalse(result["required"])

    def test_user_confirmed_selection_never_reenters_clarification(self):
        result = evaluate_clarification(
            _classification(
                recognition_source="user_confirmed_selection",
                recognition_confidence={
                    "level": "high",
                    "score": 1.0,
                    "reason_codes": ["user_confirmed_selection"],
                    "blocking": False,
                },
            )
        )

        self.assertFalse(result["required"])
        self.assertFalse(result["retake_recommended"])


if __name__ == "__main__":
    unittest.main()

