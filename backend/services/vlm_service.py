from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from pathlib import Path
from time import perf_counter

import requests
from dotenv import load_dotenv
from PIL import Image

try:
    from . import request_context
    from ..materials import (
        LABEL_TO_CATEGORY,
        MATERIAL_LABELS,
        build_material_selection_prompt,
        build_multi_object_verification_prompt,
        build_uncertain_fallback_prompt,
        resolve_material_label,
    )
except ImportError:
    from services import request_context
    from materials import (
        LABEL_TO_CATEGORY,
        MATERIAL_LABELS,
        build_material_selection_prompt,
        build_multi_object_verification_prompt,
        build_uncertain_fallback_prompt,
        resolve_material_label,
    )

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
logger = logging.getLogger(__name__)

CONFIDENT_THRESHOLD = 0.20
MARGIN_THRESHOLD = 0.05
DEFAULT_VLM_MAX_TOKENS = 60
OPEN_VLM_MAX_TOKENS = 120

CLOUDFLARE_API_BASE_URL = os.getenv(
    "CLOUDFLARE_API_BASE_URL",
    "https://api.cloudflare.com/client/v4",
).rstrip("/")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_AI_MODEL = os.getenv(
    "CLOUDFLARE_AI_MODEL",
    "@cf/meta/llama-3.2-11b-vision-instruct",
)
VLM_RECOGNITION_MODE = os.getenv("VLM_RECOGNITION_MODE", "constrained")
DETECTION_PROMPT = build_material_selection_prompt()
OPEN_DETECTION_PROMPT = (
    "You are a visual recognition model for a disposal app.\n"
    "Return exactly one JSON object and nothing else.\n"
    "No explanation, markdown, or extra text.\n"
    "Identify the single main visible item.\n"
    "Ignore background objects unless they create genuine ambiguity.\n"
    "Recognition only.\n"
    "Do not provide disposal_action.\n"
    "Do not provide disposal, recycling, compost, or trash instructions.\n"
    "Do not provide steps.\n"
    "Rules:\n"
    '- status must be exactly one of: "confident", "uncertain", "unknown"\n'
    "- raw_item_label and likely_material should each be short plain-language strings, or \"\" if unknown.\n"
    "- likely_material is the physical material hint, such as plastic, metal, glass, ceramic, paper, or fabric.\n"
    "- broad_category is only for disposal/location-search routing and must be exactly one of: automotive, batteries, construction, electronics, garden, glass, hazardous, household, metal, paint, paper, plastic, unknown, unsupported.\n"
    "- Do not use physical material for broad_category when the item routes through a special stream.\n"
    "- Examples: keyboard -> electronics, not plastic; computer mouse -> electronics, not plastic; calculator -> electronics; phone charger -> electronics; battery -> batteries; paint can -> paint or hazardous, not metal; cardboard box -> paper; plastic water bottle -> plastic; glass bottle -> glass.\n"
    "- candidates must contain at most 3 objects.\n"
    "- each candidate object must contain label and confidence.\n"
    "- visual_evidence must be a short string, 12 words or fewer, or \"\" if unknown.\n"
    "Return shape:\n"
    '{"status":"confident","raw_item_label":"keyboard","likely_material":"plastic","broad_category":"electronics","candidates":[{"label":"keyboard","confidence":0.91}],"visual_evidence":"Keys and USB cable visible."}\n'
)
BARCODE_AWARE_PROMPT_SUFFIX = (
    "\n\n"
    "Additional barcode fallback rule:\n"
    "- If the image mainly shows a barcode, nutrition label, ingredients panel, or other packaging text,\n"
    "  and the physical item itself is not visually clear, return unknown instead of guessing from the text.\n"
    "- Do not infer the item label from barcode context alone when the object shape/material is unclear.\n"
)
BARCODE_AWARE_DETECTION_PROMPT = DETECTION_PROMPT + BARCODE_AWARE_PROMPT_SUFFIX
OPEN_BARCODE_AWARE_PROMPT_SUFFIX = (
    "\n\n"
    "Additional barcode fallback rule:\n"
    "- If the image mainly shows a barcode, nutrition label, ingredients panel, or other packaging text,\n"
    "  and the physical item itself is not visually clear, return unknown instead of guessing from the text.\n"
    "- Do not infer the visible item from barcode context alone when the object shape/material is unclear.\n"
)
OPEN_BARCODE_AWARE_DETECTION_PROMPT = (
    OPEN_DETECTION_PROMPT + OPEN_BARCODE_AWARE_PROMPT_SUFFIX
)
DETECTION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["confident", "uncertain", "unknown"],
        },
        "primary_label": {
            "type": "string",
            "enum": [""] + MATERIAL_LABELS,
        },
        "candidate_labels": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": MATERIAL_LABELS,
            },
            "minItems": 0,
            "maxItems": 3,
            "uniqueItems": True,
        },
    },
    "required": ["status", "primary_label", "candidate_labels"],
}
OPEN_DETECTION_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["confident", "uncertain", "unknown"],
        },
        "raw_item_label": {"type": "string"},
        "likely_material": {"type": "string"},
        "broad_category": {
            "type": "string",
            "enum": [
                "automotive",
                "batteries",
                "construction",
                "electronics",
                "garden",
                "glass",
                "hazardous",
                "household",
                "metal",
                "paint",
                "paper",
                "plastic",
                "unknown",
                "unsupported",
            ],
        },
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {
                        "type": ["number", "null"],
                    },
                },
                "required": ["label", "confidence"],
            },
            "minItems": 0,
            "maxItems": 3,
        },
        "visual_evidence": {"type": "string"},
    },
    "required": [
        "status",
        "raw_item_label",
        "likely_material",
        "broad_category",
        "candidates",
        "visual_evidence",
    ],
}
VERIFICATION_RESPONSE_SCHEMA = DETECTION_RESPONSE_SCHEMA
CONFIDENT_SCORE = 1.0
CONFIDENT_SCORE_STEP = 0.08
UNCERTAIN_TOP_SCORE = 0.58
UNCERTAIN_SCORE_STEP = 0.02


