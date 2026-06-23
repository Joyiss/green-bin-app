import unittest

from services.open_label_normalizer import normalize_open_recognition


class OpenLabelNormalizerTests(unittest.TestCase):
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
        self.assertEqual(result["normalized"]["broad_category"], "Drinkware")

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
        self.assertEqual(result["normalized"]["broad_category"], "Electronics")
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
        self.assertEqual(result["normalized"]["broad_category"], "Food packaging")
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
        self.assertEqual(result["normalized"]["broad_category"], "Drinkware")
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
        self.assertEqual(
            result["normalized"]["matched_supported_label"],
            "Plastic water bottle",
        )

    def test_generic_water_bottle_with_plastic_material_becomes_plastic(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "water bottle",
                "likely_material": "plastic",
                "broad_category": "drinkware",
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Water bottle")
        self.assertEqual(result["normalized"]["material_category"], "Plastic")
        self.assertEqual(result["normalized"]["broad_category"], "Drinkware")

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
        self.assertEqual(result["normalized"]["matched_supported_label"], None)

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
        self.assertEqual(result["normalized"]["broad_category"], "Unknown")
        self.assertEqual(result["normalized"]["condition_flags"], [])
        self.assertEqual(result["normalized"]["special_handling_flags"], [])
        self.assertEqual(result["normalized"]["matched_supported_label"], None)


if __name__ == "__main__":
    unittest.main()
