import json
import os
import unittest
from unittest.mock import patch

import requests

from services import guidance_service
from services.guidance_llm_service import validate_guidance_basic
from services.recognition_router import _build_open_vlm_classification
from services import tavily_local_guidance_service as tavily
from services.vlm_service import OPEN_DETECTION_PROMPT


def _classification(item="Opened wrapper", *, location=None, normalized=None):
    details = {
        "normalized_item": item,
        "item_label": item,
        "material_category": "Mixed material",
        "disposal_category": "Trash",
        "broad_category": "Packaging",
        "condition_flags": ["single_use"],
        "special_handling_flags": [],
        "visual_observations": [],
        "matched_supported_label": None,
    }
    details.update(normalized or {})
    result = {
        "item": item,
        "category": details["disposal_category"],
        "status": "confident",
        "candidates": [],
        "recognition_source": "vlm_open",
        "recognition_confidence": {"level": "high", "score": 0.96},
        "recognition_details": {
            "status": "confident",
            "raw_item_label": item.casefold(),
            "candidates": [{"label": item, "confidence": 0.96}],
            "normalized": details,
        },
    }
    if location:
        result["location"] = location
    return result


def _chunk(
    chunk_id="source-1",
    *,
    local=False,
    requires_location_check=False,
    matched_fields=None,
):
    return {
        "chunk_id": chunk_id,
        "score": 10.0,
        "matched_fields": matched_fields or [],
        "requires_location_check": requires_location_check,
        "applicability": "conditional" if requires_location_check else "applicable",
        "applicability_reason_codes": [],
        "source_conditions": {},
        "chunk": {
            "id": chunk_id,
            "title": "Official disposal guidance",
            "source_name": "Official Agency",
            "source_url": "https://agency.gov/disposal",
            "location_scope": "local" if local else "federal",
            "generalizable": not local,
            "requires_location_check": requires_location_check,
            "content": "Use the listed disposal route and keep the item intact.",
            "source_excerpt": "Keep the item intact.",
            "source_claim": "Official disposal guidance applies.",
            "disposal_actions_supported": ["drop-off", "trash", "donate/reuse"],
            "warnings": [],
            "limitations": [],
            "source_metadata": {
                "title": "Official disposal guidance",
                "organization": "Official Agency",
                "url": "https://agency.gov/disposal",
                "trusted": True,
                "local": local,
                "status": "trusted_local" if local else "official_supporting",
                "trust_level": "LOCAL_PRIMARY" if local else "OFFICIAL_SUPPORTING",
            },
        },
    }


def _outcome(status="tavily_disabled", results=None):
    results = list(results or [])
    return {
        "status": status,
        "skip_reason": "missing_location" if status == "tavily_disabled" else None,
        "called": status.startswith("tavily_") and status != "tavily_disabled",
        "result_count": len(results),
        "trusted_source_count": len(results),
        "retrieval_results": results,
        "sources": [result["chunk"].get("source_metadata") for result in results],
    }


