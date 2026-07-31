import copy
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import main as main_module
from main import app
from services import guidance_cache_service
from services.guidance_service import build_prediction_response
from services.local_guidance_matcher import match_local_guidance
from services.local_guidance_source_loader import (
    _apply_pilot_config,
    _normalize_dataset,
    load_local_guidance,
)


JURISDICTION_ID = "forsyth_county_ga"
DATA_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "local_guidance"
    / "forsyth_county_local_disposal_rules.json"
)
PILOT_CONFIG_PATH = DATA_PATH.with_name("forsyth_county_pilot_config.json")


def _configured_payload():
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    config = json.loads(PILOT_CONFIG_PATH.read_text(encoding="utf-8"))
    return _apply_pilot_config(payload, config)


def _classification(item: str, category: str = "Unknown", **normalized):
    payload = {
        "item": item,
        "category": category,
        "status": "confident",
        "candidates": [],
        "recognition_source": "test",
        "recognition_confidence": {"level": "high", "score": 0.95},
    }
    if normalized:
        payload["recognition_details"] = {"normalized": normalized}
    return payload


class LocalGuidanceLoaderTests(unittest.TestCase):
    def test_dataset_loads_only_six_pilot_approved_rules(self):
        raw_payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        dataset = load_local_guidance(JURISDICTION_ID, force_reload=True)

        self.assertNotIn("schema_version", raw_payload)
        self.assertNotIn("jurisdiction_id", raw_payload)
        self.assertIsNotNone(dataset)
        self.assertEqual(
            dataset["approved_rule_ids"],
            [
                "fc_boxes",
                "fc_glass_food_beverage",
                "fc_plastic_1_2",
                "fc_hefty_renew",
                "fc_tires",
                "fc_electronics",
            ],
        )
        self.assertNotIn("fc_hhw_event", dataset["approved_rule_ids"])

    def test_duplicate_and_unknown_references_are_rejected(self):
        payload = _configured_payload()
        duplicate = copy.deepcopy(payload)
        duplicate["rules"][1]["rule_id"] = duplicate["rules"][0]["rule_id"]
        with self.assertRaises(ValueError):
            _normalize_dataset(duplicate)

        bad_location = copy.deepcopy(payload)
        bad_location["rules"][0]["allowed_location_ids"] = ["missing-center"]
        with self.assertRaises(ValueError):
            _normalize_dataset(bad_location)

    def test_malformed_approved_fee_is_rejected(self):
        payload = _configured_payload()
        tires = next(rule for rule in payload["rules"] if rule["rule_id"] == "fc_tires")
        tires["fees"]["line_items"][0]["amount"] = "three"

        with self.assertRaises(ValueError):
            _normalize_dataset(payload)


