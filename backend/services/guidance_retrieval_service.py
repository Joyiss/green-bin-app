from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

MIN_RETRIEVAL_SCORE = 3.0
_GENERIC_MATERIALS = {"metal", "plastic", "paper", "glass", "cardboard"}
_GENERIC_LOOKUP_TERMS = {
    "mixed material",
    "unknown",
    "household item",
    "general",
    "other",
}
_GENERIC_CATEGORY_ONLY_TERMS = {
    "plastic",
    "paper",
    "metal",
    "glass",
    "cardboard",
    "mixed material",
    "household item",
    "general",
    "other",
}
_ALIAS_CANONICAL_MAP = {
    "battery": "battery",
    "batteries": "battery",
    "rechargeable battery": "battery",
    "rechargeable batteries": "battery",
    "lithium ion battery": "battery",
    "lithium ion batteries": "battery",
    "electronics": "electronics/e-waste",
    "electronic": "electronics/e-waste",
    "electronics e waste": "electronics/e-waste",
    "electronic e waste": "electronics/e-waste",
    "e waste": "electronics/e-waste",
    "electronic waste": "electronics/e-waste",
    "organic": "organic waste",
    "organics": "organic waste",
    "compostable organic": "organic waste",
    "food scrap": "organic waste",
    "food scraps": "organic waste",
    "yard waste": "organic waste",
    "garden": "organic waste",
}
_EARTH911_SPECIAL_TERMS = {
    "battery",
    "electronics/e-waste",
    "paint",
    "paint/household hazardous waste",
    "aerosol can",
    "motor oil",
    "light bulb",
    "fluorescent bulb",
    "fluorescent lamp",
    "medicine",
    "medication",
    "sharp",
    "sharps",
    "needle",
    "syringe",
    "textile",
    "clothing",
    "appliance",
    "hazardous",
    "hazardous waste",
}
_EARTH911_SPECIAL_FLAGS = {
    "requires_dropoff",
    "dropoff_recommended",
    "special_handling",
    "hazardous",
    "e_waste",
    "electronics",
    "battery",
}
_BATTERY_POSITIVE_TERMS = {
    "battery",
    "batteries",
    "battery compartment",
    "battery cover",
    "calculator",
    "cell phone",
    "charging port",
    "cordless",
    "earbud",
    "earbuds",
    "headphones",
    "laptop",
    "phone",
    "power bank",
    "rechargeable",
    "rechargeable batteries",
    "remote",
    "speaker",
    "tablet",
    "wireless",
}
_BATTERY_WIRED_NEGATIVE_TERMS = {
    "cable",
    "corded",
    "cord",
    "power cord",
    "usb cable",
    "wired",
}
_ROUTING_MODIFIER_CONDITIONS = {
    "acceptance_not_verified",
    "backyard_compost_pile",
    "backyard_management",
    "check_local_rules",
    "dropoff_recommended",
    "mechanical_pretreatment",
    "mixed_curbside_collection",
    "pre_dropoff_preparation",
    "requires_dropoff",
    "single_stream_collection",
    "special_handling",
}
_UNKNOWN_OBSERVATION_VALUES = {
    "",
    "not visible",
    "uncertain",
    "unknown",
    "unknown from image",
}
_PROPERTY_ALIASES = {
    "alkaline_battery": "alkaline",
    "battery_chemistry_alkaline": "alkaline",
    "battery_chemistry_lithium": "lithium",
    "battery_chemistry_lithium_ion": "lithium_ion",
    "coated_or_laminated": "coated",
    "contains_embedded_battery": "embedded_battery",
    "lithium": "lithium",
    "lithium_battery": "lithium",
    "lithium_ion_battery": "lithium_ion",
    "nonrechargeable": "non_rechargeable",
    "not_rechargeable": "non_rechargeable",
    "rechargeable_battery": "rechargeable",
    "uncoated_paper": "uncoated",
}
_PROPERTY_CONFLICT_GROUPS = (
    {"alkaline", "lead_acid", "lithium", "lithium_ion", "nickel_cadmium", "nimh"},
    {"rechargeable", "non_rechargeable"},
    {"coated", "uncoated"},
    {"contaminated", "clean"},
    {"embedded_battery", "no_embedded_battery"},
    {"broken", "intact"},
)
_RECYCLING_ACTIONS = {"recycle", "drop off", "drop-off"}


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


def _normalize_text(value: Any) -> str:
    return normalize_guidance_phrase(value) or ""


