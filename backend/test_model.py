import unittest
from unittest.mock import Mock, patch

from backend.classifier import classify
from backend.model import detect_object, get_top_predictions
from PIL import Image


class MiniCPMCompatibilityTests(unittest.TestCase):
    @patch(
        "backend.model.detect_object",
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
        "backend.model.detect_object",
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
        "backend.model.detect_object",
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


class DetectObjectApiTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (8, 8), color="white")

    @patch("backend.model.requests.post")
    def test_detect_object_returns_cleaned_label_from_api_content(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"status":"confident","primary_label":"Plastic water bottle","candidate_labels":["Plastic water bottle","Soda bottle","Milk jug"]}',
                    }
                }
            ]
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result["status"], "confident")
        self.assertEqual(result["primary_label"], "Plastic water bottle")
        self.assertEqual(result["candidate_labels"], ["Plastic water bottle", "Soda bottle", "Milk jug"])

    @patch("backend.model.requests.post", side_effect=Exception("network down"))
    def test_detect_object_returns_empty_string_on_api_error(self, _mock_post):
        result = detect_object(self.image)

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["candidate_labels"], [])

    @patch("backend.model.requests.post")
    def test_detect_object_returns_empty_string_on_malformed_response(self, mock_post):
        response = Mock()
        response.json.return_value = {"choices": []}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["candidate_labels"], [])

    @patch("backend.model.requests.post")
    def test_detect_object_parses_uncertain_ranked_candidates(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"status":"uncertain","primary_label":"watermelon","candidate_labels":["watermelon","vegetable waste","bread"]}',
                    }
                }
            ]
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Fruit scraps")
        self.assertEqual(result["candidate_labels"], ["Fruit scraps", "Vegetable scraps", "Bread"])

    @patch("backend.model.requests.post")
    def test_detect_object_retries_when_uncertain_response_missing_candidates(self, mock_post):
        first_response = Mock()
        first_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '\n\n{"status":"uncertain","primary_label":"Keyboard"}',
                    }
                }
            ]
        }
        first_response.raise_for_status.return_value = None

        second_response = Mock()
        second_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"status":"uncertain","primary_label":"Keyboard","candidate_labels":["Keyboard","Laptop","Mouse"]}',
                    }
                }
            ]
        }
        second_response.raise_for_status.return_value = None
        mock_post.side_effect = [first_response, second_response]

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Keyboard")
        self.assertEqual(result["candidate_labels"], ["Keyboard", "Laptop", "Mouse"])

    @patch("backend.model.requests.post")
    def test_detect_object_parses_first_json_object_when_trailing_text_exists(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"status":"uncertain","primary_label":"Keyboard","candidate_labels":["Keyboard","Laptop","Mouse"]}\n'
                            'extra trailing note'
                        ),
                    }
                }
            ]
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Keyboard")
        self.assertEqual(result["candidate_labels"], ["Keyboard", "Laptop", "Mouse"])

    @patch("backend.model.requests.post")
    def test_detect_object_verifies_confident_result_for_multiple_objects(self, mock_post):
        first_response = Mock()
        first_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"status":"confident","primary_label":"Notebook paper","candidate_labels":["Notebook paper","Paper bag","Book"]}',
                    }
                }
            ]
        }
        first_response.raise_for_status.return_value = None

        verification_response = Mock()
        verification_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"status":"uncertain","primary_label":"Notebook paper","candidate_labels":["Notebook paper","Mouse","Keyboard"]}',
                    }
                }
            ]
        }
        verification_response.raise_for_status.return_value = None
        mock_post.side_effect = [first_response, verification_response]

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Notebook paper")
        self.assertEqual(result["candidate_labels"], ["Notebook paper", "Mouse", "Keyboard"])

    @patch("backend.model.requests.post")
    def test_detect_object_forces_uncertain_when_confident_has_distinct_candidates(self, mock_post):
        response = Mock()
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '\n\n{\n'
                            '"status": "confident",\n'
                            '"primary_label": "Book",\n'
                            '"candidate_labels": ["Calculator", "Mouse", "Cable"]\n'
                            "}"
                        ),
                    }
                }
            ]
        }
        response.raise_for_status.return_value = None

        verification_response = Mock()
        verification_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '\n\n{"status":"confident|uncertain","primary_label":"Book"}',
                    }
                }
            ]
        }
        verification_response.raise_for_status.return_value = None
        mock_post.side_effect = [response, verification_response]

        result = detect_object(self.image)

        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["primary_label"], "Book")
        self.assertEqual(result["candidate_labels"], ["Book", "Calculator", "Mouse"])


if __name__ == "__main__":
    unittest.main()
