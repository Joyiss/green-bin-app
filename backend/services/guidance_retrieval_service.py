from __future__ import annotations

from typing import Any

try:
    from .guidance_key_service import (
        labels_match_conservatively,
        normalize_guidance_label_for_match,
        normalize_guidance_phrase,
    )
    from .guidance_source_loader import load_trusted_guidance_chunks
except ImportError:
    from services.guidance_key_service import (
        labels_match_conservatively,
        normalize_guidance_label_for_match,
        normalize_guidance_phrase,
    )
    from services.guidance_source_loader import load_trusted_guidance_chunks

MIN_RETRIEVAL_SCORE = 3.0
_GENERIC_MATERIALS = {"metal", "plastic", "paper", "glass", "cardboard"}


def _normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized_values: list[str] = []
    for value in values:
        normalized_value = normalize_guidance_phrase(value)
        if normalized_value:
            normalized_values.append(normalized_value)

    return normalized_values


def _normalize_condition_flags(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized_values: list[str] = []
    for value in values:
        normalized_value = normalize_guidance_phrase(value)
        if normalized_value:
            normalized_values.append(normalized_value.replace(" ", "_"))

    return normalized_values


def _location_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _location_matches_nyc(location: dict[str, Any] | None) -> bool:
    if not isinstance(location, dict):
        return False

    city_values = (
        location.get("city"),
        location.get("locality"),
        location.get("metro"),
    )
    state_values = (
        location.get("state"),
        location.get("region"),
        location.get("province"),
        location.get("state_code"),
    )

    city_match = any(
        "new york city" in _location_text(value) or _location_text(value) == "nyc"
        for value in city_values
    )
    state_match = any(
        _location_text(value) in {"ny", "new york"} for value in state_values
    )
    return city_match or state_match


def _location_matches_california(location: dict[str, Any] | None) -> bool:
    if not isinstance(location, dict):
        return False

    state_values = (
        location.get("state"),
        location.get("region"),
        location.get("province"),
        location.get("state_code"),
    )
    return any(
        _location_text(value) in {"ca", "california"} for value in state_values
    )


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
    ).lower()
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
    ).lower()
    return "calrecycle" in haystack or "state: california" in haystack


def _chunk_is_location_allowed(
    chunk: dict[str, Any],
    location: dict[str, Any] | None,
) -> bool:
    if chunk.get("generalizable") is True:
        return True

    if _is_dsny_chunk(chunk):
        return _location_matches_nyc(location)

    if _is_calrecycle_chunk(chunk):
        return _location_matches_california(location)

    if chunk.get("requires_location_check") is True:
        return True

    location_scope = _location_text(chunk.get("location_scope"))
    if not location_scope or location_scope == "national":
        return True

    return False


def _chunk_is_general_fallback(chunk: dict[str, Any]) -> bool:
    applies_to = chunk.get("applies_to") or {}
    return not any(
        [
            applies_to.get("item_labels"),
            applies_to.get("materials"),
            applies_to.get("categories"),
            applies_to.get("condition_flags"),
        ]
    )


def _score_chunk(
    chunk: dict[str, Any],
    *,
    item_label: str | None,
    material: str | None,
    category: str | None,
    condition_flags: list[str],
) -> tuple[float, list[str]]:
    applies_to = chunk.get("applies_to") or {}
    matched_fields: list[str] = []
    score = 0.0
    has_primary_semantic_match = False
    is_general_fallback = _chunk_is_general_fallback(chunk)

    normalized_item = normalize_guidance_phrase(item_label)
    normalized_item_singular = normalize_guidance_label_for_match(item_label)
    chunk_item_labels = applies_to.get("item_labels") or []
    if normalized_item:
        for chunk_item_label in chunk_item_labels:
            if normalize_guidance_phrase(chunk_item_label) == normalized_item:
                score += 8.0
                matched_fields.append("item_label_exact")
                has_primary_semantic_match = True
                break
        else:
            if any(
                labels_match_conservatively(chunk_item_label, normalized_item_singular)
                for chunk_item_label in chunk_item_labels
            ):
                score += 6.0
                matched_fields.append("item_label_normalized")
                has_primary_semantic_match = True

    normalized_material = normalize_guidance_label_for_match(material)
    chunk_materials = applies_to.get("materials") or []
    material_match = False
    if normalized_material:
        material_match = any(
            labels_match_conservatively(chunk_material, normalized_material)
            for chunk_material in chunk_materials
        )
        if material_match:
            score += 4.0
            matched_fields.append("material")
            has_primary_semantic_match = True

    normalized_category = normalize_guidance_label_for_match(category)
    chunk_categories = applies_to.get("categories") or []
    if normalized_category and any(
        labels_match_conservatively(chunk_category, normalized_category)
        for chunk_category in chunk_categories
    ):
        score += 3.0
        matched_fields.append("category")
        has_primary_semantic_match = True

    if score == 0.0 and is_general_fallback:
        score += 3.0
        matched_fields.append("general_fallback")
        has_primary_semantic_match = True

    chunk_condition_flags = _normalize_condition_flags(applies_to.get("condition_flags"))
    normalized_condition_flags = _normalize_condition_flags(condition_flags)
    overlapping_flags = sorted(set(chunk_condition_flags) & set(normalized_condition_flags))
    if overlapping_flags and has_primary_semantic_match:
        score += 1.5 * len(overlapping_flags)
        matched_fields.append("condition_flags")

    if (
        material_match
        and "category" not in matched_fields
        and "item_label_exact" not in matched_fields
        and "item_label_normalized" not in matched_fields
        and normalized_material in _GENERIC_MATERIALS
    ):
        score = 0.0
        matched_fields = []

    if chunk.get("human_reviewed") is True:
        score += 1.0
    elif chunk.get("source_grounded") is True:
        score += 0.25

    if chunk.get("verified") is True:
        score += 0.1

    return score, matched_fields


def retrieve_guidance_chunks(
    *,
    item_label: str | None,
    material: str | None,
    category: str | None,
    condition_flags: list[str] | None = None,
    location: dict[str, Any] | None = None,
    chunks: list[dict[str, Any]] | None = None,
    min_score: float = MIN_RETRIEVAL_SCORE,
) -> list[dict[str, Any]]:
    candidate_chunks = (
        list(chunks) if isinstance(chunks, list) else load_trusted_guidance_chunks()
    )
    normalized_condition_flags = _normalize_condition_flags(condition_flags or [])

    matches: list[dict[str, Any]] = []
    for chunk in candidate_chunks:
        if not _chunk_is_location_allowed(chunk, location):
            continue

        score, matched_fields = _score_chunk(
            chunk,
            item_label=item_label,
            material=material,
            category=category,
            condition_flags=normalized_condition_flags,
        )
        if score < min_score:
            continue

        matches.append(
            {
                "chunk": chunk,
                "chunk_id": chunk.get("id"),
                "score": round(score, 4),
                "matched_fields": matched_fields,
                "requires_location_check": bool(chunk.get("requires_location_check")),
            }
        )

    matches.sort(
        key=lambda match: (
            -float(match["score"]),
            0 if bool(match["chunk"].get("human_reviewed")) else 1,
            0 if bool(match["chunk"].get("source_grounded")) else 1,
            str(match["chunk_id"] or ""),
        )
    )
    return matches
