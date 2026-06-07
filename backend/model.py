import base64
import io
import json
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

from materials import (
    LABEL_TO_CATEGORY,
    MATERIAL_LABELS,
    build_material_selection_prompt,
    build_multi_object_verification_prompt,
    build_uncertain_fallback_prompt,
    resolve_material_label,
)

load_dotenv(Path(__file__).resolve().parent / ".env")

CONFIDENT_THRESHOLD = 0.20
MARGIN_THRESHOLD = 0.05

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
DETECTION_PROMPT = build_material_selection_prompt()
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
VERIFICATION_RESPONSE_SCHEMA = DETECTION_RESPONSE_SCHEMA
CONFIDENT_SCORE = 1.0
UNCERTAIN_TOP_SCORE = 0.58
UNCERTAIN_SCORE_STEP = 0.02

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

    # find first JSON block
    start_index = raw_text.find("{")
    if start_index == -1:
        raise ValueError("No JSON object found in model response.")

    json_text = raw_text[start_index:]

    # 🚨 fix: sometimes model outputs multiple JSON objects
    # keep only first complete object
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


def _build_payload(
    image_base64: str,
    prompt_text: str,
    response_schema: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "image": image_base64,
        "prompt": prompt_text,
        "max_tokens": 60,
        "temperature": 0,
    }

    if response_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": response_schema,
        }

    return payload


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
) -> str:
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        _cloudflare_api_url(),
        headers=headers,
        json=_build_payload(image_base64, prompt_text, response_schema=response_schema),
        timeout=60,
    )
    response.raise_for_status()
    return _extract_cloudflare_response_text(response.json())


def _parse_detection_result(raw_output: str) -> dict[str, object]:
    parsed_output: dict[str, object]

    try:
        parsed_output = _extract_json_object(raw_output)
    except ValueError:
        partial_output = _extract_partial_json_fields(raw_output)
        if partial_output:
            parsed_output = partial_output
        else:
            return _parse_detection_result_from_text(raw_output)

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
        if normalized_primary:
            status = "confident"
        else:
            status = "unknown"

    return {
        "status": status,
        "primary_label": normalized_primary or "",
        "candidate_labels": normalized_candidates,
        "raw_output": raw_output,
    }


def _maybe_verify_confident_result(
    image_base64: str,
    result: dict[str, object],
) -> dict[str, object]:

    if result.get("status") != "uncertain":
        return result

    primary_label = (result.get("primary_label") or "").strip()
    if not primary_label:
        return result

    verification_prompt = build_multi_object_verification_prompt(primary_label)
    verification_output = _call_vision_model(
        image_base64,
        verification_prompt,
        response_schema=VERIFICATION_RESPONSE_SCHEMA,
    )

    print(f"Verification raw: {verification_output!r}")

    try:
        verification_result = _parse_detection_result(verification_output)
    except (ValueError, TypeError) as exc:
        print(f"Verification parse failed: {exc}")
        return result

    print(f"Verification parsed: {verification_result!r}")

    # 🚨 if model says uncertain → trust it
    if verification_result.get("status") == "uncertain":
        return verification_result

    verified_label = verification_result.get("primary_label", "")
    original_candidates = result.get("candidate_labels", [])
    original_candidate_set = set(original_candidates)

    # 🚨 only accept verification if it stays in same label space
    if (
        verification_result.get("status") == "confident"
        and verified_label
        and verified_label in original_candidate_set
    ):
        return verification_result

    distinct_candidates = [
        candidate for candidate in original_candidates if candidate != primary_label
    ]
    if distinct_candidates:
        return {
            "status": "uncertain",
            "primary_label": primary_label,
            "candidate_labels": original_candidates[:3],
            "raw_output": str(result.get("raw_output", "")),
        }

    return result


