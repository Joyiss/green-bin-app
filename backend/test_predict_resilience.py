import asyncio
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from routes import predict as predict_route


class PredictResilienceTests(unittest.TestCase):
    def test_bounded_concurrent_and_repeated_requests_are_isolated(self):
        async def recognize_item(*, file, selected_item):
            await asyncio.sleep(0.005)
            if selected_item == "mock-failure":
                raise RuntimeError("synthetic failure")
            return {"item": selected_item, "category": "Mock", "status": "confident"}

        def build_response(classification):
            return {
                "item": classification["item"],
                "status": "confident",
                "disposal_action": "recycle",
            }

        def send(item):
            client = TestClient(app)
            try:
                response = client.post("/predict", data={"selected_item": item})
                return response.status_code, response.json().get("item")
            except RuntimeError:
                return "failed", None

        with (
            patch("routes.predict.scan_rate_limit_service.check_scan_limits", return_value=None),
            patch("routes.predict.scan_rate_limit_service.consume_scan", return_value=None),
            patch("routes.predict._confirmed_provider_for_location", return_value=None),
            patch("routes.predict.recognize_item", side_effect=recognize_item),
            patch("routes.predict.build_prediction_response", side_effect=build_response),
        ):
            for count in (1, 5, 10):
                items = [f"mock-item-{index}" for index in range(count)]
                if count > 1:
                    items[2] = "mock-failure"
                with ThreadPoolExecutor(max_workers=count) as executor:
                    results = list(executor.map(send, items))
                for item, result in zip(items, results):
                    self.assertEqual(result, ("failed", None) if item == "mock-failure" else (200, item))
                self.assertEqual(predict_route._ACTIVE_PREDICT_REQUESTS, 0)

            for index in range(15):
                self.assertEqual(send(f"repeat-{index}"), (200, f"repeat-{index}"))
