import unittest
from unittest.mock import Mock, patch

from classifier import classify
from model import detect_object, get_top_predictions, normalize_vlm_recognition_mode
from PIL import Image
from services.vlm_service import _build_detection_prompt, _build_open_detection_prompt


class VisionModelCompatibilityTests(unittest.TestCase):
    @patch(
        "model.detect_object",
        return_value={
            "status": "confident",
            "primary_label": "Smartphone",
            "candidate_labels": ["Smartphone"],
            "raw_output": "",
        },
    )
    def test_known_generated_label_maps_to_confident_prediction(self, _mock_detect_object):
        prediction = get_top_predictions(image=None)

        self.assertEqual(prediction["top_predictions"], [("Smartphone", 1.0)])
        self.assertEqual(prediction["top1_score"], 1.0)
        self.assertEqual(prediction["margin"], 1.0)
        self.assertEqual(classify(prediction)["status"], "confident")

    @patch(
        "model.detect_object",
        return_value={
            "status": "unknown",
            "primary_label": "",
            "candidate_labels": [],
            "raw_output": "",
        },
    )
    def test_unknown_generated_label_maps_to_unknown_prediction(self, _mock_detect_object):
        prediction = get_top_predictions(image=None)

        self.assertEqual(prediction["top_predictions"], [])
        self.assertEqual(prediction["top1_score"], 0.0)
        self.assertEqual(classify(prediction)["status"], "unknown")

    @patch(
        "model.detect_object",
        return_value={
            "status": "uncertain",
            "primary_label": "Fruit scraps",
            "candidate_labels": ["Fruit scraps", "Vegetable scraps", "Leftover food"],
            "raw_output": "",
        },
    )
    def test_ranked_candidates_map_to_uncertain_prediction(self, _mock_detect_object):
        prediction = get_top_predictions(image=None)

        self.assertEqual(
            prediction["top_predictions"],
            [
                ("Fruit scraps", 0.58),
                ("Vegetable scraps", 0.5599999999999999),
                ("Leftover food", 0.5399999999999999),
            ],
        )
        self.assertLess(prediction["margin"], 0.05)
        self.assertEqual(classify(prediction)["status"], "uncertain")

    @patch(
        "model.detect_object",
        return_value={
            "status": "confident",
            "primary_label": "Calculator",
            "candidate_labels": ["Calculator", "Keyboard", "Mouse"],
            "raw_output": "",
        },
    )
    def test_confident_prediction_preserves_ranked_candidates(self, _mock_detect_object):
        prediction = get_top_predictions(image=None)
        classification = classify(prediction)

        self.assertEqual(
            prediction["top_predictions"],
            [
                ("Calculator", 1.0),
                ("Keyboard", 0.92),
                ("Mouse", 0.84),
            ],
        )
        self.assertGreaterEqual(prediction["margin"], 0.05)
        self.assertEqual(classification["status"], "confident")
        self.assertEqual(
            classification["candidates"],
            [
                ("Calculator", 1.0),
                ("Keyboard", 0.92),
                ("Mouse", 0.84),
            ],
        )


class RecognitionModeTests(unittest.TestCase):
    def test_missing_mode_defaults_to_constrained(self):
        self.assertEqual(normalize_vlm_recognition_mode(None), "constrained")

    def test_invalid_mode_defaults_to_constrained(self):
        self.assertEqual(
            normalize_vlm_recognition_mode("  definitely-not-valid  "),
            "constrained",
        )

    def test_open_mode_is_accepted(self):
        self.assertEqual(normalize_vlm_recognition_mode("  OPEN "), "open")


class DetectObjectApiTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (8, 8), color="white")
        self.account_patch = patch("model.CLOUDFLARE_ACCOUNT_ID", "account-id")
        self.token_patch = patch("model.CLOUDFLARE_API_TOKEN", "api-token")
        self.mode_patch = patch("model.VLM_RECOGNITION_MODE", "constrained")
        self.account_patch.start()
        self.token_patch.start()
        self.mode_patch.start()
        self.addCleanup(self.account_patch.stop)
        self.addCleanup(self.token_patch.stop)
        self.addCleanup(self.mode_patch.stop)

    @patch("model.requests.post")
    def test_detect_object_returns_cleaned_label_from_api_content(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": '{"status":"confident","primary_label":"Plastic water bottle","candidate_labels":["Plastic water bottle","Soda bottle","Milk jug"]}',
            },
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["primary_label"], "Plastic water bottle")
        self.assertEqual(result["candidate_labels"], ["Plastic water bottle", "Soda bottle", "Milk jug"])
        request_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(request_payload["response_format"]["type"], "json_schema")

    @patch("model.requests.post")
    def test_detect_object_accepts_json_mode_object_response(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": {
                    "status": "confident",
                    "primary_label": "Mattress",
                    "candidate_labels": ["Mattress", "Furniture"],
                },
            },
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["primary_label"], "Mattress")
        self.assertEqual(result["candidate_labels"], ["Mattress", "Furniture"])

    @patch("model.requests.post")
    def test_detect_object_open_mode_returns_structured_recognition(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": (
                    '{"status":"confident","raw_item_label":"Ceramic mug","likely_material":"Ceramic",'
                    '"broad_category":"Drinkware","candidates":[{"label":"Ceramic mug","confidence":0.93},'
                    '{"label":"Coffee mug","confidence":0.72}],"visual_evidence":"Handle and glossy cup body are visible.",'
                    '"visual_observations":[{"aspect":"packaging_use","value":"not packaging","confidence":0.86,'
                    '"evidence":"Rigid mug body with no wrapper."},{"aspect":"contamination","value":"unknown",'
                    '"confidence":null,"evidence":""}],'
                    '"disposal_action":"trash","steps":["do not trust this"]}'
                ),
            },
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        with patch("model.VLM_RECOGNITION_MODE", " open "):
            result = detect_object(self.image)

        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["raw_item_label"], "Ceramic mug")
        self.assertEqual(result["likely_material"], "Ceramic")
        self.assertEqual(result["broad_category"], "Drinkware")
        self.assertEqual(
            result["candidates"],
            [
                {"label": "Ceramic mug", "confidence": 0.93},
                {"label": "Coffee mug", "confidence": 0.72},
            ],
        )
        self.assertEqual(
            result["visual_evidence"],
            "Handle and glossy cup body are visible.",
        )
        self.assertEqual(
            result["visual_observations"],
            [
                {
                    "aspect": "packaging_use",
                    "value": "not packaging",
                    "confidence": 0.86,
                    "evidence": "Rigid mug body with no wrapper.",
                },
                {
                    "aspect": "contamination",
                    "value": "unknown",
                    "confidence": None,
                    "evidence": "",
                },
            ],
        )
        self.assertNotIn("disposal_action", result)
        self.assertNotIn("steps", result)
        request_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(request_payload["max_tokens"], 220)
        self.assertIn("visual_observations", request_payload["response_format"]["json_schema"]["required"])

    @patch("model.requests.post")
    def test_detect_object_open_mode_handles_non_json_safely(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": "Looks like a ceramic mug with a handle.",
            },
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        with patch("model.VLM_RECOGNITION_MODE", "open"):
            result = detect_object(self.image)

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["raw_item_label"], "")
        self.assertEqual(result["likely_material"], "")
        self.assertEqual(result["broad_category"], "")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["visual_evidence"], "")
        self.assertEqual(result["visual_observations"], [])
        self.assertEqual(result["raw_output"], "Looks like a ceramic mug with a handle.")

    @patch("model.requests.post")
    def test_detect_object_open_mode_recovers_truncated_json_fields(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": (
                    '{"status":"confident","raw_item_label":"Water bottle","likely_material":"Plastic",'
                    '"broad_category":"Bottle","candidates":[{"label":"Water bottle","confidence":0.96},'
                    '{"label":"Plastic bottle","confidence":0.83}],"visual_evidence":"Clear bottle with'
                ),
            },
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        with patch("model.VLM_RECOGNITION_MODE", "open"):
            result = detect_object(self.image)

        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["raw_item_label"], "Water bottle")
        self.assertEqual(result["likely_material"], "Plastic")
        self.assertEqual(result["broad_category"], "Bottle")
        self.assertEqual(
            result["candidates"],
            [
                {"label": "Water bottle", "confidence": 0.96},
                {"label": "Plastic bottle", "confidence": 0.83},
            ],
        )
        self.assertEqual(result["visual_evidence"], "")
        self.assertEqual(result["visual_observations"], [])
        self.assertTrue(result["raw_output"].startswith('{"status":"confident"'))

    @patch("model.requests.post")
    def test_get_top_predictions_open_mode_preserves_recognition_details(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": (
                    '{"status":"uncertain","raw_item_label":"Ceramic mug","likely_material":"Ceramic",'
                    '"broad_category":"Drinkware","candidates":[{"label":"Ceramic mug","confidence":null}],'
                    '"visual_evidence":"Cup silhouette with a handle.",'
                    '"visual_observations":[{"aspect":"form_factor","value":"handled cup","confidence":0.82,'
                    '"evidence":"Handle visible."}]}'
                ),
            },
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        with patch("model.VLM_RECOGNITION_MODE", "open"):
            prediction = get_top_predictions(self.image)

        self.assertEqual(prediction["top_predictions"], [])
        self.assertEqual(prediction["margin"], 0.0)
        self.assertEqual(
            prediction["recognition_details"]["candidates"],
            [{"label": "Ceramic mug", "confidence": None}],
        )
        self.assertEqual(
            prediction["recognition_details"]["visual_observations"][0]["aspect"],
            "form_factor",
        )

    @patch("model.requests.post", side_effect=Exception("network down"))
    def test_detect_object_returns_empty_string_on_api_error(self, _mock_post):
        result = detect_object(self.image)

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["candidate_labels"], [])

    @patch("model.requests.post")
    def test_detect_object_returns_empty_string_on_malformed_response(self, mock_post):
        response = Mock()
        response.json.return_value = {"success": True, "result": {}}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["candidate_labels"], [])

    @patch("model.requests.post")
    def test_detect_object_parses_uncertain_ranked_candidates(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": '{"status":"uncertain","primary_label":"watermelon","candidate_labels":["watermelon","vegetable waste","bread"]}',
            },
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Fruit scraps")
        self.assertEqual(result["candidate_labels"], ["Fruit scraps", "Vegetable scraps", "Bread"])

    @patch("model.requests.post")
    def test_detect_object_retries_when_uncertain_response_missing_candidates(self, mock_post):
        first_response = Mock()
        first_response.json.return_value = {
            "success": True,
            "result": {
                "response": '\n\n{"status":"uncertain","primary_label":"Keyboard"}',
            },
        }
        first_response.raise_for_status.return_value = None

        second_response = Mock()
        second_response.json.return_value = {
            "success": True,
            "result": {
                "response": '{"status":"uncertain","primary_label":"Keyboard","candidate_labels":["Keyboard","Laptop","Mouse"]}',
            },
        }
        second_response.raise_for_status.return_value = None
        mock_post.side_effect = [first_response, second_response]

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Keyboard")
        self.assertEqual(result["candidate_labels"], ["Keyboard", "Laptop", "Mouse"])

    @patch("model.requests.post")
    def test_detect_object_parses_first_json_object_when_trailing_text_exists(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": (
                    '{"status":"uncertain","primary_label":"Keyboard","candidate_labels":["Keyboard","Laptop","Mouse"]}\n'
                    'extra trailing note'
                ),
            },
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Keyboard")
        self.assertEqual(result["candidate_labels"], ["Keyboard", "Laptop", "Mouse"])

    @patch("model.requests.post")
    def test_detect_object_parses_prose_response_without_json(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": (
                    'The primary label is "Mattress". '
                    'The candidate labels could include "Furniture" and "Bed". '
                    'The status of the image would be "confident".'
                ),
            },
        }
        response.raise_for_status.return_value = None
        mock_post.side_effect = [response, response]

        result = detect_object(self.image)

        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["primary_label"], "Mattress")
        self.assertEqual(result["candidate_labels"], ["Mattress", "Furniture"])

    @patch("model.requests.post")
    def test_detect_object_verifies_confident_result_for_multiple_objects(self, mock_post):
        first_response = Mock()
        first_response.json.return_value = {
            "success": True,
            "result": {
                "response": '{"status":"confident","primary_label":"Notebook paper","candidate_labels":["Notebook paper","Paper bag","Book"]}',
            },
        }
        first_response.raise_for_status.return_value = None

        verification_response = Mock()
        verification_response.json.return_value = {
            "success": True,
            "result": {
                "response": '{"status":"uncertain","primary_label":"Notebook paper","candidate_labels":["Notebook paper","Mouse","Keyboard"]}',
            },
        }
        verification_response.raise_for_status.return_value = None
        mock_post.side_effect = [first_response, verification_response]

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Notebook paper")
        self.assertEqual(result["candidate_labels"], ["Notebook paper", "Mouse", "Keyboard"])

    @patch("model.requests.post")
    def test_detect_object_keeps_initial_result_when_verification_is_unstructured(self, mock_post):
        first_response = Mock()
        first_response.json.return_value = {
            "success": True,
            "result": {
                "response": '{"status":"confident","primary_label":"Mattress","candidate_labels":["Mattress"]}',
            },
        }
        first_response.raise_for_status.return_value = None

        verification_response = Mock()
        verification_response.json.return_value = {
            "success": True,
            "result": {
                "response": "Here is the JSON",
            },
        }
        verification_response.raise_for_status.return_value = None
        mock_post.side_effect = [first_response, verification_response]

        result = detect_object(self.image)

        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["primary_label"], "Mattress")
        self.assertEqual(result["candidate_labels"], ["Mattress"])

    @patch("model.requests.post")
    def test_detect_object_forces_uncertain_when_confident_has_distinct_candidates(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "result": {
                "response": (
                    '\n\n{\n'
                    '"status": "confident",\n'
                    '"primary_label": "Book",\n'
                    '"candidate_labels": ["Calculator", "Mouse", "Cable"]\n'
                    "}"
                ),
            },
        }
        response.raise_for_status.return_value = None

        verification_response = Mock()
        verification_response.json.return_value = {
            "success": True,
            "result": {
                "response": '\n\n{"status":"confident|uncertain","primary_label":"Book"}',
            },
        }
        verification_response.raise_for_status.return_value = None
        mock_post.side_effect = [response, verification_response]

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Book")
        self.assertEqual(result["candidate_labels"], ["Book", "Calculator", "Mouse"])


