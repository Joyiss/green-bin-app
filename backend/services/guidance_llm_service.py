from __future__ import annotations

import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
logger = logging.getLogger(__name__)

DEFAULT_GUIDANCE_LLM_MODEL = "llama-3.3-70b-versatile"
DEFAULT_GUIDANCE_LLM_TIMEOUT_SECONDS = 10.0
MAX_LLM_SOURCE_CHUNKS = 3
MAX_SUMMARY_LENGTH = 240
GUIDANCE_PROMPT_VERSION = "groq_basic_guidance_v2"

GENERAL_SAFE_ALLOWED_ACTIONS = {"donate/reuse", "check local guidance"}
_SOURCE_NAMES = (
    "epa",
    "r2",
    "e-stewards",
    "earth911",
    "paintcare",
    "call2recycle",
    "calrecycle",
    "dsny",
    "according to",
    "federal guidelines",
)
_ABSOLUTE_CLAIMS = (
    "accepted everywhere",
    "recyclable everywhere",
    "illegal nationwide",
)
_DANGEROUS_PATTERNS = (
    r"\bpry\s+open\b",
    r"\bforce\s+open\b",
    r"\bdismantl(?:e|ing)\b",
    r"\bdisassembl(?:e|ing)\b",
    r"\bremove\s+(?:the\s+)?built[- ]in\s+batter(?:y|ies)\b",
    r"\bcut\s+(?:the\s+)?batter(?:y|ies)\b",
    r"\bpunctur(?:e|ing)\b",
    r"\bburn(?:ing)?\b",
    r"\bpour(?:ing)?\s+(?:it\s+|this\s+|the\s+contents?\s+)?down\s+(?:the\s+)?drain\b",
)
_SAFE_NEGATION_PREFIX = re.compile(
    r"^\s*(?:do\s+not|don't|don’t|never|avoid)\b", re.IGNORECASE
)


