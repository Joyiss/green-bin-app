import os
import unittest
from unittest.mock import Mock, patch

import requests

from services import gemini_text_client as client


def _settings() -> dict[str, object]:
    return {
        "provider": "google_ai_studio",
        "model": "gemini-3.5-flash-lite",
        "api_key": "secret-key",
        "timeout_seconds": 7.0,
        "max_output_tokens": 600,
    }


def _response(text: str, *, status_code: int = 200) -> Mock:
    response = Mock(ok=status_code < 400, status_code=status_code)
    response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}]
    }
    return response


class GeminiTextClientTests(unittest.TestCase):
    def test_settings_use_gemini_environment(self):
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "key",
                "GEMINI_TEXT_MODEL": "gemini-3.5-flash-lite",
                "GEMINI_TEXT_TIMEOUT_SECONDS": "12.5",
                "GEMINI_TEXT_MAX_OUTPUT_TOKENS": "550",
            },
            clear=True,
        ):
            settings = client.current_settings()

        self.assertEqual(settings["provider"], "google_ai_studio")
        self.assertEqual(settings["model"], "gemini-3.5-flash-lite")
        self.assertEqual(settings["timeout_seconds"], 12.5)
        self.assertEqual(settings["max_output_tokens"], 550)
        self.assertIsNone(client.configuration_failure_reason(settings))

    @patch("services.gemini_text_client.requests.post")
    def test_generate_text_calls_ai_studio_with_structured_output(self, post):
        post.return_value = _response('{"ok":true}')
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }

        with self.assertLogs("services.gemini_text_client", level="INFO") as logs:
            result = client.generate_text(
                "Return JSON.",
                settings=_settings(),
                use_case="guidance_generation",
                response_schema=schema,
            )

        self.assertEqual(result, '{"ok":true}')
        self.assertIn("gemini-3.5-flash-lite:generateContent", post.call_args.args[0])
        sent = post.call_args.kwargs
        self.assertEqual(sent["headers"]["x-goog-api-key"], "secret-key")
        self.assertEqual(sent["timeout"], 7.0)
        self.assertEqual(
            sent["json"]["generationConfig"]["responseJsonSchema"], schema
        )
        self.assertEqual(sent["json"]["generationConfig"]["maxOutputTokens"], 600)
        combined = "\n".join(logs.output)
        self.assertIn("parse_success=True", combined)
        self.assertIn("schema_success=True", combined)
        self.assertIn("model_response=", combined)
        self.assertNotIn("secret-key", combined)

    @patch("services.gemini_text_client.requests.post")
    def test_rate_limit_is_normalized(self, post):
        post.return_value = Mock(ok=False, status_code=429)

        with self.assertRaises(client.GeminiTextError) as raised:
            client.generate_text("prompt", settings=_settings(), use_case="evaluation")

        self.assertEqual(raised.exception.failure_reason, "rate_limit")

    @patch("services.gemini_text_client.requests.post")
    def test_timeout_is_normalized(self, post):
        post.side_effect = requests.ReadTimeout("slow")

        with self.assertRaises(client.GeminiTextError) as raised:
            client.generate_text("prompt", settings=_settings(), use_case="normalization")

        self.assertEqual(raised.exception.failure_reason, "timeout")

    @patch("services.gemini_text_client.requests.post")
    def test_empty_response_is_normalized(self, post):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"candidates": []}
        post.return_value = response

        with self.assertRaises(client.GeminiTextError) as raised:
            client.generate_text("prompt", settings=_settings(), use_case="guidance")

        self.assertEqual(raised.exception.failure_reason, "empty_response")


if __name__ == "__main__":
    unittest.main()
