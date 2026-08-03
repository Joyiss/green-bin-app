import os
import unittest
from unittest.mock import Mock, patch

import requests

from services.earth911_material_resolver import (
    _default_catalog_matcher,
    get_grouped_material_catalog,
    get_supported_materials,
    reset_supported_materials_cache_for_tests,
    resolve_earth911_material,
)


def _material(description, material_id, *, family_ids=None, legacy=None):
    return {
        "description": description,
        "description_legacy": legacy if legacy is not None else description,
        "family_ids": family_ids if family_ids is not None else [1],
        "image": f"materials/{description.lower().replace(' ', '-')}.jpg",
        "long_description": f"How to recycle {description}.",
        "material_id": material_id,
        "url": "https://earth911.com/",
    }


def _family(description, family_id, material_ids):
    return {
        "description": description,
        "family_id": family_id,
        "family_type_id": 1,
        "material_ids": material_ids,
    }


def _fetcher(materials, families=None, calls=None):
    def fetch(endpoint, params):
        if calls is not None:
            calls.append((endpoint, params))
        if endpoint == "earth911.getMaterials":
            return materials
        if endpoint == "earth911.getFamilies":
            return families or []
        raise AssertionError(f"Unexpected endpoint: {endpoint}")

    return fetch


class Earth911MaterialResolverTests(unittest.TestCase):
    def setUp(self):
        reset_supported_materials_cache_for_tests()

    def tearDown(self):
        reset_supported_materials_cache_for_tests()

    def test_exact_match_bypasses_llm(self):
        fetch = _fetcher([_material("Mouse", 20)])

        def fail_matcher(*args):
            raise AssertionError("LLM should not be called for exact matches")

        result = resolve_earth911_material("Mouse", None, fetch, fail_matcher)

        self.assertEqual(result["material_id"], 20)
        self.assertEqual(result["matched_material_name"], "Mouse")
        self.assertEqual(result["match_type"], "exact")
        self.assertFalse(result["search_skipped"])

    def test_alias_match_bypasses_llm(self):
        fetch = _fetcher([_material("Computer Peripherals - External", 483)])

        def fail_matcher(*args):
            raise AssertionError("LLM should not be called for alias matches")

        result = resolve_earth911_material("computer mouse", None, fetch, fail_matcher)

        self.assertEqual(result["material_id"], 483)
        self.assertEqual(result["matched_material_name"], "Computer Peripherals - External")
        self.assertEqual(result["match_type"], "alias")
        self.assertFalse(result["search_skipped"])

    def test_explicit_calculator_alias_bypasses_llm(self):
        fetch = _fetcher([_material("Calculators", 585)])

        def fail_matcher(*args):
            raise AssertionError("LLM should not be called for singular/plural aliases")

        result = resolve_earth911_material("Calculator", None, fetch, fail_matcher)

        self.assertEqual(result["material_id"], 585)
        self.assertEqual(result["matched_material_name"], "Calculators")
        self.assertEqual(result["match_type"], "alias")
        self.assertFalse(result["search_skipped"])

    def test_generated_plural_aliases_bypass_llm(self):
        fetch = _fetcher(
            [
                _material("Aluminum Cans", 10),
                _material("Cardboard Box", 11),
                _material("Dry Cell Batteries", 12),
            ]
        )

        def fail_matcher(*args):
            raise AssertionError("LLM should not be called for generated plural aliases")

        cases = [
            ("aluminum can", 10, "Aluminum Cans"),
            ("cardboard boxes", 11, "Cardboard Box"),
            ("dry cell battery", 12, "Dry Cell Batteries"),
        ]
        for label, material_id, material_name in cases:
            with self.subTest(label=label):
                result = resolve_earth911_material(label, None, fetch, fail_matcher)
                self.assertEqual(result["material_id"], material_id)
                self.assertEqual(result["matched_material_name"], material_name)
                self.assertEqual(result["match_type"], "alias")

    def test_generated_plural_aliases_do_not_pluralize_generic_materials(self):
        fetch = _fetcher([_material("Glass", 5)])
        matcher = lambda *args: {
            "selection": "unsupported",
            "confidence": "low",
            "reason": "No exact material.",
        }

        result = resolve_earth911_material("glasses", None, fetch, matcher)

        self.assertIsNone(result["material_id"])
        self.assertEqual(result["match_type"], "none")
        self.assertEqual(result["validation_failure_reason"], "llm_unsupported")

    def test_high_confidence_llm_selection_must_match_exact_description(self):
        fetch = _fetcher([_material("Ceramic Fixtures", 51)])
        matcher = lambda *args: {
            "selection": "Ceramic Fixtures",
            "confidence": "high",
            "reason": "The scanned fixture matches this catalog entry.",
        }

        result = resolve_earth911_material("porcelain sink", None, fetch, matcher)

        self.assertEqual(result["material_id"], 51)
        self.assertEqual(result["match_type"], "llm")
        self.assertEqual(result["llm_confidence"], "high")
        self.assertIn("scanned fixture", result["llm_reason"])

    def test_invalid_llm_outcomes_return_unsupported(self):
        fetch = _fetcher([_material("Ceramic Fixtures", 51)])
        cases = [
            (
                {"selection": "unsupported", "confidence": "high", "reason": "No match."},
                "llm_unsupported",
            ),
            (
                {"selection": "Ceramic Fixtures", "confidence": "low", "reason": "Unsure."},
                "llm_low_confidence",
            ),
            (
                {"selection": "Invented Material", "confidence": "high", "reason": "Guess."},
                "invalid_catalog_selection",
            ),
            ("not a response object", "invalid_llm_response"),
        ]

        for llm_output, failure_reason in cases:
            with self.subTest(failure_reason=failure_reason):
                result = resolve_earth911_material(
                    "porcelain sink",
                    None,
                    fetch,
                    lambda *args, output=llm_output: output,
                )
                self.assertIsNone(result["material_id"])
                self.assertEqual(result["match_type"], "none")
                self.assertEqual(result["validation_failure_reason"], failure_reason)
                self.assertTrue(result["search_skipped"])

    def test_llm_request_failure_returns_unsupported(self):
        fetch = _fetcher([_material("Ceramic Fixtures", 51)])

        def failed_matcher(*args):
            raise requests.ConnectionError("offline")

        result = resolve_earth911_material("porcelain sink", None, fetch, failed_matcher)

        self.assertIsNone(result["material_id"])
        self.assertEqual(result["validation_failure_reason"], "llm_request_error")
        self.assertTrue(result["search_skipped"])

    def test_invalid_llm_catalog_selection_includes_debug_selection_and_candidates(self):
        fetch = _fetcher(
            [
                _material("Plastic Film", 70),
                _material("Plastic Grocery Bags", 71),
                _material("Ceramic Fixtures", 51),
            ]
        )
        matcher = lambda *args: {
            "selection": "Plastic Bags",
            "confidence": "high",
            "reason": "Exact match in Earth911 catalog",
        }

        result = resolve_earth911_material("plastic bag", None, fetch, matcher)

        self.assertIsNone(result["material_id"])
        self.assertEqual(result["validation_failure_reason"], "invalid_catalog_selection")
        self.assertEqual(result["llm_selection"], "Plastic Bags")
        self.assertIn("Plastic Grocery Bags", result["catalog_selection_candidates"])
        self.assertNotIn("Ceramic Fixtures", result["catalog_selection_candidates"])

    def test_disabled_default_llm_matcher_returns_unsupported(self):
        fetch = _fetcher([_material("Ceramic Fixtures", 51)])

        with patch.dict(os.environ, {"ENABLE_EARTH911_LLM_MATCHING": "false"}):
            result = resolve_earth911_material("porcelain sink", None, fetch)

        self.assertEqual(result["validation_failure_reason"], "llm_disabled")
        self.assertTrue(result["search_skipped"])

    def test_enabled_default_llm_matcher_is_easy_to_exercise_locally(self):
        fetch = _fetcher(
            [_material("Ceramic Fixtures", 51, family_ids=[7])],
            [_family("Construction", 7, [51])],
        )
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": (
                            '{"selection":"Ceramic Fixtures","confidence":"high",'
                            '"reason":"The sink is a ceramic fixture."}'
                        )}]}}
            ]
        }
        env = {
            "ENABLE_EARTH911_LLM_MATCHING": "true",
            "GEMINI_TEXT_MODEL": "test-model",
            "GEMINI_API_KEY": "test-key",
        }

        with (
            patch.dict(os.environ, env),
            patch("services.gemini_text_client.requests.post", return_value=response) as post,
        ):
            result = resolve_earth911_material("porcelain sink", None, fetch)

        self.assertEqual(result["material_id"], 51)
        self.assertEqual(result["match_type"], "llm")
        request_payload = post.call_args.kwargs["json"]
        prompt = request_payload["contents"][0]["parts"][0]["text"]
        self.assertIn("## Construction", prompt)
        self.assertIn("- Ceramic Fixtures", prompt)
        self.assertNotIn("## 7", prompt)

    def test_earth911_prompt_includes_complete_dynamic_catalog(self):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "candidates": [
                {"content": {"parts": [{"text": (
                            '{"selection":"unsupported","confidence":"low",'
                            '"reason":"Two catalog entries are plausible."}'
                        )}]}}
            ]
        }
        env = {
            "ENABLE_EARTH911_LLM_MATCHING": "true",
            "GEMINI_TEXT_MODEL": "test-model",
            "GEMINI_API_KEY": "test-key",
        }
        grouped_catalog = {
            "Construction": ["Ceramic Fixtures", "Porcelain"],
            "Electronics": ["Computer Peripherals - External"],
        }

        with (
            patch.dict(os.environ, env),
            patch("services.gemini_text_client.requests.post", return_value=response) as post,
        ):
            result = _default_catalog_matcher(
                "porcelain sink",
                {"recognized_item": "porcelain sink"},
                grouped_catalog,
            )

        self.assertEqual(result["selection"], "unsupported")
        prompt = post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        self.assertIn("You are a controlled matcher for the Earth911 supported-material catalog.", prompt)
        self.assertIn("Recognized item:\nporcelain sink", prompt)
        self.assertIn('"recognized_item": "porcelain sink"', prompt)
        self.assertIn("## Construction\n- Ceramic Fixtures\n- Porcelain", prompt)
        self.assertIn("## Electronics\n- Computer Peripherals - External", prompt)
        self.assertIn("OUTPUT REQUIREMENTS:", prompt)
        self.assertIn("Keep reason under 20 words.", prompt)

    def test_keyboard_plural_catalog_match_bypasses_llm(self):
        fetch = _fetcher([_material("Keyboards", 40, family_ids=[4])])

        def fail_matcher(*args):
            raise AssertionError("LLM should not be called for generated plural aliases")

        result = resolve_earth911_material(
            "keyboard",
            {"category": "Electronics", "material_category": "Plastic"},
            fetch,
            fail_matcher,
        )

        self.assertEqual(result["material_id"], 40)
        self.assertEqual(result["match_type"], "alias")
        self.assertEqual(result["routing_category"], "electronics")

    def test_electronics_fallback_routes_llm_catalog_to_electronics_not_plastic(self):
        grouped_seen = {}
        fetch = _fetcher(
            [
                _material("Computer Peripherals", 40, family_ids=[4]),
                _material("Plastic Containers", 41, family_ids=[12]),
            ],
            [
                _family("Electronics", 4, [40]),
                _family("Plastic", 12, [41]),
            ],
        )

        def matcher(_label, _details, grouped_catalog):
            grouped_seen.update(grouped_catalog)
            return {"selection": "unsupported", "confidence": "low", "reason": "No exact catalog match."}

        result = resolve_earth911_material(
            "electronic keypad",
            {"category": "Electronics", "material_category": "Plastic"},
            fetch,
            matcher,
        )

        self.assertEqual(result["routing_category"], "electronics")
        self.assertEqual(result["catalog_family_filter"], "Electronics")
        self.assertEqual(grouped_seen, {"Electronics": ["Computer Peripherals"]})

    def test_computer_mouse_routes_llm_catalog_to_electronics(self):
        grouped_seen = {}
        fetch = _fetcher(
            [
                _material("Computer Peripherals", 40, family_ids=[4]),
                _material("Plastic Containers", 41, family_ids=[12]),
            ],
            [
                _family("Electronics", 4, [40]),
                _family("Plastic", 12, [41]),
            ],
        )

        def matcher(_label, _details, grouped_catalog):
            grouped_seen.update(grouped_catalog)
            return {"selection": "unsupported", "confidence": "low", "reason": "No exact catalog match."}

        result = resolve_earth911_material(
            "computer mouse",
            {"material_category": "Plastic"},
            fetch,
            matcher,
        )

        self.assertEqual(result["routing_category"], "electronics")
        self.assertEqual(grouped_seen, {"Electronics": ["Computer Peripherals"]})

    def test_calculator_plural_catalog_match_bypasses_llm(self):
        fetch = _fetcher([_material("Calculators", 42, family_ids=[4])])

        def fail_matcher(*args):
            raise AssertionError("LLM should not be called for calculator aliases")

        result = resolve_earth911_material(
            "calculator",
            {"material_category": "Plastic"},
            fetch,
            fail_matcher,
        )

        self.assertEqual(result["material_id"], 42)
        self.assertEqual(result["match_type"], "alias")

    def test_electronics_category_routes_llm_catalog_to_electronics(self):
        grouped_seen = {}
        fetch = _fetcher(
            [
                _material("Circuit Boards", 42, family_ids=[4]),
                _material("Plastic Containers", 41, family_ids=[12]),
            ],
            [
                _family("Electronics", 4, [42]),
                _family("Plastic", 12, [41]),
            ],
        )

        def matcher(_label, _details, grouped_catalog):
            grouped_seen.update(grouped_catalog)
            return {"selection": "unsupported", "confidence": "low", "reason": "No exact catalog match."}

        resolve_earth911_material(
            "small electronic device",
            {"category": "Electronics", "material_category": "Plastic"},
            fetch,
            matcher,
        )

        self.assertEqual(grouped_seen, {"Electronics": ["Circuit Boards"]})

    def test_battery_routes_llm_catalog_to_batteries(self):
        grouped_seen = {}
        fetch = _fetcher(
            [
                _material("Alkaline Batteries", 13, family_ids=[2]),
                _material("Household Hazardous Waste", 95, family_ids=[95]),
            ],
            [
                _family("Batteries", 2, [13]),
                _family("Hazardous", 95, [95]),
            ],
        )

        def matcher(_label, _details, grouped_catalog):
            grouped_seen.update(grouped_catalog)
            return {"selection": "unsupported", "confidence": "low", "reason": "No exact catalog match."}

        resolve_earth911_material("battery pack", None, fetch, matcher)

        self.assertEqual(grouped_seen, {"Batteries": ["Alkaline Batteries"]})

    def test_paint_can_plural_catalog_match_bypasses_llm(self):
        fetch = _fetcher([_material("Paint Cans", 71, family_ids=[95])])

        def fail_matcher(*args):
            raise AssertionError("LLM should not be called for paint can plural aliases")

        result = resolve_earth911_material(
            "paint can",
            {"material_category": "Metal"},
            fetch,
            fail_matcher,
        )

        self.assertEqual(result["material_id"], 71)
        self.assertEqual(result["match_type"], "alias")

    def test_paint_category_routes_llm_catalog_to_paint_or_hazardous_not_metal(self):
        grouped_seen = {}
        fetch = _fetcher(
            [
                _material("Latex Paint", 70, family_ids=[7]),
                _material("Household Hazardous Waste", 71, family_ids=[95]),
                _material("Metal Cans", 72, family_ids=[6]),
            ],
            [
                _family("Paint", 7, [70]),
                _family("Hazardous", 95, [71]),
                _family("Metal", 6, [72]),
            ],
        )

        def matcher(_label, _details, grouped_catalog):
            grouped_seen.update(grouped_catalog)
            return {"selection": "unsupported", "confidence": "low", "reason": "No exact catalog match."}

        resolve_earth911_material("paint thinner", {"material_category": "Metal"}, fetch, matcher)

        self.assertIn("Paint", grouped_seen)
        self.assertIn("Hazardous", grouped_seen)
        self.assertNotIn("Metal", grouped_seen)

    def test_plastic_water_bottle_routes_llm_catalog_to_plastic(self):
        grouped_seen = {}
        fetch = _fetcher(
            [
                _material("Rigid Plastics", 80, family_ids=[12]),
                _material("Glass Bottles", 81, family_ids=[5]),
            ],
            [
                _family("Plastic", 12, [80]),
                _family("Glass", 5, [81]),
            ],
        )

        def matcher(_label, _details, grouped_catalog):
            grouped_seen.update(grouped_catalog)
            return {"selection": "unsupported", "confidence": "low", "reason": "No exact catalog match."}

        resolve_earth911_material("plastic water bottle", None, fetch, matcher)

        self.assertEqual(grouped_seen, {"Plastic": ["Rigid Plastics"]})

    def test_cardboard_box_plural_catalog_match_bypasses_llm(self):
        fetch = _fetcher([_material("Cardboard Boxes", 90, family_ids=[8])])

        def fail_matcher(*args):
            raise AssertionError("LLM should not be called for cardboard box plural aliases")

        result = resolve_earth911_material("cardboard box", None, fetch, fail_matcher)

        self.assertEqual(result["material_id"], 90)
        self.assertEqual(result["match_type"], "alias")

    def test_paper_category_routes_llm_catalog_to_paper(self):
        grouped_seen = {}
        fetch = _fetcher(
            [
                _material("Mixed Paper", 90, family_ids=[8]),
                _material("Plastic Containers", 91, family_ids=[12]),
            ],
            [
                _family("Paper", 8, [90]),
                _family("Plastic", 12, [91]),
            ],
        )

        def matcher(_label, _details, grouped_catalog):
            grouped_seen.update(grouped_catalog)
            return {"selection": "unsupported", "confidence": "low", "reason": "No exact catalog match."}

        resolve_earth911_material("paperboard package", {"category": "Paper"}, fetch, matcher)

        self.assertEqual(grouped_seen, {"Paper": ["Mixed Paper"]})

    def test_old_cache_without_strict_broad_category_uses_category_before_material(self):
        grouped_seen = {}
        fetch = _fetcher(
            [
                _material("Keyboards", 40, family_ids=[4]),
                _material("Plastic Containers", 41, family_ids=[12]),
            ],
            [
                _family("Electronics", 4, [40]),
                _family("Plastic", 12, [41]),
            ],
        )

        def matcher(_label, _details, grouped_catalog):
            grouped_seen.update(grouped_catalog)
            return {"selection": "unsupported", "confidence": "low", "reason": "No exact catalog match."}

        resolve_earth911_material(
            "electronic keypad",
            {"category": "Electronics", "material_category": "Plastic"},
            fetch,
            matcher,
        )

        self.assertEqual(grouped_seen, {"Electronics": ["Keyboards"]})

    def test_non_protected_word_containing_oil_is_not_marked_protected(self):
        fetch = _fetcher([_material("Aluminum Foil", 60)])

        result = resolve_earth911_material("aluminum foil", None, fetch)

        self.assertEqual(result["material_id"], 60)
        self.assertFalse(result["protected_item"])

    def test_specific_protected_item_rejects_broad_llm_target(self):
        fetch = _fetcher([_material("Batteries", 12)])
        matcher = lambda *args: {
            "selection": "Batteries",
            "confidence": "high",
            "reason": "This is a battery item.",
        }

        result = resolve_earth911_material(
            "lithium power bank",
            {"material_category": "Battery"},
            fetch,
            matcher,
        )

        self.assertTrue(result["protected_item"])
        self.assertTrue(result["protected_item_specific"])
        self.assertIsNone(result["material_id"])
        self.assertEqual(result["validation_failure_reason"], "broad_protected_target")

    def test_specific_protected_item_accepts_specific_llm_target(self):
        fetch = _fetcher([_material("Lithium-ion Batteries", 13)])
        matcher = lambda *args: {
            "selection": "Lithium-ion Batteries",
            "confidence": "high",
            "reason": "The item contains a lithium-ion battery.",
        }

        result = resolve_earth911_material(
            "lithium power bank",
            {"material_category": "Battery"},
            fetch,
            matcher,
        )

        self.assertEqual(result["material_id"], 13)
        self.assertEqual(result["match_type"], "llm")

    def test_specific_protected_item_rejects_broad_exact_legacy_match(self):
        fetch = _fetcher([_material("Batteries", 12, legacy="Lithium power bank")])

        result = resolve_earth911_material(
            "lithium power bank",
            {"material_category": "Battery"},
            fetch,
            lambda *args: None,
        )

        self.assertIsNone(result["material_id"])
        self.assertEqual(result["validation_failure_reason"], "broad_protected_target")

    def test_catalog_uses_readable_family_names_and_fallback_group(self):
        materials = [
            _material("Alkaline Batteries", 10, family_ids=[2]),
            _material("Uncategorized Item", 11, family_ids=[999]),
        ]
        families = [_family("Batteries", 2, [10])]

        get_supported_materials(_fetcher(materials, families))
        grouped = get_grouped_material_catalog()

        self.assertEqual(grouped["Batteries"], ["Alkaline Batteries"])
        self.assertEqual(grouped["Other supported materials"], ["Uncategorized Item"])
        self.assertNotIn("2", grouped)

    def test_cache_uses_ttl_and_fetches_both_catalogs(self):
        calls = []
        fetch = _fetcher(
            [_material("Mouse", 20)],
            [_family("Electronics", 1, [20])],
            calls,
        )

        first = get_supported_materials(fetch, now=100)
        second = get_supported_materials(fetch, now=200)

        self.assertIs(first, second)
        self.assertEqual([endpoint for endpoint, _ in calls], [
            "earth911.getMaterials",
            "earth911.getFamilies",
        ])

        get_supported_materials(fetch, now=100 + 24 * 60 * 60 + 1)
        self.assertEqual(len(calls), 4)

    def test_refresh_failure_serves_stale_material_catalog(self):
        initial = get_supported_materials(
            _fetcher([_material("Mouse", 20)]),
            now=100,
        )

        def failed_fetch(endpoint, params):
            raise RuntimeError("Earth911 unavailable")

        stale = get_supported_materials(
            failed_fetch,
            now=100 + 24 * 60 * 60 + 1,
        )

        self.assertIs(stale, initial)
        result = resolve_earth911_material("Mouse", None, failed_fetch)
        self.assertTrue(result["stale_catalog_used"])

    def test_initial_material_fetch_failure_is_not_hidden(self):
        def failed_fetch(endpoint, params):
            raise RuntimeError("Earth911 unavailable")

        with self.assertRaises(RuntimeError):
            get_supported_materials(failed_fetch)

    def test_family_fetch_failure_does_not_block_material_catalog(self):
        def fetch(endpoint, params):
            if endpoint == "earth911.getMaterials":
                return [_material("Mouse", 20)]
            raise RuntimeError("Families unavailable")

        materials = get_supported_materials(fetch)

        self.assertEqual(materials[0]["description"], "Mouse")
        self.assertEqual(get_grouped_material_catalog(), {"Other supported materials": ["Mouse"]})


if __name__ == "__main__":
    unittest.main()
