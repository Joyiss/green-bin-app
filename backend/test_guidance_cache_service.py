import unittest
from unittest.mock import patch

from services import guidance_cache_service


def _retrieval_result(chunk_id="chunk-1", **chunk_overrides):
    chunk = {
        "id": chunk_id,
        "source_name": "Call2Recycle",
        "source_url": "https://example.com",
        "location_scope": "national",
        "requires_location_check": True,
        "source_claim": "Use a battery drop-off.",
        "source_excerpt": "Drop off batteries.",
        "limitations": ["Availability varies."],
    }
    chunk.update(chunk_overrides)
    return {
        "chunk": chunk,
        "chunk_id": chunk_id,
        "score": 8.25,
        "matched_fields": ["item_label_exact"],
        "requires_location_check": bool(chunk.get("requires_location_check")),
        "applicability": "applicable",
        "applicability_reason_codes": ["specific_item_evidence_supports_source"],
        "source_conditions": {
            "confirmed": ["battery"],
            "unknown": [],
            "contradicted": [],
        },
    }


def _classification(status="confident"):
    return {
        "item": "Battery",
        "category": "Battery",
        "status": status,
        "recognized_material_category": "Battery",
        "recognized_broad_category": "Batteries",
        "recognition_details": {
            "normalized": {
                "normalized_item": "Battery",
                "item_label": "Battery",
                "disposal_category": "Battery",
                "material_category": "Battery",
                "broad_category": "Batteries",
            },
        },
    }


def _retrieval_inputs():
    return {
        "item_label": "Battery",
        "material": "Battery",
        "category": "Battery",
        "condition_flags": ["hazardous", "requires_dropoff"],
        "special_flags": ["battery"],
    }


def _llm_context(condition_flags=None, special_flags=None):
    return {
        "normalized_item_label": "Battery",
        "material": "Battery",
        "broad_category": "Battery",
        "condition_flags": condition_flags or ["requires_dropoff", "hazardous"],
        "special_flags": special_flags or ["battery"],
        "visual_observations": [],
    }


