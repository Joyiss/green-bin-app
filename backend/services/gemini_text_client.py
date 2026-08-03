from __future__ import annotations

import json
import logging
import os
from time import perf_counter
from typing import Any
from urllib.parse import quote

import requests


logger = logging.getLogger(__name__)

PROVIDER = "google_ai_studio"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_OUTPUT_TOKENS = 700
API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiTextError(RuntimeError):
    def __init__(self, failure_reason: str, message: str) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


def _text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _positive_float(name: str, default: float) -> float:
    raw = _text(os.getenv(name))
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_int(name: str, default: int) -> int:
    raw = _text(os.getenv(name))
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def current_settings() -> dict[str, Any]:
    return {
        "provider": PROVIDER,
        "model": _text(os.getenv("GEMINI_TEXT_MODEL")) or DEFAULT_MODEL,
        "api_key": _text(os.getenv("GEMINI_API_KEY")),
        "timeout_seconds": _positive_float(
            "GEMINI_TEXT_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS
        ),
        "max_output_tokens": _positive_int(
            "GEMINI_TEXT_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS
        ),
    }


def configuration_failure_reason(settings: dict[str, Any] | None = None) -> str | None:
    effective = settings or current_settings()
    if not _text(effective.get("api_key")):
        return "missing_GEMINI_API_KEY"
    if not _text(effective.get("model")):
        return "missing_GEMINI_TEXT_MODEL"
    return None


def _response_preview(value: Any, *, maximum: int = 2000) -> str:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=True, default=str)
    )
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= maximum else normalized[:maximum] + "..."


def _candidate_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise GeminiTextError("malformed_response", "Gemini returned a non-object response.")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        reason = "blocked_response" if payload.get("promptFeedback") else "empty_response"
        raise GeminiTextError(reason, "Gemini returned no response candidate.")
    candidate = candidates[0] if isinstance(candidates[0], dict) else {}
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    text_parts = [
        str(part.get("text"))
        for part in (parts or [])
        if isinstance(part, dict) and _text(part.get("text"))
    ]
    result = "".join(text_parts).strip()
    if not result:
        finish_reason = _text(candidate.get("finishReason"))
        reason = "blocked_response" if finish_reason in {"SAFETY", "RECITATION"} else "empty_response"
        raise GeminiTextError(reason, "Gemini returned an empty text response.")
    return result


def _schema_matches(value: Any, schema: Any) -> bool:
    if not isinstance(schema, dict):
        return True
    expected = schema.get("type")
    allowed_types = expected if isinstance(expected, list) else [expected]
    if value is None:
        return "null" in allowed_types
    expected_without_null = [item for item in allowed_types if item != "null"]
    if expected_without_null:
        expected_type = expected_without_null[0]
        if expected_type == "object" and not isinstance(value, dict):
            return False
        if expected_type == "array" and not isinstance(value, list):
            return False
        if expected_type == "string" and not isinstance(value, str):
            return False
        if expected_type == "boolean" and not isinstance(value, bool):
            return False
        if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            return False
        if expected_type == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, dict):
        required = schema.get("required") or []
        if any(key not in value for key in required):
            return False
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False and any(
            key not in properties for key in value
        ):
            return False
        return all(
            _schema_matches(child, properties[key])
            for key, child in value.items()
            if key in properties
        )
    if isinstance(value, list):
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            return False
        item_schema = schema.get("items")
        return all(_schema_matches(item, item_schema) for item in value)
    return True


