from __future__ import annotations

import logging
import re
from typing import Any

try:
    from ..materials import resolve_material_label
except ImportError:
    from materials import resolve_material_label


logger = logging.getLogger(__name__)

UNKNOWN_VALUE = "Unknown"

_MATERIAL_CATEGORIES = {
    "plastic": "Plastic",
    "metal": "Metal",
    "ceramic": "Ceramic",
    "glass": "Glass",
    "paper": "Paper",
    "cardboard": "Cardboard",
    "food-soiled cardboard": "Food-soiled cardboard",
    "electronics": "Electronics",
    "battery": "Battery",
    "hazardous": "Hazardous",
    "organic": "Organic",
    "wood": "Wood",
    "unknown": UNKNOWN_VALUE,
}

_BROAD_CATEGORIES = {
    "drinkware": "Drinkware",
    "household item": "Household item",
    "electronics": "Electronics",
    "packaging": "Packaging",
    "food packaging": "Food packaging",
    "paper product": "Paper product",
    "organic waste": "Organic waste",
    "hazardous household item": "Hazardous household item",
    "unknown": UNKNOWN_VALUE,
}

_CONDITION_FLAG_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("food_soiled", ("greasy", "grease", "food-soiled", "food soiled", "soiled")),
    ("empty", ("empty",)),
    ("broken", ("broken", "cracked", "shattered", "damaged")),
    ("wet", ("wet", "soaked", "damp")),
]

_SPECIAL_FLAG_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (
        "battery",
        ("battery", "batteries", "lithium", "alkaline", "rechargeable", "vape"),
    ),
    (
        "hazardous",
        (
            "hazardous",
            "paint",
            "propane",
            "motor oil",
            "medication",
            "chemical",
            "aerosol",
            "cleaning spray",
            "light bulb",
        ),
    ),
    (
        "electronics",
        (
            "phone",
            "iphone",
            "android",
            "mobile",
            "charger",
            "charging cable",
            "cable",
            "cord",
            "usb",
            "adapter",
            "electronics",
            "electronic",
            "computer",
            "laptop",
            "tablet",
            "monitor",
            "printer",
            "tv",
            "television",
            "keyboard",
            "mouse",
            "remote",
            "headphone",
            "earbud",
        ),
    ),
]

_EXACT_LABEL_ALIASES = {
    "ceramic coffee mug": "Ceramic mug",
    "iphone charging cable": "Charging cable",
    "phone charger": "Phone charger",
    "empty yogurt cup": "Yogurt cup",
    "greasy pizza box": "Pizza box",
    "stainless steel water bottle": "Water bottle",
}

_GENERIC_SHAPE_TERMS = {
    "bag",
    "bottle",
    "box",
    "cable",
    "can",
    "charger",
    "container",
    "cord",
    "cup",
    "frame",
    "item",
    "jar",
    "lid",
    "mug",
    "packaging",
    "piece",
    "product",
    "tube",
    "wrapper",
}

_METAL_HINT_TERMS = ("stainless steel", "stainless", "steel", "aluminum", "aluminium", "metal")
_PLASTIC_HINT_TERMS = ("plastic", "pet", "pete")


