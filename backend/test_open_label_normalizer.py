import unittest

from services.open_label_normalizer import normalize_open_recognition


class OpenLabelNormalizerTests(unittest.TestCase):
    def test_curtain_preserves_textile_disposal_and_material_signals(self):
        result = normalize_open_recognition(
            {
                "status": "confident",
                "raw_item_label": "curtain",
                "likely_material": "fabric",
                "broad_category": "textiles",
                "candidates": [],
            }
        )

        self.assertEqual(result["raw_item_label"], "curtain")
        self.assertEqual(result["likely_material"], "fabric")
        self.assertEqual(result["broad_category"], "textiles")
        self.assertEqual(result["normalized"]["normalized_item"], "Curtain")
        self.assertEqual(result["normalized"]["disposal_category"], "Textiles")
        self.assertEqual(result["normalized"]["material_category"], "Fabric/Textile")
        self.assertEqual(result["normalized"]["broad_category"], "household")
        self.assertEqual(
            result["normalized"]["original_vlm_broad_category"], "textiles"
        )
        self.assertEqual(
            result["normalized"]["original_vlm_likely_material"], "fabric"
        )

    def test_calculator_keeps_electronics_separate_from_plastic_material(self):
        result = normalize_open_recognition(
            {
                "status": "confident",
                "raw_item_label": "calculator",
                "likely_material": "plastic",
                "broad_category": "electronics",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["normalized_item"], "Calculator")
        self.assertEqual(result["normalized"]["disposal_category"], "Electronics")
        self.assertEqual(result["normalized"]["material_category"], "Plastic")
        self.assertEqual(result["normalized"]["broad_category"], "electronics")

    def test_electronic_item_keeps_specific_material_hint(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "phone charger",
                "likely_material": "plastic",
                "broad_category": "electronics",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["disposal_category"], "Electronics")
        self.assertEqual(result["normalized"]["material_category"], "Plastic")
        self.assertEqual(result["normalized"]["broad_category"], "electronics")

    def test_approved_disposal_category_aliases(self):
        cases = {
            "fabric": "Textiles",
            "clothing": "Textiles",
            "e-waste": "Electronics",
            "electronic device": "Electronics",
            "batteries": "Battery",
            "appliances": "Appliances",
            "cardboard": "Cardboard",
            "paper": "Paper",
            "glass": "Glass",
            "scrap metal": "Metal",
            "plastic": "Plastic",
            "compost": "Organic",
            "hazardous": "Hazardous",
        }

        for broad_category, expected in cases.items():
            with self.subTest(broad_category=broad_category):
                result = normalize_open_recognition(
                    {
                        "raw_item_label": "sample object",
                        "likely_material": "",
                        "broad_category": broad_category,
                        "candidates": [],
                    }
                )
                self.assertEqual(result["normalized"]["disposal_category"], expected)

    def test_unmapped_broad_category_normalizes_to_unknown_routing_category(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "decorative object",
                "likely_material": "rubber",
                "broad_category": "home decor",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["broad_category"], "unknown")
        self.assertEqual(result["normalized"]["disposal_category"], "Household item")
        self.assertEqual(result["normalized"]["material_category"], "Rubber")

    def test_vague_broad_category_uses_safe_household_fallback(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "decorative object",
                "likely_material": "unknown",
                "broad_category": "unknown",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["disposal_category"], "Household item")
        self.assertEqual(result["normalized"]["material_category"], "Unknown")
        self.assertEqual(result["normalized"]["broad_category"], "unknown")
        self.assertEqual(result["normalized"]["original_vlm_broad_category"], "unknown")

    def test_alias_normalizes_ceramic_mug(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "white ceramic coffee mug",
                "likely_material": "ceramic",
                "broad_category": "drinkware",
                "candidates": [],
            }
        )

        self.assertEqual(result["raw_item_label"], "white ceramic coffee mug")
        self.assertEqual(result["normalized"]["item_label"], "Ceramic mug")
        self.assertEqual(result["normalized"]["material_category"], "Ceramic")
        self.assertEqual(result["normalized"]["material_confidence"], "high")
        self.assertEqual(result["normalized"]["material_source"], "keyword")
        self.assertEqual(result["normalized"]["broad_category"], "unknown")

    def test_keyword_normalizes_phone_charger_with_special_flags(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "phone charger",
                "likely_material": "electronics",
                "broad_category": "electronics",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Phone charger")
        self.assertEqual(result["normalized"]["material_category"], "Electronics")
        self.assertEqual(result["normalized"]["material_confidence"], "high")
        self.assertEqual(result["normalized"]["material_source"], "keyword")
        self.assertEqual(result["normalized"]["broad_category"], "electronics")
        self.assertEqual(
            result["normalized"]["special_handling_flags"],
            ["electronics", "dropoff_recommended"],
        )

    def test_condition_flags_normalize_greasy_pizza_box(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "greasy pizza box",
                "likely_material": "cardboard",
                "broad_category": "food packaging",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Pizza box")
        self.assertEqual(result["normalized"]["material_category"], "Food-soiled cardboard")
        self.assertEqual(result["normalized"]["material_confidence"], "high")
        self.assertEqual(result["normalized"]["material_source"], "keyword")
        self.assertEqual(result["normalized"]["broad_category"], "paper")
        self.assertEqual(result["normalized"]["condition_flags"], ["food_soiled"])

    def test_generic_water_bottle_with_stainless_material_stays_unmatched(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "water bottle",
                "likely_material": "stainless steel",
                "broad_category": "drinkware",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Water bottle")
        self.assertEqual(result["normalized"]["material_category"], "Metal")
        self.assertEqual(result["normalized"]["material_confidence"], "low")
        self.assertEqual(result["normalized"]["material_source"], "vlm_hint")
        self.assertEqual(result["normalized"]["broad_category"], "metal")
        self.assertEqual(result["normalized"]["matched_supported_label"], None)

    def test_plastic_water_bottle_maps_to_supported_plastic_label(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "plastic water bottle",
                "likely_material": "",
                "broad_category": "drinkware",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Water bottle")
        self.assertEqual(result["normalized"]["material_category"], "Plastic")
        self.assertEqual(result["normalized"]["material_confidence"], "high")
        self.assertEqual(result["normalized"]["material_source"], "keyword")
        self.assertEqual(result["normalized"]["broad_category"], "plastic")
        self.assertEqual(
            result["normalized"]["matched_supported_label"],
            "Plastic water bottle",
        )

    def test_generic_water_bottle_with_plastic_hint_stays_conservative(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "water bottle",
                "likely_material": "plastic",
                "broad_category": "drinkware",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Water bottle")
        self.assertEqual(result["normalized"]["material_category"], "Mixed Material")
        self.assertEqual(result["normalized"]["material_confidence"], "low")
        self.assertEqual(result["normalized"]["material_source"], "vlm_hint")
        self.assertEqual(result["normalized"]["broad_category"], "plastic")
        self.assertEqual(result["normalized"]["matched_supported_label"], None)

    def test_plastic_water_bottle_candidate_does_not_override_stainless_material(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "water bottle",
                "likely_material": "stainless steel",
                "broad_category": "drinkware",
                "candidates": [
                    {"label": "Plastic water bottle", "confidence": 0.99},
                ],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Water bottle")
        self.assertEqual(result["normalized"]["material_category"], "Metal")
        self.assertEqual(result["normalized"]["matched_supported_label"], None)

    def test_pen_with_plastic_hint_defaults_to_mixed_material(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "pen",
                "likely_material": "plastic",
                "broad_category": "household item",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Pen")
        self.assertEqual(result["normalized"]["material_category"], "Mixed Material")
        self.assertEqual(result["normalized"]["material_confidence"], "low")
        self.assertEqual(result["normalized"]["material_source"], "fallback")
        self.assertEqual(result["normalized"]["matched_supported_label"], None)

    def test_plastic_pen_with_explicit_visual_evidence_can_become_plastic(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "pen",
                "likely_material": "plastic",
                "broad_category": "household item",
                "visual_evidence": "Transparent plastic body with ink tube visible.",
                "candidates": [{"label": "plastic pen", "confidence": 0.92}],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Pen")
        self.assertEqual(result["normalized"]["material_category"], "Plastic")
        self.assertEqual(result["normalized"]["material_confidence"], "medium")
        self.assertEqual(result["normalized"]["material_source"], "visual_evidence")
        self.assertEqual(result["normalized"]["matched_supported_label"], None)

    def test_plastic_water_bottle_with_explicit_visual_evidence_matches_supported_label(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "water bottle",
                "likely_material": "plastic",
                "broad_category": "drinkware",
                "visual_evidence": "Clear plastic bottle with thin crinkled body.",
                "candidates": [{"label": "Plastic water bottle", "confidence": 0.97}],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Water bottle")
        self.assertEqual(result["normalized"]["material_category"], "Plastic")
        self.assertEqual(result["normalized"]["material_confidence"], "medium")
        self.assertEqual(result["normalized"]["material_source"], "visual_evidence")
        self.assertEqual(
            result["normalized"]["matched_supported_label"],
            "Plastic water bottle",
        )

    def test_thermoflask_with_plastic_hint_stays_conservative(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "thermoflask",
                "likely_material": "plastic",
                "broad_category": "drinkware",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Thermoflask")
        self.assertEqual(result["normalized"]["material_category"], "Mixed Material")
        self.assertEqual(result["normalized"]["material_confidence"], "low")
        self.assertEqual(result["normalized"]["material_source"], "vlm_hint")
        self.assertEqual(result["normalized"]["matched_supported_label"], None)

    def test_stainless_steel_bottle_becomes_metal(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "stainless steel bottle",
                "likely_material": "metal",
                "broad_category": "drinkware",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Stainless Steel Bottle")
        self.assertEqual(result["normalized"]["material_category"], "Metal")
        self.assertEqual(result["normalized"]["material_confidence"], "high")
        self.assertEqual(result["normalized"]["material_source"], "keyword")
        self.assertEqual(result["normalized"]["matched_supported_label"], None)

    def test_empty_yogurt_cup_uses_high_confidence_consistent_candidate(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "empty yogurt cup",
                "likely_material": "plastic",
                "broad_category": "packaging",
                "candidates": [
                    {"label": "Yogurt container", "confidence": 0.93},
                    {"label": "Plastic cup", "confidence": 0.61},
                ],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Yogurt cup")
        self.assertEqual(result["normalized"]["material_category"], "Plastic")
        self.assertEqual(result["normalized"]["material_confidence"], "low")
        self.assertEqual(result["normalized"]["material_source"], "vlm_hint")
        self.assertEqual(result["normalized"]["condition_flags"], ["empty"])
        self.assertEqual(
            result["normalized"]["matched_supported_label"],
            "Yogurt container",
        )

    def test_weak_or_conflicting_candidates_do_not_override_primary_label(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "wooden picture frame",
                "likely_material": "",
                "broad_category": "",
                "candidates": [
                    {"label": "Plastic water bottle", "confidence": 0.99},
                    {"label": "Glass jar", "confidence": 0.88},
                ],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Wooden Picture Frame")
        self.assertEqual(result["normalized"]["material_category"], "Wood")
        self.assertEqual(result["normalized"]["material_confidence"], "high")
        self.assertEqual(result["normalized"]["material_source"], "keyword")
        self.assertEqual(result["normalized"]["matched_supported_label"], None)

    def test_battery_behavior_remains_unchanged(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "lithium battery",
                "likely_material": "battery",
                "broad_category": "hazardous household item",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Lithium Battery")
        self.assertEqual(result["normalized"]["material_category"], "Battery")
        self.assertEqual(result["normalized"]["material_confidence"], "high")
        self.assertEqual(result["normalized"]["material_source"], "keyword")
        self.assertIn("battery", result["normalized"]["special_handling_flags"])

    def test_unknown_fallback_does_not_crash(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "",
                "likely_material": "",
                "broad_category": "",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Unknown")
        self.assertEqual(result["normalized"]["material_category"], "Unknown")
        self.assertEqual(result["normalized"]["material_confidence"], "low")
        self.assertEqual(result["normalized"]["material_source"], "fallback")
        self.assertEqual(result["normalized"]["broad_category"], "unknown")
        self.assertEqual(result["normalized"]["condition_flags"], [])
        self.assertEqual(result["normalized"]["special_handling_flags"], [])
        self.assertEqual(result["normalized"]["matched_supported_label"], None)


if __name__ == "__main__":
    unittest.main()
