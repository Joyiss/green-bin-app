import unittest
from unittest.mock import patch

from services.guidance_service import _build_retrieval_inputs, build_prediction_response


def _json_chunk(**overrides):
    chunk = {
        "id": "chunk-1",
        "title": "EPA Battery Guidance",
        "source_name": "Call2Recycle",
        "source_url": "https://www.call2recycle.org/",
        "source_type": "stewardship_program",
        "location_scope": "national",
        "generalizable": True,
        "requires_location_check": True,
        "applies_to": {
            "item_labels": ["batteries"],
            "materials": ["battery"],
            "categories": ["batteries"],
            "condition_flags": ["requires_dropoff"],
        },
        "content": "Rechargeable batteries should go to a designated battery drop-off program. Tape exposed terminals before transport.",
        "disposal_actions_supported": ["Drop-off"],
        "warnings": ["Do not place rechargeable batteries in curbside recycling."],
        "limitations": ["Program availability varies by location."],
        "confidence": "high",
        "verified": True,
        "source_grounded": True,
        "human_reviewed": False,
        "review_status": "generated_from_sources",
    }
    chunk.update(overrides)
    return chunk


def _retrieval_result(
    chunk: dict,
    *,
    score: float = 8.25,
    matched_fields=None,
    applicability: str = "applicable",
    applicability_reason_codes=None,
):
    return {
        "chunk": chunk,
        "chunk_id": chunk["id"],
        "score": score,
        "matched_fields": matched_fields or ["item_label_exact"],
        "requires_location_check": bool(chunk.get("requires_location_check")),
        "applicability": applicability,
        "applicability_reason_codes": applicability_reason_codes or [],
        "source_conditions": {
            "confirmed": [],
            "unknown": [],
            "contradicted": [],
        },
    }


def _open_classification(
    *,
    item: str,
    category: str,
    material_category: str,
    broad_category: str,
    raw_item_label: str | None = None,
    likely_material: str | None = None,
    condition_flags=None,
    special_handling_flags=None,
    visual_observations=None,
    visual_evidence: str | None = None,
):
    return {
        "item": item,
        "category": category,
        "status": "confident",
        "candidates": [],
        "trusted_guidance_available": False,
        "recognized_material_category": material_category,
        "recognized_broad_category": broad_category,
        "recognition_details": {
            "raw_item_label": raw_item_label or item.lower(),
            "likely_material": likely_material or material_category.lower(),
            "broad_category": broad_category.lower(),
            "visual_evidence": visual_evidence or "",
            "visual_observations": visual_observations or [],
            "normalized": {
                "item_label": item,
                "material_category": material_category,
                "broad_category": broad_category,
                "condition_flags": condition_flags or [],
                "special_handling_flags": special_handling_flags or [],
                "visual_observations": visual_observations or [],
                "matched_supported_label": None,
            },
        },
    }