class GuidanceCacheServiceTests(unittest.TestCase):
    def _provider_cache(self, provider, *, city="Seattle", county="King County", state="Washington"):
        llm_context = _llm_context()
        llm_context.update(
            {
                "confirmed_provider": provider,
                "location": {"city": city, "county": county, "state": state},
            }
        )
        return guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[_retrieval_result()],
            llm_context=llm_context,
        )

    def test_provider_cache_is_separated_by_provider_and_no_provider(self):
        no_provider = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[_retrieval_result()],
            llm_context=_llm_context(),
        )
        provider_a = self._provider_cache("Waste Pro")
        provider_b = self._provider_cache("Red Oak Sanitation")

        self.assertNotEqual(no_provider["cache_key"], provider_a["cache_key"])
        self.assertNotEqual(provider_a["cache_key"], provider_b["cache_key"])
        self.assertNotIn("confirmed_provider_key", no_provider["cache_key_input"])
        self.assertNotIn("provider_location", no_provider["cache_key_input"])
        self.assertEqual(provider_a["cache_key_input"]["confirmed_provider_key"], "waste_pro")

    def test_provider_cache_is_separated_by_exact_location(self):
        seattle = self._provider_cache("Waste Pro")
        tacoma = self._provider_cache(
            "Waste Pro", city="Tacoma", county="Pierce County"
        )
        blank_county = self._provider_cache("Waste Pro", county="")

        self.assertNotEqual(seattle["cache_key"], tacoma["cache_key"])
        self.assertNotEqual(seattle["cache_key"], blank_county["cache_key"])
        self.assertEqual(blank_county["cache_key_input"]["provider_location"]["county"], "")

    def test_source_cache_key_is_deterministic_for_reordered_inputs(self):
        left = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[
                _retrieval_result("chunk-2"),
                _retrieval_result("chunk-1"),
            ],
            llm_context=_llm_context(
                condition_flags=["requires_dropoff", "hazardous"],
                special_flags=["dropoff_recommended", "battery"],
            ),
        )
        right = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[
                _retrieval_result("chunk-1"),
                _retrieval_result("chunk-2"),
            ],
            llm_context=_llm_context(
                condition_flags=["hazardous", "requires_dropoff"],
                special_flags=["battery", "dropoff_recommended"],
            ),
        )

        self.assertEqual(left["cache_key"], right["cache_key"])

    def test_source_excerpt_formatting_does_not_change_cache_key(self):
        base = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[_retrieval_result(source_excerpt="Drop off batteries.")],
            llm_context=_llm_context(),
        )
        changed_text = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[_retrieval_result(source_excerpt="  Drop off batteries.  ")],
            llm_context=_llm_context(),
        )

        self.assertEqual(base["cache_key"], changed_text["cache_key"])

    def test_visual_observations_are_part_of_source_cache_key(self):
        clean_context = _llm_context()
        clean_context["visual_observations"] = [
            {
                "aspect": "contamination",
                "value": "unknown",
                "confidence": None,
                "evidence": "",
            }
        ]
        residue_context = _llm_context()
        residue_context["visual_observations"] = [
            {
                "aspect": "contamination",
                "value": "food residue visible",
                "confidence": 0.8,
                "evidence": "Residue visible.",
            }
        ]

        clean = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[_retrieval_result()],
            llm_context=clean_context,
        )
        residue = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[_retrieval_result()],
            llm_context=residue_context,
        )

        self.assertNotEqual(clean["cache_key"], residue["cache_key"])
        self.assertIn("visual_observations", residue["cache_key_input"])
        self.assertNotIn("visual_observations", residue)

    def test_applicability_changes_source_cache_identity(self):
        applicable = _retrieval_result()
        conditional = {
            **_retrieval_result(),
            "applicability": "conditional",
            "applicability_reason_codes": ["local_acceptance_unverified"],
        }
        applicable_context = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[applicable],
            llm_context=_llm_context(),
        )
        conditional_context = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=[conditional],
            llm_context=_llm_context(),
        )

        self.assertNotEqual(applicable_context["cache_key"], conditional_context["cache_key"])
        self.assertIn("retrieval_applicability", conditional_context["cache_key_input"])

    def test_cache_payload_keeps_visual_observations_inside_json_context(self):
        llm_context = _llm_context()
        llm_context["visual_observations"] = [
            {
                "aspect": "condition",
                "value": "appears intact",
                "confidence": 0.9,
                "evidence": "No visible damage.",
            }
        ]
        retrieval_results = [_retrieval_result()]
        cache_context = guidance_cache_service.build_source_grounded_cache_context(
            classification=_classification(),
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=retrieval_results,
            llm_context=llm_context,
        )
        guidance = {
            "guidance_source": "json_rag_llm_generated",
            "disposal_action": "drop-off",
            "summary": "Use battery drop-off.",
            "steps": ["Tape terminals.", "Use drop-off."],
            "guidance_metadata": {
                "applicable_chunk_ids": ["chunk-1"],
                "retrieved_chunk_ids": ["chunk-1"],
            },
        }

        payload = guidance_cache_service.build_cache_payload(
            classification=_classification(),
            guidance=guidance,
            cache_context=cache_context,
            retrieval_inputs=_retrieval_inputs(),
            retrieval_results=retrieval_results,
            llm_context=llm_context,
        )

        self.assertNotIn("visual_observations", payload)
        self.assertIn("visual_observations", payload["cache_key_input"])
        self.assertEqual(
            payload["retrieval_context"]["llm_context"]["visual_observations"],
            llm_context["visual_observations"],
        )

    def test_cached_guidance_from_row_preserves_shape_and_cache_markers(self):
        guidance = guidance_cache_service.cached_guidance_from_row(
            {
                "cache_key": "cache-key",
                "cache_key_version": guidance_cache_service.CACHE_KEY_VERSION,
                "guidance_source": "json_rag_llm_generated",
                "disposal_action": "drop-off",
                "material_code": None,
                "impact_level": "Check Local Guidance",
                "summary": "Use a battery drop-off.",
                "steps": ["Tape exposed terminals.", "Use drop-off."],
                "warnings": ["Do not use curbside recycling."],
                "guidance_metadata": {
                    "retrieved_chunk_ids": ["chunk-1"],
                    "applicable_chunk_ids": ["chunk-1"],
                },
            }
        )

        self.assertEqual(guidance["guidance_source"], "json_rag_llm_generated")
        self.assertEqual(guidance["steps"], ["Tape exposed terminals.", "Use drop-off."])
        self.assertEqual(guidance["warnings"], ["Do not use curbside recycling."])
        self.assertTrue(guidance["cache_hit"])
        self.assertTrue(guidance["guidance_metadata"]["guidance_cache_hit"])
        self.assertEqual(
            guidance["guidance_metadata"]["guidance_cache_key"],
            "cache-key",
        )

    def test_previous_manual_rule_cache_version_is_not_reused(self):
        old_row = {
            "cache_key": "old-manual-key",
            "cache_key_version": "guidance_cache_v2",
            "guidance_source": "json_rag_llm_generated",
            "disposal_action": "drop-off",
            "summary": "Use the old manual destination.",
            "steps": ["Use the old manual destination."],
            "retrieved_chunk_ids": ["manual-fc_electronics"],
            "guidance_metadata": {
                "retrieved_chunk_ids": ["manual-fc_electronics"],
                "applicable_chunk_ids": ["manual-fc_electronics"],
            },
        }
        with patch.object(
            guidance_cache_service.disposal_guidance_repository,
            "get_guidance_by_cache_key",
            return_value=old_row,
        ):
            result = guidance_cache_service.get_cached_source_grounded_guidance(
                {"cache_key": "old-manual-key"}
            )

        self.assertEqual(guidance_cache_service.CACHE_KEY_VERSION, "guidance_cache_v3")
        self.assertIsNone(result)

    def test_cacheability_rejects_unsafe_cases(self):
        cache_context = {
            "retrieved_chunk_ids": ["chunk-1"],
        }
        guidance = {
            "guidance_source": "json_rag_llm_generated",
            "disposal_action": "drop-off",
            "summary": "Use battery drop-off.",
            "steps": ["Tape terminals.", "Use drop-off."],
            "guidance_metadata": {"applicable_chunk_ids": ["chunk-1"]},
        }

        self.assertFalse(
            guidance_cache_service.source_grounded_guidance_is_cacheable(
                classification=_classification(status="unknown"),
                guidance=guidance,
                cache_context=cache_context,
            )
        )
        self.assertFalse(
            guidance_cache_service.source_grounded_guidance_is_cacheable(
                classification=_classification(),
                guidance={"guidance_source": "safe_fallback", "disposal_action": None},
                cache_context=cache_context,
            )
        )
        self.assertFalse(
            guidance_cache_service.source_grounded_guidance_is_cacheable(
                classification=_classification(),
                guidance=guidance,
                cache_context={"retrieved_chunk_ids": []},
            )
        )
        self.assertFalse(
            guidance_cache_service.source_grounded_guidance_is_cacheable(
                classification=_classification(),
                guidance={"guidance_source": "json_rag_llm_generated"},
                cache_context=cache_context,
            )
        )
        self.assertTrue(
            guidance_cache_service.source_grounded_guidance_is_cacheable(
                classification=_classification(),
                guidance=guidance,
                cache_context=cache_context,
            )
        )
        self.assertFalse(
            guidance_cache_service.source_grounded_guidance_is_cacheable(
                classification=_classification(),
                guidance={
                    **guidance,
                    "disposal_action": "recycle",
                    "guidance_metadata": {
                        "applicable_chunk_ids": [],
                        "conditional_chunk_ids": ["chunk-1"],
                    },
                },
                cache_context=cache_context,
            )
        )
        self.assertTrue(
            guidance_cache_service.source_grounded_guidance_is_cacheable(
                classification=_classification(),
                guidance={
                    **guidance,
                    "disposal_action": "trash",
                    "guidance_metadata": {
                        "applicable_chunk_ids": [],
                        "conditional_chunk_ids": ["chunk-1"],
                    },
                },
                cache_context=cache_context,
            )
        )


if __name__ == "__main__":
    unittest.main()
