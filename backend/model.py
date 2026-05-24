import base64
import io
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

from .materials import LABEL_TO_CATEGORY, MATERIAL_LABELS, build_material_selection_prompt, resolve_material_label

load_dotenv(Path(__file__).resolve().parent / ".env")

CONFIDENT_THRESHOLD = 0.20
MARGIN_THRESHOLD = 0.05

API_URL = os.getenv("MODELBEST_API_URL", "https://api.modelbest.cn/v1/chat/completions")
API_KEY = os.getenv("MODELBEST_API_KEY", "")
MODEL_ID = "MiniCPM-V-4.6-Thinking"
DETECTION_PROMPT = build_material_selection_prompt()


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


def detect_object(image: Image.Image) -> str:
    try:
        if not API_KEY:
            raise RuntimeError("MODELBEST_API_KEY is not set in backend/.env.")

        rgb_image = image.convert("RGB")
        buffer = io.BytesIO()
        rgb_image.save(buffer, format="JPEG", quality=75)
        img_bytes = buffer.getvalue()
        img_str = base64.b64encode(img_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{img_str}"

        payload = {
            "model": MODEL_ID,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": DETECTION_PROMPT},
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
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        response_json = response.json()
        raw_output = response_json["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"ModelBest API error: {exc}")
        return ""

    cleaned_label = _clean_generated_label(raw_output)
    print(f"ModelBest raw output: {raw_output!r}")
    print(f"ModelBest cleaned label: {cleaned_label!r}")
    return cleaned_label


def get_top_predictions(image: Image.Image) -> dict[str, object]:
    detected_label = detect_object(image)
    canonical_label = resolve_material_label(detected_label)
    print(f"MiniCPM canonical label: {canonical_label!r}")

    if canonical_label is None:
        return {
            "top_predictions": [],
            "scores": [0.0 for _ in MATERIAL_LABELS],
            "top1_score": 0.0,
            "top2_score": 0.0,
            "margin": 0.0,
            "detected_label": detected_label,
        }

    scores = [1.0 if label == canonical_label else 0.0 for label in MATERIAL_LABELS]
    return {
        "top_predictions": [(canonical_label, 1.0)],
        "scores": scores,
        "top1_score": 1.0,
        "top2_score": 0.0,
        "margin": 1.0,
        "detected_label": detected_label,
        "category": LABEL_TO_CATEGORY[canonical_label],
    }