def _visual_observation_text_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized_values: list[str] = []
    for observation in values:
        if not isinstance(observation, dict):
            continue
        aspect = _normalize_text(observation.get("aspect"))
        value = _normalize_text(observation.get("value"))
        evidence = _normalize_text(observation.get("evidence"))
        for candidate in (aspect, value, evidence):
            if candidate:
                normalized_values.append(candidate)
    return normalized_values


def _observation_facts(values: Any) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    if not isinstance(values, list):
        return facts

    for observation in values:
        if not isinstance(observation, dict):
            continue
        aspect = _normalize_text(observation.get("aspect")).replace(" ", "_")
        if not aspect:
            continue
        value = _normalize_text(observation.get("value"))
        confidence: float | None = None
        try:
            if observation.get("confidence") is not None:
                confidence = float(observation["confidence"])
        except (TypeError, ValueError):
            confidence = None
        facts[aspect] = {
            "value": value,
            "confidence": confidence,
            "known": value not in _UNKNOWN_OBSERVATION_VALUES,
        }
    return facts


def _canonical_property(value: Any) -> str:
    normalized = _normalize_text(value).replace(" ", "_")
    return _PROPERTY_ALIASES.get(normalized, normalized)


def _confirmed_property_evidence(
    *,
    condition_flags: set[str],
    observations: dict[str, dict[str, Any]],
) -> set[str]:
    evidence = {_canonical_property(value) for value in condition_flags if value}
    for observation in observations.values():
        if not observation.get("known"):
            continue
        confidence = observation.get("confidence")
        if confidence is not None and confidence < 0.75:
            continue
        value = _normalize_text(observation.get("value"))
        if not value:
            continue
        normalized_value = value.replace(" ", "_")
        evidence.add(_canonical_property(normalized_value))
        for alias, canonical in _PROPERTY_ALIASES.items():
            if alias in normalized_value:
                evidence.add(canonical)
    return evidence


def _condition_applicability_state(
    condition: str,
    *,
    condition_flags: set[str],
    observations: dict[str, dict[str, Any]],
) -> str:
    normalized = _canonical_property(condition)
    if normalized in _ROUTING_MODIFIER_CONDITIONS:
        return "modifier"
    property_evidence = _confirmed_property_evidence(
        condition_flags=condition_flags,
        observations=observations,
    )
    conflict_group = next(
        (group for group in _PROPERTY_CONFLICT_GROUPS if normalized in group),
        None,
    )
    if conflict_group is not None:
        conflicting = (property_evidence & conflict_group) - {normalized}
        if conflicting:
            return "contradicted"
    if normalized in property_evidence:
        return "confirmed"
    if conflict_group is not None and property_evidence & conflict_group:
        return "contradicted"

    condition_value = str(observations.get("condition", {}).get("value") or "")
    contamination_value = str(
        observations.get("contamination", {}).get("value") or ""
    )
    marking_value = str(
        observations.get("recycling_marking", {}).get("value") or ""
    )
    construction_value = str(observations.get("construction", {}).get("value") or "")
    combined_state = " ".join(
        [condition_value, contamination_value, construction_value]
    )

    if normalized in {"clean_and_dry", "clean_and_free_of_food_residue"}:
        if any(
            flag in condition_flags
            for flag in {"contaminated", "food_soiled", "wet"}
        ) or any(term in contamination_value for term in ("contaminated", "residue", "soiled")):
            return "contradicted"
        clean = "appears_clean" in condition_flags or "clean" in contamination_value
        dry = "dry" in condition_flags or "dry" in combined_state
        return "confirmed" if clean and dry else "unknown"

    if normalized == "empty_and_rinsed":
        empty = "empty" in condition_flags or "empty" in combined_state
        clean = (
            "appears_clean" in condition_flags
            or "rinsed" in combined_state
            or "clean" in contamination_value
        )
        if "contaminated" in condition_flags or "food_soiled" in condition_flags:
            return "contradicted"
        return "confirmed" if empty and clean else "unknown"

    if normalized == "resin_code_present":
        if marking_value in _UNKNOWN_OBSERVATION_VALUES:
            return "unknown"
        return (
            "confirmed"
            if any(term in marking_value for term in ("resin", "code", "number", "symbol"))
            else "contradicted"
        )

    if normalized == "coated":
        if any(term in construction_value for term in ("coated", "coating", "laminated")):
            return "confirmed"
        if any(term in construction_value for term in ("uncoated", "plain paper")):
            return "contradicted"
        return "unknown"

    if normalized == "broken":
        if "broken" in condition_flags or "broken" in condition_value:
            return "confirmed"
        if "intact" in condition_flags or "intact" in condition_value:
            return "contradicted"
        return "unknown"

    return "unknown"


