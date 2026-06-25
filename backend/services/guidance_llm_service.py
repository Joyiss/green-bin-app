from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
logger = logging.getLogger(__name__)

GUIDANCE_LLM_TIMEOUT_SECONDS = 10.0
MAX_LLM_SOURCE_CHUNKS = 3
GENERAL_SAFE_REQUIRED_STEPS = [
    "Reuse or donate the item if it is still usable.",
    "Check local recycling or drop-off options before using them.",
    "If no reuse, recycling, or drop-off option is available, follow local trash guidance.",
]
GENERAL_SAFE_REQUIRED_WARNING = (
    "Do not place this item in curbside recycling unless your local program accepts it."
)
GENERAL_SAFE_ALLOWED_ACTIONS = {
    "donate/reuse",
    "check local guidance",
}
_LOCATION_CHECK_TOKENS = (
    "check local",
    "local",
    "verify",
    "availability",
    "participating",
    "program",
    "drop-off site",
    "facility",
)


def _chunk_ids(chunks: list[dict[str, Any]]) -> list[str]:
    chunk_ids: list[str] = []
    for chunk in chunks:
        chunk_id = _normalize_optional_string(chunk.get("id"))
        if chunk_id:
            chunk_ids.append(chunk_id)
    return chunk_ids


def _env_truthy(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None

    normalized_value = str(value).strip()
    return normalized_value or None


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized_values: list[str] = []
    for item in value:
        normalized_item = _normalize_optional_string(item)
        if normalized_item:
            normalized_values.append(normalized_item)
    return normalized_values


def _normalize_disposal_action(value: Any) -> str | None:
    normalized_value = _normalize_optional_string(value)
    if normalized_value is None:
        return None

    normalized_action = normalized_value.casefold()
    normalized_action = normalized_action.replace("drop off", "drop-off")
    normalized_action = normalized_action.replace("recycling", "recycle")
    normalized_action = normalized_action.replace("composting", "compost")
    normalized_action = normalized_action.replace("landfill", "trash")
    normalized_action = re.sub(r"\s*/\s*", "/", normalized_action)
    normalized_action = re.sub(r"\s+", " ", normalized_action).strip()

    if normalized_action in {"", "null", "none", "unknown"}:
        return None
    if normalized_action in {"reuse/donate", "donate / reuse", "reuse / donate"}:
        return "donate/reuse"

    return normalized_action


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    if not isinstance(raw_text, str):
        raise ValueError("Model response content must be a string.")

    start_index = raw_text.find("{")
    if start_index == -1:
        raise ValueError("No JSON object found in model response.")

    json_text = raw_text[start_index:]
    open_braces = 0
    end_index = None

    for index, character in enumerate(json_text):
        if character == "{":
            open_braces += 1
        elif character == "}":
            open_braces -= 1
            if open_braces == 0:
                end_index = index + 1
                break

    if end_index is None:
        raise ValueError("Incomplete JSON object in model response.")

    parsed = json.loads(json_text[:end_index])
    if not isinstance(parsed, dict):
        raise ValueError("Parsed model response JSON is not an object.")

    return parsed


def _extract_gemini_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Gemini response payload must be an object.")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Gemini response did not contain any candidates.")

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        content = candidate.get("content")
        if not isinstance(content, dict):
            continue

        parts = content.get("parts")
        if not isinstance(parts, list):
            continue

        for part in parts:
            if not isinstance(part, dict):
                continue

            text = _normalize_optional_string(part.get("text"))
            if text:
                return text

    raise ValueError("Gemini response did not contain any text parts.")


def _is_dsny_chunk(chunk: dict[str, Any]) -> bool:
    haystack = " ".join(
        filter(
            None,
            [
                str(chunk.get("id") or ""),
                str(chunk.get("source_name") or ""),
                str(chunk.get("location_scope") or ""),
            ],
        )
    ).casefold()
    return "dsny" in haystack or "new york city" in haystack


def _is_calrecycle_chunk(chunk: dict[str, Any]) -> bool:
    haystack = " ".join(
        filter(
            None,
            [
                str(chunk.get("id") or ""),
                str(chunk.get("source_name") or ""),
                str(chunk.get("location_scope") or ""),
            ],
        )
    ).casefold()
    return "calrecycle" in haystack or "state: california" in haystack