def _env_truthy(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() in {"1", "true", "yes", "on"}


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        normalized = _normalize_optional_string(item)
        if normalized:
            result.append(normalized)
    return result


def _normalize_disposal_action(value: Any) -> str | None:
    normalized = _normalize_optional_string(value)
    if normalized is None:
        return None
    action = normalized.casefold()
    action = action.replace("drop off", "drop-off")
    action = action.replace("recycling", "recycle")
    action = action.replace("composting", "compost")
    action = action.replace("landfill", "trash")
    action = re.sub(r"\s*/\s*", "/", action)
    action = re.sub(r"\s+", " ", action).strip()
    if action in {"", "null", "none", "unknown"}:
        return None
    if action in {"reuse/donate", "donate / reuse", "reuse / donate"}:
        return "donate/reuse"
    return action


def _parse_guidance_llm_timeout() -> float:
    raw = _normalize_optional_string(os.getenv("GUIDANCE_LLM_TIMEOUT"))
    if raw is None:
        return DEFAULT_GUIDANCE_LLM_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        return DEFAULT_GUIDANCE_LLM_TIMEOUT_SECONDS
    if not math.isfinite(timeout) or timeout <= 0:
        return DEFAULT_GUIDANCE_LLM_TIMEOUT_SECONDS
    return timeout


def _current_llm_settings() -> dict[str, Any]:
    provider = _normalize_optional_string(os.getenv("GUIDANCE_LLM_PROVIDER"))
    return {
        "enabled": _env_truthy(os.getenv("ENABLE_LLM_GUIDANCE")),
        "provider": provider.casefold() if provider else None,
        "model": _normalize_optional_string(os.getenv("GUIDANCE_LLM_MODEL"))
        or DEFAULT_GUIDANCE_LLM_MODEL,
        "api_key": _normalize_optional_string(os.getenv("GROQ_API_KEY")),
        "timeout_seconds": _parse_guidance_llm_timeout(),
    }


def llm_skip_reason(settings: dict[str, Any] | None = None) -> str | None:
    effective = settings or _current_llm_settings()
    if not effective.get("enabled"):
        return "ENABLE_LLM_GUIDANCE_false"
    if effective.get("provider") != "groq":
        return "provider_not_groq"
    if not effective.get("api_key"):
        return "missing_GROQ_API_KEY"
    return None


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    if not isinstance(raw_text, str):
        raise ValueError("Model response content must be a string.")
    start = raw_text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in model response.")
    decoder = json.JSONDecoder()
    parsed, _ = decoder.raw_decode(raw_text[start:])
    if not isinstance(parsed, dict):
        raise ValueError("Parsed model response JSON is not an object.")
    return parsed


def _extract_groq_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ValueError("Groq response payload must be an object.")
    choices = payload.get("choices")
    if not isinstance(choices, list):
        raise ValueError("Groq response did not contain choices.")
    for choice in choices:
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            continue
        content = choice["message"].get("content")
        text = _normalize_optional_string(content)
        if text:
            return text
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = _normalize_optional_string(part.get("text"))
                    if text:
                        return text
    raise ValueError("Groq response did not contain message content.")


def _safe_endpoint_path(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return endpoint.split("?", 1)[0]


def _sanitize_response_preview(value: Any, *, max_length: int = 500) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        except (TypeError, ValueError):
            value = str(value)
    preview = re.sub(r"\s+", " ", value).strip()
    if not preview:
        return None
    return preview if len(preview) <= max_length else preview[:max_length].rstrip() + "..."


def _groq_request(prompt: str, *, settings: dict[str, Any], mode: str) -> str:
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    try:
        response = requests.post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings['api_key']}",
            },
            json={
                "model": settings["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=settings["timeout_seconds"],
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        body = _sanitize_response_preview(getattr(getattr(exc, "response", None), "text", None))
        logger.info(
            "LLM guidance request failed. provider=%s mode=%s error_class=%s status_code=%s body_preview=%s model=%s endpoint=%s",
            settings.get("provider"), mode, exc.__class__.__name__, status, body,
            settings.get("model"), _safe_endpoint_path(endpoint),
        )
        raise
    return _extract_groq_text(response.json())


def _strip_chunk_for_llm(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _normalize_optional_string(chunk.get("id")),
        "title": _normalize_optional_string(chunk.get("title")),
        "section": _normalize_optional_string(chunk.get("section")),
        "source_name": _normalize_optional_string(chunk.get("source_name")),
        "source_url": _normalize_optional_string(chunk.get("source_url")),
        "location_scope": _normalize_optional_string(chunk.get("location_scope")),
        "generalizable": bool(chunk.get("generalizable")),
        "requires_location_check": bool(chunk.get("requires_location_check")),
        "content": _normalize_optional_string(chunk.get("content")),
        "source_excerpt": _normalize_optional_string(chunk.get("source_excerpt")),
        "source_claim": _normalize_optional_string(chunk.get("source_claim")),
        "decision_signals": chunk.get("decision_signals")
        if isinstance(chunk.get("decision_signals"), dict)
        else {},
        "warnings": _normalize_string_list(chunk.get("warnings")),
        "limitations": _normalize_string_list(chunk.get("limitations")),
        "disposal_actions_supported": _normalize_string_list(
            chunk.get("disposal_actions_supported")
        ),
    }


def _chunk_ids(chunks: list[dict[str, Any]]) -> list[str]:
    return [
        chunk_id
        for chunk in chunks
        if (chunk_id := _normalize_optional_string(chunk.get("id")))
    ]


def _normalized_duplicate_key(step: str) -> str:
    text = step.casefold().strip()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _dangerous_instruction(text: str) -> str | None:
    # Negation is local to one sentence/semicolon clause, so "Do not wait; burn it"
    # cannot be accidentally accepted.
    clauses = re.split(r"[.;!?\n]+", text)
    for clause in clauses:
        if not clause.strip():
            continue
        for pattern in _DANGEROUS_PATTERNS:
            match = re.search(pattern, clause, flags=re.IGNORECASE)
            if match is None:
                continue
            prefix = clause[: match.start()]
            if _SAFE_NEGATION_PREFIX.match(prefix):
                continue
            return match.group(0).casefold()
    return None


def _chunks_support_hazardous(chunks: list[dict[str, Any]]) -> bool:
    for chunk in chunks:
        signals = chunk.get("decision_signals") or {}
        if signals.get("requires_household_hazardous_waste") is True:
            return True
        evidence = " ".join(
            str(chunk.get(field) or "")
            for field in ("source_claim", "content", "source_excerpt")
        ).casefold()
        if "hazardous" in evidence or "toxic" in evidence:
            return True
    return False


def _chunks_support_curbside(chunks: list[dict[str, Any]]) -> bool:
    for chunk in chunks:
        signals = chunk.get("decision_signals") or {}
        if signals.get("supports_recycling") is not True or signals.get("avoid_curbside_recycling") is True:
            continue
        evidence = " ".join(
            str(chunk.get(field) or "")
            for field in ("source_claim", "content", "source_excerpt")
        ).casefold()
        if "curbside" in evidence or "recycling bin" in evidence:
            return True
    return False


def _has_positive_curbside_claim(text: str) -> bool:
    patterns = (
        r"\bcurbside\s+recyclable\b",
        r"\brecycl(?:e|able)\b[^.;!?\n]{0,80}\bcurbside\b",
        r"\bput\s+it\s+in\s+(?:the\s+)?curbside\s+recycling\b",
    )
    for clause in re.split(r"[.;!?\n]+", text):
        if _SAFE_NEGATION_PREFIX.match(clause):
            continue
        if any(re.search(pattern, clause, flags=re.IGNORECASE) for pattern in patterns):
            return True
    return False


def validate_guidance_basic(
    payload: Any,
    context: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(payload, dict):
        return None, ["invalid_json"]

    errors: list[str] = []
    summary = _normalize_optional_string(payload.get("summary"))
    if summary is None:
        errors.append("missing_summary")
    elif len(summary) > MAX_SUMMARY_LENGTH:
        errors.append("summary_too_long")

    raw_steps = payload.get("steps")
    steps: list[str] = []
    if not isinstance(raw_steps, list):
        errors.append("invalid_steps")
    else:
        for raw_step in raw_steps:
            if not isinstance(raw_step, str) or not raw_step.strip():
                errors.append("invalid_steps")
                break
            steps.append(raw_step.strip())
        if not errors and not 2 <= len(steps) <= 4:
            errors.append("invalid_steps_count")

    if steps:
        keys = [_normalized_duplicate_key(step) for step in steps]
        if len(keys) != len(set(keys)):
            errors.append("duplicate_steps")

    allowed_actions = {
        action
        for value in context.get("allowed_disposal_actions", set())
        if (action := _normalize_disposal_action(value)) is not None
    }
    disposal_action = _normalize_disposal_action(payload.get("disposal_action"))
    if disposal_action is None or disposal_action not in allowed_actions:
        errors.append("unsupported_disposal_action")

    main_text = " ".join([summary or "", *steps]).casefold()
    for source_name in _SOURCE_NAMES:
        if re.search(rf"(?<![a-z0-9]){re.escape(source_name)}(?![a-z0-9])", main_text):
            errors.append(f"source_name_in_main_guidance:{source_name}")
            break

    all_user_text = [summary or "", *steps, *_normalize_string_list(payload.get("warnings"))]
    for text in all_user_text:
        dangerous = _dangerous_instruction(text)
        if dangerous:
            errors.append(f"dangerous_instruction:{dangerous}")
            break

    for claim in _ABSOLUTE_CLAIMS:
        if claim in main_text:
            errors.append(f"unsupported_strong_claim:{claim}")
            break

    chunks = [chunk for chunk in context.get("retrieved_chunks", []) if isinstance(chunk, dict)]
    if re.search(r"\b(?:is|are|as)\s+hazardous\b|\bhazardous\s+(?:waste|material)\b", main_text):
        if not _chunks_support_hazardous(chunks):
            errors.append("unsupported_hazardous_claim")
    if _has_positive_curbside_claim(main_text):
        if not _chunks_support_curbside(chunks):
            errors.append("unsupported_curbside_claim")

    if errors:
        return None, list(dict.fromkeys(errors))

    known_chunk_ids = set(_chunk_ids(chunks))
    sources_used = [
        source_id
        for source_id in _normalize_string_list(payload.get("sources_used"))
        if source_id in known_chunk_ids
    ]
    return {
        "disposal_action": disposal_action,
        "summary": summary,
        "steps": steps,
        "warnings": _normalize_string_list(payload.get("warnings")),
        "confidence": _normalize_optional_string(payload.get("confidence")) or "medium",
        "sources_used": sources_used,
    }, []


def validate_mobile_guidance_output(
    payload: Any,
    *,
    mode: str,
    allowed_actions: set[str],
    chunks: list[dict[str, Any]] | None = None,
    **_: Any,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Compatibility wrapper for callers while the public helper becomes basic."""
    validated, errors = validate_guidance_basic(
        payload,
        {
            "mode": mode,
            "allowed_disposal_actions": allowed_actions,
            "retrieved_chunks": chunks or [],
        },
    )
    if validated is not None:
        validated["material_code"] = None
        validated["impact_level"] = (
            "Low Confidence Guidance" if mode == "general_safe_fallback" else None
        )
    return validated, errors


def _source_grounded_mobile_policy() -> str:
    return (
        "You are Green Bin's disposal guidance assistant.\n"
        "Your job is to give clear next steps for disposing of the exact scanned item.\n"
        "Use RAG chunks to ground disposal action and safety limits. Use recognized_item, "
        "material, broad_category, visual_evidence, and candidates to make advice specific.\n"
        "Do not write category boilerplate or give the same advice for every electronic item.\n"
        "Do not over-compress steps into two- or three-word fragments. Each step should tell the user what to do next.\n"
        "Write one short but useful summary and three practical, non-duplicate steps when possible. "
        "Each step should be one clear action and specific to the item when possible.\n"
        "The disposal_action must be in allowed_disposal_actions and supported by retrieved_chunks. "
        "Do not invent local rules, curbside acceptance, hazardous status, or illegal-disposal claims.\n"
        "Never instruct users to pry open, force open, dismantle, disassemble, remove built-in batteries, "
        "cut or puncture batteries, burn items, or pour contents down a drain. Safe warnings such as "
        "'Do not disassemble the laptop' are allowed.\n"
        "Keep source names and excerpts out of summary and steps; put evidence in sources_used or metadata.\n"
        "These examples show the desired level of usefulness. Do not copy them blindly. Adapt the advice to the actual item context.\n"
        "Examples:\n"
        "- Wired mouse: keep the cord attached; keep it out of curbside recycling; take it to electronics drop-off.\n"
        "- Wireless earbuds: keep earbuds and case together; do not remove built-in batteries; use electronics or battery drop-off.\n"
        "- Laptop: back up and erase data; remove only removable batteries; use electronics recycling.\n"
        "- Drum: wipe the shell; keep hardware attached; donate it if playable.\n"
        "Return exactly one JSON object with this shape: "
        '{"disposal_action":"","summary":"","steps":[],"warnings":[],"confidence":"","sources_used":[]}.\n'
    )


def _fallback_mobile_policy() -> str:
    return (
        _source_grounded_mobile_policy()
        + "No retrieved chunks are available. Use only the supplied conservative allowed_disposal_actions "
        "and safe item context. Prefer reuse or donation for clean, usable items. Keep confidence low. "
        "Do not claim curbside recyclability or hazardous status.\n"
    )


def _build_source_grounded_prompt(
    *,
    recognized_item: str | None,
    normalized_item_label: str | None,
    material: str | None,
    broad_category: str | None,
    condition_flags: list[str],
    special_flags: list[str],
    visual_evidence: str | None,
    candidates: list[str],
    location: dict[str, Any] | None,
    chunks: list[dict[str, Any]],
    allowed_disposal_actions: list[str],
) -> str:
    context = {
        "recognized_item": recognized_item,
        "normalized_item_label": normalized_item_label,
        "material": material,
        "broad_category": broad_category,
        "condition_flags": condition_flags,
        "special_flags": special_flags,
        "visual_evidence": visual_evidence,
        "candidates": candidates,
        "location": location,
        "allowed_disposal_actions": allowed_disposal_actions,
        "retrieved_chunks": chunks,
    }
    return _source_grounded_mobile_policy() + "Context:\n" + json.dumps(context, ensure_ascii=True)


def _build_general_safe_prompt(
    *,
    recognized_item: str | None,
    normalized_item_label: str | None,
    material: str | None,
    broad_category: str | None,
    condition_flags: list[str],
    special_flags: list[str],
    visual_evidence: str | None,
    candidates: list[str],
    allowed_actions: set[str],
    low_risk_reason: str | None = None,
    matched_terms: list[str] | None = None,
) -> str:
    context = {
        "recognized_item": recognized_item,
        "normalized_item_label": normalized_item_label,
        "material": material,
        "broad_category": broad_category,
        "condition_flags": condition_flags,
        "special_flags": special_flags,
        "visual_evidence": visual_evidence,
        "candidates": candidates,
        "allowed_disposal_actions": sorted(allowed_actions),
        "low_risk_reason": low_risk_reason,
        "matched_low_risk_terms": list(matched_terms or []),
    }
    return _fallback_mobile_policy() + "Context:\n" + json.dumps(context, ensure_ascii=True)


def _build_repair_prompt(
    *,
    original_prompt: str,
    validation_errors: list[str],
    previous_response: Any,
) -> str:
    return (
        original_prompt
        + "\nThe previous response was invalid. Fix only these API or safety errors and return one JSON object. "
        "Do not rewrite merely for style.\nValidation errors: "
        + json.dumps(validation_errors, ensure_ascii=True)
        + "\nPrevious response: "
        + json.dumps(previous_response, ensure_ascii=True)
    )


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized.casefold() not in seen:
            seen.add(normalized.casefold())
            result.append(normalized)
    return result


def _build_standardized_metadata(
    *, chunks: list[dict[str, Any]], sources_used: list[str], why_this_action: str
) -> dict[str, Any]:
    def collect(field: str) -> list[str]:
        return _dedupe_preserve_order(
            [str(chunk.get(field) or "") for chunk in chunks if chunk.get(field)]
        )

    return {
        "claims_used": collect("source_claim"),
        "source_excerpts": collect("source_excerpt"),
        "source_names": collect("source_name"),
        "source_urls": collect("source_url"),
        "limitations": _dedupe_preserve_order(
            [limit for chunk in chunks for limit in _normalize_string_list(chunk.get("limitations"))]
        ),
        "why_this_action": why_this_action,
        "retrieved_chunk_ids": _chunk_ids(chunks),
        "sources_used": sources_used,
    }


def _contract_metadata_values(_: Any = None) -> dict[str, Any]:
    """Compatibility helper; the old step-intent contract is intentionally gone."""
    return {"prompt_version": GUIDANCE_PROMPT_VERSION}


def _choose_closest_allowed_action(preferred: list[str], allowed: set[str]) -> str | None:
    normalized = {_normalize_disposal_action(value) for value in allowed}
    normalized.discard(None)
    for value in preferred:
        if value in normalized:
            return value
    return sorted(normalized)[0] if normalized else None


def _item_phrase(recognized_item: str | None) -> str:
    return (_normalize_optional_string(recognized_item) or "item").casefold()


def _source_fallback_content(
    recognized_item: str | None,
    chunks: list[dict[str, Any]],
    allowed_actions: set[str],
) -> tuple[str | None, str, list[str], str]:
    item = _item_phrase(recognized_item)
    action = _choose_closest_allowed_action(
        ["drop-off", "household hazardous waste", "recycle", "compost", "donate/reuse", "trash", "check local guidance"],
        allowed_actions,
    )
    primary = chunks[0] if chunks else {}
    claim = _normalize_optional_string(primary.get("source_claim"))
    limitations = _normalize_string_list(primary.get("limitations"))
    summary = f"Use the supported {action or 'disposal'} option for the {item}."
    steps = [
        f"Keep the {item} intact while preparing it.",
        f"Use the supported {action or 'disposal'} route for this item.",
    ]
    if limitations:
        steps.append(limitations[0].rstrip(".") + ".")
    elif claim:
        steps.append("Follow the retrieved source limits shown in More Details.")
    return action, summary, steps[:4], "The action is limited to retrieved source support."


def _general_fallback_content(
    recognized_item: str | None,
    material: str | None,
    allowed_actions: set[str],
) -> tuple[str | None, str, list[str], str]:
    item = _item_phrase(recognized_item)
    action = _choose_closest_allowed_action(["donate/reuse", "check local guidance"], allowed_actions)
    if action == "donate/reuse":
        return (
            action,
            f"Reuse or donate the {item} if it is clean and usable.",
            [f"Clean the {item} before offering it for reuse.", f"Donate the {item} if it remains usable."],
            "The low-risk fallback favors reuse without making disposal claims.",
        )
    material_text = (_normalize_optional_string(material) or "material").casefold()
    return (
        action,
        f"Check local options for this {item} before disposal.",
        [f"Keep the {item} out of curbside recycling unless accepted.", f"Check options for {material_text} items before disposal."],
        "The low-risk fallback avoids unsupported recycling claims.",
    )


def _build_deterministic_source_grounded_guidance(
    *, recognized_item: str | None, chunks: list[dict[str, Any]], allowed_actions: set[str],
    failure_reason: str, settings: dict[str, Any], **_: Any,
) -> dict[str, Any]:
    action, summary, steps, why = _source_fallback_content(recognized_item, chunks, allowed_actions)
    metadata = _build_standardized_metadata(
        chunks=chunks, sources_used=_chunk_ids(chunks), why_this_action=why
    )
    return {
        "disposal_action": action,
        "material_code": None,
        "impact_level": "Check Local Guidance"
        if any(chunk.get("requires_location_check") for chunk in chunks)
        else "Source-Grounded Guidance",
        "summary": summary,
        "steps": steps,
        "guidance_source": "json_rag_llm_generated",
        "guidance_metadata": {
            "llm_provider": "groq",
            "llm_model": settings["model"],
            "llm_mode": "source_grounded",
            "confidence": "medium",
            "llm_fallback_reason": failure_reason,
            "deterministic_fallback_used": True,
            "final_generation_path": "deterministic_fallback",
            **_contract_metadata_values(),
            **metadata,
        },
    }


def _build_deterministic_general_safe_guidance(
    *, recognized_item: str | None, material: str | None, allowed_actions: set[str],
    low_risk_reason: str | None, matched_terms: list[str], failure_reason: str,
    settings: dict[str, Any], **_: Any,
) -> dict[str, Any]:
    action, summary, steps, why = _general_fallback_content(recognized_item, material, allowed_actions)
    return {
        "disposal_action": action,
        "material_code": None,
        "impact_level": "Low Confidence Guidance",
        "summary": summary,
        "steps": steps,
        "guidance_source": "llm_general_fallback",
        "warnings": ["Do not place this item in curbside recycling unless your local program accepts it."],
        "guidance_metadata": {
            "llm_provider": "groq",
            "llm_model": settings["model"],
            "llm_mode": "general_safe_fallback",
            "confidence": "low",
            "llm_fallback_reason": failure_reason,
            "deterministic_fallback_used": True,
            "final_generation_path": "deterministic_fallback",
            "low_risk_reason": low_risk_reason,
            "matched_terms": matched_terms,
            "claims_used": [], "source_excerpts": [], "source_names": [],
            "source_urls": [], "limitations": [], "retrieved_chunk_ids": [],
            "sources_used": [], "why_this_action": why,
            **_contract_metadata_values(),
        },
    }


def _build_source_guidance(
    validated: dict[str, Any], chunks: list[dict[str, Any]], settings: dict[str, Any],
    *, repaired: bool,
) -> dict[str, Any]:
    used_ids = validated["sources_used"] or _chunk_ids(chunks)
    used_chunks = [chunk for chunk in chunks if chunk.get("id") in used_ids]
    guidance = {
        "disposal_action": validated["disposal_action"],
        "material_code": None,
        "impact_level": "Check Local Guidance"
        if any(chunk.get("requires_location_check") for chunk in used_chunks)
        else "Source-Grounded Guidance",
        "summary": validated["summary"],
        "steps": validated["steps"],
        "guidance_source": "json_rag_llm_generated",
        "guidance_metadata": {
            "llm_provider": "groq", "llm_model": settings["model"],
            "llm_mode": "source_grounded", "confidence": validated["confidence"],
            "final_generation_path": "repaired_llm" if repaired else "original_llm",
            **_contract_metadata_values(),
            **_build_standardized_metadata(
                chunks=used_chunks, sources_used=used_ids,
                why_this_action="The selected action matches retrieved source evidence.",
            ),
        },
    }
    if validated["warnings"]:
        guidance["warnings"] = validated["warnings"]
    return guidance


def _build_general_guidance(
    validated: dict[str, Any], settings: dict[str, Any], *, repaired: bool,
    low_risk_reason: str | None, matched_terms: list[str],
) -> dict[str, Any]:
    guidance = {
        "disposal_action": validated["disposal_action"], "material_code": None,
        "impact_level": "Low Confidence Guidance", "summary": validated["summary"],
        "steps": validated["steps"], "guidance_source": "llm_general_fallback",
        "guidance_metadata": {
            "llm_provider": "groq", "llm_model": settings["model"],
            "llm_mode": "general_safe_fallback", "confidence": "low", "sources_used": [],
            "final_generation_path": "repaired_llm" if repaired else "original_llm",
            "low_risk_reason": low_risk_reason, "matched_terms": matched_terms,
            "claims_used": [], "source_excerpts": [], "source_names": [], "source_urls": [],
            "limitations": [], "retrieved_chunk_ids": [],
            "why_this_action": "The model used conservative low-risk item context.",
            **_contract_metadata_values(),
        },
    }
    if validated["warnings"]:
        guidance["warnings"] = validated["warnings"]
    return guidance


def _llm_result(*, guidance: dict[str, Any] | None, failure_reason: str | None) -> dict[str, Any]:
    return {"guidance": guidance, "failure_reason": failure_reason}


def _log_deterministic_fallback(
    *, mode: str, item: str | None, original_output: Any, reasons: list[str],
    repair_attempted: bool,
) -> None:
    logger.info(
        "LLM deterministic fallback used. mode=%s item=%s original_llm_output=%s validation_reason=%s repair_attempted=%s deterministic_fallback_used=true",
        mode, item, _sanitize_response_preview(original_output), reasons, repair_attempted,
    )


def _generate_with_retry(
    *, mode: str, prompt: str, settings: dict[str, Any], context: dict[str, Any],
    item: str | None, deterministic_builder: Callable[[str], dict[str, Any]],
    accepted_builder: Callable[[dict[str, Any], bool], dict[str, Any]],
) -> dict[str, Any]:
    original_output: Any = None
    validation_errors: list[str] = []
    current_prompt = prompt
    for attempt in range(2):
        try:
            raw_response = _groq_request(current_prompt, settings=settings, mode=mode)
            if attempt == 0:
                original_output = raw_response
            parsed = _extract_json_object(raw_response)
        except requests.RequestException as exc:
            reason = "timeout" if isinstance(exc, requests.Timeout) else "request_error"
            fallback = deterministic_builder(reason)
            _log_deterministic_fallback(
                mode=mode, item=item, original_output=original_output,
                reasons=[reason], repair_attempted=attempt > 0,
            )
            return _llm_result(guidance=fallback, failure_reason=None)
        except (ValueError, json.JSONDecodeError):
            validation_errors = ["invalid_json"]
            if attempt == 0:
                current_prompt = _build_repair_prompt(
                    original_prompt=prompt,
                    validation_errors=validation_errors,
                    previous_response=raw_response,
                )
                continue
            fallback = deterministic_builder("invalid_json")
            _log_deterministic_fallback(
                mode=mode, item=item, original_output=original_output,
                reasons=validation_errors, repair_attempted=True,
            )
            return _llm_result(guidance=fallback, failure_reason=None)

        validated, validation_errors = validate_guidance_basic(parsed, context)
        if validated is not None:
            logger.info(
                "LLM guidance validation succeeded. mode=%s item=%s disposal_action=%s final_generation_path=%s",
                mode, item, validated["disposal_action"],
                "repaired_llm" if attempt else "original_llm",
            )
            return _llm_result(guidance=accepted_builder(validated, attempt > 0), failure_reason=None)

        logger.info(
            "LLM guidance validation failed. mode=%s item=%s original_llm_output=%s validation_reason=%s repair_attempted=%s deterministic_fallback_used=false",
            mode, item, _sanitize_response_preview(original_output), validation_errors, attempt > 0,
        )
        if attempt == 0:
            current_prompt = _build_repair_prompt(
                original_prompt=prompt, validation_errors=validation_errors,
                previous_response=parsed,
            )
            continue
        fallback = deterministic_builder(validation_errors[0] if validation_errors else "validation_failed")
        _log_deterministic_fallback(
            mode=mode, item=item, original_output=original_output,
            reasons=validation_errors, repair_attempted=True,
        )
        return _llm_result(guidance=fallback, failure_reason=None)
    return _llm_result(guidance=None, failure_reason="validation_failed")


def try_generate_source_grounded_guidance(
    *, recognized_item: str | None, normalized_item_label: str | None, material: str | None,
    broad_category: str | None, condition_flags: list[str] | None,
    special_flags: list[str] | None = None, visual_evidence: str | None = None,
    candidates: list[str] | None = None, location: dict[str, Any] | None,
    retrieval_results: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = _current_llm_settings()
    skip = llm_skip_reason(settings)
    if skip:
        return _llm_result(guidance=None, failure_reason=skip)
    chunks = [
        _strip_chunk_for_llm(result.get("chunk", {}))
        for result in retrieval_results[:MAX_LLM_SOURCE_CHUNKS]
        if isinstance(result.get("chunk"), dict)
    ]
    if not chunks:
        return _llm_result(guidance=None, failure_reason="no_chunks")
    allowed_actions = {
        action for chunk in chunks for value in chunk["disposal_actions_supported"]
        if (action := _normalize_disposal_action(value)) is not None
    }
    prompt = _build_source_grounded_prompt(
        recognized_item=recognized_item, normalized_item_label=normalized_item_label,
        material=material, broad_category=broad_category,
        condition_flags=list(condition_flags or []), special_flags=list(special_flags or []),
        visual_evidence=visual_evidence, candidates=list(candidates or []), location=location,
        chunks=chunks, allowed_disposal_actions=sorted(allowed_actions),
    )
    context = {"allowed_disposal_actions": allowed_actions, "retrieved_chunks": chunks}
    return _generate_with_retry(
        mode="source_grounded", prompt=prompt, settings=settings, context=context,
        item=recognized_item,
        deterministic_builder=lambda reason: _build_deterministic_source_grounded_guidance(
            recognized_item=recognized_item, chunks=chunks, allowed_actions=allowed_actions,
            failure_reason=reason, settings=settings,
        ),
        accepted_builder=lambda validated, repaired: _build_source_guidance(
            validated, chunks, settings, repaired=repaired
        ),
    )


def _general_safe_allowed_actions(
    *, recognized_item: str | None, material: str | None, broad_category: str | None,
    condition_flags: list[str], low_risk_reason: str | None,
) -> set[str]:
    text = " ".join([recognized_item or "", material or "", broad_category or ""]).casefold()
    if low_risk_reason == "allowed_paper_stationery":
        return {"check local guidance"}
    if any(token in text for token in ("drum", "instrument", "mug", "bottle", "backpack", "curtain", "toy")):
        return {"donate/reuse"}
    return set(GENERAL_SAFE_ALLOWED_ACTIONS)


def try_generate_general_safe_guidance(
    *, recognized_item: str | None, normalized_item_label: str | None, material: str | None,
    broad_category: str | None, condition_flags: list[str] | None,
    special_flags: list[str] | None = None, visual_evidence: str | None = None,
    candidates: list[str] | None = None, low_risk_reason: str | None = None,
    matched_terms: list[str] | None = None,
) -> dict[str, Any]:
    settings = _current_llm_settings()
    skip = llm_skip_reason(settings)
    if skip:
        return _llm_result(guidance=None, failure_reason=skip)
    allowed_actions = _general_safe_allowed_actions(
        recognized_item=recognized_item, material=material, broad_category=broad_category,
        condition_flags=list(condition_flags or []), low_risk_reason=low_risk_reason,
    )
    prompt = _build_general_safe_prompt(
        recognized_item=recognized_item, normalized_item_label=normalized_item_label,
        material=material, broad_category=broad_category,
        condition_flags=list(condition_flags or []), special_flags=list(special_flags or []),
        visual_evidence=visual_evidence, candidates=list(candidates or []),
        allowed_actions=allowed_actions, low_risk_reason=low_risk_reason,
        matched_terms=list(matched_terms or []),
    )
    context = {"allowed_disposal_actions": allowed_actions, "retrieved_chunks": []}
    return _generate_with_retry(
        mode="general_safe_fallback", prompt=prompt, settings=settings, context=context,
        item=recognized_item,
        deterministic_builder=lambda reason: _build_deterministic_general_safe_guidance(
            recognized_item=recognized_item, material=material, allowed_actions=allowed_actions,
            low_risk_reason=low_risk_reason, matched_terms=list(matched_terms or []),
            failure_reason=reason, settings=settings,
        ),
        accepted_builder=lambda validated, repaired: _build_general_guidance(
            validated, settings, repaired=repaired, low_risk_reason=low_risk_reason,
            matched_terms=list(matched_terms or []),
        ),
    )
