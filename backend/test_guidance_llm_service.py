import json
import os
import unittest
from unittest.mock import Mock, patch

import requests

from services.guidance_llm_service import (
    DEFAULT_GUIDANCE_LLM_MODEL,
    _build_general_safe_prompt,
    _build_source_grounded_prompt,
    _general_safe_allowed_actions,
    _groq_request,
    try_generate_general_safe_guidance,
    try_generate_source_grounded_guidance,
    validate_guidance_basic,
)


def _chunk(chunk_id="electronics_01", *, action="Drop-off", signals=None, claim=None):
    return {
        "id": chunk_id,
        "title": "Electronics guidance",
        "source_name": "EPA",
        "source_url": "https://example.com",
        "location_scope": "national",
        "generalizable": True,
        "requires_location_check": False,
        "content": claim or "Use electronics collection or recycling.",
        "source_excerpt": claim or "Use electronics collection or recycling.",
        "source_claim": claim or "Electronics collection is supported.",
        "decision_signals": signals or {"supports_recycling": True, "requires_dropoff": True},
        "warnings": [],
        "limitations": [],
        "disposal_actions_supported": [action],
    }


def _result(chunk):
    return {"chunk": chunk, "chunk_id": chunk["id"], "score": 8.0, "matched_fields": []}


def _official_result(
    chunk_id,
    *,
    content,
    action,
    applicability_label,
    location_scope,
    score=10.0,
):
    chunk = _chunk(chunk_id, action=action, claim=content)
    chunk.update(
        {
            "title": f"Official guidance for {chunk_id}",
            "source_name": "Official waste agency",
            "source_url": f"https://example.gov/{chunk_id}",
            "location_scope": location_scope,
            "generalizable": applicability_label == "official_supporting",
            "content": content,
            "source_excerpt": content,
            "source_claim": content,
            "decision_signals": {
                "applicability_label": applicability_label,
                "tavily_trust_level": (
                    "OFFICIAL_SUPPORTING"
                    if applicability_label == "official_supporting"
                    else "LOCAL_PRIMARY"
                ),
            },
            "source_metadata": {
                "title": f"Official guidance for {chunk_id}",
                "organization": "Official waste agency",
                "url": f"https://example.gov/{chunk_id}",
                "trusted": True,
                "local": applicability_label != "official_supporting",
            },
        }
    )
    return {
        "chunk": chunk,
        "chunk_id": chunk_id,
        "score": score,
        "matched_fields": [applicability_label],
        "requires_location_check": False,
        "applicability": "applicable",
        "applicability_reason_codes": [],
        "source_conditions": {},
    }


def _payload(**overrides):
    legacy_steps = overrides.pop("steps", None)
    payload = {
        "disposal_action": "drop-off",
        "summary": "Take this laptop to electronics drop-off.",
        "prep_steps": ["Back up personal files."],
        "next_step": "Take the laptop to an approved electronics collection site.",
        "alternatives": [],
        "warnings": [],
        "confidence": "high",
    }
    if legacy_steps is not None:
        payload["prep_steps"] = legacy_steps[:-1]
        payload["next_step"] = legacy_steps[-1] if legacy_steps else ""
    payload.update(overrides)
    return payload