def classify_chunk_applicability(
    chunk: dict[str, Any],
    *,
    matched_fields: list[str],
    item_label: str | None,
    primary_material: str | None,
    material_confidence: str | None,
    condition_flags: list[str],
    special_flags: list[str],
    visual_observations: list[dict[str, Any]] | None,
    location: dict[str, Any] | None,
) -> dict[str, Any]:
    observations = _observation_facts(visual_observations)
    normalized_condition_flags = set(_normalize_condition_flags(condition_flags))
    normalized_special_flags = set(_normalize_condition_flags(special_flags))
    source_conditions = _normalize_condition_flags(
        (chunk.get("applies_to") or {}).get("condition_flags")
    )
    confirmed_conditions: list[str] = []
    unknown_conditions: list[str] = []
    contradicted_conditions: list[str] = []

    for condition in source_conditions:
        state = _condition_applicability_state(
            condition,
            condition_flags=normalized_condition_flags | normalized_special_flags,
            observations=observations,
        )
        if state == "confirmed":
            confirmed_conditions.append(condition)
        elif state == "contradicted":
            contradicted_conditions.append(condition)
        elif state == "unknown":
            unknown_conditions.append(condition)

    actions = {
        _normalize_text(value)
        for value in chunk.get("disposal_actions_supported") or []
        if _normalize_text(value)
    }
    route_is_recycling = bool(actions & _RECYCLING_ACTIONS)
    route_is_compost = "compost" in actions
    route_is_donation = "donate reuse" in actions
    safety_route_confirmed = bool(
        normalized_special_flags
        & {"battery", "electronics", "hazardous", "requires_dropoff"}
    )
    broad_match_only = bool(matched_fields) and not any(
        field in matched_fields
        for field in ("item_label_exact", "item_label_normalized", "condition_flags")
    )
    reason_codes: list[str] = []
    item_context = " ".join(
        [
            _normalize_text(item_label),
            str(observations.get("packaging_use", {}).get("value") or ""),
            str(observations.get("form_factor", {}).get("value") or ""),
            str(observations.get("construction", {}).get("value") or ""),
        ]
    )
    section = _normalize_text(chunk.get("section"))
    organic_subtype_mismatch = False
    if section == "yard waste":
        organic_subtype_mismatch = not any(
            term in item_context
            for term in ("leaf", "leaves", "yard", "grass", "branch", "twig", "plant trimming")
        )
    elif section == "food scraps compost":
        organic_subtype_mismatch = not any(
            term in item_context
            for term in ("food", "fruit", "vegetable", "produce", "scrap", "peel", "core")
        )

    if organic_subtype_mismatch:
        applicability = "not_applicable"
        reason_codes.append("organic_subtype_mismatch")
    elif contradicted_conditions:
        applicability = "not_applicable"
        reason_codes.append("source_conditions_contradicted")
    else:
        applicability = "applicable"
        if unknown_conditions:
            applicability = "conditional"
            reason_codes.append("source_conditions_unconfirmed")
        if broad_match_only and not route_is_compost and not safety_route_confirmed:
            applicability = "conditional"
            reason_codes.append("broad_similarity_only")

        material_level = _normalize_text(material_confidence)
        construction = observations.get("construction", {})
        marking = observations.get("recycling_marking", {})
        if route_is_recycling and not safety_route_confirmed:
            if material_level in {"", "low", "unknown"}:
                applicability = "conditional"
                reason_codes.append("material_certainty_insufficient")
            if not construction.get("known", False):
                applicability = "conditional"
                reason_codes.append("construction_unknown")
            if chunk.get("requires_location_check") is True:
                applicability = "conditional"
                reason_codes.append("local_acceptance_unverified")
            if "resin_code_present" in source_conditions and not marking.get("known", False):
                applicability = "conditional"
                reason_codes.append("eligibility_marking_unknown")

        if route_is_donation:
            if normalized_condition_flags & {"single_use", "broken", "contaminated", "food_soiled"}:
                applicability = "not_applicable"
                reason_codes.append("item_condition_incompatible_with_reuse")
            elif not normalized_condition_flags & {"intact", "reusable", "appears_clean"}:
                applicability = "conditional"
                reason_codes.append("reusability_unconfirmed")

        if route_is_compost:
            organic_context = " ".join(
                [
                    _normalize_text(primary_material),
                    str(construction.get("value") or ""),
                ]
            )
            if not any(term in organic_context for term in ("organic", "food", "plant", "yard")):
                applicability = "conditional"
                reason_codes.append("organic_construction_unconfirmed")

    if applicability == "applicable":
        reason_codes.append("specific_item_evidence_supports_source")

    return {
        "applicability": applicability,
        "applicability_reason_codes": list(dict.fromkeys(reason_codes)),
        "source_conditions": {
            "confirmed": confirmed_conditions,
            "unknown": unknown_conditions,
            "contradicted": contradicted_conditions,
        },
        "applicability_evidence": {
            "primary_material": primary_material,
            "material_confidence": material_confidence,
            "construction_known": bool(observations.get("construction", {}).get("known")),
            "recycling_marking_known": bool(
                observations.get("recycling_marking", {}).get("known")
            ),
            "location_supplied": isinstance(location, dict) and bool(location),
        },
    }