def _strip_chunk_for_llm(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _normalize_optional_string(chunk.get("id")),
        "title": _normalize_optional_string(chunk.get("title")),
        "source_name": _normalize_optional_string(chunk.get("source_name")),
        "source_url": _normalize_optional_string(chunk.get("source_url")),
        "location_scope": _normalize_optional_string(chunk.get("location_scope")),
        "generalizable": bool(chunk.get("generalizable")),
        "requires_location_check": bool(chunk.get("requires_location_check")),
        "content": _normalize_optional_string(chunk.get("content")),
        "warnings": _normalize_string_list(chunk.get("warnings")),
        "limitations": _normalize_string_list(chunk.get("limitations")),
        "disposal_actions_supported": _normalize_string_list(
            chunk.get("disposal_actions_supported")
        ),
    }


def _current_llm_settings() -> dict[str, Any]:
    provider = _normalize_optional_string(os.getenv("GUIDANCE_LLM_PROVIDER"))
    model = _normalize_optional_string(os.getenv("GUIDANCE_LLM_MODEL"))
    api_key = _normalize_optional_string(os.getenv("GEMINI_API_KEY"))
    enabled = _env_truthy(os.getenv("ENABLE_LLM_GUIDANCE"))

    return {
        "enabled": enabled,
        "provider": provider.casefold() if provider else None,
        "model": model,
        "api_key": api_key,
    }


def llm_skip_reason(settings: dict[str, Any] | None = None) -> str | None:
    effective_settings = settings or _current_llm_settings()

    if not effective_settings.get("enabled"):
        return "ENABLE_LLM_GUIDANCE_false"
    if effective_settings.get("provider") != "gemini":
        return "provider_not_gemini"
    if not effective_settings.get("model"):
        return "missing_GUIDANCE_LLM_MODEL"
    if not effective_settings.get("api_key"):
        return "missing_GEMINI_API_KEY"

    return None


def _gemini_is_enabled(settings: dict[str, Any]) -> bool:
    return llm_skip_reason(settings) is None


def _sanitize_response_preview(value: Any, *, max_length: int = 300) -> str | None:
    if value is None:
        return None

    preview = str(value)
    preview = preview.replace("\r", " ").replace("\n", " ").strip()
    preview = re.sub(r"\s+", " ", preview)
    if not preview:
        return None

    if len(preview) > max_length:
        preview = preview[:max_length].rstrip() + "..."

    return preview