def detect_object(image: Image.Image) -> dict[str, object]:
    try:
        if not CLOUDFLARE_ACCOUNT_ID:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not set in backend/.env.")
        if not CLOUDFLARE_API_TOKEN:
            raise RuntimeError("CLOUDFLARE_API_TOKEN is not set in backend/.env.")

        rgb_image = image.convert("RGB")
        buffer = io.BytesIO()
        rgb_image.save(buffer, format="JPEG", quality=75)

        img_bytes = buffer.getvalue()
        image_base64 = base64.b64encode(img_bytes).decode("utf-8")

        raw_output = _call_vision_model(
            image_base64,
            DETECTION_PROMPT,
            response_schema=DETECTION_RESPONSE_SCHEMA,
        )
        print(f"Cloudflare Vision raw output: {raw_output!r}")

        result = _parse_detection_result(raw_output)

        # 🚨 fallback ONLY if truly weak output
        if result.get("status") == "uncertain" and len(result.get("candidate_labels", [])) < 2:
            fallback_prompt = build_uncertain_fallback_prompt(
                result.get("primary_label", "")
            )

            fallback_output = _call_vision_model(
                image_base64,
                fallback_prompt,
                response_schema=DETECTION_RESPONSE_SCHEMA,
            )
            print(f"Cloudflare Vision fallback raw output: {fallback_output!r}")

            try:
                fallback_result = _parse_detection_result(fallback_output)
            except (ValueError, TypeError) as exc:
                print(f"Fallback parse failed: {exc}")
                fallback_result = result

            if fallback_result.get("primary_label") or fallback_result.get("candidate_labels"):
                result = fallback_result

        verified_result = result
        result = verified_result

        # 🚨 final safety consistency check
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


def get_top_predictions(image: Image.Image) -> dict[str, object]:
    detection_result = detect_object(image)
    detection_status = str(detection_result.get("status", "unknown"))
    primary_label = str(detection_result.get("primary_label", "")).strip()
    candidate_labels = detection_result.get("candidate_labels", [])
    if not isinstance(candidate_labels, list):
        candidate_labels = []

    print(f"Vision model detection status: {detection_status!r}")
    print(f"Vision model candidate labels: {candidate_labels!r}")

    if detection_status == "confident" and primary_label:
        scores = [0.8 if label == primary_label else 0.0 for label in MATERIAL_LABELS]
        return {
            "top_predictions": [(primary_label, CONFIDENT_SCORE)],
            "scores": scores,
            "top1_score": CONFIDENT_SCORE,
            "top2_score": 0.0,
            "margin": CONFIDENT_SCORE,
            "detected_label": primary_label,
            "category": LABEL_TO_CATEGORY[primary_label],
        }

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
        return {
            "top_predictions": top_predictions,
            "scores": scores,
            "top1_score": top1_score,
            "top2_score": top2_score,
            "margin": top1_score - top2_score,
            "detected_label": primary_label or top_predictions[0][0],
        }

    detected_label = primary_label or ""
    if not detected_label and candidate_labels:
        detected_label = str(candidate_labels[0]).strip()

    if not detected_label:
        return {
            "top_predictions": [],
            "scores": [0.0 for _ in MATERIAL_LABELS],
            "top1_score": 0.0,
            "top2_score": 0.0,
            "margin": 0.0,
            "detected_label": "",
        }

    canonical_label = resolve_material_label(detected_label)
    if canonical_label is None:
        return {
            "top_predictions": [],
            "scores": [0.0 for _ in MATERIAL_LABELS],
            "top1_score": 0.0,
            "top2_score": 0.0,
            "margin": 0.0,
            "detected_label": detected_label,
        }

    scores = [0.8 if label == canonical_label else 0.0 for label in MATERIAL_LABELS]
    return {
        "top_predictions": [(canonical_label, CONFIDENT_SCORE)],
        "scores": scores,
        "top1_score": CONFIDENT_SCORE,
        "top2_score": 0.0,
        "margin": CONFIDENT_SCORE,
        "detected_label": detected_label,
        "category": LABEL_TO_CATEGORY[canonical_label],
    }