class BasicValidatorTests(unittest.TestCase):
    def context(self, chunks=None, actions=None):
        return {
            "allowed_disposal_actions": actions or {"drop-off"},
            "retrieved_chunks": chunks or [_chunk()],
        }

    def test_valid_short_output_is_accepted(self):
        validated, errors = validate_guidance_basic(
            _payload(summary="Drop off this laptop.", steps=["Erase your data.", "Use electronics drop-off."]),
            self.context(),
        )
        self.assertEqual(errors, [])
        self.assertEqual(validated["steps"], ["Erase your data.", "Use electronics drop-off."])

    def test_empty_prep_steps_are_accepted_without_filler(self):
        validated, errors = validate_guidance_basic(
            _payload(prep_steps=[], next_step="Set the cart out for scheduled collection."),
            self.context(),
        )
        self.assertEqual(errors, [])
        self.assertEqual(validated["prep_steps"], [])
        self.assertEqual(validated["steps"], ["Set the cart out for scheduled collection."])

    def test_style_imperfections_are_not_rejected(self):
        validated, errors = validate_guidance_basic(
            _payload(summary="Drop-off.", steps=["Data backup first", "Maybe keep its charger together"]),
            self.context(),
        )
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_summary_hard_max_only(self):
        self.assertIsNotNone(validate_guidance_basic(_payload(summary="x" * 240), self.context())[0])
        self.assertIn("summary_too_long", validate_guidance_basic(_payload(summary="x" * 241), self.context())[1])

    def test_duplicate_steps_do_not_trigger_semantic_rejection(self):
        validated, errors = validate_guidance_basic(
            _payload(steps=["Use electronics drop-off!", " use   electronics dropoff ", "Use electronics drop-off."]),
            self.context(),
        )
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_near_duplicates_are_allowed(self):
        validated, errors = validate_guidance_basic(
            _payload(steps=["Take it to electronics drop-off.", "Find a nearby electronics drop-off."]),
            self.context(),
        )
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_keyword_semantics_are_not_part_of_structural_validation(self):
        cases = [
            "Disassemble the laptop before recycling.",
            "Pry open the case.",
            "Force open the case.",
            "Open the phone before drop-off.",
            "Remove the built-in battery.",
            "Remove the battery.",
            "Remove internal parts.",
            "Puncture the battery.",
            "Burn the laptop.",
            "Pour it down the drain.",
        ]
        for instruction in cases:
            with self.subTest(instruction=instruction):
                validated, errors = validate_guidance_basic(
                    _payload(steps=[instruction, "Use electronics drop-off."]), self.context()
                )
                self.assertIsNotNone(validated)
                self.assertEqual(errors, [])

    def test_negated_safety_warnings_are_allowed(self):
        warnings = [
            "Do not disassemble the laptop.",
            "Do not dismantle the phone.",
            "Do not pry open the case.",
            "Do not remove built-in batteries.",
            "Do not remove the battery.",
            "Avoid puncturing the battery.",
            "Avoid dismantling the phone.",
            "Never burn the laptop.",
            "Keep the device intact.",
            "- Do not dismantle the phone.",
            "Please do not open the phone.",
        ]
        validated, errors = validate_guidance_basic(_payload(warnings=warnings), self.context())
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_negation_does_not_mask_later_unsafe_clause(self):
        validated, errors = validate_guidance_basic(
            _payload(warnings=["Do not wait; disassemble the laptop."]), self.context()
        )
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_negated_battery_safety_steps_are_allowed(self):
        validated, errors = validate_guidance_basic(
            _payload(
                steps=[
                    "Keep the phone intact and do not remove the battery.",
                    "Take it to an electronics drop-off.",
                ],
                warnings=["Do not dismantle the phone or puncture the battery."],
            ),
            self.context(),
        )

        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_part_removal_words_do_not_trigger_semantic_validation(self):
        cases = [
            "Dismantle the phone before taking it in.",
            "Open the device and remove the battery.",
            "Keep the device intact; then puncture the battery.",
            "Avoid delays and remove the battery.",
        ]
        for instruction in cases:
            with self.subTest(instruction=instruction):
                validated, errors = validate_guidance_basic(
                    _payload(steps=[instruction, "Use electronics drop-off."]),
                    self.context(),
                )
                self.assertIsNotNone(validated)
                self.assertEqual(errors, [])

    def test_source_names_in_main_guidance_are_nonblocking_warnings(self):
        validated, errors = validate_guidance_basic(
            _payload(steps=["Follow EPA guidance.", "Use electronics drop-off."]), self.context()
        )
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])
        self.assertEqual(validated["validation_warnings"], [])
        validated, errors = validate_guidance_basic(_payload(), self.context())
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_only_unsupported_action_is_rejected(self):
        _, errors = validate_guidance_basic(
            _payload(disposal_action="trash", summary="This is recyclable everywhere."), self.context()
        )
        self.assertIn("unsupported_disposal_action", errors)
        self.assertFalse(any(error.startswith("unsupported_strong_claim:") for error in errors))

    def test_claim_keywords_do_not_trigger_semantic_validation(self):
        curbside = _payload(summary="Recycle this container curbside.")
        self.assertEqual(validate_guidance_basic(curbside, self.context())[1], [])
        supported_chunk = _chunk(
            action="Recycle",
            claim="This container is accepted in curbside recycling.",
            signals={"supports_recycling": True, "avoid_curbside_recycling": False},
        )
        curbside["disposal_action"] = "recycle"
        validated, errors = validate_guidance_basic(curbside, self.context([supported_chunk], {"recycle"}))
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])


class GenerationFlowTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "ENABLE_LLM_GUIDANCE": "true",
            "GUIDANCE_LLM_PROVIDER": "groq",
            "GUIDANCE_LLM_MODEL": DEFAULT_GUIDANCE_LLM_MODEL,
            "GROQ_API_KEY": "test-key",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def source_call(self):
        return try_generate_source_grounded_guidance(
            recognized_item="Laptop", normalized_item_label="Laptop", material="Electronics",
            broad_category="Electronics", condition_flags=[], special_flags=["electronics"],
            visual_evidence=None, candidates=[], location=None, retrieval_results=[_result(_chunk())],
        )

    @patch("services.guidance_llm_service._groq_request")
    def test_seattle_battery_regression_keeps_supported_local_details(self, request):
        local_evidence = (
            "Seattle residents may use city household-battery drop-off for alkaline, "
            "rechargeable, and button batteries. Tape rechargeable battery terminals. "
            "Seattle Public Utilities also offers scheduled special-item pickup for eligible "
            "households, with a two-item limit and no residential pickup fee."
        )
        request.return_value = json.dumps(
            {
                "disposal_action": "drop-off",
                "summary": (
                    "Seattle accepts alkaline, rechargeable, and button batteries through "
                    "its household-battery collection service."
                ),
                "prep_steps": ["Tape the terminals on rechargeable batteries."],
                "next_step": "Use Seattle's household-battery drop-off service.",
                "alternatives": [
                    "Eligible households may schedule special-item pickup, limited to two items."
                ],
                "warnings": [],
                "confidence": "high",
            }
        )
        result = try_generate_source_grounded_guidance(
            recognized_item="Household battery",
            normalized_item_label="Household battery",
            material="Battery",
            broad_category="batteries",
            condition_flags=[],
            special_flags=["battery", "requires_dropoff"],
            visual_evidence="Small household battery.",
            candidates=[],
            location={"city": "Seattle", "county": "King County", "state": "Washington"},
            retrieval_results=[
                _official_result(
                    "seattle-battery",
                    content=local_evidence,
                    action="Drop-off",
                    applicability_label="city_exact",
                    location_scope="Seattle, Washington",
                )
            ],
        )

        guidance = result["guidance"]
        self.assertIn("alkaline, rechargeable, and button batteries", guidance["summary"])
        self.assertIn("special-item pickup", guidance["alternatives"][0])
        self.assertNotIn("search", " ".join(guidance["steps"] + guidance["alternatives"]).casefold())
        self.assertNotIn("green bin", json.dumps(guidance).casefold())
        prompt = request.call_args.args[0]
        self.assertIn(local_evidence, prompt)
        self.assertIn('"evidence_priority": "exact_local"', prompt)
        self.assertIn("supported programs, pickup services, fees, limits", prompt)
        self.assertIn("Never mention Green Bin, the app, buttons, screens", prompt)

    @patch("services.guidance_llm_service._groq_request")
    def test_local_detail_handling_spans_categories_and_jurisdictions(self, request):
        cases = [
            {
                "name": "paint_with_fee_and_pickup",
                "item": "Oil-based paint can",
                "material": "Paint",
                "category": "paint",
                "location": {"city": "Austin", "county": "Travis County", "state": "Texas"},
                "action": "household hazardous waste",
                "evidence": (
                    "Austin household hazardous waste collection accepts sealed oil-based paint "
                    "from residents. Keep lids secured. Up to 30 gallons is accepted without a fee, "
                    "and eligible residents may schedule home pickup."
                ),
                "response": {
                    "disposal_action": "household hazardous waste",
                    "summary": "Austin residents may use household hazardous waste collection for sealed oil-based paint, up to 30 gallons without a fee.",
                    "prep_steps": ["Secure the lid on the oil-based paint can."],
                    "next_step": "Use Austin's household hazardous waste collection service.",
                    "alternatives": ["Eligible residents may schedule home pickup."],
                    "warnings": ["The no-fee residential limit is 30 gallons."],
                    "confidence": "high",
                },
            },
            {
                "name": "food_scraps_with_restriction",
                "item": "Food scraps",
                "material": "Organic",
                "category": "organic",
                "location": {"city": "Portland", "county": "Multnomah County", "state": "Oregon"},
                "action": "compost",
                "evidence": (
                    "Portland curbside compost accepts food scraps and food-soiled paper. "
                    "Remove produce stickers. Compostable cups and serviceware are not accepted."
                ),
                "response": {
                    "disposal_action": "compost",
                    "summary": "Portland curbside compost accepts food scraps and food-soiled paper, but not compostable serviceware.",
                    "prep_steps": ["Remove produce stickers from the food scraps."],
                    "next_step": "Place the food scraps in the curbside compost cart.",
                    "alternatives": [],
                    "warnings": ["Do not include compostable cups or serviceware."],
                    "confidence": "high",
                },
            },
            {
                "name": "bulky_collection_without_prep_filler",
                "item": "Broken chair",
                "material": "Mixed material",
                "category": "household",
                "location": {"city": "Columbus", "county": "Franklin County", "state": "Ohio"},
                "action": "trash",
                "evidence": (
                    "Columbus residential bulk collection accepts unusable chairs by scheduled "
                    "curbside collection. No preparation requirement is listed."
                ),
                "response": {
                    "disposal_action": "trash",
                    "summary": "Columbus residential bulk collection accepts unusable chairs through scheduled curbside service.",
                    "prep_steps": [],
                    "next_step": "Use the scheduled residential bulk collection service.",
                    "alternatives": [],
                    "warnings": [],
                    "confidence": "high",
                },
            },
        ]

        for index, case in enumerate(cases):
            with self.subTest(case=case["name"]):
                request.return_value = json.dumps(case["response"])
                result = try_generate_source_grounded_guidance(
                    recognized_item=case["item"],
                    normalized_item_label=case["item"],
                    material=case["material"],
                    broad_category=case["category"],
                    condition_flags=[],
                    special_flags=[],
                    visual_evidence=None,
                    candidates=[],
                    location=case["location"],
                    retrieval_results=[
                        _official_result(
                            f"local-case-{index}",
                            content=case["evidence"],
                            action=case["action"],
                            applicability_label="city_exact",
                            location_scope=f"{case['location']['city']}, {case['location']['state']}",
                        )
                    ],
                )
                guidance = result["guidance"]
                self.assertEqual(guidance["prep_steps"], case["response"]["prep_steps"])
                self.assertEqual(guidance["next_step"], case["response"]["next_step"])
                self.assertIn(case["evidence"], request.call_args.args[0])
                self.assertNotIn("green bin", json.dumps(guidance).casefold())
                self.assertNotIn("search online", json.dumps(guidance).casefold())

    @patch("services.guidance_llm_service._groq_request")
    def test_exact_local_evidence_is_prioritized_before_state_and_federal(self, request):
        request.return_value = json.dumps(
            {
                "disposal_action": "drop-off",
                "summary": "Local electronics collection accepts televisions under the stated limits.",
                "prep_steps": ["Keep the television intact."],
                "next_step": "Use the local electronics collection service.",
                "alternatives": [],
                "warnings": [],
                "confidence": "high",
            }
        )
        retrieval_results = [
            _official_result(
                "federal-tv",
                content="Federal electronics stewardship overview.",
                action="Drop-off",
                applicability_label="official_supporting",
                location_scope="federal",
                score=100.0,
            ),
            _official_result(
                "state-tv",
                content="Nebraska statewide electronics information.",
                action="Drop-off",
                applicability_label="statewide_rule",
                location_scope="Nebraska",
                score=5.0,
            ),
            _official_result(
                "county-tv",
                content="Douglas County accepts televisions with a two-unit household limit.",
                action="Drop-off",
                applicability_label="county_exact",
                location_scope="Douglas County, Nebraska",
                score=6.0,
            ),
            _official_result(
                "city-tv",
                content="Omaha electronics collection accepts intact televisions.",
                action="Drop-off",
                applicability_label="city_exact",
                location_scope="Omaha, Nebraska",
                score=7.0,
            ),
        ]

        result = try_generate_source_grounded_guidance(
            recognized_item="Television",
            normalized_item_label="Television",
            material="Electronics",
            broad_category="electronics",
            condition_flags=[],
            special_flags=["electronics"],
            visual_evidence=None,
            candidates=[],
            location={"city": "Omaha", "county": "Douglas County", "state": "Nebraska"},
            retrieval_results=retrieval_results,
        )

        prompt = request.call_args.args[0]
        self.assertLess(prompt.index('"id": "city-tv"'), prompt.index('"id": "state-tv"'))
        self.assertLess(prompt.index('"id": "county-tv"'), prompt.index('"id": "state-tv"'))
        self.assertNotIn('"id": "federal-tv"', prompt)
        self.assertEqual(
            result["guidance"]["guidance_metadata"]["retrieved_chunk_ids"],
            ["city-tv", "county-tv", "state-tv"],
        )

    @patch("services.guidance_llm_service._groq_request")
    def test_conditional_chunk_is_prompt_context_not_main_action_authority(self, request):
        request.return_value = json.dumps(
            _payload(
                disposal_action="trash",
                summary="Put this personal-care container in household trash.",
                steps=[
                    "Empty any remaining product.",
                    "Place the container in household trash.",
                ],
                sources_used=[],
            )
        )
        result = try_generate_source_grounded_guidance(
            recognized_item="Personal care container",
            normalized_item_label="Plastic lotion pump bottle",
            material="Plastic",
            broad_category="Plastic",
            condition_flags=[],
            special_flags=[],
            visual_evidence="Rigid pump container.",
            visual_observations=[
                {
                    "aspect": "packaging_use",
                    "value": "personal care product container",
                    "confidence": 0.95,
                    "evidence": "A product label and pump are visible.",
                },
                {
                    "aspect": "recycling_marking",
                    "value": "unknown",
                    "confidence": None,
                    "evidence": "",
                },
            ],
            candidates=["cosmetic container"],
            location=None,
            retrieval_results=[
                {
                    **_result(_chunk(action="Recycle")),
                    "applicability": "conditional",
                    "applicability_reason_codes": [
                        "eligibility_marking_unknown",
                        "local_acceptance_unverified",
                    ],
                    "source_conditions": {
                        "confirmed": [],
                        "unknown": ["resin_code_present"],
                        "contradicted": [],
                    },
                }
            ],
        )

        self.assertEqual(result["guidance"]["disposal_action"], "trash")
        prompt = request.call_args.args[0]
        self.assertIn('"applicability": "conditional"', prompt)
        self.assertIn('"check local guidance"', prompt)
        self.assertIn('"trash"', prompt)

    @patch("services.guidance_llm_service._groq_request")
    def test_original_safe_output_has_original_path(self, request):
        request.return_value = json.dumps(_payload())
        guidance = self.source_call()["guidance"]
        self.assertEqual(guidance["guidance_metadata"]["final_generation_path"], "original_llm")
        request.assert_called_once()

    @patch("services.guidance_llm_service._groq_request")
    def test_duplicate_reaches_response_without_repair(self, request):
        request.return_value = json.dumps(_payload(steps=["Use drop-off.", "Use drop-off."]))
        result = self.source_call()
        request.assert_called_once()
        self.assertIsNotNone(result["guidance"])
        self.assertIsNone(result["failure_reason"])

    @patch("services.guidance_llm_service._groq_request")
    def test_style_imperfection_does_not_repair_or_fallback(self, request):
        request.return_value = json.dumps(_payload(summary="Drop-off.", steps=["Backup maybe", "Keep charger nearby"]))
        guidance = self.source_call()["guidance"]
        request.assert_called_once()
        self.assertEqual(guidance["guidance_metadata"]["final_generation_path"], "original_llm")

    @patch("services.guidance_llm_service._groq_request")
    def test_source_name_warning_does_not_trigger_repair(self, request):
        request.return_value = json.dumps(
            _payload(
                summary="EPA says to use electronics drop-off.",
                steps=["Keep the laptop intact.", "Use electronics drop-off."],
            )
        )

        guidance = self.source_call()["guidance"]

        request.assert_called_once()
        self.assertEqual(guidance["summary"], "EPA says to use electronics drop-off.")
        self.assertEqual(
            guidance["guidance_metadata"]["final_generation_path"],
            "original_llm",
        )

    @patch("services.guidance_llm_service._groq_request")
    def test_keyword_output_is_not_replaced_by_validator(self, request):
        request.return_value = json.dumps(_payload(steps=["Disassemble the laptop.", "Use drop-off."]))
        with self.assertLogs("services.guidance_llm_service", level="INFO") as logs:
            result = self.source_call()
        request.assert_called_once()
        self.assertIsNotNone(result["guidance"])
        self.assertIsNone(result["failure_reason"])
        combined = " ".join(logs.output)
        self.assertIn("validation succeeded", combined)

    @patch("services.guidance_llm_service._groq_request", side_effect=requests.Timeout())
    def test_request_failure_returns_no_guidance_without_repair(self, request):
        with self.assertLogs("services.guidance_llm_service", level="INFO") as logs:
            result = self.source_call()
        request.assert_called_once()
        self.assertIsNone(result["guidance"])
        self.assertEqual(result["failure_reason"], "timeout")
        self.assertIn("result=request_exception", " ".join(logs.output))

    @patch("services.guidance_llm_service._groq_request")
    def test_invalid_json_fails_without_repair(self, request):
        request.return_value = "not json"
        result = self.source_call()
        request.assert_called_once()
        self.assertIsNone(result["guidance"])
        self.assertEqual(result["failure_reason"], "invalid_json")

    def test_source_grounded_prompt_places_context_before_output_schema(self):
        prompt = _build_source_grounded_prompt(
            recognized_item="Laptop", normalized_item_label="Laptop", material="Electronics",
            broad_category="Electronics", condition_flags=[], special_flags=[], visual_evidence=None,
            candidates=[], location=None, chunks=[_chunk()], allowed_disposal_actions=["drop-off"],
        )
        self.assertLess(
            prompt.index("INPUT CONTEXT"),
            prompt.index("OUTPUT REQUIREMENTS"),
        )
        self.assertLess(
            prompt.index('"retrieved_chunks"'),
            prompt.index('"disposal_action": ""'),
        )
        self.assertTrue(prompt.rstrip().endswith('  "confidence": ""\n}'))
        self.assertIn('"prep_steps": []', prompt)
        self.assertIn('"next_step": ""', prompt)
        self.assertIn('"alternatives": []', prompt)
        self.assertNotIn('"sources_used"', prompt)
        self.assertIn("You are a source-grounded disposal guidance writer.", prompt)
        self.assertIn("Do not tell the user to search for a facility.", prompt)
        self.assertNotIn('"intent"', prompt)

    def test_source_prompt_requires_realistic_object_specific_action(self):
        prompt = _build_source_grounded_prompt(
            recognized_item="Opened single-use chip bag",
            normalized_item_label="Chip bag",
            material="Mixed Material",
            broad_category="plastic",
            condition_flags=["opened"],
            special_flags=[],
            visual_evidence="Crinkly snack pouch with crumbs.",
            candidates=["chip bag", "food wrapper"],
            location=None,
            chunks=[_chunk(action="Trash", claim="Flexible snack packaging is handled as trash.")],
            allowed_disposal_actions=["trash"],
        )

        self.assertIn(
            "Use the recognized item as the authority for item identity.",
            prompt,
        )
        self.assertIn(
            "Use only chunks marked applicable, or conditional chunks whose stated condition is confirmed",
            prompt,
        )
        self.assertIn(
            "Never infer battery chemistry, resin, coating, contamination, embedded batteries",
            prompt,
        )
        self.assertIn('"recognized_item": "Opened single-use chip bag"', prompt)
        self.assertIn('"visual_evidence": "Crinkly snack pouch with crumbs."', prompt)

    def test_source_prompt_has_no_object_specific_destination_example(self):
        prompt = _build_source_grounded_prompt(
            recognized_item="Desk fan",
            normalized_item_label="Desk fan",
            material="Mixed Material",
            broad_category="electronics",
            condition_flags=[],
            special_flags=["electronics"],
            visual_evidence=None,
            candidates=[],
            location=None,
            chunks=[_chunk()],
            allowed_disposal_actions=["drop-off"],
        )

        self.assertIn(
            "- next_step: One concrete disposal action supported by the accepted evidence. Describe the destination or collection route without adding item types that are not present in the current recognition or accepted evidence. Do not describe the interface.",
            prompt,
        )
        self.assertNotIn("computer peripherals", prompt)
        self.assertNotIn("electronics drop-off that accepts", prompt)

    def test_source_role_and_claim_scope_are_in_guidance_context(self):
        chunk = _chunk(
            action="Drop-off",
            claim="A local recycler says it accepts monitors at its own facility.",
        )
        chunk.update(
            {
                "source_role": "direct_service_provider",
                "claim_scope": [
                    "own_accepted_items",
                    "own_services",
                    "own_locations",
                ],
            }
        )

        prompt = _build_source_grounded_prompt(
            recognized_item="Monitor",
            normalized_item_label="Monitor",
            material="Electronics",
            broad_category="electronics",
            condition_flags=[],
            special_flags=["electronics"],
            visual_evidence=None,
            candidates=[],
            location={"city": "Denver", "state": "Colorado"},
            chunks=[chunk],
            allowed_disposal_actions=["drop-off"],
        )

        self.assertIn('"source_role": "direct_service_provider"', prompt)
        self.assertIn('"claim_scope": ["own_accepted_items", "own_services", "own_locations"]', prompt)
        self.assertIn("State provider claims as provider-specific, never as citywide rules.", prompt)
        self.assertIn("cannot by itself support a strong local rule", prompt)

    @patch("services.guidance_llm_service._groq_request")
    def test_discovery_only_result_is_not_sent_to_guidance_llm(self, request):
        discovery_chunk = _chunk(
            action="Drop-off",
            claim="A directory lists possible battery recyclers.",
        )
        discovery_chunk.update(
            {
                "source_role": "discovery_only",
                "claim_scope": ["source_discovery"],
            }
        )

        result = try_generate_source_grounded_guidance(
            recognized_item="Household battery",
            normalized_item_label="Household battery",
            material="Battery",
            broad_category="batteries",
            condition_flags=[],
            special_flags=["battery"],
            visual_evidence=None,
            candidates=[],
            location={"city": "Raleigh", "state": "North Carolina"},
            retrieval_results=[_result(discovery_chunk)],
        )

        request.assert_not_called()
        self.assertIsNone(result["guidance"])
        self.assertEqual(result["failure_reason"], "no_chunks")

    def test_general_safe_fallback_prompt_is_standalone_without_retrieved_chunks(self):
        observations = [
            {
                "aspect": "contamination",
                "value": "food residue visible",
                "confidence": 0.81,
                "evidence": "Residue inside cup.",
            }
        ]
        prompt = _build_general_safe_prompt(
            recognized_item="Used plastic yogurt container",
            normalized_item_label="Yogurt container",
            material="Plastic",
            broad_category="plastic",
            condition_flags=["empty"],
            special_flags=[],
            visual_evidence="Open plastic cup with food residue.",
            visual_observations=observations,
            candidates=["yogurt container", "plastic cup"],
            allowed_actions={"trash"},
            low_risk_reason="allowed_reusable_household",
            matched_terms=["yogurt container"],
        )

        self.assertIn("You are a conservative disposal fallback writer.", prompt)
        self.assertNotIn("You are a source-grounded disposal guidance writer.", prompt)
        self.assertNotIn("retrieved_chunks", prompt)
        self.assertNotIn("retrieved chunks", prompt)
        self.assertNotIn('"sources_used"', prompt)
        self.assertLess(
            prompt.index("INPUT CONTEXT"),
            prompt.index("OUTPUT REQUIREMENTS"),
        )
        self.assertLess(
            prompt.index('"recognized_item"'),
            prompt.index('"disposal_action": ""'),
        )
        self.assertTrue(prompt.rstrip().endswith('  "confidence": "low"\n}'))
        self.assertIn("No retrieved disposal evidence is available.", prompt)
        self.assertIn("Use household trash only for ordinary low-risk disposable items", prompt)
        self.assertIn('"allowed_disposal_actions": ["trash"]', prompt)
        self.assertIn('"recognized_item": "Used plastic yogurt container"', prompt)
        self.assertIn('"visual_evidence": "Open plastic cup with food residue."', prompt)
        self.assertIn('"visual_observations": [{"aspect": "contamination"', prompt)

    def test_general_safe_allowed_actions_use_trash_for_non_reusable_low_risk_items(self):
        self.assertEqual(
            _general_safe_allowed_actions(
                recognized_item="Used plastic yogurt container",
                material="Plastic",
                broad_category="plastic",
                condition_flags=["empty"],
                special_flags=[],
                low_risk_reason="allowed_reusable_household",
            ),
            {"trash"},
        )
        self.assertEqual(
            _general_safe_allowed_actions(
                recognized_item="Wet cardboard sleeve",
                material="Paper",
                broad_category="paper",
                condition_flags=["wet"],
                special_flags=[],
                low_risk_reason="allowed_paper_stationery",
            ),
            {"trash"},
        )

    def test_general_safe_allowed_actions_reserve_local_check_for_special_handling(self):
        self.assertEqual(
            _general_safe_allowed_actions(
                recognized_item="Unknown battery powered device",
                material="Mixed material",
                broad_category="household",
                condition_flags=[],
                special_flags=["battery", "dropoff_recommended"],
                low_risk_reason="allowed_reusable_household",
            ),
            {"check local guidance"},
        )

    @patch("services.guidance_llm_service.requests.post")
    def test_groq_request_uses_configured_model_and_json_mode(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": '{"ok":true}'}}]}
        post.return_value = response
        settings = {"api_key": "secret", "model": DEFAULT_GUIDANCE_LLM_MODEL, "timeout_seconds": 7, "provider": "groq"}
        self.assertEqual(_groq_request("prompt", settings=settings, mode="test"), '{"ok":true}')
        sent = post.call_args.kwargs
        self.assertEqual(sent["json"]["model"], "llama-3.3-70b-versatile")
        self.assertEqual(sent["json"]["response_format"], {"type": "json_object"})

    @patch("services.guidance_llm_service._groq_request")
    def test_general_safe_output_keeps_public_shape(self, request):
        request.return_value = json.dumps({
            "disposal_action": "donate/reuse", "summary": "Donate this drum if it still plays.",
            "prep_steps": ["Wipe dust from the shell."],
            "next_step": "Donate it through an accepted reuse program if it is playable.",
            "alternatives": [], "warnings": [], "confidence": "low",
        })
        result = try_generate_general_safe_guidance(
            recognized_item="Drum", normalized_item_label="Drum", material="Wood",
            broad_category="Instrument", condition_flags=[], special_flags=[], visual_evidence=None,
            candidates=[], low_risk_reason="allowed_reusable_household", matched_terms=["drum"],
        )
        guidance = result["guidance"]
        self.assertEqual(guidance["guidance_metadata"]["final_generation_path"], "original_llm")
        self.assertEqual(
            {"disposal_action", "material_code", "impact_level", "summary", "prep_steps", "next_step", "alternatives", "steps", "guidance_source", "guidance_metadata"},
            set(guidance),
        )

    @patch("services.guidance_llm_service._groq_request")
    def test_general_safe_generation_uses_trash_for_single_use_packaging(self, request):
        request.return_value = json.dumps({
            "disposal_action": "trash",
            "summary": "Put this used yogurt container in household trash if it has residue.",
            "prep_steps": ["Empty loose residue first."],
            "next_step": "Place the used container in household trash.",
            "alternatives": [],
            "warnings": [],
            "confidence": "low",
        })

        result = try_generate_general_safe_guidance(
            recognized_item="Used plastic yogurt container",
            normalized_item_label="Yogurt container",
            material="Plastic",
            broad_category="plastic",
            condition_flags=["empty"],
            special_flags=[],
            visual_evidence="Open plastic cup with food residue.",
            candidates=["yogurt container", "plastic cup"],
            low_risk_reason="allowed_reusable_household",
            matched_terms=["yogurt container"],
        )

        guidance = result["guidance"]
        self.assertEqual(guidance["disposal_action"], "trash")
        self.assertEqual(guidance["guidance_metadata"]["final_generation_path"], "original_llm")
        sent_prompt = request.call_args.args[0]
        self.assertIn('"allowed_disposal_actions": ["trash"]', sent_prompt)
        self.assertIn("Use household trash only for ordinary low-risk disposable items", sent_prompt)
        self.assertIn("ordinary single-use products", sent_prompt)


if __name__ == "__main__":
    unittest.main()