def _candidate_values(primary_value: Any, candidate_values: Any) -> list[str]:
    normalized_candidates: list[str] = []
    seen: set[str] = set()

    combined_values: list[Any] = []
    if primary_value is not None:
        combined_values.append(primary_value)
    if isinstance(candidate_values, list):
        combined_values.extend(candidate_values)

    for value in combined_values:
        normalized_value = normalize_guidance_phrase(value)
        if normalized_value and normalized_value not in seen:
            seen.add(normalized_value)
            normalized_candidates.append(str(value).strip())

    return normalized_candidates


def _canonical_alias(value: Any) -> str | None:
    normalized_value = normalize_guidance_label_for_match(value)
    if normalized_value is None:
        return None

    return _ALIAS_CANONICAL_MAP.get(normalized_value, normalized_value)


def _is_generic_lookup_term(value: Any) -> bool:
    normalized_value = normalize_guidance_label_for_match(value)
    if normalized_value is None:
        return False
    return normalized_value in _GENERIC_LOOKUP_TERMS


def _is_earth911_chunk(chunk: dict[str, Any]) -> bool:
    haystack = " ".join(
        filter(
            None,
            [
                str(chunk.get("id") or ""),
                str(chunk.get("source_name") or ""),
            ],
        )
    ).casefold()
    return "earth911" in haystack


def _is_earth911_special_term(value: Any) -> bool:
    canonical_value = _canonical_alias(value)
    if canonical_value is None:
        return False
    return canonical_value in _EARTH911_SPECIAL_TERMS


def _labels_match_with_aliases(left: Any, right: Any) -> bool:
    if labels_match_conservatively(left, right):
        return True

    canonical_left = _canonical_alias(left)
    canonical_right = _canonical_alias(right)
    if canonical_left is None or canonical_right is None:
        return False

    return canonical_left == canonical_right


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


def chunk_is_battery_related(chunk: dict[str, Any]) -> bool:
    applies_to = chunk.get("applies_to") or {}
    if _normalize_text(chunk.get("section")) == "batteries":
        return True

    texts = [
        chunk.get("id"),
        chunk.get("title"),
        chunk.get("source_name"),
        chunk.get("content"),
        chunk.get("source_claim"),
        chunk.get("source_excerpt"),
    ]
    for values in (
        applies_to.get("item_labels"),
        applies_to.get("materials"),
        applies_to.get("categories"),
        applies_to.get("condition_flags"),
    ):
        if isinstance(values, list):
            texts.extend(values)

    normalized_text = " ".join(filter(None, (_normalize_text(value) for value in texts)))
    return "battery" in normalized_text or "rechargeable" in normalized_text


