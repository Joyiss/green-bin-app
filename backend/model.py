from __future__ import annotations

import requests
from PIL import Image

try:
    from .materials import LABEL_TO_CATEGORY, MATERIAL_LABELS, resolve_material_label
    from .services import vlm_service
except ImportError:
    from materials import LABEL_TO_CATEGORY, MATERIAL_LABELS, resolve_material_label
    from services import vlm_service

CONFIDENT_THRESHOLD = vlm_service.CONFIDENT_THRESHOLD
MARGIN_THRESHOLD = vlm_service.MARGIN_THRESHOLD

CLOUDFLARE_API_BASE_URL = vlm_service.CLOUDFLARE_API_BASE_URL
CLOUDFLARE_ACCOUNT_ID = vlm_service.CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN = vlm_service.CLOUDFLARE_API_TOKEN
CLOUDFLARE_AI_MODEL = vlm_service.CLOUDFLARE_AI_MODEL
DETECTION_PROMPT = vlm_service.DETECTION_PROMPT
DETECTION_RESPONSE_SCHEMA = vlm_service.DETECTION_RESPONSE_SCHEMA
VERIFICATION_RESPONSE_SCHEMA = vlm_service.VERIFICATION_RESPONSE_SCHEMA
CONFIDENT_SCORE = vlm_service.CONFIDENT_SCORE
CONFIDENT_SCORE_STEP = vlm_service.CONFIDENT_SCORE_STEP
UNCERTAIN_TOP_SCORE = vlm_service.UNCERTAIN_TOP_SCORE
UNCERTAIN_SCORE_STEP = vlm_service.UNCERTAIN_SCORE_STEP


def _sync_service_config() -> None:
    vlm_service.CLOUDFLARE_API_BASE_URL = CLOUDFLARE_API_BASE_URL
    vlm_service.CLOUDFLARE_ACCOUNT_ID = CLOUDFLARE_ACCOUNT_ID
    vlm_service.CLOUDFLARE_API_TOKEN = CLOUDFLARE_API_TOKEN
    vlm_service.CLOUDFLARE_AI_MODEL = CLOUDFLARE_AI_MODEL
    vlm_service.DETECTION_PROMPT = DETECTION_PROMPT
    vlm_service.DETECTION_RESPONSE_SCHEMA = DETECTION_RESPONSE_SCHEMA
    vlm_service.VERIFICATION_RESPONSE_SCHEMA = VERIFICATION_RESPONSE_SCHEMA
    vlm_service.CONFIDENT_SCORE = CONFIDENT_SCORE
    vlm_service.CONFIDENT_SCORE_STEP = CONFIDENT_SCORE_STEP
    vlm_service.UNCERTAIN_TOP_SCORE = UNCERTAIN_TOP_SCORE
    vlm_service.UNCERTAIN_SCORE_STEP = UNCERTAIN_SCORE_STEP


def detect_object(image: Image.Image) -> dict[str, object]:
    _sync_service_config()
    return vlm_service.detect_object(image)


def get_top_predictions(image: Image.Image) -> dict[str, object]:
    detection_result = detect_object(image)
    return vlm_service.build_prediction_result(detection_result)


__all__ = [
    "CONFIDENT_THRESHOLD",
    "MARGIN_THRESHOLD",
    "CLOUDFLARE_API_BASE_URL",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_AI_MODEL",
    "DETECTION_PROMPT",
    "DETECTION_RESPONSE_SCHEMA",
    "VERIFICATION_RESPONSE_SCHEMA",
    "CONFIDENT_SCORE",
    "CONFIDENT_SCORE_STEP",
    "UNCERTAIN_TOP_SCORE",
    "UNCERTAIN_SCORE_STEP",
    "requests",
    "LABEL_TO_CATEGORY",
    "MATERIAL_LABELS",
    "resolve_material_label",
    "detect_object",
    "get_top_predictions",
]
