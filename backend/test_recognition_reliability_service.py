import unittest

from services.open_label_normalizer import normalize_open_recognition
from services.recognition_reliability_service import evaluate_open_recognition


def _evaluate(**overrides):
    details = {
        "status": "confident",
        "raw_item_label": "stainless steel cup",
        "likely_material": "metal",
        "broad_category": "metal",
        "candidates": [{"label": "stainless steel cup", "confidence": 0.92}],
        "visual_observations": [
            {
                "aspect": "form_factor",
                "value": "handleless open drinking cup",
                "confidence": 0.91,
                "evidence": "Open rim and cup body visible.",
            },
            {
                "aspect": "construction",
                "value": "stainless steel",
                "confidence": 0.94,
                "evidence": "Reflective metal body.",
            },
            {
                "aspect": "condition",
                "value": "appears intact",
                "confidence": 0.8,
                "evidence": "No visible damage.",
            },
        ],
    }
    details.update(overrides)
    return evaluate_open_recognition(normalize_open_recognition(details))


class RecognitionReliabilityTests(unittest.TestCase):
    def test_strong_consistent_item_is_high_confidence(self):
        result = _evaluate()

        self.assertEqual(result["level"], "high")
        self.assertFalse(result["blocking"])
        self.assertEqual(result["label_observation_agreement"], "supported")

    def test_pump_container_mislabeled_as_mug_is_blocking(self):
        result = _evaluate(
            raw_item_label="ceramic mug",
            likely_material="ceramic",
            broad_category="household",
            candidates=[
                {"label": "ceramic mug", "confidence": 0.91},
                {"label": "cosmetic container", "confidence": 0.38},
            ],
            visual_observations=[
                {
                    "aspect": "packaging_use",
                    "value": "personal care pump bottle",
                    "confidence": 0.94,
                    "evidence": "Product label and pump visible.",
                },
                {
                    "aspect": "form_factor",
                    "value": "rectangular bottle with pump",
                    "confidence": 0.96,
                    "evidence": "No handle or cup opening visible.",
                },
                {
                    "aspect": "construction",
                    "value": "opaque rigid plastic",
                    "confidence": 0.82,
                    "evidence": "Molded bottle body.",
                },
            ],
        )

        self.assertEqual(result["level"], "low")
        self.assertTrue(result["blocking"])
        self.assertIn("specific_container_feature_conflict", result["reason_codes"])
        self.assertEqual(result["suggested_label"], "Personal care container")

    def test_unresolved_battery_signal_blocks_ordinary_object_label(self):
        result = _evaluate(
            raw_item_label="metal cylinder",
            likely_material="metal",
            broad_category="household",
            candidates=[
                {"label": "metal cylinder", "confidence": 0.61},
                {"label": "AA battery", "confidence": 0.52},
            ],
            visual_observations=[
                {
                    "aspect": "power_source",
                    "value": "battery-like cell",
                    "confidence": 0.66,
                    "evidence": "Raised terminal visible.",
                },
                {
                    "aspect": "form_factor",
                    "value": "small cylindrical cell",
                    "confidence": 0.82,
                    "evidence": "Cylindrical casing.",
                },
            ],
        )

        self.assertTrue(result["blocking"])
        self.assertIn("unresolved_power_source_conflict", result["reason_codes"])
        self.assertEqual(result["suggested_label"], "Battery")

    def test_medium_confidence_is_not_automatically_blocking(self):
        result = _evaluate(
            raw_item_label="rigid container",
            likely_material="plastic",
            broad_category="plastic",
            candidates=[{"label": "rigid container", "confidence": 0.78}],
            visual_observations=[
                {
                    "aspect": "form_factor",
                    "value": "rigid container",
                    "confidence": 0.7,
                    "evidence": "Rigid walls visible.",
                }
            ],
        )

        self.assertEqual(result["level"], "medium")
        self.assertFalse(result["blocking"])

    def test_small_candidate_margin_caps_confidence(self):
        result = _evaluate(
            candidates=[
                {"label": "metal cup", "confidence": 0.82},
                {"label": "metal container", "confidence": 0.78},
            ]
        )

        self.assertEqual(result["level"], "medium")
        self.assertIn("ambiguous_candidate_margin", result["reason_codes"])

    def test_recovered_output_requires_confirmation(self):
        result = _evaluate(parse_mode="recovered")

        self.assertEqual(result["level"], "medium")
        self.assertTrue(result["blocking"])
        self.assertIn("truncated_or_recovered_output", result["reason_codes"])

    def test_protected_electronic_identity_is_not_erased_by_generic_care_observation(self):
        result = _evaluate(
            raw_item_label="electric toothbrush",
            likely_material="plastic",
            broad_category="personal care",
            candidates=[{"label": "electric toothbrush", "confidence": 0.94}],
            visual_observations=[
                {
                    "aspect": "packaging_use",
                    "value": "personal-care product",
                    "confidence": 0.9,
                    "evidence": "Brush head and grip visible.",
                },
                {
                    "aspect": "form_factor",
                    "value": "handheld powered toothbrush",
                    "confidence": 0.93,
                    "evidence": "Brush head attached to a powered handle.",
                },
                {
                    "aspect": "power_source",
                    "value": "charging port visible",
                    "confidence": 0.92,
                    "evidence": "Charging connection visible at the base.",
                },
                {
                    "aspect": "construction",
                    "value": "rigid plastic body",
                    "confidence": 0.88,
                    "evidence": "Molded housing.",
                },
            ],
        )

        self.assertFalse(result["blocking"])
        self.assertIsNone(result["suggested_label"])
        self.assertNotIn("item_observation_contradiction", result["reason_codes"])

    def test_swimming_goggles_with_pump_bottle_observations_is_blocking(self):
        result = _evaluate(
            raw_item_label="swimming goggles",
            likely_material="rubber",
            broad_category="personal accessory",
            candidates=[{"label": "swimming goggles", "confidence": 0.93}],
            visual_observations=[
                {
                    "aspect": "form_factor",
                    "value": "rigid container with pump",
                    "confidence": 0.96,
                    "evidence": "Bottle body and pump nozzle are visible.",
                },
                {
                    "aspect": "construction",
                    "value": "rigid plastic with plastic pump",
                    "confidence": 0.93,
                    "evidence": "Molded plastic bottle and pump.",
                },
                {
                    "aspect": "packaging_use",
                    "value": "dispensing container",
                    "confidence": 0.91,
                    "evidence": "Pump dispenses contents from the bottle.",
                },
            ],
        )

        self.assertEqual(result["level"], "low")
        self.assertTrue(result["blocking"])
        self.assertIn("item_observation_contradiction", result["reason_codes"])
        self.assertIn("material_observation_contradiction", result["reason_codes"])
        self.assertEqual(result["suggested_label"], "Rigid container")

    def test_matching_lotion_pump_observations_remain_accepted(self):
        result = _evaluate(
            raw_item_label="lotion bottle",
            likely_material="plastic",
            broad_category="personal care container",
            candidates=[{"label": "lotion bottle", "confidence": 0.94}],
            visual_observations=[
                {
                    "aspect": "packaging_use",
                    "value": "personal care pump bottle",
                    "confidence": 0.94,
                    "evidence": "Lotion label and pump visible.",
                },
                {
                    "aspect": "form_factor",
                    "value": "rigid bottle with pump nozzle",
                    "confidence": 0.95,
                    "evidence": "Bottle body and pump are visible.",
                },
                {
                    "aspect": "construction",
                    "value": "rigid plastic with plastic pump",
                    "confidence": 0.91,
                    "evidence": "Molded plastic construction.",
                },
            ],
        )

        self.assertFalse(result["blocking"])
        self.assertNotIn("item_observation_contradiction", result["reason_codes"])
        self.assertEqual(result["suggested_label"], "Personal care container")

    def test_matching_generic_container_observations_remain_nonblocking(self):
        result = _evaluate(
            raw_item_label="rigid container",
            likely_material="plastic",
            broad_category="plastic",
            candidates=[{"label": "rigid container", "confidence": 0.79}],
            visual_observations=[
                {
                    "aspect": "form_factor",
                    "value": "rigid container with cap",
                    "confidence": 0.86,
                    "evidence": "Rigid walls and a removable cap are visible.",
                },
                {
                    "aspect": "construction",
                    "value": "rigid plastic",
                    "confidence": 0.88,
                    "evidence": "Uniform molded plastic body.",
                },
            ],
        )

        self.assertFalse(result["blocking"])
        self.assertNotIn("item_observation_contradiction", result["reason_codes"])

    def test_minor_container_wording_differences_do_not_create_contradiction(self):
        result = _evaluate(
            raw_item_label="cosmetic bottle",
            likely_material="plastic",
            broad_category="personal care container",
            candidates=[{"label": "cosmetic container", "confidence": 0.91}],
            visual_observations=[
                {
                    "aspect": "form_factor",
                    "value": "personal-care dispenser",
                    "confidence": 0.9,
                    "evidence": "A capped dispensing bottle is visible.",
                },
                {
                    "aspect": "construction",
                    "value": "opaque molded plastic",
                    "confidence": 0.87,
                    "evidence": "Plastic body and closure.",
                },
            ],
        )

        self.assertFalse(result["blocking"])
        self.assertNotIn("item_observation_contradiction", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()

