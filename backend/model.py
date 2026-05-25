import base64
import io
import json
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

from .materials import (
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

API_URL = os.getenv("MODELBEST_API_URL", "https://api.modelbest.cn/v1/chat/completions")
API_KEY = os.getenv("MODELBEST_API_KEY", "")
MODEL_ID = "MiniCPM-V-4.6-Thinking"
DETECTION_PROMPT = build_material_selection_prompt()
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

    start_index = raw_text.find("{")
    if start_index == -1:
        raise ValueError("No JSON object found in model response.")

    json_text = raw_text[start_index:]
    decoder = json.JSONDecoder()
    parsed, _end_index = decoder.raw_decode(json_text)
    if not isinstance(parsed, dict):
        raise ValueError("Parsed model response JSON is not an object.")

    return parsed


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


def _build_payload(data_uri: str, prompt_text: str) -> dict[str, object]:
    return {
        "model": MODEL_ID,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_uri,
                        },
                    },
                ],
            }
        ],
    }


def _call_modelbest(data_uri: str, prompt_text: str) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        API_URL,
        headers=headers,
        json=_build_payload(data_uri, prompt_text),
        timeout=60,
    )
    response.raise_for_status()
    response_json = response.json()
    return response_json["choices"][0]["message"]["content"]


def _parse_detection_result(raw_output: str) -> dict[str, object]:
    parsed_output = _extract_json_object(raw_output)
    status = str(parsed_output.get("status", "")).strip().lower()
    primary_label = _clean_generated_label(str(parsed_output.get("primary_label", "")))
    raw_candidate_labels = parsed_output.get("candidate_labels", [])
    if not isinstance(raw_candidate_labels, list):
        raw_candidate_labels = []

    cleaned_raw_candidate_labels = [
        _clean_generated_label(str(label))
        for label in raw_candidate_labels
        if str(label).strip()
    ]
    cleaned_candidate_labels = list(cleaned_raw_candidate_labels)
    if primary_label:
        cleaned_candidate_labels.insert(0, primary_label)

    normalized_candidates = _normalize_candidate_labels(cleaned_candidate_labels)[:3]
    normalized_raw_candidates = _normalize_candidate_labels(cleaned_raw_candidate_labels)
    normalized_primary = resolve_material_label(primary_label)
    if normalized_primary is None and normalized_candidates:
        normalized_primary = normalized_candidates[0]

    normalized_status = status if status in {"confident", "uncertain"} else "unknown"
    distinct_raw_candidates = [
        candidate
        for candidate in normalized_raw_candidates
        if candidate and candidate != (normalized_primary or "")
    ]

    if normalized_status == "confident" and normalized_primary is None:
        normalized_status = "unknown"
    if (
        normalized_status == "confident"
        and normalized_primary
        and normalized_primary not in normalized_raw_candidates
        and len(distinct_raw_candidates) >= 2
    ):
        normalized_status = "uncertain"
    if normalized_status == "uncertain" and len(normalized_candidates) < 2:
        normalized_status = "unknown"

    return {
        "status": normalized_status,
        "primary_label": normalized_primary or "",
        "candidate_labels": normalized_candidates,
        "raw_output": raw_output,
    }


def _maybe_verify_confident_result(
    data_uri: str,
    result: dict[str, object],
) -> dict[str, object]:
    if str(result.get("status", "unknown")) != "confident":
        return result

    primary_label = str(result.get("primary_label", "")).strip()
    if not primary_label:
        return result

    verification_prompt = build_multi_object_verification_prompt(primary_label)
    verification_output = _call_modelbest(data_uri, verification_prompt)
    print(f"ModelBest verification raw output: {verification_output!r}")
    verification_result = _parse_detection_result(verification_output)
    print(f"ModelBest verification parsed result: {verification_result!r}")

    if (
        str(verification_result.get("status", "unknown")) == "uncertain"
        and len(verification_result.get("candidate_labels", [])) >= 2
    ):
        return verification_result

    return result


def detect_object(image: Image.Image) -> dict[str, object]:
    try:
        if not API_KEY:
            raise RuntimeError("MODELBEST_API_KEY is not set in backend/.env.")

        rgb_image = image.convert("RGB")
        buffer = io.BytesIO()
        rgb_image.save(buffer, format="JPEG", quality=75)
        img_bytes = buffer.getvalue()
        img_str = base64.b64encode(img_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{img_str}"
        raw_output = _call_modelbest(data_uri, DETECTION_PROMPT)
        result = _parse_detection_result(raw_output)
        print(f"ModelBest raw output: {raw_output!r}")

        raw_parsed = _extract_json_object(raw_output)
        raw_status = str(raw_parsed.get("status", "")).strip().lower()
        if raw_status == "uncertain" and len(result["candidate_labels"]) < 2:
            fallback_prompt = build_uncertain_fallback_prompt(str(raw_parsed.get("primary_label", "")).strip())
            fallback_output = _call_modelbest(data_uri, fallback_prompt)
            print(f"ModelBest fallback raw output: {fallback_output!r}")
            fallback_result = _parse_detection_result(fallback_output)
            if len(fallback_result["candidate_labels"]) >= 2:
                print(f"ModelBest parsed fallback result: {fallback_result!r}")
                return fallback_result

        result = _maybe_verify_confident_result(data_uri, result)
    except Exception as exc:
        print(f"ModelBest API error: {exc}")
        return {
            "status": "unknown",
            "primary_label": "",
            "candidate_labels": [],
            "raw_output": "",
        }

    print(f"ModelBest parsed result: {result!r}")
    return result


def get_top_predictions(image: Image.Image) -> dict[str, object]:
    detection_result = detect_object(image)
    detection_status = str(detection_result.get("status", "unknown"))
    primary_label = str(detection_result.get("primary_label", "")).strip()
    candidate_labels = detection_result.get("candidate_labels", [])
    if not isinstance(candidate_labels, list):
        candidate_labels = []

    print(f"MiniCPM detection status: {detection_status!r}")
    print(f"MiniCPM candidate labels: {candidate_labels!r}")

    if detection_status == "confident" and primary_label:
        scores = [CONFIDENT_SCORE if label == primary_label else 0.0 for label in MATERIAL_LABELS]
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

    scores = [CONFIDENT_SCORE if label == canonical_label else 0.0 for label in MATERIAL_LABELS]
    return {
        "top_predictions": [(canonical_label, CONFIDENT_SCORE)],
        "scores": scores,
        "top1_score": CONFIDENT_SCORE,
        "top2_score": 0.0,
        "margin": CONFIDENT_SCORE,
        "detected_label": detected_label,
        "category": LABEL_TO_CATEGORY[canonical_label],
    }