def _clean_text(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[_/]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s\-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _title_case_label(value: str) -> str:
    if not value:
        return UNKNOWN_VALUE

    words = []
    for word in value.split():
        if not word:
            continue
        if "-" in word:
            parts = [part.capitalize() for part in word.split("-") if part]
            words.append("-".join(parts))
        else:
            words.append(word.capitalize())
    return " ".join(words) if words else UNKNOWN_VALUE


def _extract_flags(normalized_text: str) -> tuple[list[str], list[str]]:
    condition_flags: list[str] = []
    for flag, patterns in _CONDITION_FLAG_PATTERNS:
        if any(pattern in normalized_text for pattern in patterns):
            condition_flags.append(flag)

    special_flags: list[str] = []
    for flag, patterns in _SPECIAL_FLAG_PATTERNS:
        if any(pattern in normalized_text for pattern in patterns):
            special_flags.append(flag)

    if "electronics" in special_flags and "dropoff_recommended" not in special_flags:
        special_flags.append("dropoff_recommended")
    if "battery" in special_flags and "dropoff_recommended" not in special_flags:
        special_flags.append("dropoff_recommended")
    if "hazardous" in special_flags and "dropoff_recommended" not in special_flags:
        special_flags.append("dropoff_recommended")

    return condition_flags, special_flags


def _normalize_item_label(normalized_text: str) -> tuple[str, str]:
    if not normalized_text:
        return UNKNOWN_VALUE, "unknown_fallback"

    exact_alias = _EXACT_LABEL_ALIASES.get(normalized_text)
    if exact_alias is not None:
        return exact_alias, "exact_alias"

    if "coffee mug" in normalized_text and "ceramic" in normalized_text:
        return "Ceramic mug", "keyword_rule"
    if "mug" in normalized_text:
        if "ceramic" in normalized_text:
            return "Ceramic mug", "keyword_rule"
        return "Mug", "keyword_rule"

    if "charger" in normalized_text:
        if any(term in normalized_text for term in ("phone", "iphone", "mobile", "usb")):
            return "Phone charger", "keyword_rule"
        return "Charger", "keyword_rule"

    if "cable" in normalized_text or "cord" in normalized_text:
        if any(
            term in normalized_text
            for term in ("charging", "charger", "phone", "iphone", "mobile", "usb")
        ):
            return "Charging cable", "keyword_rule"
        return "Cable", "keyword_rule"

    if "yogurt" in normalized_text and (
        "cup" in normalized_text or "container" in normalized_text
    ):
        return "Yogurt cup", "keyword_rule"

    if "pizza" in normalized_text and "box" in normalized_text:
        return "Pizza box", "keyword_rule"

    if "water" in normalized_text and "bottle" in normalized_text:
        return "Water bottle", "keyword_rule"

    return _title_case_label(normalized_text), "clean_fallback"


def _map_material_hint(value: str) -> str:
    normalized_value = _clean_text(value)
    if not normalized_value:
        return UNKNOWN_VALUE
    if any(term in normalized_value for term in _METAL_HINT_TERMS):
        return _MATERIAL_CATEGORIES["metal"]
    if "ceramic" in normalized_value:
        return _MATERIAL_CATEGORIES["ceramic"]
    if "glass" in normalized_value:
        return _MATERIAL_CATEGORIES["glass"]
    if any(term in normalized_value for term in _PLASTIC_HINT_TERMS):
        return _MATERIAL_CATEGORIES["plastic"]
    if "cardboard" in normalized_value:
        return _MATERIAL_CATEGORIES["cardboard"]
    if "paper" in normalized_value:
        return _MATERIAL_CATEGORIES["paper"]
    if "electronic" in normalized_value:
        return _MATERIAL_CATEGORIES["electronics"]
    if "battery" in normalized_value:
        return _MATERIAL_CATEGORIES["battery"]
    if "hazard" in normalized_value:
        return _MATERIAL_CATEGORIES["hazardous"]
    if "organic" in normalized_value:
        return _MATERIAL_CATEGORIES["organic"]
    if "wood" in normalized_value:
        return _MATERIAL_CATEGORIES["wood"]
    return UNKNOWN_VALUE


def _infer_material_category(
    item_label: str,
    normalized_text: str,
    likely_material: str,
    condition_flags: list[str],
    special_flags: list[str],
) -> str:
    hinted_material = _map_material_hint(likely_material)

    if item_label == "Pizza box" and "food_soiled" in condition_flags:
        return _MATERIAL_CATEGORIES["food-soiled cardboard"]
    if item_label == "Water bottle":
        if any(term in normalized_text for term in _METAL_HINT_TERMS):
            return _MATERIAL_CATEGORIES["metal"]
        if any(term in normalized_text for term in _PLASTIC_HINT_TERMS):
            return _MATERIAL_CATEGORIES["plastic"]
        if hinted_material in {"Metal", "Plastic", "Glass"}:
            return hinted_material
        return UNKNOWN_VALUE
    if item_label == "Yogurt cup":
        if hinted_material == "Plastic":
            return hinted_material
        if any(term in normalized_text for term in _PLASTIC_HINT_TERMS):
            return _MATERIAL_CATEGORIES["plastic"]
        return _MATERIAL_CATEGORIES["plastic"]
    if item_label == "Ceramic mug":
        return _MATERIAL_CATEGORIES["ceramic"]
    if item_label == "Mug" and "ceramic" in normalized_text:
        return _MATERIAL_CATEGORIES["ceramic"]
    if item_label == "Wooden picture frame" or "wood" in normalized_text:
        return _MATERIAL_CATEGORIES["wood"]
    if "battery" in special_flags:
        return _MATERIAL_CATEGORIES["battery"]
    if "hazardous" in special_flags:
        return _MATERIAL_CATEGORIES["hazardous"]
    if "electronics" in special_flags:
        return _MATERIAL_CATEGORIES["electronics"]

    if hinted_material != UNKNOWN_VALUE:
        return hinted_material

    return UNKNOWN_VALUE


def _map_broad_category_hint(value: str) -> str:
    normalized_value = _clean_text(value)
    if not normalized_value:
        return UNKNOWN_VALUE
    if "drinkware" in normalized_value or "bottle" in normalized_value:
        return _BROAD_CATEGORIES["drinkware"]
    if "electronics" in normalized_value:
        return _BROAD_CATEGORIES["electronics"]
    if "food packaging" in normalized_value:
        return _BROAD_CATEGORIES["food packaging"]
    if "packaging" in normalized_value:
        return _BROAD_CATEGORIES["packaging"]
    if "paper" in normalized_value:
        return _BROAD_CATEGORIES["paper product"]
    if "organic" in normalized_value:
        return _BROAD_CATEGORIES["organic waste"]
    if "hazard" in normalized_value:
        return _BROAD_CATEGORIES["hazardous household item"]
    if "household" in normalized_value:
        return _BROAD_CATEGORIES["household item"]
    return UNKNOWN_VALUE


def _infer_broad_category(
    item_label: str,
    raw_broad_category: str,
    special_flags: list[str],
) -> str:
    if item_label in {"Ceramic mug", "Mug", "Water bottle"}:
        return _BROAD_CATEGORIES["drinkware"]
    if item_label in {"Yogurt cup", "Pizza box"}:
        return _BROAD_CATEGORIES["food packaging"]
    if item_label in {"Charging cable", "Phone charger", "Charger", "Cable"}:
        return _BROAD_CATEGORIES["electronics"]
    if "hazardous" in special_flags:
        return _BROAD_CATEGORIES["hazardous household item"]
    if "electronics" in special_flags:
        return _BROAD_CATEGORIES["electronics"]

    hinted_category = _map_broad_category_hint(raw_broad_category)
    if hinted_category != UNKNOWN_VALUE:
        return hinted_category

    if item_label in {UNKNOWN_VALUE, ""}:
        return UNKNOWN_VALUE
    return _BROAD_CATEGORIES["household item"]


def _normalize_candidate_label(value: Any) -> str:
    return _clean_text(value)


def _labels_are_consistent(primary_label: str, candidate_label: str) -> bool:
    primary = _normalize_candidate_label(primary_label)
    candidate = _normalize_candidate_label(candidate_label)
    if not primary or not candidate:
        return False
    if primary == candidate:
        return True
    if primary in candidate or candidate in primary:
        return True

    primary_terms = {term for term in primary.split() if term}
    candidate_terms = {term for term in candidate.split() if term}
    if not primary_terms or not candidate_terms:
        return False

    primary_specific_terms = primary_terms - _GENERIC_SHAPE_TERMS
    candidate_specific_terms = candidate_terms - _GENERIC_SHAPE_TERMS
    if primary_specific_terms and candidate_specific_terms:
        return primary_specific_terms == candidate_specific_terms

    overlap = len(primary_terms & candidate_terms)
    smaller_size = min(len(primary_terms), len(candidate_terms))
    return smaller_size > 0 and (overlap / smaller_size) >= 0.75


def _resolve_supported_label_from_candidates(
    normalized_item_label: str,
    material_category: str,
    candidates: Any,
) -> str | None:
    if not isinstance(candidates, list):
        return None

    for candidate in candidates[:3]:
        if not isinstance(candidate, dict):
            continue

        candidate_label = str(candidate.get("label") or "").strip()
        if not candidate_label:
            continue

        if not _labels_are_consistent(normalized_item_label, candidate_label):
            continue

        confidence = candidate.get("confidence")
        if confidence is None:
            if not _normalize_candidate_label(normalized_item_label) == _normalize_candidate_label(
                candidate_label
            ):
                continue
        else:
            try:
                if float(confidence) < 0.85:
                    continue
            except (TypeError, ValueError):
                continue

        resolved_label = resolve_material_label(candidate_label)
        if resolved_label is not None and _supported_label_matches_material(
            resolved_label,
            material_category,
        ):
            return resolved_label

    return None


def _supported_label_matches_material(
    supported_label: str,
    material_category: str,
) -> bool:
    normalized_supported_label = _normalize_candidate_label(supported_label)
    if material_category == "Metal":
        return not any(term in normalized_supported_label for term in ("plastic",))
    if material_category == "Plastic":
        return "plastic" in normalized_supported_label or "yogurt container" in normalized_supported_label
    return True


def _resolve_supported_label_from_primary(
    item_label: str,
    raw_item_label: str,
    likely_material: str,
    material_category: str,
) -> str | None:
    if item_label in {"", UNKNOWN_VALUE}:
        return None

    normalized_raw_item = _clean_text(raw_item_label)
    normalized_likely_material = _clean_text(likely_material)

    if item_label == "Water bottle":
        raw_has_plastic = any(term in normalized_raw_item for term in _PLASTIC_HINT_TERMS)
        material_has_plastic = any(
            term in normalized_likely_material for term in _PLASTIC_HINT_TERMS
        )
        if material_category != "Plastic" or not (raw_has_plastic or material_has_plastic):
            return None

    resolved_label = resolve_material_label(item_label)
    if resolved_label is None:
        return None
    if not _supported_label_matches_material(resolved_label, material_category):
        return None
    return resolved_label


def normalize_open_recognition(recognition_details: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(recognition_details, dict):
        return recognition_details

    raw_item_label = recognition_details.get("raw_item_label", "")
    likely_material = recognition_details.get("likely_material", "")
    raw_broad_category = recognition_details.get("broad_category", "")
    candidates = recognition_details.get("candidates", [])

    normalized_text = _clean_text(raw_item_label)
    condition_flags, special_flags = _extract_flags(normalized_text)
    item_label, normalization_source = _normalize_item_label(normalized_text)
    material_category = _infer_material_category(
        item_label,
        normalized_text,
        str(likely_material or ""),
        condition_flags,
        special_flags,
    )
    broad_category = _infer_broad_category(
        item_label,
        str(raw_broad_category or ""),
        special_flags,
    )

    matched_supported_label = None
    if item_label not in {"", UNKNOWN_VALUE}:
        matched_supported_label = _resolve_supported_label_from_primary(
            item_label,
            str(raw_item_label or ""),
            str(likely_material or ""),
            material_category,
        )
    if matched_supported_label is None:
        matched_supported_label = _resolve_supported_label_from_candidates(
            item_label,
            material_category,
            candidates,
        )

    normalized_payload = {
        "item_label": item_label,
        "material_category": material_category,
        "broad_category": broad_category,
        "condition_flags": condition_flags,
        "special_handling_flags": special_flags,
        "matched_supported_label": matched_supported_label,
        "normalization_source": normalization_source,
    }

    enriched_details = {
        **recognition_details,
        "normalized": normalized_payload,
    }

    logger.info(
        "Open recognition normalized. raw_label=%s normalized_item=%s material_category=%s broad_category=%s condition_flags=%s special_flags=%s matched_supported_label=%s",
        raw_item_label,
        normalized_payload["item_label"],
        normalized_payload["material_category"],
        normalized_payload["broad_category"],
        normalized_payload["condition_flags"],
        normalized_payload["special_handling_flags"],
        normalized_payload["matched_supported_label"],
    )

    return enriched_details


def labels_are_consistent_for_matching(primary_label: str, candidate_label: str) -> bool:
    return _labels_are_consistent(primary_label, candidate_label)
