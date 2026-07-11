import unittest
from unittest.mock import patch

from services.guidance_service import build_prediction_response


def _clarification_classification():
    return {
        "item": "Personal care container",
        "category": "Plastic",
        "status": "uncertain",
        "candidates": [
            ("Shampoo bottle", 0.38),
            ("Plastic cup", 0.31),
        ],
        "recognition_source": "vlm_open",
        "recognition_confidence": {
            "level": "low",
            "score": 0.39,
            "reason_codes": ["specific_container_feature_conflict"],
            "blocking": True,
        },
        "recognition_details": {
            "raw_item_label": "ceramic mug",
            "candidates": [
                {"label": "ceramic mug", "confidence": 0.91},
                {"label": "cosmetic container", "confidence": 0.38},
            ],
            "normalized": {
                "item_label": "Ceramic mug",
                "disposal_category": "Household item",
                "material_category": "Plastic",
                "broad_category": "plastic",
                "special_handling_flags": [],
                "matched_supported_label": None,
            },
        },
    }


class GuidanceClarificationTests(unittest.TestCase):
    def test_uncertain_recognition_skips_retrieval_and_both_guidance_models(self):
        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks"
            ) as mock_retrieve,
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_source_grounded_guidance"
            ) as mock_source_llm,
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance"
            ) as mock_general_llm,
        ):
            response = build_prediction_response(_clarification_classification())

        mock_retrieve.assert_not_called()
        mock_source_llm.assert_not_called()
        mock_general_llm.assert_not_called()
        self.assertEqual(response["status"], "uncertain")
        self.assertEqual(
            response["guidance_source"], "recognition_clarification_required"
        )
        self.assertIsNone(response["disposal_action"])
        self.assertEqual(response["steps"], [])
        self.assertTrue(response["clarification"]["required"])
        self.assertIn(
            "specific_container_feature_conflict",
            response["clarification"]["reason_codes"],
        )
        self.assertTrue(response["clarification"]["retake_recommended"])
        self.assertGreaterEqual(len(response["candidates"]), 2)

    def test_safety_ambiguity_skips_guidance_even_when_status_was_confident(self):
        classification = {
            "item": "Plastic household object",
            "category": "Household item",
            "status": "confident",
            "candidates": [],
            "recognition_source": "vlm_open",
            "recognition_confidence": {
                "level": "medium",
                "score": 0.7,
                "reason_codes": [],
                "blocking": False,
            },
            "recognition_details": {
                "normalized": {
                    "item_label": "Plastic household object",
                    "disposal_category": "Household item",
                    "broad_category": "household",
                    "special_handling_flags": ["electronics", "dropoff_recommended"],
                }
            },
        }

        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks"
        ) as mock_retrieve:
            response = build_prediction_response(classification)

        mock_retrieve.assert_not_called()
        self.assertEqual(response["status"], "uncertain")
        self.assertIn(
            "unresolved_electronics_identity",
            response["clarification"]["reason_codes"],
        )

    def test_nonblocking_medium_confidence_continues_to_guidance(self):
        classification = {
            "item": "Curtain",
            "category": "Textiles",
            "status": "confident",
            "candidates": [],
            "recognition_source": "vlm_open",
            "recognition_confidence": {
                "level": "medium",
                "score": 0.7,
                "reason_codes": ["weak_visual_evidence"],
                "blocking": False,
            },
            "trusted_guidance_available": False,
            "recognition_details": {
                "raw_item_label": "curtain",
                "likely_material": "fabric",
                "normalized": {
                    "item_label": "Curtain",
                    "material_category": "Fabric/Textile",
                    "disposal_category": "Textiles",
                    "broad_category": "household",
                    "condition_flags": [],
                    "special_handling_flags": [],
                    "matched_supported_label": None,
                },
            },
        }
        generated_guidance = {
            "disposal_action": "donate/reuse",
            "material_code": None,
            "impact_level": "Low Confidence Guidance",
            "summary": "Reuse or donate the curtain if it remains usable.",
            "steps": ["Clean the curtain.", "Offer it for reuse or donation."],
            "guidance_source": "llm_general_fallback",
            "guidance_metadata": {"confidence": "low"},
        }

        with (
            patch(
                "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
                return_value=[],
            ) as mock_retrieve,
            patch(
                "services.guidance_service.guidance_llm_service.try_generate_general_safe_guidance",
                return_value={"guidance": generated_guidance, "failure_reason": None},
            ) as mock_general_llm,
        ):
            response = build_prediction_response(classification)

        mock_retrieve.assert_called_once()
        mock_general_llm.assert_called_once()
        self.assertEqual(response["status"], "confident")
        self.assertNotIn("clarification", response)
        self.assertEqual(response["disposal_action"], "donate/reuse")

    def test_user_confirmed_selection_continues_to_guidance(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [],
            "recognition_source": "user_confirmed_selection",
            "recognition_confidence": {
                "level": "high",
                "score": 1.0,
                "reason_codes": ["user_confirmed_selection"],
                "blocking": False,
            },
        }

        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
        ) as mock_retrieve:
            response = build_prediction_response(classification)

        mock_retrieve.assert_called_once()
        self.assertEqual(response["status"], "confident")
        self.assertNotIn("clarification", response)
        self.assertEqual(response["disposal_action"], "e-waste recycling")

    def test_strong_recognition_preserves_existing_response_contract(self):
        classification = {
            "item": "Calculator",
            "category": "Electronics",
            "status": "confident",
            "candidates": [("Calculator", 0.96)],
            "recognition_source": "vlm_open",
            "recognition_confidence": {
                "level": "high",
                "score": 0.94,
                "reason_codes": [],
                "blocking": False,
            },
        }

        with patch(
            "services.guidance_service.guidance_retrieval_service.retrieve_guidance_chunks",
            return_value=[],
        ):
            response = build_prediction_response(classification)

        for key in (
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
            self.assertIn(key, response)
        self.assertEqual(response["status"], "confident")
        self.assertNotIn("clarification", response)


if __name__ == "__main__":
    unittest.main()
