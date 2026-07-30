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


def _payload(**overrides):
    payload = {
        "disposal_action": "drop-off",
        "summary": "Take this laptop to electronics drop-off.",
        "steps": ["Back up personal files.", "Take the laptop to drop-off."],
        "warnings": [],
        "confidence": "high",
        "sources_used": ["electronics_01"],
    }
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

    def test_exact_normalized_duplicate_is_rejected(self):
        _, errors = validate_guidance_basic(
            _payload(steps=["Use electronics drop-off!", " use   electronics dropoff ", "Use electronics drop-off."]),
            self.context(),
        )
        # Punctuation removal does not erase a meaningful hyphen, so only the first and third match.
        self.assertIn("duplicate_steps", errors)

    def test_near_duplicates_are_allowed(self):
        validated, errors = validate_guidance_basic(
            _payload(steps=["Take it to electronics drop-off.", "Find a nearby electronics drop-off."]),
            self.context(),
        )
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_affirmative_dangerous_instructions_are_rejected(self):
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
                _, errors = validate_guidance_basic(
                    _payload(steps=[instruction, "Use electronics drop-off."]), self.context()
                )
                self.assertTrue(any(error.startswith("dangerous_instruction:") for error in errors))

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
        _, errors = validate_guidance_basic(
            _payload(warnings=["Do not wait; disassemble the laptop."]), self.context()
        )
        self.assertTrue(any(error.startswith("dangerous_instruction:") for error in errors))

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

    def test_genuinely_dangerous_part_removal_is_rejected(self):
        cases = [
            "Dismantle the phone before taking it in.",
            "Open the device and remove the battery.",
            "Keep the device intact; then puncture the battery.",
            "Avoid delays and remove the battery.",
        ]
        for instruction in cases:
            with self.subTest(instruction=instruction):
                _, errors = validate_guidance_basic(
                    _payload(steps=[instruction, "Use electronics drop-off."]),
                    self.context(),
                )
                self.assertTrue(any(error.startswith("dangerous_instruction:") for error in errors))

    def test_source_names_in_main_guidance_are_nonblocking_warnings(self):
        validated, errors = validate_guidance_basic(
            _payload(steps=["Follow EPA guidance.", "Use electronics drop-off."]), self.context()
        )
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])
        self.assertIn(
            "source_name_in_main_guidance:epa",
            validated["validation_warnings"],
        )
        validated, errors = validate_guidance_basic(_payload(), self.context())
        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_unsupported_action_and_absolute_claims_are_rejected(self):
        _, errors = validate_guidance_basic(
            _payload(disposal_action="trash", summary="This is recyclable everywhere."), self.context()
        )
        self.assertIn("unsupported_disposal_action", errors)
        self.assertTrue(any(error.startswith("unsupported_strong_claim:") for error in errors))

    def test_curbside_and_hazardous_claims_require_source_support(self):
        curbside = _payload(summary="Recycle this container curbside.")
        self.assertIn("unsupported_curbside_claim", validate_guidance_basic(curbside, self.context())[1])
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
        self.assertIn('"allowed_disposal_actions": ["trash"]', prompt)

    @patch("services.guidance_llm_service._groq_request")
    def test_original_safe_output_has_original_path(self, request):
        request.return_value = json.dumps(_payload())
        guidance = self.source_call()["guidance"]
        self.assertEqual(guidance["guidance_metadata"]["final_generation_path"], "original_llm")
        request.assert_called_once()

    @patch("services.guidance_llm_service._groq_request")
    def test_duplicate_fails_without_repair(self, request):
        request.return_value = json.dumps(_payload(steps=["Use drop-off.", "Use drop-off."]))
        result = self.source_call()
        request.assert_called_once()
        self.assertIsNone(result["guidance"])
        self.assertEqual(result["failure_reason"], "duplicate_steps")

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
    def test_unsafe_output_fails_without_repair_or_deterministic_fallback(self, request):
        request.return_value = json.dumps(_payload(steps=["Disassemble the laptop.", "Use drop-off."]))
        with self.assertLogs("services.guidance_llm_service", level="INFO") as logs:
            result = self.source_call()
        request.assert_called_once()
        self.assertIsNone(result["guidance"])
        self.assertEqual(result["failure_reason"], "dangerous_instruction:disassemble")
        combined = " ".join(logs.output)
        self.assertIn("original_llm_output=", combined)
        self.assertIn("validation_reason=", combined)
        self.assertIn("repair_attempted=False", combined)
        self.assertIn("deterministic_fallback_used=false", combined)

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

    def test_prompt_marks_examples_as_non_templates(self):
        prompt = _build_source_grounded_prompt(
            recognized_item="Laptop", normalized_item_label="Laptop", material="Electronics",
            broad_category="Electronics", condition_flags=[], special_flags=[], visual_evidence=None,
            candidates=[], location=None, chunks=[_chunk()], allowed_disposal_actions=["drop-off"],
        )
        self.assertIn("Do not copy them blindly", prompt)
        self.assertIn('"steps":[]', prompt)
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
            "Base the disposal_action on the actual recognized physical object",
            prompt,
        )
        self.assertIn(
            "packaging/container type, material, condition_flags, cleanliness or residue",
            prompt,
        )
        self.assertIn(
            "Do not choose donate/reuse for opened, used, dirty, broken, food-soiled, or ordinary single-use packaging",
            prompt,
        )
        self.assertIn(
            "If packaging and contents are both mentioned, guide disposal for the package/container",
            prompt,
        )
        self.assertIn("Use applicable chunks for definite disposal claims.", prompt)
        self.assertIn(
            "A conditional chunk may be mentioned only as an if-then alternative",
            prompt,
        )
        self.assertIn("Separate confirmed visual facts from unknown properties.", prompt)
        self.assertIn('"recognized_item": "Opened single-use chip bag"', prompt)
        self.assertIn('"visual_evidence": "Crinkly snack pouch with crumbs."', prompt)

    def test_general_safe_prompt_excludes_reuse_for_single_use_packaging(self):
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

        self.assertIn(
            "Avoid technically possible but unrealistic advice for the specific object.",
            prompt,
        )
        self.assertIn("use household trash as the main action when trash is allowed", prompt)
        self.assertIn("Reserve check local guidance as the main action only when", prompt)
        self.assertIn('"allowed_disposal_actions": ["trash"]', prompt)
        self.assertIn('"recognized_item": "Used plastic yogurt container"', prompt)
        self.assertIn('"visual_evidence": "Open plastic cup with food residue."', prompt)
        self.assertIn('"visual_observations": [{"aspect": "contamination"', prompt)
        self.assertIn("Treat visual_observations as recognition evidence only.", prompt)
        self.assertIn(
            "For edible food, prefer using or sharing it while still edible",
            prompt,
        )

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
            "steps": ["Wipe dust from the shell.", "Donate it if playable."], "warnings": [],
            "confidence": "low", "sources_used": [],
        })
        result = try_generate_general_safe_guidance(
            recognized_item="Drum", normalized_item_label="Drum", material="Wood",
            broad_category="Instrument", condition_flags=[], special_flags=[], visual_evidence=None,
            candidates=[], low_risk_reason="allowed_reusable_household", matched_terms=["drum"],
        )
        guidance = result["guidance"]
        self.assertEqual(guidance["guidance_metadata"]["final_generation_path"], "original_llm")
        self.assertEqual(
            {"disposal_action", "material_code", "impact_level", "summary", "steps", "guidance_source", "guidance_metadata"},
            set(guidance),
        )

    @patch("services.guidance_llm_service._groq_request")
    def test_general_safe_generation_uses_trash_for_single_use_packaging(self, request):
        request.return_value = json.dumps({
            "disposal_action": "trash",
            "summary": "Put this used yogurt container in household trash if it has residue.",
            "steps": ["Empty loose residue first.", "Place the used container in household trash."],
            "warnings": [],
            "confidence": "low",
            "sources_used": [],
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
        self.assertIn("household trash as the main action", sent_prompt)
        self.assertIn("ordinary single-use packaging", sent_prompt)


if __name__ == "__main__":
    unittest.main()
