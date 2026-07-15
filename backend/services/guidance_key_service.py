from __future__ import annotations

import re
from typing import Any


def normalize_guidance_key(value: Any) -> str | None:
    if value is None:
        return None

    normalized_value = str(value).strip().lower()
    if not normalized_value:
        return None

    normalized_value = re.sub(r"[^a-z0-9]+", "_", normalized_value)
    normalized_value = normalized_value.strip("_")
    return normalized_value or None


def normalize_guidance_phrase(value: Any) -> str | None:
    if value is None:
        return None

    normalized_value = str(value).strip().lower()
    if not normalized_value:
        return None

    normalized_value = normalized_value.replace("_", " ")
    normalized_value = re.sub(r"[^a-z0-9]+", " ", normalized_value)
    normalized_value = re.sub(r"\s+", " ", normalized_value)
    normalized_value = normalized_value.strip()
    return normalized_value or None


def _singularize_word(word: str) -> str:
    if len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return f"{word[:-3]}y"
    if word.endswith("sses") or word.endswith("shes") or word.endswith("ches"):
        return word[:-2]
    if word.endswith("xes") or word.endswith("zes"):
        return word[:-2]
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]
    if word.endswith("ses") and not word.endswith("ss") and len(word) > 4:
        return word[:-1]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def normalize_guidance_label_for_match(value: Any) -> str | None:
    normalized_phrase = normalize_guidance_phrase(value)
    if normalized_phrase is None:
        return None

    singular_terms = [_singularize_word(term) for term in normalized_phrase.split()]
    normalized_label = " ".join(term for term in singular_terms if term)
    return normalized_label or None


def labels_match_conservatively(left: Any, right: Any) -> bool:
    normalized_left = normalize_guidance_label_for_match(left)
    normalized_right = normalize_guidance_label_for_match(right)
    if normalized_left is None or normalized_right is None:
        return False

    return normalized_left == normalized_right