def battery_chunk_relevant_for_context(
    *,
    item_label: str | None,
    material: str | None,
    category: str | None,
    item_candidates: list[str] | None = None,
    condition_flags: list[str] | None = None,
    special_flags: list[str] | None = None,
    visual_evidence: str | None = None,
    visual_observations: list[dict[str, Any]] | None = None,
) -> bool:
    normalized_condition_flags = _normalize_condition_flags(condition_flags or [])
    normalized_special_flags = _normalize_condition_flags(special_flags or [])
    if any(
        flag in {"battery", "battery_possible", "contains_battery"}
        for flag in (*normalized_condition_flags, *normalized_special_flags)
    ):
        return True

    text_values = [
        item_label,
        material,
        category,
        visual_evidence,
        *(item_candidates or []),
        *_visual_observation_text_values(visual_observations),
    ]
    normalized_text = " ".join(filter(None, (_normalize_text(value) for value in text_values)))
    if any(term in normalized_text for term in _BATTERY_POSITIVE_TERMS):
        return True

    if any(term in normalized_text for term in _BATTERY_WIRED_NEGATIVE_TERMS):
        return False

    return False


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
    item_candidates: list[str],
    material_candidates: list[str],
    category_candidates: list[str],
    condition_flags: list[str],
    specific_context_required: bool = False,
) -> tuple[float, list[str]]:
    applies_to = chunk.get("applies_to") or {}
    matched_fields: list[str] = []
    score = 0.0
    has_primary_semantic_match = False
    is_general_fallback = _chunk_is_general_fallback(chunk)
    earth911_special_semantic_match = False

    effective_item_candidates = [
        candidate for candidate in item_candidates if not _is_generic_lookup_term(candidate)
    ]
    effective_material_candidates = [
        candidate for candidate in material_candidates if not _is_generic_lookup_term(candidate)
    ]
    effective_category_candidates = [
        candidate for candidate in category_candidates if not _is_generic_lookup_term(candidate)
    ]

    chunk_item_labels = applies_to.get("item_labels") or []
    if effective_item_candidates:
        exact_item_match = any(
            normalize_guidance_phrase(chunk_item_label)
            == normalize_guidance_phrase(candidate_item)
            for candidate_item in effective_item_candidates
            for chunk_item_label in chunk_item_labels
            if normalize_guidance_phrase(candidate_item)
        )
        if exact_item_match:
            score += 8.0
            matched_fields.append("item_label_exact")
            has_primary_semantic_match = True
            earth911_special_semantic_match = any(
                _is_earth911_special_term(candidate_item)
                or _is_earth911_special_term(chunk_item_label)
                for candidate_item in effective_item_candidates
                for chunk_item_label in chunk_item_labels
                if normalize_guidance_phrase(chunk_item_label)
                == normalize_guidance_phrase(candidate_item)
            )
        elif any(
            _labels_match_with_aliases(chunk_item_label, candidate_item)
            for candidate_item in effective_item_candidates
            for chunk_item_label in chunk_item_labels
        ):
            score += 6.0
            matched_fields.append("item_label_normalized")
            has_primary_semantic_match = True
            earth911_special_semantic_match = any(
                _is_earth911_special_term(candidate_item)
                or _is_earth911_special_term(chunk_item_label)
                for candidate_item in effective_item_candidates
                for chunk_item_label in chunk_item_labels
                if _labels_match_with_aliases(chunk_item_label, candidate_item)
            )

    chunk_materials = applies_to.get("materials") or []
    material_match = False
    material_match_candidate: str | None = None
    if effective_material_candidates:
        material_match = any(
            _labels_match_with_aliases(chunk_material, candidate_material)
            for candidate_material in effective_material_candidates
            for chunk_material in chunk_materials
        )
        if material_match:
            for candidate_material in effective_material_candidates:
                if any(
                    _labels_match_with_aliases(chunk_material, candidate_material)
                    for chunk_material in chunk_materials
                ):
                    material_match_candidate = candidate_material
                    break
            score += 4.0
            matched_fields.append("material")
            has_primary_semantic_match = True
            earth911_special_semantic_match = earth911_special_semantic_match or any(
                _is_earth911_special_term(candidate_material)
                or _is_earth911_special_term(chunk_material)
                for candidate_material in effective_material_candidates
                for chunk_material in chunk_materials
                if _labels_match_with_aliases(chunk_material, candidate_material)
            )

    chunk_categories = applies_to.get("categories") or []
    if effective_category_candidates and any(
        _labels_match_with_aliases(chunk_category, candidate_category)
        for candidate_category in effective_category_candidates
        for chunk_category in chunk_categories
    ):
        score += 3.0
        matched_fields.append("category")
        has_primary_semantic_match = True
        earth911_special_semantic_match = earth911_special_semantic_match or any(
            _is_earth911_special_term(candidate_category)
            or _is_earth911_special_term(chunk_category)
            for candidate_category in effective_category_candidates
            for chunk_category in chunk_categories
            if _labels_match_with_aliases(chunk_category, candidate_category)
        )

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
        and _canonical_alias(material_match_candidate) in _GENERIC_MATERIALS
    ):
        score = 0.0
        matched_fields = []

    if chunk.get("human_reviewed") is True:
        score += 1.0
    elif chunk.get("source_grounded") is True:
        score += 0.25

    if chunk.get("verified") is True:
        score += 0.1

    if _is_earth911_chunk(chunk):
        special_flag_overlap = bool(
            set(normalized_condition_flags) & _EARTH911_SPECIAL_FLAGS
        )
        if not earth911_special_semantic_match:
            score = 0.0
            matched_fields = []
        elif not special_flag_overlap and "category" not in matched_fields and "item_label_exact" not in matched_fields and "item_label_normalized" not in matched_fields:
            score = 0.0
            matched_fields = []

    if (
        specific_context_required
        and matched_fields == ["category"]
        and effective_category_candidates
        and all(
            normalize_guidance_phrase(candidate) in _GENERIC_CATEGORY_ONLY_TERMS
            for candidate in effective_category_candidates
            if normalize_guidance_phrase(candidate)
        )
    ):
        score = 0.0
        matched_fields = []

    return score, matched_fields