def _safe_endpoint_path(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return endpoint.split("?", 1)[0]


def _top_level_keys(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    return sorted(str(key) for key in payload.keys())


def _payload_preview(payload: Any) -> str | None:
    if payload is None:
        return None

    try:
        serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    except (TypeError, ValueError):
        serialized = str(payload)

    return _sanitize_response_preview(serialized)


def _log_validation_failure(
    *,
    mode: str,
    reason: str | None,
    payload: dict[str, Any] | None,
) -> None:
    logger.info(
        "Gemini guidance validation failed. mode=%s reason=%s parsed_keys=%s response_preview=%s",
        mode,
        reason,
        _top_level_keys(payload),
        _payload_preview(payload),
    )


def _log_gemini_request_exception(
    exc: requests.RequestException,
    *,
    settings: dict[str, Any],
    mode: str,
    endpoint: str,
) -> None:
    status_code = None
    body_preview = None
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        response_text = None
        try:
            response_text = getattr(response, "text", None)
        except Exception:
            response_text = None
        if response_text is None:
            try:
                response_text = response.content.decode("utf-8", errors="replace")
            except Exception:
                response_text = None
        body_preview = _sanitize_response_preview(response_text)

    logger.info(
        "Gemini guidance request failed. mode=%s reason=%s error_class=%s status_code=%s body_preview=%s model=%s endpoint=%s",
        mode,
        "request_error",
        exc.__class__.__name__,
        status_code,
        body_preview,
        settings.get("model"),
        _safe_endpoint_path(endpoint),
    )


def _gemini_request(prompt: str, *, settings: dict[str, Any], mode: str) -> str:
    model = settings["model"]
    api_key = settings["api_key"]
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=GUIDANCE_LLM_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        _log_gemini_request_exception(
            exc,
            settings=settings,
            mode=mode,
            endpoint=endpoint,
        )
        raise

    if response.status_code >= 400:
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            _log_gemini_request_exception(
                exc,
                settings=settings,
                mode=mode,
                endpoint=endpoint,
            )
            raise

    response.raise_for_status()
    return _extract_gemini_text(response.json())


def _text_contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    normalized_text = text.casefold()
    return any(token in normalized_text for token in tokens)


def _build_source_grounded_prompt(
    *,
    recognized_item: str | None,
    normalized_item_label: str | None,
    material: str | None,
    broad_category: str | None,
    condition_flags: list[str],
    location: dict[str, Any] | None,
    chunks: list[dict[str, Any]],
    allowed_disposal_actions: list[str],
) -> str:
    prompt_payload = {
        "recognized_item": recognized_item,
        "normalized_item_label": normalized_item_label,
        "material": material,
        "broad_category": broad_category,
        "condition_flags": condition_flags,
        "location": location,
        "allowed_disposal_actions": allowed_disposal_actions,
        "retrieved_chunks": chunks,
        "required_output_schema": {
            "disposal_action": "string or null",
            "material_code": "string or null",
            "impact_level": "string or null",
            "summary": "string",
            "steps": ["string"],
            "warnings": ["string"],
            "confidence": "string",
            "sources_used": ["chunk_id"],
        },
    }

    return (
        "You are generating disposal guidance for a mobile app.\n"
        "Use only the retrieved source chunks below. Do not use outside knowledge.\n"
        "Do not invent disposal instructions, local rules, or source claims.\n"
        "Preserve warnings, limitations, and requires_location_check caveats.\n"
        "Do not treat DSNY or CalRecycle guidance as national.\n"
        "For PaintCare, preserve program and location availability caveats.\n"
        "For Earth911, preserve local facility verification caveats.\n"
        "Only use a disposal_action that is explicitly supported by the chunks.\n"
        "Return exactly one JSON object and nothing else.\n\n"
        f"{json.dumps(prompt_payload, ensure_ascii=True)}"
    )


def _build_general_safe_prompt(
    *,
    recognized_item: str | None,
    normalized_item_label: str | None,
    material: str | None,
    broad_category: str | None,
    condition_flags: list[str],
    low_risk_reason: str | None = None,
    matched_terms: list[str] | None = None,
    repair_reason: str | None = None,
    previous_response: dict[str, Any] | None = None,
) -> str:
    prompt_payload = {
        "recognized_item": recognized_item,
        "normalized_item_label": normalized_item_label,
        "material": material,
        "broad_category": broad_category,
        "condition_flags": condition_flags,
        "low_risk_reason": low_risk_reason,
        "matched_low_risk_terms": list(matched_terms or []),
        "required_output_schema": {
            "disposal_action": '"donate/reuse" | "check local guidance" | null',
            "material_code": "string or null",
            "impact_level": "Low Confidence Guidance",
            "summary": "One short item-specific conservative sentence.",
            "steps": ["string", "string", "string"],
            "warnings": ["string"],
            "confidence": "low",
            "sources_used": [],
        },
    }
    if repair_reason:
        prompt_payload["repair_reason"] = repair_reason
    if isinstance(previous_response, dict):
        prompt_payload["previous_invalid_response"] = previous_response

    return (
        "You are generating a conservative low-risk disposal fallback for a mobile app.\n"
        "This item has no trusted retrieved source chunks.\n"
        "Tailor the guidance to the recognized item, material, and broad category.\n"
        "Give practical advice that fits the object and avoid identical wording across items.\n"
        "Prefer reuse, donation, or repair when appropriate.\n"
        "Mention local recycling or drop-off checks only when relevant.\n"
        "Use local trash guidance only as the final fallback.\n"
        "Return exactly one JSON object and nothing else.\n"
        "Include every required key.\n"
        "summary must be a non-empty string.\n"
        "steps must contain 2 to 4 non-empty strings.\n"
        'disposal_action may only be "donate/reuse", "check local guidance", or null.\n'
        'confidence must be exactly "low".\n'
        "sources_used must be [].\n"
        "Do not claim curbside recycling is accepted.\n"
        "Do not claim composting, hazardous waste rules, or local program availability.\n"
        "Do not say the item is always recyclable, always accepted, or always trash.\n"
        "Keep the wording conservative and item-specific.\n"
        "Use this exact target shape and keep the wording conservative:\n"
        '{'
        '"disposal_action": "donate/reuse" | "check local guidance" | null,'
        '"material_code": "string or null",'
        '"impact_level": "Low Confidence Guidance",'
        '"summary": "One short item-specific conservative sentence.",'
        '"steps": ['
        '"Item-specific step 1.",'
        '"Item-specific step 2.",'
        '"Item-specific step 3."'
        '],'
        '"warnings": ["Optional warning."],'
        '"confidence": "low",'
        '"sources_used": []'
        '}\n'
        "Examples of acceptable style:\n"
        "- A pencil can mention using it until finished or donating unused pencils.\n"
        "- Sheet music can mention clean, dry paper and checking local paper recycling rules.\n"
        "- A toy or container can mention reuse first and not assuming curbside acceptance.\n\n"
        f"{json.dumps(prompt_payload, ensure_ascii=True)}"
    )


def _validate_source_grounded_output(
    payload: dict[str, Any],
    *,
    chunks: list[dict[str, Any]],
    allowed_actions: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    summary = _normalize_optional_string(payload.get("summary"))
    if summary is None:
        return None, "missing_summary"

    steps = _normalize_string_list(payload.get("steps"))
    if not steps:
        return None, "missing_steps"

    disposal_action = _normalize_disposal_action(payload.get("disposal_action"))
    if disposal_action is not None and disposal_action not in allowed_actions:
        return None, "unsupported_disposal_action"

    sources_used = _normalize_string_list(payload.get("sources_used"))
    chunk_map = {
        str(chunk.get("id")): chunk
        for chunk in chunks
        if _normalize_optional_string(chunk.get("id"))
    }
    if not sources_used or any(source_id not in chunk_map for source_id in sources_used):
        return None, "invalid_sources_used"

    warnings = _normalize_string_list(payload.get("warnings"))
    combined_text = " ".join([summary, *steps, *warnings]).casefold()
    used_chunks = [chunk_map[source_id] for source_id in sources_used]

    requires_location_check = any(
        bool(chunk.get("requires_location_check")) for chunk in used_chunks
    )
    if requires_location_check and not _text_contains_any(
        combined_text, _LOCATION_CHECK_TOKENS
    ):
        return None, "missing_location_check_caveat"

    if any(
        str(chunk.get("source_name") or "").casefold() == "paintcare"
        for chunk in used_chunks
    ) and not _text_contains_any(
        combined_text,
        ("paintcare", "participating", "program", "availability", "local"),
    ):
        return None, "missing_paintcare_caveat"

    if any(
        "earth911" in str(chunk.get("source_name") or "").casefold()
        for chunk in used_chunks
    ) and not _text_contains_any(
        combined_text,
        ("earth911", "verify", "facility", "accept", "local"),
    ):
        return None, "missing_earth911_caveat"

    if any(_is_dsny_chunk(chunk) for chunk in used_chunks):
        if "national" in combined_text:
            return None, "dsny_treated_as_national"
        if not _text_contains_any(
            combined_text,
            ("new york city", "nyc", "local"),
        ):
            return None, "missing_dsny_scope"

    if any(_is_calrecycle_chunk(chunk) for chunk in used_chunks):
        if "national" in combined_text:
            return None, "calrecycle_treated_as_national"
        if not _text_contains_any(
            combined_text,
            ("california", "local"),
        ):
            return None, "missing_calrecycle_scope"

    normalized_payload = {
        "disposal_action": disposal_action,
        "material_code": _normalize_optional_string(payload.get("material_code")),
        "impact_level": _normalize_optional_string(payload.get("impact_level")),
        "summary": summary,
        "steps": steps,
        "warnings": warnings,
        "confidence": _normalize_optional_string(payload.get("confidence")) or "medium",
        "sources_used": sources_used,
    }
    return normalized_payload, None


def _validate_general_safe_output(
    payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    summary = _normalize_optional_string(payload.get("summary"))
    if summary is None:
        return None, "missing_summary"

    steps = _normalize_string_list(payload.get("steps"))
    if not steps:
        return None, "missing_steps"
    if len(steps) < 2 or len(steps) > 4:
        return None, "invalid_steps_count"

    disposal_action = _normalize_disposal_action(payload.get("disposal_action"))
    if (
        disposal_action is not None
        and disposal_action not in GENERAL_SAFE_ALLOWED_ACTIONS
    ):
        return None, "general_fallback_unsupported_action"

    confidence = _normalize_optional_string(payload.get("confidence"))
    if confidence != "low":
        return None, "general_fallback_requires_low_confidence"

    sources_used = payload.get("sources_used")
    if not isinstance(sources_used, list) or sources_used:
        return None, "general_fallback_requires_empty_sources_used"

    warnings = _normalize_string_list(payload.get("warnings"))
    combined_text = " ".join([summary, *steps, *warnings]).casefold()
    if not _text_contains_any(combined_text, ("reuse", "donate", "usable", "repair")):
        return None, "missing_reuse_context"
    if _text_contains_any(
        combined_text,
        (
            "always recyclable",
            "guaranteed",
            "definitely accepted",
            "place it in your curbside recycling bin",
            "put it in curbside recycling",
            "curbside recycling accepts",
            "accepted in curbside recycling",
            "always accepted",
        ),
    ):
        return None, "overconfident_general_fallback"
    if _text_contains_any(
        combined_text,
        (
            "compost it",
            "place it in compost",
            "put it in compost",
            "compost bin",
            "accepted in compost",
        ),
    ):
        return None, "unsupported_compost_claim"
    if _text_contains_any(
        combined_text,
        (
            "always throw it away",
            "always put it in the trash",
            "always go in trash",
            "always goes in the trash",
        ),
    ):
        return None, "overstated_trash_claim"

    normalized_payload = {
        "disposal_action": disposal_action,
        "material_code": _normalize_optional_string(payload.get("material_code")),
        "impact_level": _normalize_optional_string(payload.get("impact_level"))
        or "Low Confidence Guidance",
        "summary": summary,
        "steps": steps,
        "warnings": warnings,
        "confidence": confidence,
        "sources_used": [],
    }
    return normalized_payload, None


def _llm_result(
    *,
    guidance: dict[str, Any] | None,
    failure_reason: str | None,
) -> dict[str, Any]:
    return {
        "guidance": guidance,
        "failure_reason": failure_reason,
    }


def try_generate_source_grounded_guidance(
    *,
    recognized_item: str | None,
    normalized_item_label: str | None,
    material: str | None,
    broad_category: str | None,
    condition_flags: list[str] | None,
    location: dict[str, Any] | None,
    retrieval_results: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = _current_llm_settings()
    if not _gemini_is_enabled(settings):
        return _llm_result(guidance=None, failure_reason=llm_skip_reason(settings))

    top_results = retrieval_results[:MAX_LLM_SOURCE_CHUNKS]
    stripped_chunks = [
        _strip_chunk_for_llm(result.get("chunk", {}))
        for result in top_results
        if isinstance(result.get("chunk"), dict)
    ]
    if not stripped_chunks:
        return _llm_result(guidance=None, failure_reason="no_chunks")

    allowed_actions = {
        normalized_action
        for chunk in stripped_chunks
        for normalized_action in (
            _normalize_disposal_action(action)
            for action in chunk.get("disposal_actions_supported", [])
        )
        if normalized_action is not None
    }

    prompt = _build_source_grounded_prompt(
        recognized_item=recognized_item,
        normalized_item_label=normalized_item_label,
        material=material,
        broad_category=broad_category,
        condition_flags=list(condition_flags or []),
        location=location,
        chunks=stripped_chunks,
        allowed_disposal_actions=sorted(allowed_actions),
    )

    logger.info(
        "Gemini guidance attempt. provider=%s model=%s mode=%s chunk_ids=%s timeout_seconds=%.1f",
        settings.get("provider"),
        settings.get("model"),
        "source_grounded",
        _chunk_ids(stripped_chunks),
        GUIDANCE_LLM_TIMEOUT_SECONDS,
    )

    try:
        raw_response = _gemini_request(
            prompt,
            settings=settings,
            mode="source_grounded",
        )
        parsed_payload = _extract_json_object(raw_response)
    except requests.Timeout:
        logger.info(
            "Gemini guidance request failed. mode=%s reason=%s",
            "source_grounded",
            "timeout",
        )
        return _llm_result(guidance=None, failure_reason="timeout")
    except requests.RequestException:
        return _llm_result(guidance=None, failure_reason="request_error")
    except (ValueError, json.JSONDecodeError):
        logger.info(
            "Gemini guidance request failed. mode=%s reason=%s",
            "source_grounded",
            "invalid_json",
        )
        return _llm_result(guidance=None, failure_reason="invalid_json")

    validated_payload, validation_error = _validate_source_grounded_output(
        parsed_payload,
        chunks=stripped_chunks,
        allowed_actions=allowed_actions,
    )
    if validated_payload is None:
        _log_validation_failure(
            mode="source_grounded",
            reason=validation_error,
            payload=parsed_payload,
        )
        return _llm_result(guidance=None, failure_reason=validation_error)

    logger.info(
        "Gemini guidance validation succeeded. mode=%s sources_used=%s disposal_action=%s",
        "source_grounded",
        validated_payload["sources_used"],
        validated_payload["disposal_action"],
    )

    guidance = {
        "disposal_action": validated_payload["disposal_action"],
        "material_code": validated_payload["material_code"],
        "impact_level": validated_payload["impact_level"]
        or (
            "Check Local Guidance"
            if any(chunk.get("requires_location_check") for chunk in stripped_chunks)
            else "Source-Grounded Guidance"
        ),
        "summary": validated_payload["summary"],
        "steps": validated_payload["steps"],
        "guidance_source": "json_rag_llm_generated",
        "guidance_metadata": {
            "llm_provider": "gemini",
            "llm_model": settings["model"],
            "llm_mode": "source_grounded",
            "confidence": validated_payload["confidence"],
            "sources_used": validated_payload["sources_used"],
        },
    }
    if validated_payload["warnings"]:
        guidance["warnings"] = validated_payload["warnings"]

    return _llm_result(guidance=guidance, failure_reason=None)


def try_generate_general_safe_guidance(
    *,
    recognized_item: str | None,
    normalized_item_label: str | None,
    material: str | None,
    broad_category: str | None,
    condition_flags: list[str] | None,
    low_risk_reason: str | None = None,
    matched_terms: list[str] | None = None,
) -> dict[str, Any]:
    settings = _current_llm_settings()
    if not _gemini_is_enabled(settings):
        return _llm_result(guidance=None, failure_reason=llm_skip_reason(settings))

    logger.info(
        "Gemini guidance attempt. provider=%s model=%s mode=%s chunk_ids=%s timeout_seconds=%.1f",
        settings.get("provider"),
        settings.get("model"),
        "general_safe_fallback",
        [],
        GUIDANCE_LLM_TIMEOUT_SECONDS,
    )
    repair_reason: str | None = None
    previous_payload: dict[str, Any] | None = None
    last_failure_reason: str | None = None

    for attempt_index in range(2):
        prompt = _build_general_safe_prompt(
            recognized_item=recognized_item,
            normalized_item_label=normalized_item_label,
            material=material,
            broad_category=broad_category,
            condition_flags=list(condition_flags or []),
            low_risk_reason=low_risk_reason,
            matched_terms=list(matched_terms or []),
            repair_reason=repair_reason,
            previous_response=previous_payload,
        )

        try:
            raw_response = _gemini_request(
                prompt,
                settings=settings,
                mode="general_safe_fallback",
            )
            parsed_payload = _extract_json_object(raw_response)
        except requests.Timeout:
            logger.info(
                "Gemini guidance request failed. mode=%s reason=%s",
                "general_safe_fallback",
                "timeout",
            )
            return _llm_result(guidance=None, failure_reason="timeout")
        except requests.RequestException:
            return _llm_result(guidance=None, failure_reason="request_error")
        except (ValueError, json.JSONDecodeError):
            logger.info(
                "Gemini guidance request failed. mode=%s reason=%s",
                "general_safe_fallback",
                "invalid_json",
            )
            return _llm_result(guidance=None, failure_reason="invalid_json")

        validated_payload, validation_error = _validate_general_safe_output(parsed_payload)
        if validated_payload is not None:
            logger.info(
                "Gemini guidance validation succeeded. mode=%s sources_used=%s disposal_action=%s",
                "general_safe_fallback",
                [],
                None,
            )
            guidance = {
                "disposal_action": validated_payload["disposal_action"],
                "material_code": validated_payload["material_code"],
                "impact_level": validated_payload["impact_level"],
                "summary": validated_payload["summary"],
                "steps": validated_payload["steps"],
                "guidance_source": "llm_general_fallback",
                "guidance_metadata": {
                    "llm_provider": "gemini",
                    "llm_model": settings["model"],
                    "llm_mode": "general_safe_fallback",
                    "confidence": "low",
                    "sources_used": [],
                },
            }
            if validated_payload["warnings"]:
                guidance["warnings"] = validated_payload["warnings"]

            return _llm_result(guidance=guidance, failure_reason=None)

        _log_validation_failure(
            mode="general_safe_fallback",
            reason=validation_error,
            payload=parsed_payload,
        )
        last_failure_reason = validation_error
        if attempt_index == 0 and validation_error in {"missing_summary", "missing_steps"}:
            repair_reason = validation_error
            previous_payload = parsed_payload
            logger.info(
                "Gemini guidance repair retry scheduled. mode=%s reason=%s",
                "general_safe_fallback",
                validation_error,
            )
            continue

        return _llm_result(guidance=None, failure_reason=validation_error)
    return _llm_result(guidance=None, failure_reason=last_failure_reason)