class BarcodeAwarePromptTests(unittest.TestCase):
    def test_constrained_prompt_prioritizes_physical_disposal_item(self):
        prompt = _build_detection_prompt(barcode_aware=False)

        self.assertIn(
            "Identify the actual physical object the user would dispose of",
            prompt,
        )
        self.assertIn(
            "Use visible packaging form and material when choosing a label",
            prompt,
        )
        self.assertIn("opened, used, empty, food-soiled, wet, broken", prompt)
        self.assertIn("chips in a crinkly pouch -> Chip bag", prompt)
        self.assertIn("yogurt in a plastic tub -> Yogurt container", prompt)

    def test_open_prompt_prioritizes_object_over_product_text_and_contents(self):
        prompt = _build_open_detection_prompt(barcode_aware=False)

        self.assertIn(
            "raw_item_label must name the physical object being disposed of",
            prompt,
        )
        self.assertIn(
            "not just the product, brand, logo, printed text, flavor, or contents",
            prompt,
        )
        self.assertIn(
            "packaging type, container type, opened/used/empty/food-soiled/broken condition",
            prompt,
        )
        self.assertIn(
            "branded chips -> opened chip bag, not chips",
            prompt,
        )
        self.assertIn(
            "candle jar -> glass candle jar with wax residue",
            prompt,
        )

    def test_barcode_product_context_prompt_forbids_product_name_answers(self):
        prompt = _build_detection_prompt(
            barcode_aware=True,
            barcode_context={
                "barcode_value": "0072554001628",
                "product_name": "Frozen dairy dessert cone",
                "brand": "Acme",
                "category": "Ice cream cones",
                "packaging": "unknown",
            },
        )

        self.assertIn("This metadata is product context only, not answer labels.", prompt)
        self.assertIn(
            "The answer must identify the packaging or physical item that should be disposed of",
            prompt,
        )
        self.assertIn(
            "Do not output product names like Frozen dairy dessert cone, Ice cream cone, Nutella, Coca-Cola, Chips, or Candy",
            prompt,
        )
        self.assertIn(
            "Choose only from the backend's supported item labels / canonical inventory list.",
            prompt,
        )
        self.assertIn(
            "Prefer the actual disposable packaging, container, or household item over the product name",
            prompt,
        )
        self.assertIn("Use visible packaging type, material, and condition", prompt)
        self.assertIn(
            '{"status":"unknown","primary_label":"","candidate_labels":[]}',
            prompt,
        )
        self.assertIn("Product context, not answer labels:", prompt)
        self.assertIn("- product_name: Frozen dairy dessert cone", prompt)

    def test_open_prompt_requests_json_only_structured_recognition(self):
        prompt = _build_open_detection_prompt(
            barcode_aware=True,
            barcode_context={
                "barcode_value": "0072554001628",
                "product_name": "Frozen dairy dessert cone",
                "brand": "Acme",
                "category": "Ice cream cones",
                "packaging": "wrapper",
            },
        )

        self.assertIn("Return exactly one JSON object and nothing else.", prompt)
        self.assertIn("Recognition only.", prompt)
        self.assertIn("Do not provide disposal_action.", prompt)
        self.assertIn("Do not provide steps.", prompt)
        self.assertIn('"candidates":[{"label":"ceramic mug","confidence":0.91}', prompt)
        self.assertIn('"visual_observations":[{"aspect":"packaging_use"', prompt)
        self.assertIn('"visual_evidence":"Handle, cup opening, glossy rigid body."', prompt)
        self.assertIn("visual_evidence must be a short string, 12 words or fewer", prompt)
        self.assertIn("For each observation, use value \"unknown\" and confidence null", prompt)
        self.assertIn("visual_observations must describe image-visible disposal context only", prompt)
        self.assertIn("Barcode lookup found product metadata, but this metadata is only context.", prompt)
        self.assertIn(
            "Use visible packaging type, material, and condition in raw_item_label and visual_evidence.",
            prompt,
        )
        self.assertIn("- product_name: Frozen dairy dessert cone", prompt)


if __name__ == "__main__":
    unittest.main()
