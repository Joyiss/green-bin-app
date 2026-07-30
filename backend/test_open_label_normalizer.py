import unittest

from services.open_label_normalizer import normalize_open_recognition


class OpenLabelNormalizerTests(unittest.TestCase):
    def test_electric_toothbrush_keeps_specific_electronic_identity(self):
        result = normalize_open_recognition(
            {
                "status": "confident",
                "raw_item_label": "electric toothbrush",
                "likely_material": "plastic",
                "broad_category": "personal-care product",
                "candidates": [
                    {"label": "electric toothbrush", "confidence": 0.94}
                ],
                "visual_observations": [
                    {
                        "aspect": "packaging_use",
                        "value": "personal-care product",
                        "confidence": 0.9,
                        "evidence": "Brush head and grip are visible.",
                    },
                    {
                        "aspect": "form_factor",
                        "value": "handheld powered toothbrush",
                        "confidence": 0.92,
                        "evidence": "Narrow brush head attached to a powered handle.",
                    },
                    {
                        "aspect": "power_source",
                        "value": "charging port visible",
                        "confidence": 0.91,
                        "evidence": "Charging connection is visible at the handle base.",
                    },
                    {
                        "aspect": "construction",
                        "value": "rigid plastic body",
                        "confidence": 0.87,
                        "evidence": "Molded plastic housing.",
                    },
                ],
            }
        )

        normalized = result["normalized"]
        self.assertEqual(normalized["normalized_item"], "Electric Toothbrush")
        self.assertEqual(normalized["disposal_category"], "Electronics")
        self.assertEqual(normalized["broad_category"], "electronics")
        self.assertIn("electronics", normalized["special_handling_flags"])

    def test_charging_port_evidence_preserves_electronics_safety_flag(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "oral care tool",
                "likely_material": "plastic",
                "broad_category": "personal care",
                "candidates": [],
                "visual_observations": [
                    {
                        "aspect": "power_source",
                        "value": "charging port",
                        "confidence": 0.9,
                        "evidence": "A recessed charging connection is visible.",
                    }
                ],
            }
        )

        normalized = result["normalized"]
        self.assertIn("electronics", normalized["special_handling_flags"])
        self.assertEqual(normalized["disposal_category"], "Electronics")

    def test_wireless_earbuds_remain_electronics(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "wireless earbuds",
                "likely_material": "plastic",
                "broad_category": "personal accessory",
                "candidates": [],
            }
        )

        normalized = result["normalized"]
        self.assertEqual(normalized["normalized_item"], "Wireless Earbuds")
        self.assertEqual(normalized["disposal_category"], "Electronics")
        self.assertIn("electronics", normalized["special_handling_flags"])

    def test_ordinary_personal_care_bottles_do_not_gain_protected_flags(self):
        for label in ("lotion bottle", "face cleanser bottle"):
            with self.subTest(label=label):
                result = normalize_open_recognition(
                    {
                        "raw_item_label": label,
                        "likely_material": "plastic",
                        "broad_category": "personal care container",
                        "candidates": [],
                        "visual_observations": [
                            {
                                "aspect": "form_factor",
                                "value": "rigid bottle with pump",
                                "confidence": 0.93,
                                "evidence": "Bottle body and pump are visible.",
                            },
                            {
                                "aspect": "construction",
                                "value": "rigid plastic with plastic pump",
                                "confidence": 0.9,
                                "evidence": "Molded plastic components.",
                            },
                        ],
                    }
                )

                normalized = result["normalized"]
                self.assertEqual(normalized["material_category"], "Plastic")
                self.assertNotIn("electronics", normalized["special_handling_flags"])
                self.assertNotIn("battery", normalized["special_handling_flags"])

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

    def test_exact_supported_label_match_is_not_rejected_by_material(self):
        result = normalize_open_recognition(
            {
                "status": "confident",
                "raw_item_label": "calculator",
                "likely_material": "plastic",
                "broad_category": "unknown",
                "candidates": [{"label": "calculator", "confidence": 1.0}],
                "visual_evidence": "Calculator with buttons and screen.",
                "visual_observations": [
                    {
                        "aspect": "form_factor",
                        "value": "rigid container",
                        "confidence": 0.92,
                        "evidence": "Calculator body is visible.",
                    },
                    {
                        "aspect": "construction",
                        "value": "rigid plastic",
                        "confidence": 0.88,
                        "evidence": "Calculator body appears plastic.",
                    },
                ],
            }
        )

        normalized = result["normalized"]
        self.assertEqual(normalized["normalized_item"], "Calculator")
        self.assertEqual(normalized["matched_supported_label"], "Calculator")
        self.assertEqual(normalized["disposal_category"], "Electronics")
        self.assertEqual(normalized["material_category"], "Plastic")
        self.assertEqual(normalized["broad_category"], "electronics")

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

    def test_visual_observations_survive_and_derive_disposal_relevant_flags(self):
        result = normalize_open_recognition(
            {
                "status": "confident",
                "raw_item_label": "yogurt cup",
                "likely_material": "unknown",
                "broad_category": "plastic",
                "visual_evidence": "Open plastic cup with residue.",
                "visual_observations": [
                    {
                        "aspect": "packaging_use",
                        "value": "single-use food container",
                        "confidence": 0.89,
                        "evidence": "Small branded yogurt cup.",
                    },
                    {
                        "aspect": "contamination",
                        "value": "food residue visible",
                        "confidence": 0.81,
                        "evidence": "White residue inside cup.",
                    },
                    {
                        "aspect": "recycling_marking",
                        "value": "unknown",
                        "confidence": 0.2,
                        "evidence": "mark guessed from brand text",
                    },
                ],
                "candidates": [],
            }
        )

        observations = result["normalized"]["visual_observations"]
        self.assertEqual(observations[0]["aspect"], "packaging_use")
        self.assertEqual(observations[0]["value"], "single-use food container")
        self.assertEqual(observations[1]["confidence"], 0.81)
        self.assertEqual(observations[2]["value"], "Unknown")
        self.assertIsNone(observations[2]["confidence"])
        self.assertEqual(observations[2]["evidence"], "")
        self.assertIn("single_use", result["normalized"]["condition_flags"])
        self.assertIn("food_soiled", result["normalized"]["condition_flags"])
        self.assertIn("contaminated", result["normalized"]["condition_flags"])
        self.assertEqual(result["normalized"]["material_category"], "Plastic")

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

    def test_clean_plate_uses_explicit_observation_without_contamination_flags(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "clean disposable paper plate",
                "likely_material": "paper",
                "broad_category": "paper",
                "visual_evidence": "Paper plate normally used for food.",
                "visual_observations": [
                    {
                        "aspect": "condition",
                        "value": "appears_clean",
                        "confidence": 0.91,
                        "evidence": "No food residue visible.",
                    },
                    {
                        "aspect": "contamination",
                        "value": "no visible contamination",
                        "confidence": 0.88,
                        "evidence": "Surface appears empty and clean.",
                    },
                ],
                "candidates": [],
            }
        )

        flags = result["normalized"]["condition_flags"]
        self.assertIn("appears_clean", flags)
        self.assertIn("single_use", flags)
        self.assertNotIn("food_soiled", flags)
        self.assertNotIn("contaminated", flags)

    def test_condition_flags_ignore_unrelated_free_text_evidence(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "stainless steel cup",
                "likely_material": "metal",
                "broad_category": "metal",
                "visual_evidence": "An opened package and pen are visible in the background.",
                "visual_observations": [
                    {
                        "aspect": "construction",
                        "value": "stainless steel",
                        "confidence": 0.94,
                        "evidence": "Reflective metal body without visible staining.",
                    }
                ],
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["condition_flags"], [])
        self.assertEqual(result["normalized"]["material_category"], "Metal")

    def test_bananas_preserve_organic_category_over_household_hint(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "bunch of bananas",
                "likely_material": "organic food",
                "broad_category": "household",
                "visual_observations": [],
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["material_category"], "Organic")
        self.assertEqual(result["normalized"]["primary_material"], "Organic")
        self.assertEqual(result["normalized"]["disposal_category"], "Organic")
        self.assertEqual(result["normalized"]["broad_category"], "garden")

    def test_leafy_material_preserves_organic_context(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "green leaves",
                "likely_material": "organic plant material",
                "broad_category": "household",
                "visual_observations": [],
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["material_category"], "Organic")
        self.assertEqual(result["normalized"]["disposal_category"], "Organic")
        self.assertEqual(result["normalized"]["broad_category"], "garden")

    def test_dominant_metal_construction_beats_secondary_plastic_handle(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "metal cooking utensil with plastic handle",
                "likely_material": "plastic",
                "broad_category": "household",
                "visual_observations": [
                    {
                        "aspect": "construction",
                        "value": "primarily stainless steel with plastic handle",
                        "confidence": 0.94,
                        "evidence": "Metal forms the working end and most of the object.",
                    }
                ],
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["material_category"], "Metal")
        self.assertEqual(result["normalized"]["primary_material"], "Metal")
        self.assertEqual(result["normalized"]["secondary_materials"], ["Plastic"])
        self.assertEqual(
            result["normalized"]["material_source"], "structured_observation"
        )

    def test_opened_does_not_trigger_pen_matching(self):
        result = normalize_open_recognition(
            {
                "raw_item_label": "opened wrapper",
                "likely_material": "plastic film",
                "broad_category": "plastic",
                "visual_observations": [],
                "candidates": [],
            }
        )

        self.assertEqual(result["normalized"]["item_label"], "Opened Wrapper")
        self.assertIn("opened", result["normalized"]["condition_flags"])
        self.assertNotEqual(result["normalized"]["material_source"], "fallback")


if __name__ == "__main__":
    unittest.main()