class SimplifiedGuidancePipelineTests(unittest.TestCase):
    def _llm_env(self):
        return patch.dict(
            os.environ,
            {
                "ENABLE_LLM_GUIDANCE": "true",
                "GUIDANCE_LLM_PROVIDER": "groq",
                "GROQ_API_KEY": "test-key",
            },
            clear=False,
        )

    def test_vlm_item_identity_is_not_replaced_by_alias_normalization(self):
        result = _build_open_vlm_classification(
            {
                "recognition_details": {
                    "status": "confident",
                    "raw_item_label": "cell phone",
                    "likely_material": "electronics",
                    "broad_category": "electronics",
                    "candidates": [{"label": "cell phone", "confidence": 0.97}],
                    "visual_observations": [],
                }
            }
        )

        self.assertEqual(result["item"], "Cell Phone")
        self.assertNotEqual(result["item"], "Smartphone")

    def test_open_vlm_prompt_has_only_a_neutral_response_shape(self):
        neutral_shape = OPEN_DETECTION_PROMPT.split(
            "Use this neutral return shape when the item cannot be identified:\n",
            1,
        )[1].strip()
        payload = json.loads(neutral_shape)

        self.assertEqual(payload["status"], "unknown")
        self.assertEqual(payload["raw_item_label"], "")
        self.assertEqual(payload["candidates"], [])
        self.assertTrue(payload["visual_observations"])
        self.assertTrue(
            all(item["value"] == "unknown" for item in payload["visual_observations"])
        )

    def test_incomplete_manual_rule_does_not_block_tavily(self):
        incomplete = {
            "status": "applicable",
            "rules_version": "test",
            "can_skip_tavily": False,
            "retrieval_results": [],
            "guidance": {
                "local_guidance": {"rule_id": "incomplete"},
                "guidance_metadata": {
                    "jurisdiction_id": "forsyth_county_ga",
                    "applicable_local_rule_ids": ["incomplete"],
                    "local_rule_applicability": "applicable",
                },
            },
        }
        with (
            patch("services.guidance_service.local_guidance_matcher.match_local_guidance", return_value=incomplete),
            patch("services.guidance_service.tavily_local_guidance_service.search_local_guidance", return_value=_outcome()) as search,
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch.dict(os.environ, {"ENABLE_LLM_GUIDANCE": "false"}, clear=False),
        ):
            guidance_service.build_prediction_response(
                _classification(location={"city": "Cumming", "state": "Georgia"}),
                jurisdiction_id="forsyth_county_ga",
            )

        search.assert_called_once()

    def test_official_city_county_and_state_sources_are_classified(self):
        cases = (
            ("City of Raleigh Solid Waste", "https://raleighnc.gov/waste", "raleighnc.gov", "city_exact"),
            ("Wake County Solid Waste", "https://wake.gov/waste", "wake.gov", "county_exact"),
            ("North Carolina Statewide Recycling", "https://deq.nc.gov/recycling", "deq.nc.gov", "statewide"),
        )
        location = {"city": "Raleigh", "county": "Wake County", "state": "North Carolina"}
        for title, url, domain, expected in cases:
            with self.subTest(expected=expected):
                record = tavily._SourceRecord(
                    position=1,
                    title=title,
                    url=url,
                    domain=domain,
                    organization=title,
                    snippet=(
                        f"{title} accepts batteries through its designated recycling drop-off."
                    ),
                    content=(
                        f"{title} accepts batteries through its designated recycling drop-off."
                    ),
                    relevance_score=1.0,
                    raw_content="",
                )
                validation = tavily._validation_result(
                    record,
                    classification=_classification("Battery"),
                    location=location,
                )
                self.assertEqual(validation.trust_level, tavily.LOCAL_PRIMARY)
                self.assertEqual(validation.applicability_label, expected)

    def test_wrong_state_source_is_rejected(self):
        record = tavily._SourceRecord(
            position=1,
            title="Georgia Statewide Battery Recycling",
            url="https://epd.ga.gov/battery-recycling",
            domain="epd.ga.gov",
            organization="Georgia EPD",
            snippet="Georgia statewide battery recycling and waste disposal.",
            content="Georgia statewide battery recycling and waste disposal.",
            relevance_score=1.0,
            raw_content="",
        )
        validation = tavily._validation_result(
            record,
            classification=_classification("Battery"),
            location={"city": "Raleigh", "state": "North Carolina"},
        )

        self.assertEqual(validation.trust_level, tavily.REJECTED)
        self.assertIn("wrong_state", validation.rejection_reasons)

    def test_do_not_dismantle_is_accepted_by_structural_validation(self):
        validated, errors = validate_guidance_basic(
            {
                "disposal_action": "drop-off",
                "summary": "Use an electronics drop-off.",
                "prep_steps": ["Do not dismantle the phone."],
                "next_step": "Take the phone to an approved electronics collection site.",
                "alternatives": [],
            },
            {
                "allowed_disposal_actions": {"drop-off"},
                "retrieved_chunks": [_chunk()["chunk"]],
            },
        )

        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_paraphrased_source_names_do_not_reject_guidance(self):
        validated, errors = validate_guidance_basic(
            {
                "disposal_action": "drop-off",
                "summary": "Use an electronics drop-off.",
                "prep_steps": ["Keep the phone intact."],
                "next_step": "Take the phone to an approved electronics collection site.",
                "alternatives": [],
                "sources_used": ["Official Agency electronics page"],
            },
            {
                "allowed_disposal_actions": {"drop-off"},
                "retrieved_chunks": [_chunk()["chunk"]],
            },
        )

        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])
        self.assertNotIn("sources_used", validated)

    def test_missing_sources_used_does_not_reject_guidance(self):
        validated, errors = validate_guidance_basic(
            {
                "disposal_action": "drop-off",
                "summary": "Use an electronics drop-off.",
                "prep_steps": ["Keep the phone intact."],
                "next_step": "Take the phone to an approved electronics collection site.",
                "alternatives": [],
            },
            {
                "allowed_disposal_actions": {"drop-off"},
                "retrieved_chunks": [_chunk()["chunk"]],
            },
        )

        self.assertIsNotNone(validated)
        self.assertEqual(errors, [])

    def test_invalid_json_and_missing_required_fields_still_fail(self):
        context = {
            "allowed_disposal_actions": {"drop-off"},
            "retrieved_chunks": [_chunk()["chunk"]],
        }

        self.assertEqual(validate_guidance_basic("not json", context)[1], ["invalid_json"])
        validated, errors = validate_guidance_basic(
            {"disposal_action": "drop-off"},
            context,
        )
        self.assertIsNone(validated)
        self.assertIn("missing_summary", errors)
        self.assertIn("invalid_prep_steps", errors)
        self.assertIn("missing_next_step", errors)

    def test_valid_llm_guidance_reaches_the_response_unchanged(self):
        result = _chunk()
        payload = {
            "disposal_action": "donate/reuse",
            "summary": "Keep using this wrapper as a craft material if it is clean.",
            "prep_steps": ["Keep it intact."],
            "next_step": "Donate it through an accepted local reuse program.",
            "alternatives": ["Reuse it only if it is clean."],
            "warnings": [],
            "confidence": "medium",
        }
        with (
            self._llm_env(),
            patch("services.guidance_service.local_guidance_matcher.match_local_guidance", return_value={"status": "no_match"}),
            patch("services.guidance_service.tavily_local_guidance_service.search_local_guidance", return_value=_outcome()),
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[result]),
            patch("services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance", return_value=None),
            patch("services.guidance_llm_service._groq_request", return_value=json.dumps(payload)),
        ):
            response = guidance_service.build_prediction_response(_classification())

        self.assertEqual(response["guidance_source"], "json_rag_llm_generated")
        self.assertEqual(response["summary"], payload["summary"])
        self.assertEqual(response["prep_steps"], payload["prep_steps"])
        self.assertEqual(response["next_step"], payload["next_step"])
        self.assertEqual(response["alternatives"], payload["alternatives"])
        self.assertEqual(response["steps"], [*payload["prep_steps"], payload["next_step"]])
        self.assertTrue(response["guidance_metadata"]["location_search_recommended"])
        self.assertEqual(response["guidance_metadata"]["location_search_provider"], "earth911")
        self.assertEqual(response["guidance_metadata"]["guidance_generation_status"], "succeeded")
        self.assertEqual(
            response["guidance_metadata"]["accepted_sources"],
            [
                {
                    "source_id": "source-1",
                    "title": "Official disposal guidance",
                    "url": "https://agency.gov/disposal",
                    "organization": "Official Agency",
                    "trust_level": "OFFICIAL_SUPPORTING",
                    "jurisdiction": {
                        "location_scope": "federal",
                        "applicability": "applicable",
                        "applicability_label": None,
                        "requires_location_check": False,
                        "matched_fields": [],
                    },
                }
            ],
        )

    def test_llm_failure_preserves_manual_local_evidence(self):
        with (
            self._llm_env(),
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch("services.guidance_service.guidance_cache_service.build_source_grounded_cache_context", return_value=None),
            patch("services.guidance_llm_service._groq_request", side_effect=requests.Timeout()),
        ):
            response = guidance_service.build_prediction_response(
                _classification("Laptop", normalized={"disposal_category": "Electronics"}),
                jurisdiction_id="forsyth_county_ga",
            )

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["local_guidance"]["rule_id"], "fc_electronics")
        self.assertTrue(response["guidance_metadata"]["source_urls"])
        self.assertEqual(response["guidance_metadata"]["local_evidence_status"], "accepted")
        self.assertEqual(response["guidance_metadata"]["guidance_generation_status"], "failed")

    def test_verified_local_requires_applicable_local_evidence(self):
        federal = _chunk(requires_location_check=True)
        federal_payload = {
            "disposal_action": "drop-off",
            "summary": "Use an appropriate drop-off.",
            "prep_steps": ["Keep it intact."],
            "next_step": "Take it to an approved collection site.",
            "alternatives": [],
            "warnings": [],
            "confidence": "medium",
        }
        with (
            self._llm_env(),
            patch("services.guidance_service.local_guidance_matcher.match_local_guidance", return_value={"status": "no_match"}),
            patch("services.guidance_service.tavily_local_guidance_service.search_local_guidance", return_value=_outcome("tavily_official_supporting", [federal])),
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch("services.guidance_llm_service._groq_request", return_value=json.dumps(federal_payload)),
        ):
            response = guidance_service.build_prediction_response(
                _classification(location={"city": "Raleigh", "state": "North Carolina"})
            )
        self.assertNotEqual(response["impact_level"], "Verified Local Guidance")

        local_payload = dict(federal_payload)
        with (
            self._llm_env(),
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch("services.guidance_service.guidance_cache_service.build_source_grounded_cache_context", return_value=None),
            patch("services.guidance_llm_service._groq_request", return_value=json.dumps(local_payload)),
        ):
            local_response = guidance_service.build_prediction_response(
                _classification("Laptop", normalized={"disposal_category": "Electronics"}),
                jurisdiction_id="forsyth_county_ga",
            )
        self.assertEqual(local_response["impact_level"], "Verified Local Guidance")


if __name__ == "__main__":
    unittest.main()