class LocalGuidanceMatcherTests(unittest.TestCase):
    def assert_match(self, item, status, rule_id, category="Unknown", **normalized):
        result = match_local_guidance(
            _classification(item, category, **normalized),
            JURISDICTION_ID,
        )
        self.assertEqual(result["status"], status)
        self.assertEqual(result["guidance"]["local_guidance"]["rule_id"], rule_id)
        return result["guidance"]

    def test_required_pilot_matches(self):
        boxes = self.assert_match("Cardboard box", "applicable", "fc_boxes")
        self.assertIn("Flatten all boxes", boxes["steps"])

        self.assert_match("Glass jar", "applicable", "fc_glass_food_beverage")
        self.assert_match("Plastic shopping bag", "applicable", "fc_hefty_renew")

        laptop = self.assert_match("Laptop", "applicable", "fc_electronics")
        self.assertEqual(
            laptop["local_guidance"]["allowed_location_names"],
            ["Tolbert Street Center"],
        )
        self.assertEqual(
            [item["amount"] for item in laptop["local_guidance"]["fees"]["line_items"]],
            [2, 5],
        )

        tire = self.assert_match("Tire", "applicable", "fc_tires")
        self.assertEqual(
            tire["local_guidance"]["allowed_location_names"],
            ["Coal Mountain Center"],
        )
        self.assertEqual(
            [item["amount"] for item in tire["local_guidance"]["fees"]["line_items"]],
            [3, 15],
        )

    def test_glass_exclusions_never_become_container_acceptance(self):
        for item in ("Mirror", "Light bulb", "Window glass", "Drinking glass"):
            with self.subTest(item=item):
                guidance = self.assert_match(
                    item,
                    "excluded",
                    "fc_glass_food_beverage",
                    category="Glass",
                )
                self.assertEqual(guidance["disposal_action"], "Check local guidance")
                self.assertEqual(
                    guidance["local_guidance"]["decision"],
                    "not_accepted",
                )

    def test_unknown_resin_plastic_bottle_is_conditional(self):
        guidance = self.assert_match(
            "Plastic bottle",
            "conditional",
            "fc_plastic_1_2",
            material_category="Plastic",
        )
        self.assertEqual(guidance["disposal_action"], "Check local guidance")
        self.assertIn("#1 or #2", guidance["steps"][0])

    def test_visible_pet_evidence_makes_bottle_applicable(self):
        self.assert_match(
            "Plastic bottle",
            "applicable",
            "fc_plastic_1_2",
            visual_observations=[
                {
                    "aspect": "recycling_marking",
                    "value": "#1 PET",
                    "evidence": "A #1 symbol is visible.",
                }
            ],
        )

    def test_uncovered_item_has_no_local_match(self):
        result = match_local_guidance(
            _classification("Ceramic mug", "Household"),
            JURISDICTION_ID,
        )
        self.assertEqual(result["status"], "no_match")
        self.assertNotIn("guidance", result)

    def test_category_only_match_is_conditional(self):
        result = match_local_guidance(
            _classification("Unknown device", "Electronics"),
            JURISDICTION_ID,
        )

        self.assertEqual(result["status"], "conditional")
        self.assertEqual(
            result["guidance"]["local_guidance"]["rule_id"],
            "fc_electronics",
        )


