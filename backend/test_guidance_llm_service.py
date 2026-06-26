import json
import os
import unittest
from unittest.mock import Mock, patch

import requests

from services.guidance_llm_service import (
    try_generate_general_safe_guidance,
    try_generate_source_grounded_guidance,
)


def _chunk(
    chunk_id: str,
    *,
    source_name: str = "Call2Recycle",
    source_url: str = "https://example.com",
    location_scope: str = "national",
    generalizable: bool = True,
    requires_location_check: bool = False,
    content: str = "Guidance content.",
    warnings=None,
    limitations=None,
    disposal_actions_supported=None,
    extra_fields=None,
):
    chunk = {
        "id": chunk_id,
        "title": chunk_id,
        "source_name": source_name,
        "source_url": source_url,
        "source_type": "ignored_by_llm_prompt",
        "location_scope": location_scope,
        "generalizable": generalizable,
        "requires_location_check": requires_location_check,
        "content": content,
        "warnings": warnings or [],
        "limitations": limitations or [],
        "disposal_actions_supported": disposal_actions_supported or ["Drop-off"],
    }
    if extra_fields:
        chunk.update(extra_fields)
    return chunk


def _retrieval_result(chunk: dict, score: float = 8.2):
    return {
        "chunk": chunk,
        "chunk_id": chunk["id"],
        "score": score,
        "matched_fields": ["item_label_exact"],
        "requires_location_check": bool(chunk.get("requires_location_check")),
    }


def _gemini_http_response(text: str) -> Mock:
    response = Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": text}],
                }
            }
        ]
    }
    return response


class GuidanceLlmServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "ENABLE_LLM_GUIDANCE": "true",
            "GUIDANCE_LLM_PROVIDER": "gemini",
            "GUIDABCE_LLM_MODEL": "gemini-2.5-flash",
            "GUIDANCE_LLM_TIMEOUT": "",
            "GEMINI_API_KEY": "test-key",
        }

    def test_valid_grounded_json_is_accepted(self):
        retrieval_results = [
            _retrieval_result(
                _chunk(
                    "chunk-1",
                    requires_location_check=True,
                    content="Use a battery drop-off program.",
                    warnings=["Do not place batteries in curbside recycling."],
                    limitations=["Program availability varies by location."],
                )
            )
        ]
        response_text = json.dumps(
            {
                "disposal_action": "drop-off",
                "material_code": None,
                "impact_level": "Check Local Guidance",
                "summary": "Use a battery drop-off program and check local availability.",
                "steps": [
                    "Take the battery to a drop-off program.",
                    "Verify local availability before relying on this option.",
                ],
                "warnings": ["Do not place batteries in curbside recycling."],
                "confidence": "high",
                "sources_used": ["chunk-1"],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=["requires_dropoff"],
                location=None,
                retrieval_results=retrieval_results,
            )

        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["guidance"]["guidance_source"], "json_rag_llm_generated")
        self.assertEqual(result["guidance"]["disposal_action"], "drop-off")

    def test_gemini_request_uses_header_auth_without_key_query_param(self):
        response_text = json.dumps(
            {
                "disposal_action": "drop-off",
                "material_code": None,
                "impact_level": "Check Local Guidance",
                "summary": "Use a battery drop-off program and check local availability.",
                "steps": [
                    "Take the battery to a drop-off program.",
                    "Verify local availability before relying on this option.",
                ],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["chunk-1"],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ) as mock_post:
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertIsNotNone(result["guidance"])
        request_url = mock_post.call_args.args[0]
        request_headers = mock_post.call_args.kwargs["headers"]
        self.assertIn(
            "/models/gemini-2.5-flash:generateContent",
            request_url,
        )
        self.assertNotIn("?key=", request_url)
        self.assertEqual(
            request_headers["x-goog-api-key"],
            self.env["GEMINI_API_KEY"],
        )
        self.assertEqual(request_headers["Content-Type"], "application/json")

    def test_old_model_env_name_is_ignored_for_safe_default(self):
        env = {
            "ENABLE_LLM_GUIDANCE": "true",
            "GUIDANCE_LLM_PROVIDER": "gemini",
            "GUIDANCE_LLM_MODEL": "gemini-3-flash-preview",
            "GUIDANCE_LLM_TIMEOUT": "",
            "GEMINI_API_KEY": "test-key",
        }
        response_text = json.dumps(
            {
                "disposal_action": "drop-off",
                "summary": "Use a battery drop-off program and check local availability.",
                "steps": [
                    "Take the battery to a drop-off program.",
                    "Verify local availability before relying on this option.",
                ],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["chunk-1"],
            }
        )

        with patch.dict(os.environ, env, clear=True), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ) as mock_post:
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertIsNotNone(result["guidance"])
        request_url = mock_post.call_args.args[0]
        self.assertIn("/models/gemini-2.5-flash:generateContent", request_url)
        self.assertNotIn("gemini-3-flash-preview", request_url)

    def test_gemini_request_uses_configured_timeout(self):
        env = dict(self.env)
        env["GUIDANCE_LLM_TIMEOUT"] = "20"
        response_text = json.dumps(
            {
                "disposal_action": "drop-off",
                "summary": "Use a battery drop-off program and check local availability.",
                "steps": [
                    "Take the battery to a drop-off program.",
                    "Verify local availability before relying on this option.",
                ],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["chunk-1"],
            }
        )

        with patch.dict(os.environ, env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ) as mock_post, self.assertLogs(
            "services.guidance_llm_service", level="INFO"
        ) as captured_logs:
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertIsNotNone(result["guidance"])
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 20.0)
        combined_logs = "\n".join(captured_logs.output)
        self.assertIn("provider=gemini", combined_logs)
        self.assertIn("model=gemini-2.5-flash", combined_logs)
        self.assertIn("mode=source_grounded", combined_logs)
        self.assertIn("chunk_ids=['chunk-1']", combined_logs)
        self.assertIn("timeout_seconds=20.0", combined_logs)

    def test_invalid_timeout_falls_back_safely(self):
        env = dict(self.env)
        env["GUIDANCE_LLM_TIMEOUT"] = "not-a-number"
        response_text = json.dumps(
            {
                "disposal_action": "drop-off",
                "summary": "Use a battery drop-off program and check local availability.",
                "steps": [
                    "Take the battery to a drop-off program.",
                    "Verify local availability before relying on this option.",
                ],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["chunk-1"],
            }
        )

        with patch.dict(os.environ, env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ) as mock_post, self.assertLogs(
            "services.guidance_llm_service", level="WARNING"
        ) as captured_logs:
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertIsNotNone(result["guidance"])
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 10.0)
        combined_logs = "\n".join(captured_logs.output)
        self.assertIn("Invalid GUIDANCE_LLM_TIMEOUT value", combined_logs)
        self.assertIn("default_timeout_seconds=10.0", combined_logs)

    def test_invalid_json_falls_back(self):
        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response("not json"),
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertIsNone(result["guidance"])
        self.assertEqual(result["failure_reason"], "invalid_json")

    def test_missing_summary_is_rejected(self):
        response_text = json.dumps(
            {
                "disposal_action": "drop-off",
                "steps": ["Use a drop-off option.", "Verify local availability."],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["chunk-1"],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertEqual(result["failure_reason"], "missing_summary")

    def test_unsupported_disposal_action_is_rejected(self):
        response_text = json.dumps(
            {
                "disposal_action": "recycle",
                "summary": "Recycle this item.",
                "steps": ["Place it in recycling.", "Check local guidance."],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["chunk-1"],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1", disposal_actions_supported=["Drop-off"]))],
            )

        self.assertEqual(result["failure_reason"], "unsupported_disposal_action")

    def test_unrecognized_sources_used_is_rejected(self):
        response_text = json.dumps(
            {
                "disposal_action": "drop-off",
                "summary": "Use a drop-off program and check local availability.",
                "steps": ["Use a drop-off option.", "Verify local availability."],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["not-retrieved"],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertEqual(result["failure_reason"], "invalid_sources_used")

    def test_paintcare_location_check_caveat_is_required(self):
        response_text = json.dumps(
            {
                "disposal_action": "drop-off",
                "summary": "Use PaintCare where available in your local program area.",
                "steps": [
                    "Bring the paint to a participating PaintCare site.",
                    "Check local program availability before visiting.",
                ],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["paintcare"],
            }
        )
        retrieval_results = [
            _retrieval_result(
                _chunk(
                    "paintcare",
                    source_name="PaintCare",
                    generalizable=False,
                    requires_location_check=True,
                    content="Architectural paint may be accepted through PaintCare.",
                )
            )
        ]

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Paint",
                normalized_item_label="Paint",
                material="Paint",
                broad_category="Paint",
                condition_flags=[],
                location=None,
                retrieval_results=retrieval_results,
            )

        self.assertIsNotNone(result["guidance"])

    def test_dsny_is_not_treated_as_national(self):
        response_text = json.dumps(
            {
                "disposal_action": "recycle",
                "summary": "This is nationally recyclable.",
                "steps": ["Place it in recycling nationally.", "Use this guidance everywhere."],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["dsny"],
            }
        )
        retrieval_results = [
            _retrieval_result(
                _chunk(
                    "dsny",
                    source_name="NYC DSNY Recycling & Disposal",
                    location_scope="city: New York City",
                    generalizable=False,
                    content="NYC residents can recycle this item curbside.",
                    disposal_actions_supported=["Recycle"],
                )
            )
        ]

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Paper",
                normalized_item_label="Paper",
                material="Paper",
                broad_category="Paper",
                condition_flags=[],
                location={"city": "New York City", "state": "NY"},
                retrieval_results=retrieval_results,
            )

        self.assertEqual(result["failure_reason"], "dsny_treated_as_national")

    def test_timeout_falls_through_safely(self):
        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            side_effect=requests.Timeout(),
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertEqual(result["failure_reason"], "timeout")

    def test_request_error_logs_sanitized_status_and_body_preview(self):
        error_response = Mock()
        error_response.status_code = 401
        error_response.text = (
            "Model gemini-2.5-flash not found. "
            + ("details " * 80)
            + "key=test-key"
        )
        http_error = requests.HTTPError("401 Client Error")
        http_error.response = error_response

        failed_response = Mock()
        failed_response.status_code = 401
        failed_response.raise_for_status.side_effect = http_error

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=failed_response,
        ), self.assertLogs("services.guidance_llm_service", level="INFO") as captured_logs:
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertEqual(result["failure_reason"], "request_error")
        combined_logs = "\n".join(captured_logs.output)
        self.assertIn("HTTPError", combined_logs)
        self.assertIn("status_code=401", combined_logs)
        self.assertIn("model=gemini-2.5-flash", combined_logs)
        self.assertIn(
            "endpoint=https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            combined_logs,
        )
        self.assertNotIn("test-key", combined_logs)
        self.assertNotIn("?key=", combined_logs)
        self.assertIn("body_preview=", combined_logs)
        self.assertIn("Model gemini-2.5-flash not found.", combined_logs)
        self.assertIn("...", combined_logs)

    def test_missing_api_key_skips_gemini_safely(self):
        env = dict(self.env)
        env["GEMINI_API_KEY"] = ""

        with patch.dict(os.environ, env, clear=False), patch(
            "services.guidance_llm_service.requests.post"
        ) as mock_post:
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertEqual(result["failure_reason"], "missing_GEMINI_API_KEY")
        mock_post.assert_not_called()

    def test_wrong_model_id_returns_safe_fallback_not_crash(self):
        error_response = Mock()
        error_response.status_code = 404
        error_response.text = '{"error":{"message":"Model not found"}}'
        http_error = requests.HTTPError("404 Client Error")
        http_error.response = error_response

        failed_response = Mock()
        failed_response.status_code = 404
        failed_response.raise_for_status.side_effect = http_error

        env = dict(self.env)
        env["GUIDABCE_LLM_MODEL"] = "gemini-2.5-flash-typo"

        with patch.dict(os.environ, env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=failed_response,
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertIsNone(result["guidance"])
        self.assertEqual(result["failure_reason"], "request_error")

    def test_unauthenticated_401_returns_safe_fallback_not_crash(self):
        error_response = Mock()
        error_response.status_code = 401
        error_response.text = '{"error":{"message":"UNAUTHENTICATED"}}'
        http_error = requests.HTTPError("401 Client Error")
        http_error.response = error_response

        failed_response = Mock()
        failed_response.status_code = 401
        failed_response.raise_for_status.side_effect = http_error

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=failed_response,
        ):
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=[_retrieval_result(_chunk("chunk-1"))],
            )

        self.assertIsNone(result["guidance"])
        self.assertEqual(result["failure_reason"], "request_error")

    def test_only_top_stripped_chunks_are_sent_to_gemini(self):
        retrieval_results = [
            _retrieval_result(_chunk(f"chunk-{index}", extra_fields={"applies_to": {"item_labels": ["battery"]}}), score=10 - index)
            for index in range(1, 5)
        ]
        response_text = json.dumps(
            {
                "disposal_action": "drop-off",
                "summary": "Use a drop-off option and check local availability.",
                "steps": ["Use a drop-off option.", "Check local availability before relying on it."],
                "warnings": [],
                "confidence": "high",
                "sources_used": ["chunk-1"],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ) as mock_post:
            result = try_generate_source_grounded_guidance(
                recognized_item="Battery",
                normalized_item_label="Battery",
                material="Battery",
                broad_category="Batteries",
                condition_flags=[],
                location=None,
                retrieval_results=retrieval_results,
            )

        self.assertIsNotNone(result["guidance"])
        prompt_text = mock_post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
        self.assertIn('"id": "chunk-1"', prompt_text)
        self.assertIn('"id": "chunk-3"', prompt_text)
        self.assertNotIn('"id": "chunk-4"', prompt_text)
        self.assertNotIn("source_type", prompt_text)
        self.assertNotIn("applies_to", prompt_text)

    def test_general_safe_fallback_accepts_conservative_json(self):
        response_text = json.dumps(
            {
                "disposal_action": "donate/reuse",
                "material_code": None,
                "impact_level": "Low Confidence Guidance",
                "summary": "If the bottle is reusable, keep using it or donate it.",
                "steps": [
                    "Keep using the bottle or donate it if it is still usable.",
                    "Check local reuse or drop-off options if it is damaged.",
                    "If no better option is available, follow local trash guidance.",
                ],
                "warnings": [
                    "Do not place this item in curbside recycling unless your local program accepts it."
                ],
                "confidence": "low",
                "sources_used": [],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_general_safe_guidance(
                recognized_item="Thermoflask",
                normalized_item_label="Thermoflask",
                material="Metal",
                broad_category="Drinkware",
                condition_flags=[],
            )

        self.assertEqual(result["guidance"]["guidance_source"], "llm_general_fallback")
        self.assertEqual(result["guidance"]["guidance_metadata"]["confidence"], "low")
        self.assertEqual(result["guidance"]["disposal_action"], "donate/reuse")

    def test_general_safe_fallback_accepts_check_local_guidance_action(self):
        response_text = json.dumps(
            {
                "disposal_action": "check local guidance",
                "material_code": "paper",
                "impact_level": "Low Confidence Guidance",
                "summary": "If the sheet music is clean and dry, check whether local paper recycling accepts it.",
                "steps": [
                    "Reuse or donate the sheet music if someone can still use it.",
                    "Check local paper recycling rules before placing it in recycling.",
                    "If it is damaged or not accepted, follow local trash guidance.",
                ],
                "warnings": [
                    "Do not place this item in curbside recycling unless your local program accepts it."
                ],
                "confidence": "low",
                "sources_used": [],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_general_safe_guidance(
                recognized_item="Sheet Music",
                normalized_item_label="Sheet Music",
                material="Paper",
                broad_category="Paper",
                condition_flags=[],
            )

        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["guidance"]["disposal_action"], "check local guidance")

    def test_general_safe_output_missing_summary_is_rejected(self):
        response_text = json.dumps(
            {
                "disposal_action": None,
                "material_code": None,
                "impact_level": "Low Confidence Guidance",
                "steps": [
                    "Reuse or donate the item if it is still usable.",
                    "Check local recycling or drop-off options before using them.",
                    "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
                ],
                "warnings": [
                    "Do not place this item in curbside recycling unless your local program accepts it."
                ],
                "confidence": "low",
                "sources_used": [],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_general_safe_guidance(
                recognized_item="Pencil",
                normalized_item_label="Pencil",
                material="Mixed Material",
                broad_category="Household item",
                condition_flags=[],
            )

        self.assertEqual(result["failure_reason"], "missing_summary")

    def test_general_safe_output_missing_steps_is_rejected(self):
        response_text = json.dumps(
            {
                "disposal_action": None,
                "material_code": None,
                "impact_level": "Low Confidence Guidance",
                "summary": "Reuse the item if it is still usable.",
                "warnings": [
                    "Do not place this item in curbside recycling unless your local program accepts it."
                ],
                "confidence": "low",
                "sources_used": [],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_general_safe_guidance(
                recognized_item="Pencil",
                normalized_item_label="Pencil",
                material="Mixed Material",
                broad_category="Household item",
                condition_flags=[],
            )

        self.assertEqual(result["failure_reason"], "missing_steps")

    def test_general_safe_output_with_unsupported_disposal_action_is_rejected(self):
        response_text = json.dumps(
            {
                "disposal_action": "trash",
                "material_code": None,
                "impact_level": "Low Confidence Guidance",
                "summary": "Reuse the item if it is still usable.",
                "steps": [
                    "Reuse or donate the item if it is still usable.",
                    "Check local recycling or drop-off options before using them.",
                    "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
                ],
                "warnings": [
                    "Do not place this item in curbside recycling unless your local program accepts it."
                ],
                "confidence": "low",
                "sources_used": [],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_general_safe_guidance(
                recognized_item="Pencil",
                normalized_item_label="Pencil",
                material="Mixed Material",
                broad_category="Household item",
                condition_flags=[],
            )

        self.assertEqual(result["failure_reason"], "general_fallback_unsupported_action")

    def test_general_safe_output_claiming_guaranteed_curbside_recycling_is_rejected(self):
        response_text = json.dumps(
            {
                "disposal_action": "check local guidance",
                "material_code": None,
                "impact_level": "Low Confidence Guidance",
                "summary": "This item is definitely accepted in curbside recycling everywhere.",
                "steps": [
                    "Reuse or donate the item if it is still usable.",
                    "Place it in your curbside recycling bin.",
                ],
                "warnings": [],
                "confidence": "low",
                "sources_used": [],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ):
            result = try_generate_general_safe_guidance(
                recognized_item="Plastic Toy",
                normalized_item_label="Plastic Toy",
                material="Plastic",
                broad_category="Toy",
                condition_flags=[],
            )

        self.assertEqual(result["failure_reason"], "overconfident_general_fallback")

    def test_general_safe_validation_failure_logs_parsed_keys_without_api_key(self):
        response_text = json.dumps(
            {
                "disposal_action": None,
                "material_code": None,
                "impact_level": "Low Confidence Guidance",
                "steps": [
                    "Reuse or donate the item if it is still usable.",
                    "Check local recycling or drop-off options before using them.",
                    "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
                ],
                "warnings": [
                    "Do not place this item in curbside recycling unless your local program accepts it."
                ],
                "confidence": "low",
                "sources_used": [],
            }
        )

        with patch.dict(os.environ, self.env, clear=False), patch(
            "services.guidance_llm_service.requests.post",
            return_value=_gemini_http_response(response_text),
        ), self.assertLogs("services.guidance_llm_service", level="INFO") as captured_logs:
            result = try_generate_general_safe_guidance(
                recognized_item="Pencil",
                normalized_item_label="Pencil",
                material="Mixed Material",
                broad_category="Household item",
                condition_flags=[],
            )

        self.assertEqual(result["failure_reason"], "missing_summary")
        combined_logs = "\n".join(captured_logs.output)
        self.assertIn("parsed_keys=", combined_logs)
        self.assertIn("response_preview=", combined_logs)
        self.assertNotIn("test-key", combined_logs)


if __name__ == "__main__":
    unittest.main()
