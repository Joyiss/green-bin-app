from __future__ import annotations

from typing import Any

try:
    from ..rules import get_rules
except ImportError:
    from rules import get_rules


def _empty_guidance() -> dict[str, Any]:
    return {
        "disposal_action": None,
        "material_code": None,
        "impact_level": None,
        "steps": [],
    }


def _open_guidance_unavailable(classification: dict[str, Any]) -> dict[str, Any]:
    recognized_material = classification.get("recognized_material_category")
    steps = ["Trusted disposal guidance is not available yet for this recognized item."]
    if isinstance(recognized_material, str) and recognized_material and recognized_material != "Unknown":
        steps.append(f"Detected material category: {recognized_material}.")
    steps.append("Use local guidance or scan a supported item for trusted disposal instructions.")

    return {
        "disposal_action": None,
        "material_code": None,
        "impact_level": "Trusted Guidance Unavailable",
        "steps": steps,
    }


def _format_item_name(item: str) -> str:
    if not item:
        return ""

    words = []
    for word in item.split():
        if "-" in word:
            parts = [
                part if part.isupper() else part.capitalize()
                for part in word.split("-")
            ]
            words.append("-".join(parts))
        else:
            words.append(word if word.isupper() else word.capitalize())

    return " ".join(words)


def _serialize_candidates(candidates: list[tuple[str, float]]) -> list[dict[str, Any]]:
    return [
        {
            "label": label.title(),
            "score": round(float(score), 4),
        }
        for label, score in candidates
    ]


def build_prediction_response(classification: dict[str, Any]) -> dict[str, Any]:
    if (
        classification.get("status") == "confident"
        and classification.get("trusted_guidance_available") is False
    ):
        guidance = _open_guidance_unavailable(classification)
    else:
        guidance = (
            get_rules(classification["category"])
            if classification["status"] == "confident"
            else _empty_guidance()
        )

    response = {
        "item": _format_item_name(classification["item"]),
        "category": classification["category"],
        "status": classification["status"],
        "candidates": _serialize_candidates(classification.get("candidates", [])),
        "disposal_action": guidance["disposal_action"],
        "material_code": guidance["material_code"],
        "impact_level": guidance["impact_level"],
        "steps": guidance["steps"],
    }

    if "cache_hit" in classification:
        response["cache_hit"] = bool(classification["cache_hit"])
    if "recognition_source" in classification:
        response["recognition_source"] = classification["recognition_source"]

    return response
