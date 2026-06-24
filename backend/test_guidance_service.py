import unittest
from unittest.mock import patch

from services.guidance_service import build_prediction_response


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


class GuidanceServiceTests(unittest.TestCase):
    def test_json_retrieval_wins_before_legacy_rules(self):
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
            patch("services.guidance_service.get_rules") as mock_rules,
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "json_rag_direct_generated")
        self.assertEqual(response["disposal_action"], "drop-off")
        self.assertEqual(response["impact_level"], "Check Local Guidance")
        self.assertIn("designated battery drop-off program", response["summary"])
        self.assertEqual(
            response["warnings"],
            ["Do not place rechargeable batteries in curbside recycling."],
        )
        self.assertIn("guidance_metadata", response)
        self.assertEqual(
            response["guidance_metadata"]["retrieved_chunk_ids"],
            ["chunk-1"],
        )
        mock_rules.assert_not_called()

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
                },
            },
        }

        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[_retrieval_result(_json_chunk(), matched_fields=["item_label_normalized", "material", "category", "condition_flags"])],
        ) as mock_retrieve:
            response = build_prediction_response(classification)

        self.assertEqual(response["guidance_source"], "json_rag_direct_generated")
        retrieve_kwargs = mock_retrieve.call_args.kwargs
        self.assertEqual(retrieve_kwargs["item_label"], "Battery")
        self.assertEqual(retrieve_kwargs["material"], "Battery")
        self.assertEqual(retrieve_kwargs["category"], "Batteries")
        self.assertEqual(retrieve_kwargs["condition_flags"], ["requires_dropoff"])

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
                },
            },
        }

        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[_retrieval_result(_json_chunk(disposal_actions_supported=["Drop-off"]))],
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["disposal_action"], "drop-off")
        self.assertNotEqual(response["disposal_action"], "recycle")
        self.assertNotEqual(response["steps"], ["ignore this"])

    def test_direct_json_guidance_returns_frontend_compatible_fields(self):
        classification = {
            "item": "Battery",
            "category": "Battery",
            "status": "confident",
            "candidates": [],
        }

        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[_retrieval_result(_json_chunk())],
        ):
            response = build_prediction_response(classification)

        for field_name in (
            "item",
            "category",
            "status",
            "candidates",
            "disposal_action",
            "material_code",
            "impact_level",
            "summary",
            "steps",
            "guidance_source",
        ):
            self.assertIn(field_name, response)

        self.assertEqual(response["guidance_source"], "json_rag_direct_generated")
        self.assertIn("guidance_metadata", response)

    def test_if_no_chunks_match_legacy_rules_fallback_can_still_work(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [],
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

    def test_open_off_inventory_item_can_stay_safe_when_json_and_rules_miss(self):
        classification = {
            "item": "Water bottle",
            "category": "Unknown",
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
                    "matched_supported_label": None,
                },
            },
        }

        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
        ):
            response = build_prediction_response(classification)

        self.assertEqual(response["item"], "Water Bottle")
        self.assertEqual(response["guidance_source"], "safe_fallback")
        self.assertIsNone(response["disposal_action"])


if __name__ == "__main__":
    unittest.main()