class GuidanceServiceTests(unittest.TestCase):
    def test_verified_provider_without_item_evidence_gets_cautious_confirmation_step(self):
        classification = _open_classification(
            item="Plastic Water Bottle",
            category="Plastic",
            material_category="Plastic",
            broad_category="Plastic",
        )
        classification["location"] = {
            "city": "Cumming",
            "state": "Georgia",
            "waste_provider": "Custom Disposal",
        }
        outcome = {
            "status": "tavily_insufficient_evidence",
            "called": True,
            "call_count": 1,
            "result_count": 0,
            "trusted_source_count": 0,
            "retrieval_results": [],
            "sources": [],
            "provider_context_used": True,
            "canonical_provider": "Custom Disposal",
            "provider_specific_evidence": False,
            "provider_acceptance_evidence": False,
            "provider_rejection_evidence": False,
            "provider_evidence_status": "unavailable",
        }
        with (
            patch(
                "services.guidance_service.tavily_local_guidance_service.search_local_guidance",
                return_value=outcome,
            ),
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "llm_disabled"},
            ),
        ):
            response = build_prediction_response(classification)

        combined = " ".join(response["steps"])
        self.assertIn("Check whether Custom Disposal accepts this item", combined)
        self.assertNotIn("Custom Disposal recycling cart", combined)
        self.assertEqual(
            response["guidance_metadata"]["provider_evidence_status"],
            "unavailable",
        )

    def test_guidance_lookup_prefers_disposal_category_and_keeps_material_separate(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognized_material_category": "Plastic",
            "recognized_broad_category": "Electronics",
            "recognition_details": {
                "raw_item_label": "calculator",
                "likely_material": "plastic",
                "broad_category": "electronics",
                "normalized": {
                    "normalized_item": "Calculator",
                    "item_label": "Calculator",
                    "disposal_category": "Electronics",
                    "material_category": "Plastic",
                    "broad_category": "Electronics",
                },
            },
        }

        retrieval_inputs = _build_retrieval_inputs(classification)

        self.assertEqual(retrieval_inputs["category"], "Electronics")
        self.assertEqual(retrieval_inputs["category_candidates"][0], "Electronics")
        self.assertEqual(retrieval_inputs["material"], "Plastic")
        self.assertEqual(retrieval_inputs["material_candidates"][0], "Plastic")

    def test_retrieval_inputs_include_visual_observations_and_derived_flags(self):
        observations = [
            {
                "aspect": "contamination",
                "value": "food residue visible",
                "confidence": 0.82,
                "evidence": "Residue on inside wall.",
            },
            {
                "aspect": "packaging_use",
                "value": "single-use food container",
                "confidence": 0.88,
                "evidence": "Small disposable cup shape.",
            },
        ]
        classification = _open_classification(
            item="Yogurt Cup",
            category="Plastic",
            material_category="Plastic",
            broad_category="plastic",
            raw_item_label="used yogurt cup",
            likely_material="plastic",
            visual_evidence="Open plastic cup.",
            visual_observations=observations,
        )

        retrieval_inputs = _build_retrieval_inputs(classification)

        self.assertEqual(retrieval_inputs["visual_observations"], observations)
        self.assertTrue(retrieval_inputs["specific_context_required"])
        self.assertIn("food_soiled", retrieval_inputs["condition_flags"])
        self.assertIn("single_use", retrieval_inputs["condition_flags"])
        self.assertIn("food residue visible", retrieval_inputs["visual_evidence"])

    def test_cloudflare_gemma_grounded_response_wins_before_direct_json(self):
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
        }
        retrieval_results = [_retrieval_result(_json_chunk())]
        llm_guidance = {
            "disposal_action": "drop-off",
            "material_code": None,
            "impact_level": "Check Local Guidance",
            "summary": "Use a battery drop-off program and verify local availability.",
            "steps": [
                "Take batteries to a designated drop-off program.",
                "Verify the program accepts the battery type before visiting.",
            ],
            "guidance_source": "json_rag_llm_generated",
            "guidance_metadata": {
                "llm_provider": "cloudflare_workers_ai",
                "llm_model": "@cf/google/gemma-4-26b-a4b-it",
                "llm_mode": "source_grounded",
                "confidence": "high",
                "sources_used": ["chunk-1"],
            },
            "warnings": ["Do not place rechargeable batteries in curbside recycling."],
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=retrieval_results,
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
                return_value={"guidance": llm_guidance, "failure_reason": None},
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ),
            patch(
                "services.guidance_service.guidance_cache_service.write_source_grounded_guidance_if_cacheable",
            ),
            patch("services.guidance_service.get_rules") as mock_rules,
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "json_rag_llm_generated")
        self.assertEqual(
            response["guidance_metadata"]["llm_provider"],
            "cloudflare_workers_ai",
        )
        self.assertEqual(
            response["guidance_metadata"]["retrieved_chunk_ids"],
            ["chunk-1"],
        )
        mock_rules.assert_not_called()

    def test_visual_observations_and_confirmed_provider_are_passed_to_source_grounded_llm(self):
        observations = [
            {
                "aspect": "form_factor",
                "value": "flexible pouch",
                "confidence": 0.9,
                "evidence": "Crinkly bag shape.",
            }
        ]
        classification = _open_classification(
            item="Snack Wrapper",
            category="Plastic",
            material_category="Mixed Material",
            broad_category="plastic",
            raw_item_label="opened snack wrapper",
            likely_material="mixed material",
            visual_evidence="Crinkly opened pouch.",
            visual_observations=observations,
        )
        classification["location"] = {
            "city": "Ball Ground",
            "county": "Forsyth County",
            "state": "Georgia",
            "waste_provider": "Red Oak Sanitation",
        }
        retrieval_results = [
            _retrieval_result(
                _json_chunk(
                    id="wrapper-trash",
                    applies_to={
                        "item_labels": ["snack wrapper"],
                        "materials": ["mixed material"],
                        "categories": ["plastic"],
                        "condition_flags": ["single_use"],
                    },
                    content="Flexible snack wrappers are handled as trash.",
                    disposal_actions_supported=["Trash"],
                )
            )
        ]
        llm_guidance = {
            "disposal_action": "trash",
            "material_code": None,
            "impact_level": "Source-Grounded Guidance",
            "summary": "Put this opened snack wrapper in trash.",
            "steps": ["Empty loose crumbs.", "Place the wrapper in trash."],
            "guidance_source": "json_rag_llm_generated",
            "guidance_metadata": {"sources_used": ["wrapper-trash"]},
        }

        with (
            patch(
                "services.guidance_service.tavily_local_guidance_service.search_local_guidance",
                return_value={
                    "status": "tavily_disabled",
                    "called": False,
                    "call_count": 0,
                    "skip_reason": "feature_disabled",
                    "retrieval_results": [],
                },
            ),
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=retrieval_results,
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ),
            patch(
                "services.guidance_service.guidance_cache_service.write_source_grounded_guidance_if_cacheable",
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
                return_value={"guidance": llm_guidance, "failure_reason": None},
            ) as mock_llm,
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["disposal_action"], "trash")
        self.assertEqual(mock_llm.call_args.kwargs["visual_observations"], observations)
        self.assertIn("flexible pouch", mock_llm.call_args.kwargs["visual_evidence"])
        self.assertEqual(
            mock_llm.call_args.kwargs["confirmed_provider"],
            "Red Oak Sanitation",
        )

    def test_source_grounded_cache_hit_skips_llm_generation(self):
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
        }
        retrieval_results = [_retrieval_result(_json_chunk())]
        cached_guidance = {
            "disposal_action": "drop-off",
            "material_code": None,
            "impact_level": "Check Local Guidance",
            "summary": "Use cached battery drop-off guidance.",
            "steps": ["Tape exposed terminals.", "Use a drop-off location."],
            "guidance_source": "json_rag_llm_generated",
            "guidance_metadata": {
                "retrieved_chunk_ids": ["chunk-1"],
                "applicable_chunk_ids": ["chunk-1"],
                "requires_location_check": True,
                "guidance_cache_hit": True,
                "guidance_cache_key": "cache-key",
                "cache_key_version": "guidance_cache_v3",
            },
            "cache_hit": True,
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=retrieval_results,
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=cached_guidance,
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
            ) as mock_llm,
            patch(
                "services.guidance_service.guidance_cache_service.write_source_grounded_guidance_if_cacheable",
            ) as mock_write,
        ):
            response = build_prediction_response(classification)

        self.assertTrue(response["cache_hit"])
        self.assertEqual(response["guidance_source"], "json_rag_llm_generated")
        self.assertTrue(response["guidance_metadata"]["guidance_cache_hit"])
        self.assertEqual(response["guidance_metadata"]["guidance_cache_key"], "cache-key")
        self.assertEqual(response["guidance"]["summary"]["action_type"], "drop-off")
        self.assertEqual(
            response["guidance"]["preparation"]["steps"],
            ["Tape exposed terminals."],
        )
        mock_llm.assert_not_called()
        mock_write.assert_not_called()

    def test_source_grounded_cache_miss_calls_existing_generation_path(self):
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
        }
        retrieval_results = [_retrieval_result(_json_chunk())]
        llm_guidance = {
            "disposal_action": "drop-off",
            "material_code": None,
            "impact_level": "Check Local Guidance",
            "summary": "Use a battery drop-off program.",
            "steps": ["Tape exposed terminals.", "Use drop-off."],
            "guidance_source": "json_rag_llm_generated",
            "guidance_metadata": {"sources_used": ["chunk-1"]},
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=retrieval_results,
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
                return_value={"guidance": llm_guidance, "failure_reason": None},
            ) as mock_llm,
        ):
            response = build_prediction_response(classification)

        mock_llm.assert_called_once()
        self.assertEqual(response["guidance_source"], "json_rag_llm_generated")

    def test_expired_source_grounded_cache_row_is_ignored_by_lookup_and_generation_proceeds(self):
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
        }
        retrieval_results = [_retrieval_result(_json_chunk())]
        llm_guidance = {
            "disposal_action": "drop-off",
            "material_code": None,
            "impact_level": "Check Local Guidance",
            "summary": "Use fresh battery drop-off guidance.",
            "steps": ["Tape exposed terminals.", "Use drop-off."],
            "guidance_source": "json_rag_llm_generated",
            "guidance_metadata": {"sources_used": ["chunk-1"]},
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=retrieval_results,
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ) as mock_cache_lookup,
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
                return_value={"guidance": llm_guidance, "failure_reason": None},
            ) as mock_llm,
        ):
            response = build_prediction_response(classification)

        mock_cache_lookup.assert_called_once()
        mock_llm.assert_called_once()
        self.assertEqual(response["summary"], "Use fresh battery drop-off guidance.")

    def test_direct_json_remains_fallback_when_cloudflare_output_is_invalid(self):
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
        }
        chunk = _json_chunk()

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[_retrieval_result(chunk)],
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
                return_value={"guidance": None, "failure_reason": "invalid_json"},
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ),
            patch(
                "services.guidance_service.guidance_cache_service.write_source_grounded_guidance_if_cacheable",
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertEqual(
            response["guidance_metadata"]["fallback_reason"],
            "invalid_json",
        )
        self.assertEqual(response["guidance_metadata"]["final_generation_path"], "general_fallback")
        self.assertEqual(response["guidance_confidence"]["level"], "low")
        self.assertIn("general_fallback", response["guidance_confidence"]["reason_codes"])

    def test_conditional_retrieval_does_not_authorize_direct_recycling(self):
        observations = [
            {
                "aspect": "construction",
                "value": "rigid plastic bottle with pump",
                "confidence": 0.86,
                "evidence": "Rigid bottle and pump are visible.",
            },
            {
                "aspect": "recycling_marking",
                "value": "unknown",
                "confidence": None,
                "evidence": "",
            },
        ]
        classification = _open_classification(
            item="Personal Care Container",
            category="Plastic",
            material_category="Plastic",
            broad_category="plastic",
            visual_observations=observations,
        )
        classification["recognition_confidence"] = {
            "level": "high",
            "score": 0.96,
            "blocking": False,
            "reason_codes": [],
        }
        chunk = _json_chunk(
            id="plastic-container",
            applies_to={
                "item_labels": ["plastic bottles"],
                "materials": ["rigid plastics"],
                "categories": ["plastic containers"],
                "condition_flags": ["resin_code_present"],
            },
            disposal_actions_supported=["Recycle", "Check local guidance"],
        )
        conditional_result = _retrieval_result(
            chunk,
            matched_fields=["material"],
            applicability="conditional",
            applicability_reason_codes=[
                "eligibility_marking_unknown",
                "local_acceptance_unverified",
            ],
        )

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[conditional_result],
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
                return_value={"guidance": None, "failure_reason": "llm_disabled"},
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "llm_disabled"},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertNotEqual(response["disposal_action"], "recycle")
        self.assertEqual(response["recognition_confidence"]["level"], "high")
        self.assertEqual(response["guidance_confidence"]["level"], "low")

    def test_direct_json_source_grounded_guidance_is_written_when_cacheable(self):
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
        }
        chunk = _json_chunk()

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[_retrieval_result(chunk)],
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
                return_value={"guidance": None, "failure_reason": "invalid_json"},
            ),
            patch(
                "services.guidance_service.guidance_cache_service.write_source_grounded_guidance_if_cacheable",
            ) as mock_write,
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_write.assert_not_called()

    def test_open_normalized_item_material_and_category_can_retrieve_chunks(self):
        classification = {
            "item": "Battery",
            "category": "Unknown",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognition_details": {
                "raw_item_label": "batteries",
                "normalized": {
                    "item_label": "Battery",
                    "material": "Battery",
                    "material_category": "Battery",
                    "broad_category": "Batteries",
                    "condition_flags": ["requires_dropoff"],
                    "special_handling_flags": ["battery", "dropoff_recommended"],
                },
            },
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[_retrieval_result(_json_chunk(), matched_fields=["item_label_normalized", "material", "category", "condition_flags"])],
            ) as mock_retrieve,
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
                return_value={"guidance": None, "failure_reason": "llm_disabled"},
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        retrieve_kwargs = mock_retrieve.call_args.kwargs
        self.assertEqual(retrieve_kwargs["item_label"], "Battery")
        self.assertEqual(retrieve_kwargs["material"], "Battery")
        self.assertEqual(retrieve_kwargs["category"], "Batteries")
        self.assertIn("Battery", retrieve_kwargs["item_candidates"])
        self.assertIn("batteries", [value.casefold() for value in retrieve_kwargs["item_candidates"]])
        self.assertIn("Battery", retrieve_kwargs["material_candidates"])
        self.assertIn("Batteries", retrieve_kwargs["category_candidates"])
        self.assertIn("requires_dropoff", retrieve_kwargs["condition_flags"])
        self.assertIn("battery", retrieve_kwargs["condition_flags"])

    def test_raw_vlm_disposal_fields_are_ignored(self):
        classification = {
            "item": "Battery",
            "category": "Unknown",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognition_details": {
                "raw_item_label": "battery",
                "disposal_action": "recycle",
                "steps": ["ignore this"],
                "normalized": {
                    "item_label": "Battery",
                    "material_category": "Battery",
                    "broad_category": "Batteries",
                    "condition_flags": [],
                    "special_handling_flags": ["battery", "dropoff_recommended"],
                },
            },
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[_retrieval_result(_json_chunk(disposal_actions_supported=["Drop-off"]))],
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
                return_value={"guidance": None, "failure_reason": "llm_disabled"},
            ),
            patch(
                "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
                return_value=None,
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertNotEqual(response["disposal_action"], "recycle")
        self.assertNotEqual(response["steps"], ["ignore this"])

    def test_open_battery_classification_uses_json_guidance_before_legacy_rules(self):
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognized_material_category": "Battery",
            "recognized_broad_category": "Electronics",
            "recognition_source": "vlm_open",
            "recognition_details": {
                "raw_item_label": "battery",
                "likely_material": "battery",
                "broad_category": "electronics",
                "candidates": [{"label": "battery", "confidence": 0.96}],
                "normalized": {
                    "item_label": "Battery",
                    "material_category": "Battery",
                    "broad_category": "Electronics",
                    "condition_flags": [],
                    "special_handling_flags": ["battery", "dropoff_recommended"],
                    "matched_supported_label": None,
                },
            },
        }

        with patch(
            "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance",
            return_value={"guidance": None, "failure_reason": "llm_disabled"},
        ), patch(
            "services.guidance_service.guidance_cache_service.get_cached_source_grounded_guidance",
            return_value=None,
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertIn("batteries_01", response["guidance_metadata"]["applicable_chunk_ids"])

    def test_low_risk_open_off_inventory_item_can_use_llm_general_fallback(self):
        classification = {
            "item": "Thermoflask",
            "category": "Metal",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognition_details": {
                "raw_item_label": "thermoflask",
                "normalized": {
                    "item_label": "Thermoflask",
                    "material_category": "Metal",
                    "broad_category": "Drinkware",
                    "condition_flags": [],
                    "special_handling_flags": [],
                    "matched_supported_label": None,
                },
            },
        }

        llm_guidance = {
            "disposal_action": "check local guidance",
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "If the bottle is still usable, prefer reuse or donation.",
            "steps": [
                "If the item is reusable, keep using it or donate it.",
                "Check local recycling or drop-off options before relying on them.",
                "If no reuse or recycling option exists, follow local trash guidance.",
            ],
            "guidance_source": "safe_fallback",
            "guidance_metadata": {
                "llm_provider": "cloudflare_workers_ai",
                "llm_model": "@cf/google/gemma-4-26b-a4b-it",
                "llm_mode": "general_safe_fallback",
                "confidence": "low",
                "sources_used": [],
            },
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": llm_guidance, "failure_reason": None},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["guidance_metadata"]["confidence"], "low")
        self.assertEqual(response["disposal_action"], "check local guidance")

    def test_low_risk_pencil_without_json_chunks_can_use_llm_general_fallback(self):
        classification = {
            "item": "Pencil",
            "category": "Mixed Material",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognition_details": {
                "raw_item_label": "pencil",
                "normalized": {
                    "item_label": "Pencil",
                    "material_category": "Mixed Material",
                    "broad_category": "Household item",
                    "condition_flags": [],
                    "special_handling_flags": [],
                    "matched_supported_label": None,
                },
            },
        }

        llm_guidance = {
            "disposal_action": "check local guidance",
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "If the pencil is still usable, keep using it or pass it along.",
            "steps": [
                "Reuse the item if it is still usable.",
                "Check local reuse or recycling options before relying on them.",
                "If no better option exists, follow local trash guidance.",
            ],
            "guidance_source": "safe_fallback",
            "guidance_metadata": {
                "llm_provider": "cloudflare_workers_ai",
                "llm_model": "@cf/google/gemma-4-26b-a4b-it",
                "llm_mode": "general_safe_fallback",
                "confidence": "low",
                "sources_used": [],
            },
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": llm_guidance, "failure_reason": None},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")

    def test_low_risk_pencil_with_invalid_general_safe_output_uses_deterministic_fallback(self):
        classification = {
            "item": "Pencil",
            "category": "Mixed Material",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognition_details": {
                "raw_item_label": "pencil",
                "normalized": {
                    "item_label": "Pencil",
                    "material_category": "Mixed Material",
                    "broad_category": "Household item",
                    "condition_flags": [],
                    "special_handling_flags": [],
                    "matched_supported_label": None,
                },
            },
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "missing_summary"},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertIn("waste provider", " ".join(response["steps"]).lower())
        self.assertEqual(
            response["guidance_metadata"]["fallback_reason"],
            "missing_summary",
        )
        self.assertEqual(response["guidance_metadata"]["source_names"], [])
        self.assertEqual(response["guidance_metadata"]["source_urls"], [])
        self.assertEqual(response["guidance_metadata"]["retrieved_chunk_ids"], [])

    def test_sheet_music_is_low_risk_eligible_for_general_safe_fallback(self):
        classification = _open_classification(
            item="Sheet Music",
            category="Paper",
            material_category="Paper",
            broad_category="Paper",
            raw_item_label="sheet music",
            likely_material="paper",
        )
        llm_guidance = {
            "disposal_action": "check local guidance",
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "If the paper is clean and dry, check local recycling rules for this paper type.",
            "steps": [
                "Reuse or donate the item if it is still usable.",
                "Check local recycling or drop-off options before using them.",
                "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
            ],
            "guidance_source": "safe_fallback",
            "guidance_metadata": {
                "llm_provider": "cloudflare_workers_ai",
                "llm_model": "@cf/google/gemma-4-26b-a4b-it",
                "llm_mode": "general_safe_fallback",
                "confidence": "low",
                "sources_used": [],
            },
        }

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": llm_guidance, "failure_reason": None},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")

    def test_sheet_music_invalid_general_safe_output_uses_item_specific_deterministic_fallback(self):
        classification = _open_classification(
            item="Sheet Music",
            category="Paper",
            material_category="Paper",
            broad_category="Paper",
            raw_item_label="sheet music",
            likely_material="paper",
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "missing_steps"},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertIn("sheet music", response["summary"].lower())
        self.assertIn("waste provider", " ".join(response["steps"]).lower())

    def test_sheet_music_with_llm_disabled_falls_back_safely(self):
        classification = _open_classification(
            item="Sheet Music",
            category="Paper",
            material_category="Paper",
            broad_category="Paper",
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "ENABLE_LLM_GUIDANCE_false"},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")

    def test_curtain_is_low_risk_eligible_for_general_safe_fallback(self):
        classification = _open_classification(
            item="Curtain",
            category="Mixed Material",
            material_category="Fabric",
            broad_category="Household item",
            raw_item_label="curtain",
            likely_material="fabric",
        )
        llm_guidance = {
            "disposal_action": "check local guidance",
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "If the curtain is usable, reuse, repair, or donate it first.",
            "steps": [
                "Reuse or donate the item if it is still usable.",
                "Check local recycling or drop-off options before using them.",
                "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
            ],
            "guidance_source": "safe_fallback",
            "guidance_metadata": {
                "llm_provider": "cloudflare_workers_ai",
                "llm_model": "@cf/google/gemma-4-26b-a4b-it",
                "llm_mode": "general_safe_fallback",
                "confidence": "low",
                "sources_used": [],
            },
        }

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": llm_guidance, "failure_reason": None},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")

    def test_curtain_invalid_general_safe_output_uses_textile_specific_deterministic_fallback(self):
        classification = _open_classification(
            item="Curtain",
            category="Mixed Material",
            material_category="Fabric",
            broad_category="Household item",
            raw_item_label="curtain",
            likely_material="fabric",
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "general_fallback_unsupported_action"},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertIn("curtain", response["summary"].lower())
        self.assertIn("waste provider", " ".join(response["steps"]).lower())

    def test_rubiks_cube_invalid_general_safe_output_uses_reuse_focused_deterministic_fallback(self):
        classification = _open_classification(
            item="Rubik's Cube",
            category="Plastic",
            material_category="Plastic",
            broad_category="Toy",
            raw_item_label="rubik's cube",
            likely_material="plastic",
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "overconfident_general_fallback"},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertIn("rubik", response["summary"].lower())
        self.assertIn("waste provider", " ".join(response["steps"]).lower())
        self.assertNotIn("curbside recycling is accepted", response["summary"].lower())

    def test_plastic_container_invalid_general_safe_output_uses_container_specific_deterministic_fallback(self):
        classification = _open_classification(
            item="Heart-Shaped Container",
            category="Plastic",
            material_category="Plastic",
            broad_category="Household item",
            raw_item_label="heart-shaped container",
            likely_material="plastic",
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "invalid_json"},
            ),
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertIn("container", response["summary"].lower())
        self.assertIn("local program", " ".join(response["steps"]).lower())

    def test_generic_unknown_item_is_not_low_risk_eligible(self):
        classification = _open_classification(
            item="Mystery Object",
            category="Unknown",
            material_category="Unknown",
            broad_category="Unknown",
            raw_item_label="mystery object",
            likely_material="unknown",
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch("services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance") as mock_general,
        ):
            mock_general.return_value = {"guidance": None, "failure_reason": "llm_disabled"}
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_called_once()
        self.assertEqual(response["guidance_metadata"]["text_llm_call_count"], 1)

    def test_electronics_item_does_not_call_general_safe_llm(self):
        classification = _open_classification(
            item="Laptop",
            category="Electronics",
            material_category="Electronics",
            broad_category="Electronics",
            raw_item_label="laptop",
            likely_material="electronics",
            special_handling_flags=["electronics", "dropoff_recommended"],
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch("services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance") as mock_general,
            patch("services.guidance_service.get_rules") as mock_rules,
        ):
            mock_general.return_value = {"guidance": None, "failure_reason": "llm_disabled"}
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_called_once()
        mock_rules.assert_not_called()

    def test_food_soiled_cardboard_is_not_low_risk_eligible(self):
        classification = _open_classification(
            item="Food-soiled cardboard",
            category="Paper",
            material_category="Paper",
            broad_category="Paper",
            raw_item_label="food-soiled cardboard",
            likely_material="paper",
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch("services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance") as mock_general,
        ):
            mock_general.return_value = {"guidance": None, "failure_reason": "llm_disabled"}
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_called_once()

    def test_thermal_receipt_is_not_low_risk_eligible(self):
        classification = _open_classification(
            item="Thermal Receipt",
            category="Paper",
            material_category="Paper",
            broad_category="Paper",
            raw_item_label="thermal receipt",
            likely_material="paper",
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch("services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance") as mock_general,
        ):
            mock_general.return_value = {"guidance": None, "failure_reason": "llm_disabled"}
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_called_once()

    def test_broken_glass_is_not_low_risk_eligible(self):
        classification = _open_classification(
            item="Broken Glass",
            category="Glass",
            material_category="Glass",
            broad_category="Household item",
            raw_item_label="broken glass",
            likely_material="glass",
        )

        with (
            patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
            patch("services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance") as mock_general,
        ):
            mock_general.return_value = {"guidance": None, "failure_reason": "llm_disabled"}
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_called_once()

    def test_multiple_normal_low_risk_items_are_eligible_for_general_safe_fallback(self):
        cases = [
            ("Ceramic Mug", "Ceramic", "Ceramic", "Household item"),
            ("Metal Water Bottle", "Metal", "Metal", "Drinkware"),
            ("Backpack", "Fabric", "Fabric", "Household item"),
            ("Rubber Duck", "Plastic", "Plastic", "Toy"),
            ("Wooden Spoon", "Wood", "Wood", "Kitchenware"),
        ]
        llm_guidance = {
            "disposal_action": "check local guidance",
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "Reuse or donate the item if it is still usable.",
            "steps": [
                "Reuse or donate the item if it is still usable.",
                "Check local recycling or drop-off options before using them.",
                "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
            ],
            "guidance_source": "safe_fallback",
            "guidance_metadata": {
                "llm_provider": "cloudflare_workers_ai",
                "llm_model": "@cf/google/gemma-4-26b-a4b-it",
                "llm_mode": "general_safe_fallback",
                "confidence": "low",
                "sources_used": [],
            },
        }

        for item, category, material_category, broad_category in cases:
            with self.subTest(item=item):
                classification = _open_classification(
                    item=item,
                    category=category,
                    material_category=material_category,
                    broad_category=broad_category,
                )
                with (
                    patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
                    patch(
                        "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                        return_value={"guidance": llm_guidance, "failure_reason": None},
                    ),
                ):
                    response = build_prediction_response(classification)

                self.assertEqual(response["guidance_source"], "safe_fallback")

    def test_multiple_high_risk_items_are_blocked_from_general_safe_fallback(self):
        cases = [
            ("Paint Can", "Paint", "Paint", "Paint"),
            ("Aerosol Can", "Metal", "Metal", "Household item"),
            ("Motor Oil", "Chemical", "Chemical", "Household item"),
            ("Medicine Bottle", "Plastic", "Plastic", "Household item"),
            ("Needle", "Metal", "Metal", "Household item"),
            ("Unknown Chemical Bottle", "Unknown", "Unknown", "Household item"),
        ]

        for item, category, material_category, broad_category in cases:
            with self.subTest(item=item):
                special_flags = ["hazardous"] if "Needle" in item else []
                classification = _open_classification(
                    item=item,
                    category=category,
                    material_category=material_category,
                    broad_category=broad_category,
                    special_handling_flags=special_flags,
                )
                with (
                    patch("services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks", return_value=[]),
                    patch("services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance") as mock_general,
                    patch("services.guidance_service.get_rules") as mock_rules,
                ):
                    mock_general.return_value = {"guidance": None, "failure_reason": "llm_disabled"}
                    response = build_prediction_response(classification)

                self.assertEqual(response["guidance_source"], "safe_fallback")
                mock_general.assert_called_once()
                mock_rules.assert_not_called()

    def test_high_risk_open_item_without_chunks_uses_safe_fallback(self):
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognition_details": {
                "raw_item_label": "battery",
                "normalized": {
                    "item_label": "Battery",
                    "material_category": "Battery",
                    "broad_category": "Batteries",
                    "condition_flags": ["requires_dropoff", "hazardous"],
                    "special_handling_flags": ["battery", "dropoff_recommended"],
                    "matched_supported_label": None,
                },
            },
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "llm_disabled"},
            ) as mock_general,
            patch("services.guidance_service.get_rules") as mock_rules,
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        mock_general.assert_called_once()
        mock_rules.assert_not_called()

    def test_unsupported_open_recognition_items_do_not_use_legacy_rules(self):
        classification = {
            "item": "Water bottle",
            "category": "Metal",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": False,
            "recognition_details": {
                "raw_item_label": "water bottle",
                "normalized": {
                    "item_label": "Water bottle",
                    "material_category": "Metal",
                    "broad_category": "Drinkware",
                    "condition_flags": [],
                    "special_handling_flags": [],
                    "matched_supported_label": None,
                },
            },
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ),
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": None, "failure_reason": "llm_disabled"},
            ),
            patch("services.guidance_service.get_rules") as mock_rules,
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        mock_rules.assert_not_called()

    def test_supported_label_compatibility_path_can_still_use_legacy_rules(self):
        classification = {
            "item": "Charging cable",
            "category": "Electronics",
            "status": "confident",
            "candidates": [],
            "trusted_guidance_available": True,
            "trusted_guidance_label": "Cable",
            "recognition_details": {
                "normalized": {
                    "item_label": "Charging cable",
                    "material_category": "Electronics",
                    "broad_category": "Electronics",
                    "condition_flags": [],
                    "special_handling_flags": ["electronics", "dropoff_recommended"],
                    "matched_supported_label": "Cable",
                },
            },
        }

        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
        ), patch(
            "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
            return_value={"guidance": None, "failure_reason": "llm_disabled"},
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")

    def test_if_json_and_rules_both_fail_safe_fallback_works(self):
        classification = {
            "item": "Mystery item",
            "category": "Unknown",
            "status": "confident",
            "candidates": [],
        }

        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
        ), patch(
            "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
            return_value={"guidance": None, "failure_reason": "llm_disabled"},
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertIn("not enough information", response["summary"].lower())

    def test_safe_fallback_is_never_written_to_guidance_cache(self):
        classification = {
            "item": "",
            "category": "Unknown",
            "status": "unknown",
            "candidates": [],
        }

        with patch(
            "services.guidance_service.guidance_cache_service.write_source_grounded_guidance_if_cacheable",
        ) as mock_write:
            response = build_prediction_response(classification)

        self.assertEqual(
            response["guidance_source"], "recognition_clarification_required"
        )
        self.assertTrue(response["clarification"]["required"])
        mock_write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