def _duration_ms(started: float) -> float:
    return (perf_counter() - started) * 1000


def _log_vlm_timing(stage: str, started: float, **fields: object) -> None:
    request_id = request_context.get_predict_request_id()
    if request_id is not None and "request_id" not in fields:
        fields = {"request_id": request_id, **fields}
    field_text = " ".join(f"{key}={value}" for key, value in fields.items())
    if field_text:
        logger.info(
            "vlm_timing stage=%s duration_ms=%.1f %s",
            stage,
            _duration_ms(started),
            field_text,
        )
        return

    logger.info(
        "vlm_timing stage=%s duration_ms=%.1f",
        stage,
        _duration_ms(started),
    )


def normalize_vlm_recognition_mode(value: object) -> str:
    if not isinstance(value, str):
        return "constrained"

    normalized_value = value.strip().casefold()
    if normalized_value == "open":
        return "open"
    if normalized_value == "constrained":
        return "constrained"

    return "constrained"


def _clean_generated_label(raw_text: str) -> str:
    text = raw_text.replace("\\n", "\n").strip()
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidate = lines[0] if lines else text
    candidate = re.sub(r"^[\-\*\d\.\)\s]+", "", candidate)
    candidate = re.sub(
        r"^(?:label|answer|object|main object)\s*:\s*",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(
        r"^(?:the main object(?: in this image)? is|this is|it is|the object is)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.split(r"[.!?\n]", candidate, maxsplit=1)[0]
    return candidate.strip(" \"'`,:;()[]{}")


def _extract_json_object(raw_text: str) -> dict[str, object]:
    if not isinstance(raw_text, str):
        raise ValueError("Model response content must be a string.")

    start_index = raw_text.find("{")
    if start_index == -1:
        raise ValueError("No JSON object found in model response.")

    json_text = raw_text[start_index:]

    open_braces = 0
    end_index = None

    for i, ch in enumerate(json_text):
        if ch == "{":
            open_braces += 1
        elif ch == "}":
            open_braces -= 1
            if open_braces == 0:
                end_index = i + 1
                break

    if end_index is None:
        raise ValueError("Incomplete JSON object in model response.")

    json_text = json_text[:end_index]

    decoder = json.JSONDecoder()
    parsed, _ = decoder.raw_decode(json_text)

    if not isinstance(parsed, dict):
        raise ValueError("Parsed model response JSON is not an object.")

    return parsed


def _extract_partial_json_fields(raw_text: str) -> dict[str, object]:
    if not isinstance(raw_text, str):
        return {}

    status_match = re.search(
        r'"status"\s*:\s*"(confident|uncertain|unknown)"',
        raw_text,
        flags=re.IGNORECASE,
    )
    primary_match = re.search(
        r'"primary_label"\s*:\s*"([^"]+)"',
        raw_text,
        flags=re.IGNORECASE,
    )
    candidate_block_match = re.search(
        r'"candidate_labels"\s*:\s*\[(.*?)\]',
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    parsed: dict[str, object] = {}

    if status_match:
        parsed["status"] = status_match.group(1).strip().lower()

    if primary_match:
        parsed["primary_label"] = _clean_generated_label(primary_match.group(1))

    if candidate_block_match:
        quoted_candidates = re.findall(r'"([^"]+)"', candidate_block_match.group(1))
        parsed["candidate_labels"] = [
            _clean_generated_label(candidate)
            for candidate in quoted_candidates
            if _clean_generated_label(candidate)
        ]

    return parsed


def _parse_candidate_phrase(raw_text: str) -> list[str]:
    candidate_match = re.search(
        r"candidate labels?\s*(?:could\s+include|could\s+be|are|include|:)\s*(.+?)(?:[.\n]|$)",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not candidate_match:
        return []

    candidate_text = candidate_match.group(1).strip()
    if not candidate_text:
        return []

    quoted_candidates = re.findall(r'"([^"]+)"', candidate_text)
    if quoted_candidates:
        return [_clean_generated_label(candidate) for candidate in quoted_candidates]

    parts = re.split(r",|\band\b", candidate_text, flags=re.IGNORECASE)
    return [_clean_generated_label(part) for part in parts if part.strip()]


def _extract_primary_label_from_text(raw_text: str) -> str:
    primary_patterns = (
        r'primary label\s*(?:could be|would be|is|:)\s*"([^"]+)"',
        r'primary label\s*(?:could be|would be|is|:)\s*([A-Za-z0-9][^.\n,;]+)',
        r'main object\s*(?:could be|would be|is|:)\s*"([^"]+)"',
        r'main object\s*(?:could be|would be|is|:)\s*([A-Za-z0-9][^.\n,;]+)',
    )

    for pattern in primary_patterns:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            return _clean_generated_label(match.group(1))

    return ""


def _extract_status_from_text(raw_text: str) -> str:
    status_patterns = (
        r'status\s*(?:of the image\s*)?(?:would be|is|:)\s*"?(confident|uncertain|unknown)"?',
        r'return status\s+"?(confident|uncertain|unknown)"?',
    )

    for pattern in status_patterns:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().lower()

    return ""


def _parse_detection_result_from_text(raw_output: str) -> dict[str, object]:
    status = _extract_status_from_text(raw_output)
    primary_label = _extract_primary_label_from_text(raw_output)
    candidate_labels = _parse_candidate_phrase(raw_output)

    if primary_label:
        candidate_labels.insert(0, primary_label)

    normalized_candidates = _normalize_candidate_labels(
        [label for label in candidate_labels if label]
    )[:3]
    normalized_primary = resolve_material_label(primary_label)

    if normalized_primary is None and normalized_candidates:
        normalized_primary = normalized_candidates[0]

    if status not in {"confident", "uncertain"}:
        if len(normalized_candidates) >= 2:
            status = "uncertain"
        elif normalized_primary:
            status = "confident"
        else:
            status = "unknown"

    if status == "confident" and not normalized_primary:
        status = "unknown"

    return {
        "status": status,
        "primary_label": normalized_primary or "",
        "candidate_labels": normalized_candidates,
        "raw_output": raw_output,
    }


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalize_candidate_labels(candidate_labels: list[str]) -> list[str]:
    normalized_candidates = []
    for label in candidate_labels:
        canonical_label = resolve_material_label(label)
        if canonical_label is not None:
            normalized_candidates.append(canonical_label)

    return _dedupe_preserve_order(normalized_candidates)


def _clean_optional_field(value: object) -> str:
    cleaned_value = _clean_generated_label(str(value or ""))
    if cleaned_value.lower() in {"none", "null"}:
        return ""
    return cleaned_value


def _clean_free_text_field(value: object) -> str:
    text = str(value or "").replace("\\n", "\n").strip()
    if text.lower() in {"none", "null"}:
        return ""
    return text


def _coerce_candidate_confidence(value: object) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe_open_candidates(
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    deduped_candidates: list[dict[str, object]] = []
    seen_labels: set[str] = set()

    for candidate in candidates:
        label = str(candidate.get("label", "")).strip()
        if not label:
            continue

        label_key = label.casefold()
        if label_key in seen_labels:
            continue

        seen_labels.add(label_key)
        deduped_candidates.append(candidate)

    return deduped_candidates


def _rank_candidate_predictions(
    candidate_labels: list[str],
    top_score: float,
    score_step: float,
) -> list[tuple[str, float]]:
    ranked_candidates = _dedupe_preserve_order(candidate_labels)[:3]
    return [
        (label, max(CONFIDENT_THRESHOLD, top_score - (index * score_step)))
        for index, label in enumerate(ranked_candidates)
    ]


def _build_payload(
    image_base64: str,
    prompt_text: str,
    response_schema: dict[str, object] | None = None,
    *,
    max_tokens: int = DEFAULT_VLM_MAX_TOKENS,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "image": image_base64,
        "prompt": prompt_text,
        "max_tokens": max_tokens,
        "temperature": 0,
    }

    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": response_schema,
        }

    return payload


def _build_barcode_context_suffix(barcode_context: dict[str, object] | None) -> str:
    if not isinstance(barcode_context, dict):
        return ""

    barcode_value = str(barcode_context.get("barcode_value") or "").strip() or "unknown"
    product_name = str(barcode_context.get("product_name") or "").strip() or "unknown"
    brand = str(barcode_context.get("brand") or "").strip() or "unknown"
    category = str(barcode_context.get("category") or "").strip() or "unknown"
    packaging = str(barcode_context.get("packaging") or "").strip() or "unknown"

    return (
        "\n\n"
        "Barcode lookup found product metadata, but packaging could not be mapped.\n"
        "This metadata is product context only, not answer labels.\n"
        "Use the image and this product context to identify the visible disposal item/package/container.\n"
        "The answer must identify the packaging or physical item that should be disposed of, such as wrapper, plastic bag, cardboard box, glass jar, plastic bottle, soda can, drink carton, or another supported disposal label.\n"
        "Do not answer with the food or product identity unless that exact label is already a supported disposal item in the allowed inventory.\n"
        "Do not output product names like Frozen dairy dessert cone, Ice cream cone, Nutella, Coca-Cola, Chips, or Candy unless that exact label is a supported Green Bin disposal item.\n"
        "Choose only from the backend's supported item labels / canonical inventory list.\n"
        "If the visible disposal item is unclear, or the image mostly shows only a barcode, return exactly:\n"
        '{"status":"unknown","primary_label":"","candidate_labels":[]}\n'
        "Product context, not answer labels:\n"
        f"- barcode_value: {barcode_value}\n"
        f"- product_name: {product_name}\n"
        f"- brand: {brand}\n"
        f"- category: {category}\n"
        f"- packaging: {packaging}\n"
    )


def _build_open_barcode_context_suffix(barcode_context: dict[str, object] | None) -> str:
    if not isinstance(barcode_context, dict):
        return ""

    barcode_value = str(barcode_context.get("barcode_value") or "").strip() or "unknown"
    product_name = str(barcode_context.get("product_name") or "").strip() or "unknown"
    brand = str(barcode_context.get("brand") or "").strip() or "unknown"
    category = str(barcode_context.get("category") or "").strip() or "unknown"
    packaging = str(barcode_context.get("packaging") or "").strip() or "unknown"

    return (
        "\n\n"
        "Barcode lookup found product metadata, but this metadata is only context.\n"
        "Use the image first to recognize the visible physical item or packaging.\n"
        "Do not infer the visible item from barcode text alone when the object shape/material is unclear.\n"
        "If the visible item is unclear, return unknown.\n"
        "Product context:\n"
        f"- barcode_value: {barcode_value}\n"
        f"- product_name: {product_name}\n"
        f"- brand: {brand}\n"
        f"- category: {category}\n"
        f"- packaging: {packaging}\n"
    )


def _build_detection_prompt(
    *,
    barcode_aware: bool,
    barcode_context: dict[str, object] | None = None,
) -> str:
    prompt_text = BARCODE_AWARE_DETECTION_PROMPT if barcode_aware else DETECTION_PROMPT
    if barcode_aware:
        prompt_text += _build_barcode_context_suffix(barcode_context)
    return prompt_text


def _build_open_detection_prompt(
    *,
    barcode_aware: bool,
    barcode_context: dict[str, object] | None = None,
) -> str:
    prompt_text = (
        OPEN_BARCODE_AWARE_DETECTION_PROMPT if barcode_aware else OPEN_DETECTION_PROMPT
    )
    if barcode_aware:
        prompt_text += _build_open_barcode_context_suffix(barcode_context)
    return prompt_text


def _apply_barcode_fallback_rules(
    prompt_text: str,
    *,
    barcode_aware: bool,
    barcode_context: dict[str, object] | None = None,
) -> str:
    if not barcode_aware:
        return prompt_text
    return (
        prompt_text
        + BARCODE_AWARE_PROMPT_SUFFIX
        + _build_barcode_context_suffix(barcode_context)
    )


def _cloudflare_api_url() -> str:
    return (
        f"{CLOUDFLARE_API_BASE_URL}/accounts/"
        f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/{CLOUDFLARE_AI_MODEL}"
    )


def _normalize_cloudflare_result_value(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None

    if isinstance(value, (dict, list)):
        return json.dumps(value)

    return None


def _extract_cloudflare_response_text(response_json: dict[str, object]) -> str:
    if "success" in response_json and not response_json.get("success"):
        errors = response_json.get("errors") or []
        raise RuntimeError(f"Cloudflare Workers AI returned an error: {errors}")

    result = response_json.get("result")
    if isinstance(result, dict):
        for key in ("response", "output_text", "text"):
            normalized_value = _normalize_cloudflare_result_value(result.get(key))
            if normalized_value is not None:
                return normalized_value

        normalized_result = _normalize_cloudflare_result_value(result)
        if normalized_result is not None:
            return normalized_result
    else:
        normalized_result = _normalize_cloudflare_result_value(result)
        if normalized_result is not None:
            return normalized_result

    normalized_top_level_response = _normalize_cloudflare_result_value(
        response_json.get("response")
    )
    if normalized_top_level_response is not None:
        return normalized_top_level_response

    raise ValueError("Cloudflare Workers AI response did not include text output.")


def _call_vision_model(
    image_base64: str,
    prompt_text: str,
    response_schema: dict[str, object] | None = None,
    *,
    max_tokens: int = DEFAULT_VLM_MAX_TOKENS,
    request_label: str = "detection",
) -> str:
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload_started = perf_counter()
    payload = _build_payload(
        image_base64,
        prompt_text,
        response_schema=response_schema,
        max_tokens=max_tokens,
    )
    _log_vlm_timing(
        "payload_construction",
        payload_started,
        provider="cloudflare",
        model=CLOUDFLARE_AI_MODEL,
        request=request_label,
        prompt_chars=len(prompt_text),
        image_base64_chars=len(image_base64),
        has_response_schema=response_schema is not None,
        max_tokens=max_tokens,
    )

    request_started = perf_counter()
    try:
        response = requests.post(
            _cloudflare_api_url(),
            headers=headers,
            json=payload,
            timeout=60,
        )
    except Exception as exc:
        _log_vlm_timing(
            "cloudflare_http_request",
            request_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            request=request_label,
            timeout_seconds=60,
            proxy_env_present=any(
                os.getenv(name)
                for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
            ),
            result="exception",
            error_type=type(exc).__name__,
        )
        raise
    else:
        _log_vlm_timing(
            "cloudflare_http_request",
            request_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            request=request_label,
            timeout_seconds=60,
            proxy_env_present=any(
                os.getenv(name)
                for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
            ),
            status_code=getattr(response, "status_code", "unknown"),
        )
    response.raise_for_status()

    extraction_started = perf_counter()
    try:
        response_json = response.json()
        raw_output = _extract_cloudflare_response_text(response_json)
    except Exception as exc:
        _log_vlm_timing(
            "cloudflare_response_extract",
            extraction_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            request=request_label,
            result="exception",
            error_type=type(exc).__name__,
        )
        raise
    _log_vlm_timing(
        "cloudflare_response_extract",
        extraction_started,
        provider="cloudflare",
        model=CLOUDFLARE_AI_MODEL,
        request=request_label,
        raw_output_chars=len(raw_output),
    )
    return raw_output


def _parse_detection_result(raw_output: str) -> dict[str, object]:
    parse_started = perf_counter()
    parsed_output: dict[str, object]
    parse_mode = "exact"

    try:
        parsed_output = _extract_json_object(raw_output)
    except ValueError:
        partial_output = _extract_partial_json_fields(raw_output)
        if partial_output:
            parsed_output = partial_output
            parse_mode = "partial"
        else:
            result = _parse_detection_result_from_text(raw_output)
            _log_vlm_timing(
                "json_parse",
                parse_started,
                provider="cloudflare",
                model=CLOUDFLARE_AI_MODEL,
                mode="constrained",
                parse_mode="prose",
                status=result.get("status"),
                raw_output_chars=len(raw_output),
            )
            return result

    status = str(parsed_output.get("status", "")).strip().lower()
    if status not in {"confident", "uncertain", "unknown"}:
        status = "unknown"

    primary_label = _clean_generated_label(
        str(parsed_output.get("primary_label", ""))
    )

    if primary_label.lower() in {"none", "null", "unknown"}:
        primary_label = ""

    raw_candidate_labels = parsed_output.get("candidate_labels", [])
    if not isinstance(raw_candidate_labels, list):
        raw_candidate_labels = []

    cleaned_candidates = [
        _clean_generated_label(str(label))
        for label in raw_candidate_labels
        if str(label).strip()
    ]

    if primary_label:
        cleaned_candidates.insert(0, primary_label)

    normalized_candidates = _normalize_candidate_labels(cleaned_candidates)[:3]
    normalized_primary = resolve_material_label(primary_label)

    if normalized_primary is None and normalized_candidates:
        normalized_primary = normalized_candidates[0]

    if normalized_primary and normalized_primary not in normalized_candidates:
        normalized_candidates.insert(0, normalized_primary)
        normalized_candidates = _dedupe_preserve_order(normalized_candidates)[:3]

    if status == "confident" and not normalized_primary:
        status = "unknown"

    if status == "uncertain" and len(normalized_candidates) < 2:
        if not normalized_primary:
            status = "unknown"

    result = {
        "status": status,
        "primary_label": normalized_primary or "",
        "candidate_labels": normalized_candidates,
        "raw_output": raw_output,
    }
    _log_vlm_timing(
        "json_parse",
        parse_started,
        provider="cloudflare",
        model=CLOUDFLARE_AI_MODEL,
        mode="constrained",
        parse_mode=parse_mode,
        status=status,
        candidate_count=len(normalized_candidates),
        raw_output_chars=len(raw_output),
    )
    return result


def _unknown_open_detection_result(
    raw_output: str = "",
    *,
    error: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "unknown",
        "raw_item_label": "",
        "likely_material": "",
        "broad_category": "",
        "candidates": [],
        "visual_evidence": "",
        "raw_output": raw_output,
    }
    if error is not None:
        result["error"] = error
    return result


def _extract_partial_open_detection_fields(raw_text: str) -> dict[str, object]:
    if not isinstance(raw_text, str):
        return {}

    parsed: dict[str, object] = {}

    status_match = re.search(
        r'"status"\s*:\s*"(confident|uncertain|unknown)"',
        raw_text,
        flags=re.IGNORECASE,
    )
    if status_match:
        parsed["status"] = status_match.group(1).strip().lower()

    raw_item_label_match = re.search(
        r'"raw_item_label"\s*:\s*"([^"]*)"',
        raw_text,
        flags=re.IGNORECASE,
    )
    if raw_item_label_match:
        parsed["raw_item_label"] = _clean_optional_field(raw_item_label_match.group(1))

    likely_material_match = re.search(
        r'"likely_material"\s*:\s*"([^"]*)"',
        raw_text,
        flags=re.IGNORECASE,
    )
    if likely_material_match:
        parsed["likely_material"] = _clean_free_text_field(
            likely_material_match.group(1)
        )

    broad_category_match = re.search(
        r'"broad_category"\s*:\s*"([^"]*)"',
        raw_text,
        flags=re.IGNORECASE,
    )
    if broad_category_match:
        parsed["broad_category"] = _clean_free_text_field(
            broad_category_match.group(1)
        )

    visual_evidence_match = re.search(
        r'"visual_evidence"\s*:\s*"([^"]*)"',
        raw_text,
        flags=re.IGNORECASE,
    )
    if visual_evidence_match:
        parsed["visual_evidence"] = _clean_free_text_field(
            visual_evidence_match.group(1)
        )

    candidate_matches = re.finditer(
        r'\{\s*"label"\s*:\s*"([^"]+)"\s*,\s*"confidence"\s*:\s*(null|-?\d+(?:\.\d+)?)',
        raw_text,
        flags=re.IGNORECASE,
    )
    candidates: list[dict[str, object]] = []
    for match in candidate_matches:
        label = _clean_optional_field(match.group(1))
        if not label:
            continue

        confidence_value = match.group(2)
        confidence: float | None = None
        if confidence_value.strip().lower() != "null":
            confidence = _coerce_candidate_confidence(confidence_value)

        candidates.append({"label": label, "confidence": confidence})
        if len(candidates) == 3:
            break

    if candidates:
        parsed["candidates"] = _dedupe_open_candidates(candidates)

    return parsed


def _parse_open_detection_result(raw_output: str) -> dict[str, object]:
    parse_started = perf_counter()
    parse_mode = "exact"
    try:
        parsed_output = _extract_json_object(raw_output)
    except ValueError:
        parsed_output = _extract_partial_open_detection_fields(raw_output)
        if not parsed_output:
            logger.warning("Open VLM JSON parse failed; returning unknown.")
            result = _unknown_open_detection_result(raw_output)
            _log_vlm_timing(
                "json_parse",
                parse_started,
                provider="cloudflare",
                model=CLOUDFLARE_AI_MODEL,
                mode="open",
                parse_mode="failed",
                status=result.get("status"),
                raw_output_chars=len(raw_output),
            )
            return result
        parse_mode = "recovered"

    status = str(parsed_output.get("status", "")).strip().lower()
    if status not in {"confident", "uncertain", "unknown"}:
        status = "unknown"

    raw_item_label = _clean_optional_field(parsed_output.get("raw_item_label", ""))
    likely_material = _clean_free_text_field(parsed_output.get("likely_material", ""))
    broad_category = _clean_free_text_field(parsed_output.get("broad_category", ""))

    raw_candidates = parsed_output.get("candidates", [])
    if not isinstance(raw_candidates, list):
        raw_candidates = []

    parsed_candidates: list[dict[str, object]] = []
    for raw_candidate in raw_candidates[:3]:
        if not isinstance(raw_candidate, dict):
            continue

        label = _clean_optional_field(raw_candidate.get("label", ""))
        if not label:
            continue

        parsed_candidates.append(
            {
                "label": label,
                "confidence": _coerce_candidate_confidence(
                    raw_candidate.get("confidence")
                ),
            }
        )

    visual_evidence = _clean_free_text_field(parsed_output.get("visual_evidence", ""))

    if parse_mode == "recovered":
        recovered_has_signal = any(
            (
                raw_item_label,
                likely_material,
                broad_category,
                parsed_candidates,
            )
        )
        if not recovered_has_signal:
            logger.warning("Open VLM JSON recovery failed; returning unknown.")
            result = _unknown_open_detection_result(raw_output)
            _log_vlm_timing(
                "json_parse",
                parse_started,
                provider="cloudflare",
                model=CLOUDFLARE_AI_MODEL,
                mode="open",
                parse_mode="recovery_failed",
                status=result.get("status"),
                raw_output_chars=len(raw_output),
            )
            return result
        logger.info(
            "Open VLM JSON parse recovered. status=%s raw_item_label=%s candidate_count=%s",
            status,
            raw_item_label,
            len(parsed_candidates),
        )
    else:
        logger.info(
            "Open VLM JSON parse exact. status=%s raw_item_label=%s candidate_count=%s",
            status,
            raw_item_label,
            len(parsed_candidates),
        )

    result = {
        "status": status,
        "raw_item_label": raw_item_label,
        "likely_material": likely_material,
        "broad_category": broad_category,
        "candidates": _dedupe_open_candidates(parsed_candidates),
        "visual_evidence": visual_evidence,
        "raw_output": raw_output,
    }
    _log_vlm_timing(
        "json_parse",
        parse_started,
        provider="cloudflare",
        model=CLOUDFLARE_AI_MODEL,
        mode="open",
        parse_mode=parse_mode,
        status=status,
        candidate_count=len(result["candidates"]),
        raw_output_chars=len(raw_output),
    )
    return result


def _maybe_verify_confident_result(
    image_base64: str,
    result: dict[str, object],
) -> dict[str, object]:
    verification_started = perf_counter()
    if result.get("status") != "confident":
        _log_vlm_timing(
            "verification",
            verification_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            skipped=True,
            reason="status_not_confident",
            status=result.get("status"),
        )
        return result

    primary_label = (result.get("primary_label") or "").strip()
    if not primary_label:
        _log_vlm_timing(
            "verification",
            verification_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            skipped=True,
            reason="missing_primary_label",
            status=result.get("status"),
        )
        return result

    verification_prompt = build_multi_object_verification_prompt(primary_label)
    verification_output = _call_vision_model(
        image_base64,
        verification_prompt,
        response_schema=VERIFICATION_RESPONSE_SCHEMA,
        request_label="verification",
    )

    print(f"Verification raw: {verification_output!r}")

    try:
        verification_result = _parse_detection_result(verification_output)
    except (ValueError, TypeError) as exc:
        print(f"Verification parse failed: {exc}")
        _log_vlm_timing(
            "verification",
            verification_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            skipped=False,
            result="parse_failed",
            error_type=type(exc).__name__,
        )
        return result

    print(f"Verification parsed: {verification_result!r}")

    if verification_result.get("status") == "uncertain":
        _log_vlm_timing(
            "verification",
            verification_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            skipped=False,
            result="used_uncertain",
            status=verification_result.get("status"),
        )
        return verification_result

    verified_label = verification_result.get("primary_label", "")
    original_candidates = result.get("candidate_labels", [])
    original_candidate_set = set(original_candidates)

    if (
        verification_result.get("status") == "confident"
        and verified_label
        and verified_label in original_candidate_set
    ):
        _log_vlm_timing(
            "verification",
            verification_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            skipped=False,
            result="used_confident",
            status=verification_result.get("status"),
            verified_label=verified_label,
        )
        return verification_result

    distinct_candidates = [
        candidate for candidate in original_candidates if candidate != primary_label
    ]
    if distinct_candidates:
        adjusted_result = {
            "status": "uncertain",
            "primary_label": primary_label,
            "candidate_labels": original_candidates[:3],
            "raw_output": str(result.get("raw_output", "")),
        }
        _log_vlm_timing(
            "verification",
            verification_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            skipped=False,
            result="forced_uncertain",
            status=adjusted_result.get("status"),
        )
        return adjusted_result

    _log_vlm_timing(
        "verification",
        verification_started,
        provider="cloudflare",
        model=CLOUDFLARE_AI_MODEL,
        skipped=False,
        result="kept_original",
        status=result.get("status"),
    )
    return result


def _detect_object_constrained(
    image: Image.Image,
    *,
    barcode_aware: bool = False,
    barcode_context: dict[str, object] | None = None,
) -> dict[str, object]:
    try:
        if not CLOUDFLARE_ACCOUNT_ID:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not set in backend/.env.")
        if not CLOUDFLARE_API_TOKEN:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is not set in backend/.env.")

        encode_started = perf_counter()
        original_size = image.size
        original_mode = image.mode
        rgb_image = image.convert("RGB")
        buffer = io.BytesIO()
        rgb_image.save(buffer, format="JPEG", quality=75)

        img_bytes = buffer.getvalue()
        image_base64 = base64.b64encode(img_bytes).decode("utf-8")
        _log_vlm_timing(
            "image_preprocess_encode",
            encode_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            mode="constrained",
            original_dimensions=f"{original_size[0]}x{original_size[1]}",
            original_mode=original_mode,
            outgoing_dimensions=f"{rgb_image.size[0]}x{rgb_image.size[1]}",
            outgoing_image_bytes=len(img_bytes),
            image_base64_chars=len(image_base64),
        )

        raw_output = _call_vision_model(
            image_base64,
            _build_detection_prompt(
                barcode_aware=barcode_aware,
                barcode_context=barcode_context,
            ),
            response_schema=DETECTION_RESPONSE_SCHEMA,
            request_label="detection",
        )
        print(f"Cloudflare Vision raw output: {raw_output!r}")

        result = _parse_detection_result(raw_output)

        if result.get("status") == "uncertain" and len(result.get("candidate_labels", [])) < 2:
            fallback_started = perf_counter()
            fallback_prompt = build_uncertain_fallback_prompt(
                result.get("primary_label", "")
            )

            fallback_output = _call_vision_model(
                image_base64,
                _apply_barcode_fallback_rules(
                    fallback_prompt,
                    barcode_aware=barcode_aware,
                    barcode_context=barcode_context,
                ),
                response_schema=DETECTION_RESPONSE_SCHEMA,
                request_label="uncertain_fallback",
            )
            print(f"Cloudflare Vision fallback raw output: {fallback_output!r}")

            try:
                fallback_result = _parse_detection_result(fallback_output)
            except (ValueError, TypeError) as exc:
                print(f"Fallback parse failed: {exc}")
                fallback_result = result
                _log_vlm_timing(
                    "retry_or_repair",
                    fallback_started,
                    provider="cloudflare",
                    model=CLOUDFLARE_AI_MODEL,
                    mode="constrained",
                    retry="uncertain_fallback",
                    result="parse_failed",
                    error_type=type(exc).__name__,
                )
            else:
                _log_vlm_timing(
                    "retry_or_repair",
                    fallback_started,
                    provider="cloudflare",
                    model=CLOUDFLARE_AI_MODEL,
                    mode="constrained",
                    retry="uncertain_fallback",
                    result="parsed",
                    status=fallback_result.get("status"),
                    candidate_count=len(fallback_result.get("candidate_labels", [])),
                )

            if fallback_result.get("primary_label") or fallback_result.get("candidate_labels"):
                result = fallback_result
        else:
            skipped_retry_started = perf_counter()
            _log_vlm_timing(
                "retry_or_repair",
                skipped_retry_started,
                provider="cloudflare",
                model=CLOUDFLARE_AI_MODEL,
                mode="constrained",
                skipped=True,
                reason="no_uncertain_fallback",
                status=result.get("status"),
                candidate_count=len(result.get("candidate_labels", [])),
            )

        result = _maybe_verify_confident_result(image_base64, result)

        if result.get("candidate_labels") and result.get("primary_label"):
            if result["primary_label"] not in result["candidate_labels"]:
                result["primary_label"] = result["candidate_labels"][0]

    except Exception as exc:
        print(f"Cloudflare Workers AI error: {exc}")
        return {
            "status": "unknown",
            "primary_label": "",
            "candidate_labels": [],
            "raw_output": "",
            "error": str(exc),
        }

    print(f"Cloudflare Vision parsed result: {result!r}")
    return result


def _detect_object_open(
    image: Image.Image,
    *,
    barcode_aware: bool = False,
    barcode_context: dict[str, object] | None = None,
) -> dict[str, object]:
    try:
        if not CLOUDFLARE_ACCOUNT_ID:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not set in backend/.env.")
        if not CLOUDFLARE_API_TOKEN:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is not set in backend/.env.")

        encode_started = perf_counter()
        original_size = image.size
        original_mode = image.mode
        rgb_image = image.convert("RGB")
        buffer = io.BytesIO()
        rgb_image.save(buffer, format="JPEG", quality=75)

        img_bytes = buffer.getvalue()
        image_base64 = base64.b64encode(img_bytes).decode("utf-8")
        _log_vlm_timing(
            "image_preprocess_encode",
            encode_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            mode="open",
            original_dimensions=f"{original_size[0]}x{original_size[1]}",
            original_mode=original_mode,
            outgoing_dimensions=f"{rgb_image.size[0]}x{rgb_image.size[1]}",
            outgoing_image_bytes=len(img_bytes),
            image_base64_chars=len(image_base64),
        )

        raw_output = _call_vision_model(
            image_base64,
            _build_open_detection_prompt(
                barcode_aware=barcode_aware,
                barcode_context=barcode_context,
            ),
            response_schema=OPEN_DETECTION_RESPONSE_SCHEMA,
            max_tokens=OPEN_VLM_MAX_TOKENS,
            request_label="open_detection",
        )
        print(f"Cloudflare Vision open raw output: {raw_output!r}")

        result = _parse_open_detection_result(raw_output)
        skipped_retry_started = perf_counter()
        _log_vlm_timing(
            "retry_or_repair",
            skipped_retry_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            mode="open",
            skipped=True,
            reason="no_open_retry",
            status=result.get("status"),
            candidate_count=len(result.get("candidates", [])),
        )
    except Exception as exc:
        print(f"Cloudflare Workers AI error: {exc}")
        return _unknown_open_detection_result("", error=str(exc))

    print(f"Cloudflare Vision open parsed result: {result!r}")
    return result


def detect_object(
    image: Image.Image,
    *,
    barcode_aware: bool = False,
    barcode_context: dict[str, object] | None = None,
    recognition_mode: str | None = None,
) -> dict[str, object]:
    mode = normalize_vlm_recognition_mode(
        VLM_RECOGNITION_MODE if recognition_mode is None else recognition_mode
    )
    if mode == "open":
        return _detect_object_open(
            image,
            barcode_aware=barcode_aware,
            barcode_context=barcode_context,
        )

    return _detect_object_constrained(
        image,
        barcode_aware=barcode_aware,
        barcode_context=barcode_context,
    )


def build_prediction_result(
    detection_result: dict[str, object],
) -> dict[str, object]:
    normalization_started = perf_counter()
    if "raw_item_label" in detection_result:
        result = {
            "top_predictions": [],
            "scores": [0.0 for _ in MATERIAL_LABELS],
            "top1_score": 0.0,
            "top2_score": 0.0,
            "margin": 0.0,
            "detected_label": "",
            "recognition_details": detection_result,
        }
        _log_vlm_timing(
            "result_normalization",
            normalization_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            mode="open",
            status=detection_result.get("status"),
            candidate_count=len(detection_result.get("candidates", [])),
        )
        return result

    detection_status = str(detection_result.get("status", "unknown"))
    primary_label = str(detection_result.get("primary_label", "")).strip()
    candidate_labels = detection_result.get("candidate_labels", [])
    if not isinstance(candidate_labels, list):
        candidate_labels = []

    print(f"Vision model detection status: {detection_status!r}")
    print(f"Vision model candidate labels: {candidate_labels!r}")

    if detection_status == "confident" and primary_label:
        top_predictions = _rank_candidate_predictions(
            [primary_label, *candidate_labels],
            CONFIDENT_SCORE,
            CONFIDENT_SCORE_STEP,
        )
        scores = [
            next((score for candidate, score in top_predictions if candidate == label), 0.0)
            for label in MATERIAL_LABELS
        ]
        top1_score = top_predictions[0][1]
        top2_score = top_predictions[1][1] if len(top_predictions) > 1 else 0.0
        result = {
            "top_predictions": top_predictions,
            "scores": scores,
            "top1_score": top1_score,
            "top2_score": top2_score,
            "margin": top1_score - top2_score if len(top_predictions) > 1 else top1_score,
            "detected_label": primary_label,
            "category": LABEL_TO_CATEGORY[primary_label],
        }
        _log_vlm_timing(
            "result_normalization",
            normalization_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            mode="constrained",
            status=detection_status,
            candidate_count=len(top_predictions),
        )
        return result

    if detection_status == "uncertain" and len(candidate_labels) >= 2:
        top_predictions = [
            (label, max(0.0, UNCERTAIN_TOP_SCORE - (index * UNCERTAIN_SCORE_STEP)))
            for index, label in enumerate(candidate_labels[:3])
        ]
        scores = [
            next((score for candidate, score in top_predictions if candidate == label), 0.0)
            for label in MATERIAL_LABELS
        ]
        top1_score = top_predictions[0][1]
        top2_score = top_predictions[1][1] if len(top_predictions) > 1 else 0.0
        result = {
            "top_predictions": top_predictions,
            "scores": scores,
            "top1_score": top1_score,
            "top2_score": top2_score,
            "margin": top1_score - top2_score,
            "detected_label": primary_label or top_predictions[0][0],
        }
        _log_vlm_timing(
            "result_normalization",
            normalization_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            mode="constrained",
            status=detection_status,
            candidate_count=len(top_predictions),
        )
        return result

    detected_label = primary_label or ""
    if not detected_label and candidate_labels:
        detected_label = str(candidate_labels[0]).strip()

    if not detected_label:
        result = {
            "top_predictions": [],
            "scores": [0.0 for _ in MATERIAL_LABELS],
            "top1_score": 0.0,
            "top2_score": 0.0,
            "margin": 0.0,
            "detected_label": "",
        }
        _log_vlm_timing(
            "result_normalization",
            normalization_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            mode="constrained",
            status=detection_status,
            candidate_count=0,
        )
        return result

    canonical_label = resolve_material_label(detected_label)
    if canonical_label is None:
        result = {
            "top_predictions": [],
            "scores": [0.0 for _ in MATERIAL_LABELS],
            "top1_score": 0.0,
            "top2_score": 0.0,
            "margin": 0.0,
            "detected_label": detected_label,
        }
        _log_vlm_timing(
            "result_normalization",
            normalization_started,
            provider="cloudflare",
            model=CLOUDFLARE_AI_MODEL,
            mode="constrained",
            status=detection_status,
            candidate_count=0,
            resolved=False,
        )
        return result

    top_predictions = _rank_candidate_predictions(
        [canonical_label, *candidate_labels],
        CONFIDENT_SCORE,
        CONFIDENT_SCORE_STEP,
    )
    scores = [
        next((score for candidate, score in top_predictions if candidate == label), 0.0)
        for label in MATERIAL_LABELS
    ]
    top1_score = top_predictions[0][1]
    top2_score = top_predictions[1][1] if len(top_predictions) > 1 else 0.0
    result = {
        "top_predictions": top_predictions,
        "scores": scores,
        "top1_score": top1_score,
        "top2_score": top2_score,
        "margin": top1_score - top2_score if len(top_predictions) > 1 else top1_score,
        "detected_label": detected_label,
        "category": LABEL_TO_CATEGORY[canonical_label],
    }
    _log_vlm_timing(
        "result_normalization",
        normalization_started,
        provider="cloudflare",
        model=CLOUDFLARE_AI_MODEL,
        mode="constrained",
        status=detection_status,
        candidate_count=len(top_predictions),
        resolved=True,
    )
    return result


def get_top_predictions(
    image: Image.Image,
    *,
    barcode_aware: bool = False,
    barcode_context: dict[str, object] | None = None,
    recognition_mode: str | None = None,
) -> dict[str, object]:
    detection_result = detect_object(
        image,
        barcode_aware=barcode_aware,
        barcode_context=barcode_context,
        recognition_mode=recognition_mode,
    )
    return build_prediction_result(detection_result)
