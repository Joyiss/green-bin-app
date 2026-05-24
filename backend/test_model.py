import unittest
from unittest.mock import Mock, patch

from backend.classifier import classify
from backend.model import detect_object, get_top_predictions
from PIL import Image


class MiniCPMCompatibilityTests(unittest.TestCase):
    @patch("backend.model.detect_object", return_value="Smartphone")
    def test_known_generated_label_maps_to_confident_prediction(self, _mock_detect_object):
        prediction = get_top_predictions(image=None)

        self.assertEqual(prediction["top_predictions"], [("Smartphone", 1.0)])
        self.assertEqual(prediction["top1_score"], 1.0)
        self.assertEqual(prediction["margin"], 1.0)
        self.assertEqual(classify(prediction)["status"], "confident")

    @patch("backend.model.detect_object", return_value="Garden hose")
    def test_unknown_generated_label_maps_to_unknown_prediction(self, _mock_detect_object):
        prediction = get_top_predictions(image=None)

        self.assertEqual(prediction["top_predictions"], [])
        self.assertEqual(prediction["top1_score"], 0.0)
        self.assertEqual(classify(prediction)["status"], "unknown")


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
                        "content": "Label: Plastic water bottle",
                    }
                }
            ]
        }
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result, "Plastic water bottle")

    @patch("backend.model.requests.post", side_effect=Exception("network down"))
    def test_detect_object_returns_empty_string_on_api_error(self, _mock_post):
        result = detect_object(self.image)

        self.assertEqual(result, "")

    @patch("backend.model.requests.post")
    def test_detect_object_returns_empty_string_on_malformed_response(self, mock_post):
        response = Mock()
        response.json.return_value = {"choices": []}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = detect_object(self.image)

        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