def retrieve_guidance_chunks(
    *,
    item_label: str | None,
    material: str | None,
    category: str | None,
    item_candidates: list[str] | None = None,
    material_candidates: list[str] | None = None,
    category_candidates: list[str] | None = None,
    condition_flags: list[str] | None = None,
    special_flags: list[str] | None = None,
    visual_evidence: str | None = None,
    visual_observations: list[dict[str, Any]] | None = None,
    primary_material: str | None = None,
    material_confidence: str | None = None,
    specific_context_required: bool = False,
    location: dict[str, Any] | None = None,
    chunks: list[dict[str, Any]] | None = None,
    min_score: float = MIN_RETRIEVAL_SCORE,
) -> list[dict[str, Any]]:
    candidate_chunks = (
        list(chunks) if isinstance(chunks, list) else load_trusted_guidance_chunks()
    )
    effective_item_candidates = _candidate_values(item_label, item_candidates)
    effective_material_candidates = _candidate_values(material, material_candidates)
    effective_category_candidates = _candidate_values(category, category_candidates)
    normalized_condition_flags = _normalize_condition_flags(condition_flags or [])
    battery_relevant = battery_chunk_relevant_for_context(
        item_label=item_label,
        material=material,
        category=category,
        item_candidates=effective_item_candidates,
        condition_flags=normalized_condition_flags,
        special_flags=special_flags or [],
        visual_evidence=visual_evidence,
        visual_observations=visual_observations,
    )

    matches: list[dict[str, Any]] = []
    for chunk in candidate_chunks:
        if not _chunk_is_location_allowed(chunk, location):
            continue
        if chunk_is_battery_related(chunk) and not battery_relevant:
            logger.info(
                "Guidance retrieval skipped battery chunk. chunk_id=%s item_label=%s visual_evidence=%s",
                chunk.get("id"),
                item_label,
            visual_evidence,
        )
            continue

        score, matched_fields = _score_chunk(
            chunk,
            item_candidates=effective_item_candidates,
            material_candidates=effective_material_candidates,
            category_candidates=effective_category_candidates,
            condition_flags=normalized_condition_flags,
            specific_context_required=specific_context_required,
        )
        if score < min_score:
            continue

        applicability = classify_chunk_applicability(
            chunk,
            matched_fields=matched_fields,
            item_label=item_label,
            primary_material=primary_material or material,
            material_confidence=material_confidence,
            condition_flags=normalized_condition_flags,
            special_flags=list(special_flags or []),
            visual_observations=visual_observations,
            location=location,
        )

        matches.append(
            {
                "chunk": chunk,
                "chunk_id": chunk.get("id"),
                "score": round(score, 4),
                "matched_fields": matched_fields,
                "requires_location_check": bool(chunk.get("requires_location_check")),
                **applicability,
            }
        )

    matches.sort(
        key=lambda match: (
            {"applicable": 0, "conditional": 1, "not_applicable": 2}.get(
                str(match.get("applicability")), 3
            ),
            -float(match["score"]),
            0 if bool(match["chunk"].get("human_reviewed")) else 1,
            0 if bool(match["chunk"].get("source_grounded")) else 1,
            str(match["chunk_id"] or ""),
        )
    )
    return matches