class LocalGuidanceIntegrationTests(unittest.TestCase):
    def test_local_rule_becomes_evidence_for_the_shared_pipeline(self):
        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ) as retrieval,
            patch.dict("os.environ", {"ENABLE_LLM_GUIDANCE": "false"}, clear=False),
        ):
            response = build_prediction_response(
                _classification("Laptop", "Electronics"),
                jurisdiction_id=JURISDICTION_ID,
            )

        retrieval.assert_called_once()
        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["jurisdiction_id"], JURISDICTION_ID)
        self.assertEqual(response["local_guidance"]["rule_id"], "fc_electronics")
        self.assertTrue(response["guidance_metadata"]["source_urls"])

    def test_no_local_match_keeps_existing_guidance_flow(self):
        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
        ):
            response = build_prediction_response(
                _classification("Ceramic mug", "Household"),
                jurisdiction_id=JURISDICTION_ID,
            )

        self.assertNotEqual(response["guidance_source"], "local_rules")
        self.assertNotIn("local_guidance", response)

    def test_predict_passes_known_jurisdiction_without_changing_recognition(self):
        client = TestClient(app)
        classification = _classification("Laptop", "Electronics")
        with patch(
            "routes.predict.recognize_item",
            AsyncMock(return_value=classification),
        ) as recognize:
            response = client.post(
                "/predict",
                data={
                    "selected_item": "Laptop",
                    "jurisdiction_id": JURISDICTION_ID,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["guidance_source"], "local_rules")
        self.assertEqual(response.json()["local_guidance"]["rule_id"], "fc_electronics")
        recognize.assert_awaited_once()
        self.assertNotIn("jurisdiction_id", recognize.await_args.kwargs)

    def test_cache_identity_separates_national_and_local_fallbacks(self):
        classification = _classification(
            "Battery",
            "Battery",
            normalized_item="Battery",
            item_label="Battery",
            disposal_category="Battery",
            material_category="Battery",
            broad_category="Batteries",
        )
        retrieval_results = [
            {
                "chunk_id": "chunk-1",
                "chunk": {
                    "id": "chunk-1",
                    "source_name": "EPA",
                    "source_url": "https://www.epa.gov/example",
                    "location_scope": "national",
                    "source_claim": "Use a battery drop-off.",
                },
                "applicability": "applicable",
                "applicability_reason_codes": [],
                "source_conditions": {},
            }
        ]
        arguments = {
            "classification": classification,
            "retrieval_inputs": {
                "item_label": "Battery",
                "material": "Battery",
                "category": "Battery",
            },
            "retrieval_results": retrieval_results,
            "llm_context": {
                "normalized_item_label": "Battery",
                "material": "Battery",
                "broad_category": "Battery",
                "condition_flags": [],
                "special_flags": ["battery"],
                "visual_observations": [],
            },
        }
        national = guidance_cache_service.build_source_grounded_cache_context(**arguments)
        local = guidance_cache_service.build_source_grounded_cache_context(
            **arguments,
            jurisdiction_id=JURISDICTION_ID,
            local_rules_version="1",
        )

        self.assertNotEqual(national["cache_key"], local["cache_key"])
        self.assertNotIn("jurisdiction_id", national["cache_key_input"])
        self.assertEqual(
            local["cache_key_input"]["jurisdiction_id"],
            JURISDICTION_ID,
        )


class LocalGuidanceEarth911Tests(unittest.TestCase):
    def test_electronics_results_are_filtered_to_tolbert(self):
        client = TestClient(app)
        resolution = {
            "material_id": 20,
            "resolved_material_label": "Laptop",
            "search_skipped": False,
        }
        locations = [
            {
                "id": "tolbert",
                "name": "Forsyth County Recycling - Tolbert Street",
            },
            {
                "id": "coal",
                "name": "Forsyth County Recycling - Coal Mountain",
            },
        ]
        with (
            patch("main.resolve_earth911_material", return_value=resolution),
            patch("main._search_locations_for_material", return_value=locations),
        ):
            response = client.get(
                "/nearby_locations",
                params={
                    "item": "Laptop",
                    "lat": 34.2,
                    "lon": -84.1,
                    "jurisdiction_id": JURISDICTION_ID,
                    "local_rule_id": "fc_electronics",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [location["name"] for location in response.json()["locations"]],
            ["Forsyth County Recycling - Tolbert Street"],
        )

    def test_tire_results_are_filtered_to_coal_mountain(self):
        client = TestClient(app)
        with (
            patch(
                "main.resolve_earth911_material",
                return_value={"material_id": 22, "search_skipped": False},
            ),
            patch(
                "main._search_locations_for_material",
                return_value=[
                    {"id": "tolbert", "name": "Tolbert Street Center"},
                    {"id": "coal", "name": "Coal Mountain Center"},
                ],
            ),
        ):
            response = client.get(
                "/nearby_locations",
                params={
                    "item": "Tire",
                    "lat": 34.2,
                    "lon": -84.1,
                    "jurisdiction_id": JURISDICTION_ID,
                    "local_rule_id": "fc_tires",
                },
            )

        self.assertEqual(
            [location["name"] for location in response.json()["locations"]],
            ["Coal Mountain Center"],
        )

    def test_empty_filtered_results_return_official_destination(self):
        client = TestClient(app)
        with (
            patch(
                "main.resolve_earth911_material",
                return_value={"material_id": 20, "search_skipped": False},
            ),
            patch(
                "main._search_locations_for_material",
                return_value=[{"id": "other", "name": "Unrelated Electronics Store"}],
            ),
        ):
            response = client.get(
                "/nearby_locations",
                params={
                    "item": "Laptop",
                    "lat": 34.2,
                    "lon": -84.1,
                    "jurisdiction_id": JURISDICTION_ID,
                    "local_rule_id": "fc_electronics",
                },
            )

        location = response.json()["locations"][0]
        self.assertEqual(location["name"], "Tolbert Street Center")
        self.assertEqual(location["phone"], "(770) 781-2176")
        self.assertEqual(location["distance"], "Distance unavailable")
        self.assertTrue(location["official"])
        self.assertEqual(location["source"], "forsyth_county")

    def test_rule_material_override_is_loaded_server_side(self):
        dataset = load_local_guidance(JURISDICTION_ID)
        rule = copy.deepcopy(dataset["rule_index"]["fc_electronics"])
        rule["earth911_material_label"] = "Verified Laptop Catalog Label"
        with (
            patch("main.get_local_rule", return_value=(dataset, rule)),
            patch(
                "main.resolve_earth911_material",
                return_value={"material_id": None, "search_skipped": True},
            ) as resolver,
        ):
            main_module.nearby_locations(
                item="Laptop",
                lat=34.2,
                lon=-84.1,
                jurisdiction_id=JURISDICTION_ID,
                local_rule_id="fc_electronics",
            )

        self.assertEqual(resolver.call_args.args[0], "Verified Laptop Catalog Label")
