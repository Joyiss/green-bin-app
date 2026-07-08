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


def _retrieval_result(chunk: dict, *, score: float = 8.25, matched_fields=None):
    return {
        "chunk": chunk,
        "chunk_id": chunk["id"],
        "score": score,
        "matched_fields": matched_fields or ["item_label_exact"],
        "requires_location_check": bool(chunk.get("requires_location_check")),
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
            "normalized": {
                "item_label": item,
                "material_category": material_category,
                "broad_category": broad_category,
                "condition_flags": condition_flags or [],
                "special_handling_flags": special_handling_flags or [],
                "matched_supported_label": None,
            },
        },
    }


class GuidanceServiceTests(unittest.TestCase):
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

    def test_groq_grounded_response_wins_before_direct_json(self):
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
                "llm_provider": "groq",
                "llm_model": "llama-3.1-8b-instant",
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
            patch("services.guidance_service.get_rules") as mock_rules,
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "json_rag_llm_generated")
        self.assertEqual(response["guidance_metadata"]["llm_provider"], "groq")
        self.assertEqual(
            response["guidance_metadata"]["retrieved_chunk_ids"],
            ["chunk-1"],
        )
        mock_rules.assert_not_called()

    def test_direct_json_remains_fallback_when_groq_output_is_invalid(self):
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
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "json_rag_direct_generated")
        self.assertEqual(response["disposal_action"], "drop-off")
        self.assertEqual(
            response["guidance_metadata"]["llm_fallback_reason"],
            "invalid_json",
        )
        self.assertIn("claims_used", response["guidance_metadata"])
        self.assertIn("source_excerpts", response["guidance_metadata"])
        self.assertIn("source_names", response["guidance_metadata"])
        self.assertIn("source_urls", response["guidance_metadata"])
        self.assertIn("limitations", response["guidance_metadata"])
        self.assertIn("why_this_action", response["guidance_metadata"])
        self.assertIn("retrieved_chunk_ids", response["guidance_metadata"])

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
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "json_rag_direct_generated")
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
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["disposal_action"], "drop-off")
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
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "json_rag_direct_generated")
        self.assertEqual(response["disposal_action"], "drop-off")
        self.assertIn(
            "batteries_01",
            response["guidance_metadata"]["retrieved_chunk_ids"],
        )
        self.assertNotIn(
            "hhw_02",
            response["guidance_metadata"]["retrieved_chunk_ids"],
        )

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
            "disposal_action": None,
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "If the bottle is still usable, prefer reuse or donation.",
            "steps": [
                "If the item is reusable, keep using it or donate it.",
                "Check local recycling or drop-off options before relying on them.",
                "If no reuse or recycling option exists, follow local trash guidance.",
            ],
            "guidance_source": "llm_general_fallback",
            "guidance_metadata": {
                "llm_provider": "groq",
                "llm_model": "llama-3.1-8b-instant",
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

        self.assertEqual(response["guidance_source"], "llm_general_fallback")
        self.assertEqual(response["guidance_metadata"]["confidence"], "low")
        self.assertIsNone(response["disposal_action"])

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
            "disposal_action": None,
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "If the pencil is still usable, keep using it or pass it along.",
            "steps": [
                "Reuse the item if it is still usable.",
                "Check local reuse or recycling options before relying on them.",
                "If no better option exists, follow local trash guidance.",
            ],
            "guidance_source": "llm_general_fallback",
            "guidance_metadata": {
                "llm_provider": "groq",
                "llm_model": "llama-3.1-8b-instant",
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

        self.assertEqual(response["guidance_source"], "llm_general_fallback")
        self.assertIsNone(response["disposal_action"])

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

        self.assertEqual(response["guidance_source"], "llm_general_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertIn("pencil", response["summary"].lower())
        self.assertIn("local trash guidance", " ".join(response["steps"]).lower())
        self.assertEqual(
            response["guidance_metadata"]["llm_fallback_reason"],
            "missing_summary",
        )
        self.assertTrue(response["guidance_metadata"]["deterministic_fallback_used"])
        self.assertEqual(response["guidance_metadata"]["claims_used"], [])
        self.assertEqual(response["guidance_metadata"]["source_excerpts"], [])
        self.assertEqual(response["guidance_metadata"]["source_names"], [])
        self.assertEqual(response["guidance_metadata"]["source_urls"], [])
        self.assertEqual(response["guidance_metadata"]["retrieved_chunk_ids"], [])
        self.assertIn("why_this_action", response["guidance_metadata"])

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
            "disposal_action": None,
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "If the paper is clean and dry, check local recycling rules for this paper type.",
            "steps": [
                "Reuse or donate the item if it is still usable.",
                "Check local recycling or drop-off options before using them.",
                "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
            ],
            "guidance_source": "llm_general_fallback",
            "guidance_metadata": {
                "llm_provider": "groq",
                "llm_model": "llama-3.1-8b-instant",
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

        self.assertEqual(response["guidance_source"], "llm_general_fallback")

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

        self.assertEqual(response["guidance_source"], "llm_general_fallback")
        self.assertEqual(response["disposal_action"], "check local guidance")
        self.assertIn("sheet music", response["summary"].lower())
        self.assertIn("clean and dry", response["summary"].lower())
        self.assertIn("paper recycling", " ".join(response["steps"]).lower())

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
            "disposal_action": None,
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "If the curtain is usable, reuse, repair, or donate it first.",
            "steps": [
                "Reuse or donate the item if it is still usable.",
                "Check local recycling or drop-off options before using them.",
                "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
            ],
            "guidance_source": "llm_general_fallback",
            "guidance_metadata": {
                "llm_provider": "groq",
                "llm_model": "llama-3.1-8b-instant",
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

        self.assertEqual(response["guidance_source"], "llm_general_fallback")

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

        self.assertEqual(response["guidance_source"], "llm_general_fallback")
        self.assertEqual(response["disposal_action"], "donate/reuse")
        self.assertIn("curtain", response["summary"].lower())
        self.assertIn("textile", " ".join(response["steps"]).lower())

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

        self.assertEqual(response["guidance_source"], "llm_general_fallback")
        self.assertEqual(response["disposal_action"], "donate/reuse")
        self.assertIn("rubik", response["summary"].lower())
        self.assertIn("donate", " ".join(response["steps"]).lower())
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

        self.assertEqual(response["guidance_source"], "llm_general_fallback")
        self.assertEqual(response["disposal_action"], "donate/reuse")
        self.assertIn("container", response["summary"].lower())
        self.assertIn("reuse", response["summary"].lower())
        self.assertIn("plastic container", " ".join(response["steps"]).lower())

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
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_not_called()

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
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_not_called()
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
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_not_called()

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
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_not_called()

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
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        mock_general.assert_not_called()

    def test_multiple_normal_low_risk_items_are_eligible_for_general_safe_fallback(self):
        cases = [
            ("Ceramic Mug", "Ceramic", "Ceramic", "Household item"),
            ("Metal Water Bottle", "Metal", "Metal", "Drinkware"),
            ("Backpack", "Fabric", "Fabric", "Household item"),
            ("Rubber Duck", "Plastic", "Plastic", "Toy"),
            ("Wooden Spoon", "Wood", "Wood", "Kitchenware"),
        ]
        llm_guidance = {
            "disposal_action": None,
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "Reuse or donate the item if it is still usable.",
            "steps": [
                "Reuse or donate the item if it is still usable.",
                "Check local recycling or drop-off options before using them.",
                "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
            ],
            "guidance_source": "llm_general_fallback",
            "guidance_metadata": {
                "llm_provider": "groq",
                "llm_model": "llama-3.1-8b-instant",
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

                self.assertEqual(response["guidance_source"], "llm_general_fallback")

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
                    response = build_prediction_response(classification)

                self.assertEqual(response["guidance_source"], "safe_fallback")
                mock_general.assert_not_called()
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
            patch("services.guidance_service.get_rules") as mock_rules,
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertIsNone(response["disposal_action"])
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
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "legacy_rules_fallback")
        self.assertEqual(response["disposal_action"], "e-waste recycling")

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
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertIsNone(response["disposal_action"])
        self.assertEqual(response["summary"], "Trusted disposal guidance is not available yet.")


if __name__ == "__main__":
    unittest.main()
