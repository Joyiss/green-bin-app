import json
import os
import unittest
from unittest.mock import patch

from services import guidance_service
from services.gemini_text_client import GeminiTextError
from services.guidance_llm_service import (
    try_generate_source_grounded_guidance,
    validate_guidance_basic,
)


def _result(
    chunk_id: str,
    *,
    title: str,
    url: str,
    content: str,
    action: str,
    local: bool,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "score": 10.0 if local else 3.0,
        "matched_fields": ["city_exact"] if local else [],
        "applicability": "applicable",
        "source_conditions": {},
        "chunk": {
            "id": chunk_id,
            "title": title,
            "source_name": title,
            "source_url": url,
            "source_role": "official_primary",
            "location_scope": "Seattle, Washington" if local else "national",
            "content": content,
            "source_excerpt": content,
            "source_claim": content,
            "disposal_actions_supported": [action],
            "warnings": [],
            "limitations": [],
            "source_metadata": {
                "title": title,
                "organization": title,
                "url": url,
                "local": local,
            },
            "decision_signals": {
                "applicability_label": "city_exact" if local else "official_supporting"
            },
        },
    }


def _writer_payload(action: str, destination: str) -> dict:
    return {
        "summary": {
            "action_type": action,
            "destination": destination,
            "qualifier": None,
        },
        "preparation": {
            "required": False,
            "steps": [],
            "no_preparation_message": None,
        },
        "important_notes": [],
        "reasoning": "The local source names this disposal route.",
        "references": [],
    }


class GeminiGuidanceRegressionTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {"ENABLE_LLM_GUIDANCE": "true", "GEMINI_API_KEY": "test-key"},
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    @patch("services.guidance_llm_service._text_llm_request")
    def test_seattle_computer_mouse_prefers_local_excerpt_and_one_call(self, request):
        local_text = (
            "Seattle accepts computer mice at city electronics drop-off sites. "
            "Keep the mouse intact and bring it to an electronics collection site."
        )
        request.return_value = json.dumps(
            _writer_payload("drop-off", "Seattle electronics drop-off site")
        )
        sources = [
            _result(
                "epa",
                title="EPA electronics overview",
                url="https://www.epa.gov/recycle/electronics-donation-and-recycling",
                content="Electronics recycling availability varies across the United States.",
                action="check local guidance",
                local=False,
            ),
            _result(
                "seattle-mouse",
                title="Seattle electronics collection",
                url="https://seattle.gov/utilities/electronics",
                content=local_text,
                action="drop-off",
                local=True,
            ),
            _result(
                "duplicate",
                title="Duplicate Seattle page",
                url="https://seattle.gov/utilities/electronics-copy",
                content=local_text,
                action="drop-off",
                local=True,
            ),
            _result(
                "noise",
                title="Department home page",
                url="https://seattle.gov/home",
                content="Welcome. News. Departments. Contact us. Accessibility links.",
                action="drop-off",
                local=True,
            ),
        ]

        result = try_generate_source_grounded_guidance(
            recognized_item="Computer mouse",
            normalized_item_label="Computer mouse",
            material="Electronics",
            broad_category="Electronics",
            condition_flags=[],
            special_flags=["electronics"],
            visual_evidence=None,
            candidates=[],
            location={"city": "Seattle", "state": "Washington"},
            retrieval_results=sources,
        )

        self.assertEqual(result["guidance"]["disposal_action"], "drop-off")
        request.assert_called_once()
        prompt = request.call_args.args[0]
        self.assertEqual(prompt.count("Seattle accepts computer mice"), 1)
        self.assertNotIn("EPA electronics overview", prompt)
        self.assertNotIn("Accessibility links", prompt)

    def test_aa_battery_rejects_lead_acid_and_ev_restrictions(self):
        evidence = {
            "content": "AA alkaline batteries are accepted at the household battery drop-off.",
            "conditions": {},
            "warnings": [],
            "limitations": [],
        }
        payload = _writer_payload("drop-off", "Household battery drop-off")
        payload["important_notes"] = [
            "Lead-acid and EV batteries have separate transport restrictions."
        ]

        validated, errors = validate_guidance_basic(
            payload,
            {
                "recognized_item": "AA battery",
                "allowed_disposal_actions": {"drop-off"},
                "retrieved_chunks": [evidence],
                "condition_flags": [],
            },
        )

        self.assertIsNone(validated)
        self.assertIn("unrelated_battery_restriction", errors)

    def test_lead_acid_restriction_is_allowed_when_item_and_evidence_match(self):
        evidence = {
            "content": "Lead-acid vehicle batteries must use the hazardous battery drop-off.",
            "conditions": {},
            "warnings": [],
            "limitations": [],
        }
        payload = _writer_payload("drop-off", "Hazardous battery drop-off")
        payload["important_notes"] = ["This route is for lead-acid vehicle batteries."]

        validated, errors = validate_guidance_basic(
            payload,
            {
                "recognized_item": "Lead-acid vehicle battery",
                "allowed_disposal_actions": {"drop-off"},
                "retrieved_chunks": [evidence],
                "condition_flags": [],
            },
        )

        self.assertEqual(errors, [])
        self.assertIsNotNone(validated)

    @patch("services.guidance_llm_service._text_llm_request")
    def test_insufficient_evidence_skips_gemini(self, request):
        result = try_generate_source_grounded_guidance(
            recognized_item="Computer mouse",
            normalized_item_label="Computer mouse",
            material="Electronics",
            broad_category="Electronics",
            condition_flags=[],
            special_flags=[],
            visual_evidence=None,
            candidates=[],
            location=None,
            retrieval_results=[
                _result(
                    "noise",
                    title="Generic page",
                    url="https://example.gov/home",
                    content="Welcome to our website. Read news and contact the department.",
                    action="drop-off",
                    local=False,
                )
            ],
        )

        self.assertIsNone(result["guidance"])
        self.assertEqual(result["failure_reason"], "no_chunks")
        request.assert_not_called()

    def test_guidance_timeout_uses_safe_fallback_after_one_call(self):
        source = _result(
            "seattle-mouse",
            title="Seattle electronics collection",
            url="https://seattle.gov/utilities/electronics",
            content="Seattle accepts computer mice at electronics drop-off sites.",
            action="drop-off",
            local=True,
        )
        classification = {
            "item": "Computer mouse",
            "category": "Electronics",
            "status": "confident",
            "candidates": [],
            "location": {"city": "Seattle", "state": "Washington"},
        }
        tavily_outcome = {
            "status": "tavily_success",
            "called": True,
            "retrieval_results": [],
            "sources": [],
        }
        with (
            patch(
                "services.guidance_service.tavily_local_guidance_service.search_local_guidance",
                return_value=tavily_outcome,
            ),
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[source],
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ),
            patch(
                "services.guidance_llm_service._text_llm_request",
                side_effect=GeminiTextError("timeout", "timed out"),
            ),
        ):
            response = guidance_service.build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["guidance_metadata"]["fallback_reason"], "timeout")
        self.assertEqual(response["guidance_metadata"]["text_llm_call_count"], 1)


if __name__ == "__main__":
    unittest.main()