def generate_text(
    prompt: str,
    *,
    settings: dict[str, Any] | None = None,
    use_case: str,
    response_schema: dict[str, Any] | None = None,
    temperature: float = 0.1,
) -> str:
    effective = settings or current_settings()
    failure = configuration_failure_reason(effective)
    if failure:
        raise GeminiTextError(failure, "Gemini text API is not configured.")

    model = str(effective["model"])
    timeout_seconds = float(effective["timeout_seconds"])
    max_output_tokens = int(effective["max_output_tokens"])
    generation_config: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    if response_schema:
        generation_config.update(
            {
                "responseMimeType": "application/json",
                "responseJsonSchema": response_schema,
            }
        )
    request_body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    url = f"{API_BASE_URL}/models/{quote(model, safe='')}:generateContent"
    started = perf_counter()
    logger.info(
        "gemini_text_request provider=%s model=%s use_case=%s timeout_seconds=%s max_output_tokens=%s",
        PROVIDER,
        model,
        use_case,
        timeout_seconds,
        max_output_tokens,
    )
    try:
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": str(effective["api_key"]),
            },
            json=request_body,
            timeout=timeout_seconds,
        )
    except requests.Timeout as exc:
        logger.warning(
            "gemini_text_response provider=%s model=%s use_case=%s latency_ms=%.1f timeout=true parse_success=false schema_success=false failure_reason=timeout model_response=None",
            PROVIDER,
            model,
            use_case,
            (perf_counter() - started) * 1000,
        )
        raise GeminiTextError("timeout", "Gemini text request timed out.") from exc
    except requests.RequestException as exc:
        logger.warning(
            "gemini_text_response provider=%s model=%s use_case=%s latency_ms=%.1f timeout=false parse_success=false schema_success=false failure_reason=request_error error_type=%s model_response=None",
            PROVIDER,
            model,
            use_case,
            (perf_counter() - started) * 1000,
            type(exc).__name__,
        )
        raise GeminiTextError("request_error", "Gemini text request failed.") from exc

    if response.status_code == 429:
        failure_reason = "rate_limit"
    elif response.status_code in {408, 504}:
        failure_reason = "timeout"
    elif not response.ok:
        failure_reason = "api_error"
    else:
        failure_reason = None
    if failure_reason:
        logger.warning(
            "gemini_text_response provider=%s model=%s use_case=%s latency_ms=%.1f timeout=%s parse_success=false schema_success=false failure_reason=%s status_code=%s model_response=%s",
            PROVIDER,
            model,
            use_case,
            (perf_counter() - started) * 1000,
            failure_reason == "timeout",
            failure_reason,
            response.status_code,
            _response_preview(response.text),
        )
        raise GeminiTextError(failure_reason, f"Gemini API returned HTTP {response.status_code}.")

    try:
        payload = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        logger.warning(
            "gemini_text_response provider=%s model=%s use_case=%s latency_ms=%.1f timeout=false parse_success=false schema_success=false failure_reason=malformed_response model_response=%s",
            PROVIDER,
            model,
            use_case,
            (perf_counter() - started) * 1000,
            _response_preview(response.text),
        )
        raise GeminiTextError("malformed_response", "Gemini returned invalid response JSON.") from exc
    try:
        raw_text = _candidate_text(payload)
    except GeminiTextError as exc:
        logger.warning(
            "gemini_text_response provider=%s model=%s use_case=%s latency_ms=%.1f timeout=false parse_success=false schema_success=false failure_reason=%s model_response=%s",
            PROVIDER,
            model,
            use_case,
            (perf_counter() - started) * 1000,
            exc.failure_reason,
            _response_preview(payload),
        )
        raise
    parse_success: bool | None = None
    schema_success: bool | None = None
    if response_schema:
        try:
            parsed = json.loads(raw_text)
            parse_success = True
            schema_success = _schema_matches(parsed, response_schema)
        except json.JSONDecodeError:
            parse_success = False
            schema_success = False
    failure_reason = None
    if parse_success is False:
        failure_reason = "invalid_json"
    elif schema_success is False:
        failure_reason = "schema_validation_failed"
    logger.info(
        "gemini_text_response provider=%s model=%s use_case=%s latency_ms=%.1f timeout=false parse_success=%s schema_success=%s failure_reason=%s model_response=%s",
        PROVIDER,
        model,
        use_case,
        (perf_counter() - started) * 1000,
        parse_success,
        schema_success,
        failure_reason,
        _response_preview(raw_text),
    )
    return raw_text
