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

_DISPLAY_ACRONYMS = {
    "aa": "AA",
    "aaa": "AAA",
    "lcd": "LCD",
    "led": "LED",
    "pc": "PC",
    "tv": "TV",
    "usb": "USB",
}

_SEARCH_ABBREVIATIONS = {
    "pc": "personal computer",
    "tv": "television",
}

_VAGUE_SEARCH_LABELS = {
    "",
    "item",
    "material",
    "object",
    "thing",
    "container",
    "unknown",
    "unknown item",
    "unknown material",
    "unknown object",
}
_MEANINGFUL_THREE_LETTER_OBJECTS = {
    "bag",
    "bin",
    "box",
    "can",
    "cup",
    "jar",
    "pen",
    "toy",
}

_SEARCH_DESCRIPTOR_TERMS = {
    "big",
    "blue",
    "bright",
    "broken",
    "clean",
    "cracked",
    "dark",
    "dirty",
    "green",
    "large",
    "long",
    "new",
    "old",
    "red",
    "round",
    "short",
    "small",
    "square",
    "white",
    "yellow",
}

_MATERIAL_CATEGORIES = {
    "plastic": "Plastic",
    "metal": "Metal",
    "mixed material": "Mixed Material",
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
    "fabric/textile": "Fabric/Textile",
    "unknown": UNKNOWN_VALUE,
}

_APPROVED_DISPOSAL_CATEGORIES = {
    "textiles": "Textiles",
    "electronics": "Electronics",
    "battery": "Battery",
    "appliances": "Appliances",
    "cardboard": "Cardboard",
    "paper": "Paper",
    "glass": "Glass",
    "metal": "Metal",
    "plastic": "Plastic",
    "organic": "Organic",
    "hazardous": "Hazardous",
}

_DISPOSAL_CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "textiles": ("textile", "textiles", "fabric", "fabrics", "clothing", "clothes", "apparel"),
    "electronics": (
        "electronics",
        "electronic",
        "electronic device",
        "electronic devices",
        "electronic waste",
        "e waste",
        "e-waste",
        "ewaste",
    ),
    "battery": ("battery", "batteries"),
    "appliances": ("appliance", "appliances"),
    "cardboard": ("cardboard", "scrap cardboard"),
    "paper": ("paper", "paper product", "paper products"),
    "glass": ("glass", "scrap glass"),
    "metal": ("metal", "metals", "scrap metal", "scrap-metal"),
    "plastic": ("plastic", "plastics"),
    "organic": (
        "organic",
        "organics",
        "organic waste",
        "food",
        "food waste",
        "compost",
        "compostable",
        "compostables",
    ),
    "hazardous": ("hazardous", "hazardous waste", "household hazardous waste"),
}

_VAGUE_HINT_VALUES = {
    "",
    "unknown",
    "unsure",
    "uncertain",
    "none",
    "n a",
    "na",
    "not applicable",
    "other",
    "item",
    "object",
    "material",
    "category",
}

_ROUTING_CATEGORIES = {
    "automotive": "automotive",
    "batteries": "batteries",
    "construction": "construction",
    "electronics": "electronics",
    "garden": "garden",
    "glass": "glass",
    "hazardous": "hazardous",
    "household": "household",
    "metal": "metal",
    "paint": "paint",
    "paper": "paper",
    "plastic": "plastic",
    "unknown": "unknown",
    "unsupported": "unsupported",
}

_CONDITION_FLAG_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("food_soiled", ("greasy", "grease", "food-soiled", "food soiled", "food residue", "crumb", "soiled")),
    ("contaminated", ("contaminated", "dirty", "residue", "stained")),
    ("appears_clean", ("appears clean", "visibly clean", "clean")),
    ("intact", ("appears intact", "intact")),
    ("empty", ("empty",)),
    ("broken", ("broken", "cracked", "shattered", "damaged")),
    ("wet", ("wet", "soaked", "damp")),
    ("opened", ("opened", "open", "unsealed")),
    ("single_use", ("single-use", "single use", "disposable")),
    ("reusable", ("reusable", "durable", "refillable")),
    ("recycling_mark_visible", ("recycling mark", "recycling symbol", "recycle symbol", "resin code")),
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
            "electric",
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
            "camera",
            "desk fan",
            "desk lamp",
            "electric fan",
            "lamp",
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
            "headphones",
            "earbud",
            "earbuds",
            "wireless",
            "bluetooth",
            "powered device",
            "battery powered",
            "charging port",
            "charging contact",
            "power button",
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
_GLASS_HINT_TERMS = ("glass",)
_GENERIC_BOTTLE_TERMS = (
    "water bottle",
    "bottle",
    "reusable bottle",
    "insulated bottle",
    "thermos",
    "thermoflask",
    "flask",
)
_PEN_TERMS = ("pen",)
_ORGANIC_ITEM_TERMS = (
    "banana",
    "bananas",
    "banana bunch",
    "leafy green",
    "leafy greens",
    "green leaves",
    "plant leaves",
    "leaves",
    "food scrap",
    "food scraps",
    "fruit scraps",
    "vegetable scraps",
    "spoiled produce",
    "produce scraps",
)
_ORGANIC_MATERIAL_TERMS = (
    "organic",
    "organic food",
    "organic plant material",
    "plant material",
    "compostable organic",
    "food",
    "food scraps",
    "fruit",
    "produce",
)
_PRIMARY_ELECTRONIC_ITEM_TERMS = (
    "camera",
    "calculator",
    "charger",
    "computer",
    "computer mouse",
    "desk fan",
    "desk lamp",
    "earbud",
    "electronic device",
    "electric fan",
    "electric toothbrush",
    "headphone",
    "keyboard",
    "lamp",
    "laptop",
    "monitor",
    "phone",
    "printer",
    "remote",
    "tablet",
    "television",
    "tv",
    "usb accessory",
)
_PRIMARY_TEXTILE_ITEM_TERMS = (
    "backpack",
    "clothing",
    "curtain",
    "fabric item",
    "garment",
    "textile",
)
_MATERIAL_TERM_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Metal", _METAL_HINT_TERMS),
    ("Plastic", _PLASTIC_HINT_TERMS),
    ("Glass", _GLASS_HINT_TERMS),
    ("Ceramic", ("ceramic", "glazed ceramic")),
    ("Paper", ("paper", "paperboard", "coated paper")),
    ("Cardboard", ("cardboard", "corrugated cardboard")),
    ("Organic", _ORGANIC_MATERIAL_TERMS),
    ("Wood", ("wood", "wooden")),
    ("Fabric/Textile", ("fabric", "textile", "cloth")),
)
_OBSERVATION_ASPECTS = {
    "packaging_use",
    "form_factor",
    "condition",
    "contamination",
    "recycling_marking",
    "construction",
    "contents",
    "closure_state",
    "power_source",
    "reusability",
    "other",
}


def _clean_text(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"[_/]+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9\s\-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _term_tokens(value: Any) -> list[str]:
    normalized = _clean_text(value).replace("-", " ")
    return normalized.split() if normalized else []


def _contains_term(text: Any, term: Any) -> bool:
    text_tokens = _term_tokens(text)
    term_tokens = _term_tokens(term)
    if not text_tokens or not term_tokens or len(term_tokens) > len(text_tokens):
        return False
    width = len(term_tokens)
    return any(
        text_tokens[index : index + width] == term_tokens
        for index in range(len(text_tokens) - width + 1)
    )


def _contains_any_term(text: Any, terms: tuple[str, ...]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _coerce_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence < 0:
        return 0.0
    if confidence > 1:
        return 1.0
    return confidence


def _normalize_visual_observations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    observations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw_observation in value:
        if not isinstance(raw_observation, dict):
            continue
        aspect = _clean_text(raw_observation.get("aspect")).replace(" ", "_").replace("-", "_")
        if aspect not in _OBSERVATION_ASPECTS:
            continue
        observation_value = str(raw_observation.get("value") or "").strip()
        if not observation_value or _is_vague_hint(observation_value):
            observation_value = UNKNOWN_VALUE
        evidence = str(raw_observation.get("evidence") or "").strip()
        confidence = _coerce_confidence(raw_observation.get("confidence"))
        if observation_value == UNKNOWN_VALUE:
            confidence = None
            evidence = ""

        dedupe_key = (aspect, _clean_text(observation_value))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        observations.append(
            {
                "aspect": aspect,
                "value": observation_value,
                "confidence": confidence,
                "evidence": evidence,
            }
        )
        if len(observations) == 8:
            break
    return observations


def _visual_observation_text(observations: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for observation in observations:
        value = str(observation.get("value") or "").strip()
        evidence = str(observation.get("evidence") or "").strip()
        if value and not _is_vague_hint(value):
            values.append(value)
        if evidence:
            values.append(evidence)
    return _clean_text(" ".join(values))


def _title_case_label(value: str) -> str:
    if not value:
        return UNKNOWN_VALUE

    words = []
    for word in value.split():
        if not word:
            continue
        if "-" in word:
            parts = [
                _DISPLAY_ACRONYMS.get(part.casefold(), part.capitalize())
                for part in word.split("-")
                if part
            ]
            words.append("-".join(parts))
        else:
            words.append(_DISPLAY_ACRONYMS.get(word.casefold(), word.capitalize()))
    return " ".join(words) if words else UNKNOWN_VALUE


def normalize_display_label(value: Any) -> str:
    """Normalize ordinary casing while preserving common acronym casing."""
    return _title_case_label(_clean_text(value))


def build_canonical_search_label(
    recognized_label: Any,
    *,
    broad_category: Any = None,
) -> str:
    """Build a short deterministic search identity without changing display text."""
    normalized = _clean_text(recognized_label)
    if normalized in _VAGUE_SEARCH_LABELS:
        return ""

    if normalized in _SEARCH_ABBREVIATIONS:
        return _SEARCH_ABBREVIATIONS[normalized]

    tokens = [
        token
        for token in normalized.split()
        if token not in _SEARCH_DESCRIPTOR_TERMS
    ]
    compact = " ".join(tokens).strip()
    if not compact or compact in _VAGUE_SEARCH_LABELS:
        return ""

    if _contains_term(compact, "usb") and _contains_term(compact, "accessory"):
        return "USB accessory"

    if _contains_any_term(
        compact,
        (
            "edible",
            "food scrap",
            "food scraps",
            "fruit scrap",
            "fruit scraps",
            "vegetable scrap",
            "vegetable scraps",
            "spoiled produce",
        ),
    ):
        return "food scraps"

    if len(compact.split()) > 6:
        category = _clean_text(broad_category)
        if category not in _VAGUE_SEARCH_LABELS and category not in {
            "household",
            "general",
            "unsupported",
        }:
            return category

    return " ".join(
        _DISPLAY_ACRONYMS.get(token.casefold(), token)
        for token in compact.split()[:6]
    )


def is_meaningful_search_label(value: Any) -> bool:
    normalized = _clean_text(value)
    if not normalized or normalized in _VAGUE_SEARCH_LABELS:
        return False
    tokens = normalized.split()
    if not any(re.search(r"[a-z]", token) for token in tokens):
        return False
    if len(tokens) == 1 and len(tokens[0]) <= 3:
        return tokens[0] in _MEANINGFUL_THREE_LETTER_OBJECTS
    return True


def _is_vague_hint(value: str) -> bool:
    normalized_value = _clean_text(value)
    if normalized_value in _VAGUE_HINT_VALUES:
        return True
    return normalized_value.startswith(
        ("unknown ", "not sure", "cannot determine", "unable to determine")
    )


def _positive_observation_value(value: Any) -> str:
    normalized = _clean_text(value)
    if _is_vague_hint(normalized):
        return ""
    return normalized


def _condition_flags_from_value(value: Any) -> list[str]:
    normalized = _positive_observation_value(value)
    if not normalized:
        return []

    clean_or_negative = _contains_any_term(
        normalized,
        (
            "appears clean",
            "visibly clean",
            "no visible contamination",
            "no contamination visible",
            "no visible food residue",
            "free of residue",
        ),
    )
    flags: list[str] = []
    for flag, patterns in _CONDITION_FLAG_PATTERNS:
        if clean_or_negative and flag in {"food_soiled", "contaminated"}:
            continue
        if _contains_any_term(normalized, patterns):
            flags.append(flag)
    if clean_or_negative and "appears_clean" not in flags:
        flags.append("appears_clean")
    return flags


def _extract_flags(
    normalized_text: str,
    visual_observations: list[dict[str, Any]],
    *,
    special_context: str = "",
) -> tuple[list[str], list[str]]:
    condition_flags: list[str] = []
    for flag in _condition_flags_from_value(normalized_text):
        if flag not in condition_flags:
            condition_flags.append(flag)

    condition_aspects = {
        "packaging_use",
        "condition",
        "contamination",
        "closure_state",
        "reusability",
        "recycling_marking",
    }
    observation_values: list[str] = []
    for observation in visual_observations:
        aspect = str(observation.get("aspect") or "").strip()
        value = _positive_observation_value(observation.get("value"))
        if not value:
            continue
        observation_values.append(value)
        if aspect not in condition_aspects:
            continue
        for flag in _condition_flags_from_value(value):
            if flag not in condition_flags:
                condition_flags.append(flag)

    special_flags: list[str] = []
    special_text = _clean_text(
        " ".join([normalized_text, special_context, *observation_values])
    )
    for flag, patterns in _SPECIAL_FLAG_PATTERNS:
        if _contains_any_term(special_text, patterns):
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

    if _contains_term(normalized_text, "coffee mug") and _contains_term(normalized_text, "ceramic"):
        return "Ceramic mug", "keyword_rule"
    if _contains_term(normalized_text, "mug"):
        if _contains_term(normalized_text, "ceramic"):
            return "Ceramic mug", "keyword_rule"
        return "Mug", "keyword_rule"

    if _contains_term(normalized_text, "charger"):
        if _contains_any_term(normalized_text, ("phone", "iphone", "mobile", "usb")):
            return "Phone charger", "keyword_rule"
        return "Charger", "keyword_rule"

    if _contains_any_term(normalized_text, ("cable", "cord")):
        if _contains_any_term(
            normalized_text,
            ("charging", "charger", "phone", "iphone", "mobile", "usb"),
        ):
            return "Charging cable", "keyword_rule"
        return "Cable", "keyword_rule"

    if _contains_term(normalized_text, "yogurt") and (
        _contains_term(normalized_text, "cup")
        or _contains_term(normalized_text, "container")
    ):
        return "Yogurt cup", "keyword_rule"

    if _contains_term(normalized_text, "pizza") and _contains_term(normalized_text, "box"):
        return "Pizza box", "keyword_rule"

    if _contains_term(normalized_text, "water") and _contains_term(normalized_text, "bottle"):
        return "Water bottle", "keyword_rule"

    return _title_case_label(normalized_text), "clean_fallback"


def _is_organic_item(*values: Any) -> bool:
    return any(
        _contains_any_term(value, _ORGANIC_ITEM_TERMS)
        for value in values
        if value is not None
    )


def _primary_identity_profile(item_label: str) -> tuple[str | None, str | None]:
    """Return routing and material facts stated by the primary item identity."""
    normalized = _clean_text(item_label)
    if _contains_any_term(normalized, ("battery", "batteries")):
        return "batteries", "Battery"
    if _contains_any_term(normalized, _PRIMARY_ELECTRONIC_ITEM_TERMS):
        return "electronics", None
    if _is_organic_item(normalized) or _contains_any_term(
        normalized, ("edible", "food", "food scraps", "produce")
    ):
        return "garden", "Organic"
    if _contains_any_term(normalized, _PRIMARY_TEXTILE_ITEM_TERMS):
        return "household", "Fabric/Textile"
    if _contains_term(normalized, "glass"):
        return "glass", "Glass"
    if _contains_term(normalized, "ceramic"):
        return "household", "Ceramic"
    if _contains_term(normalized, "cardboard"):
        return "paper", "Cardboard"
    if _contains_term(normalized, "paper"):
        return "paper", "Paper"
    return None, None


def _metadata_conflicts_with_identity(
    *,
    identity_route: str | None,
    identity_material: str | None,
    likely_material: Any,
    broad_category: Any,
    structured_material: str,
    metadata_special_flags: list[str],
) -> list[str]:
    conflicts: list[str] = []
    hinted_material = _map_material_hint(str(likely_material or ""))
    if (
        identity_material
        and hinted_material not in {UNKNOWN_VALUE, identity_material}
    ):
        conflicts.append("likely_material_conflicts_with_primary_identity")
    if (
        identity_material
        and structured_material not in {UNKNOWN_VALUE, identity_material}
    ):
        conflicts.append("construction_conflicts_with_primary_identity")

    routed_hint = _map_routing_category_hint(str(broad_category or ""))
    if (
        identity_route
        and routed_hint not in {"unknown", "unsupported", identity_route}
    ):
        conflicts.append("broad_category_conflicts_with_primary_identity")

    if identity_route == "electronics" and "battery" in metadata_special_flags:
        conflicts.append("secondary_battery_signal_does_not_replace_electronics")
    return conflicts


def _map_material_hint(value: str) -> str:
    normalized_value = _clean_text(value)
    if _is_vague_hint(normalized_value):
        return UNKNOWN_VALUE
    if _contains_any_term(normalized_value, _METAL_HINT_TERMS):
        return _MATERIAL_CATEGORIES["metal"]
    if _contains_term(normalized_value, "ceramic"):
        return _MATERIAL_CATEGORIES["ceramic"]
    if _contains_term(normalized_value, "glass"):
        return _MATERIAL_CATEGORIES["glass"]
    if _contains_any_term(normalized_value, _PLASTIC_HINT_TERMS):
        return _MATERIAL_CATEGORIES["plastic"]
    if _contains_term(normalized_value, "cardboard"):
        return _MATERIAL_CATEGORIES["cardboard"]
    if _contains_term(normalized_value, "paper"):
        return _MATERIAL_CATEGORIES["paper"]
    if _contains_any_term(normalized_value, ("electronic", "electronics")):
        return _MATERIAL_CATEGORIES["electronics"]
    if _contains_any_term(normalized_value, ("battery", "batteries")):
        return _MATERIAL_CATEGORIES["battery"]
    if _contains_any_term(normalized_value, ("hazard", "hazardous")):
        return _MATERIAL_CATEGORIES["hazardous"]
    if _contains_any_term(normalized_value, _ORGANIC_MATERIAL_TERMS):
        return _MATERIAL_CATEGORIES["organic"]
    if _contains_any_term(normalized_value, ("wood", "wooden")):
        return _MATERIAL_CATEGORIES["wood"]
    if _contains_any_term(normalized_value, ("fabric", "textile", "cloth")):
        return _MATERIAL_CATEGORIES["fabric/textile"]
    return _title_case_label(normalized_value)


def _structured_materials(
    visual_observations: list[dict[str, Any]],
) -> tuple[str, list[str], float | None]:
    construction = next(
        (
            observation
            for observation in visual_observations
            if observation.get("aspect") == "construction"
            and _positive_observation_value(observation.get("value"))
        ),
        None,
    )
    if construction is None:
        return UNKNOWN_VALUE, [], None

    value = _positive_observation_value(construction.get("value"))
    mentions: list[tuple[int, str]] = []
    value_tokens = _term_tokens(value)
    for material, terms in _MATERIAL_TERM_GROUPS:
        best_index: int | None = None
        for term in terms:
            term_tokens = _term_tokens(term)
            width = len(term_tokens)
            for index in range(max(0, len(value_tokens) - width + 1)):
                if value_tokens[index : index + width] == term_tokens:
                    best_index = index if best_index is None else min(best_index, index)
        if best_index is not None:
            mentions.append((best_index, material))

    mentions.sort(key=lambda item: item[0])
    ordered_materials: list[str] = []
    for _, material in mentions:
        if material not in ordered_materials:
            ordered_materials.append(material)
    if not ordered_materials:
        return UNKNOWN_VALUE, [], _coerce_confidence(construction.get("confidence"))
    return (
        ordered_materials[0],
        ordered_materials[1:],
        _coerce_confidence(construction.get("confidence")),
    )


def _candidate_has_term_evidence(
    candidates: Any,
    terms: tuple[str, ...],
    *,
    required_terms: tuple[str, ...] = (),
) -> bool:
    if not isinstance(candidates, list):
        return False

    for candidate in candidates[:3]:
        if not isinstance(candidate, dict):
            continue

        candidate_label = _clean_text(candidate.get("label"))
        if not candidate_label:
            continue
        if required_terms and not all(
            _contains_term(candidate_label, term) for term in required_terms
        ):
            continue
        if not _contains_any_term(candidate_label, terms):
            continue

        confidence = candidate.get("confidence")
        if confidence is None:
            continue
        try:
            if float(confidence) < 0.85:
                continue
        except (TypeError, ValueError):
            continue

        return True

    return False


def _is_generic_bottle_like_label(item_label: str, normalized_text: str) -> bool:
    normalized_item_label = _clean_text(item_label)
    return (
        normalized_item_label == "water bottle"
        or _contains_any_term(normalized_text, _GENERIC_BOTTLE_TERMS)
    )


def _is_pen_like_label(item_label: str, normalized_text: str) -> bool:
    normalized_item_label = _clean_text(item_label)
    return normalized_item_label == "pen" or _contains_any_term(normalized_text, _PEN_TERMS)


def _infer_material_details(
    item_label: str,
    normalized_text: str,
    likely_material: str,
    visual_evidence: str,
    candidates: Any,
    condition_flags: list[str],
    special_flags: list[str],
    structured_primary_material: str = UNKNOWN_VALUE,
    structured_material_confidence: float | None = None,
) -> tuple[str, str, str]:
    hinted_material = _map_material_hint(likely_material)
    normalized_visual_evidence = _clean_text(visual_evidence)

    raw_has_plastic = _contains_any_term(normalized_text, _PLASTIC_HINT_TERMS)
    visual_has_plastic = _contains_any_term(normalized_visual_evidence, _PLASTIC_HINT_TERMS)
    candidate_has_plastic = _candidate_has_term_evidence(candidates, _PLASTIC_HINT_TERMS)

    raw_has_metal = _contains_any_term(normalized_text, _METAL_HINT_TERMS)
    visual_has_metal = _contains_any_term(normalized_visual_evidence, _METAL_HINT_TERMS)
    candidate_has_metal = _candidate_has_term_evidence(candidates, _METAL_HINT_TERMS)

    raw_has_glass = _contains_any_term(normalized_text, _GLASS_HINT_TERMS)
    visual_has_glass = _contains_any_term(normalized_visual_evidence, _GLASS_HINT_TERMS)
    candidate_has_glass = _candidate_has_term_evidence(candidates, _GLASS_HINT_TERMS)

    if _is_organic_item(item_label, normalized_text):
        return _MATERIAL_CATEGORIES["organic"], "high", "item_identity"

    if "battery" in special_flags:
        source = (
            "keyword"
            if _contains_any_term(normalized_text, ("battery", "batteries"))
            else "structured_power_source"
        )
        return _MATERIAL_CATEGORIES["battery"], "high", source

    if structured_primary_material != UNKNOWN_VALUE:
        confidence = (
            "high"
            if structured_material_confidence is not None
            and structured_material_confidence >= 0.85
            else "medium"
        )
        return structured_primary_material, confidence, "structured_observation"

    if item_label == "Pizza box" and "food_soiled" in condition_flags:
        return _MATERIAL_CATEGORIES["food-soiled cardboard"], "high", "keyword"

    if _is_generic_bottle_like_label(item_label, normalized_text):
        if raw_has_plastic:
            return _MATERIAL_CATEGORIES["plastic"], "high", "keyword"
        if raw_has_metal:
            return _MATERIAL_CATEGORIES["metal"], "high", "keyword"
        if visual_has_plastic:
            return _MATERIAL_CATEGORIES["plastic"], "medium", "visual_evidence"
        if visual_has_metal or candidate_has_metal:
            return _MATERIAL_CATEGORIES["metal"], "medium", "visual_evidence"
        if hinted_material == "Metal":
            return _MATERIAL_CATEGORIES["metal"], "low", "vlm_hint"
        if candidate_has_plastic:
            return _MATERIAL_CATEGORIES["plastic"], "medium", "keyword"
        if raw_has_glass:
            return _MATERIAL_CATEGORIES["glass"], "high", "keyword"
        if visual_has_glass or candidate_has_glass:
            return _MATERIAL_CATEGORIES["glass"], "medium", "visual_evidence"
        if hinted_material == "Plastic":
            return _MATERIAL_CATEGORIES["mixed material"], "low", "vlm_hint"
        return _MATERIAL_CATEGORIES["mixed material"], "low", "fallback"

    if _is_pen_like_label(item_label, normalized_text):
        if raw_has_plastic:
            return _MATERIAL_CATEGORIES["plastic"], "high", "keyword"
        if visual_has_plastic or candidate_has_plastic:
            return _MATERIAL_CATEGORIES["plastic"], "medium", "visual_evidence"
        if raw_has_metal:
            return _MATERIAL_CATEGORIES["metal"], "high", "keyword"
        if visual_has_metal or candidate_has_metal:
            return _MATERIAL_CATEGORIES["metal"], "medium", "visual_evidence"
        return _MATERIAL_CATEGORIES["mixed material"], "low", "fallback"

    if item_label == "Yogurt cup":
        if raw_has_plastic:
            return _MATERIAL_CATEGORIES["plastic"], "high", "keyword"
        if visual_has_plastic or candidate_has_plastic:
            return _MATERIAL_CATEGORIES["plastic"], "medium", "visual_evidence"
        if hinted_material == "Plastic":
            return _MATERIAL_CATEGORIES["plastic"], "low", "vlm_hint"
        return _MATERIAL_CATEGORIES["plastic"], "medium", "fallback"
    if item_label == "Ceramic mug":
        if _clean_text(normalized_text) in _EXACT_LABEL_ALIASES:
            return _MATERIAL_CATEGORIES["ceramic"], "high", "alias"
        return _MATERIAL_CATEGORIES["ceramic"], "high", "keyword"
    if item_label == "Mug" and _contains_term(normalized_text, "ceramic"):
        return _MATERIAL_CATEGORIES["ceramic"], "high", "keyword"
    if item_label == "Wooden picture frame" or _contains_any_term(
        normalized_text, ("wood", "wooden")
    ):
        return _MATERIAL_CATEGORIES["wood"], "high", "keyword"
    if raw_has_plastic:
        return _MATERIAL_CATEGORIES["plastic"], "high", "keyword"
    if visual_has_plastic or candidate_has_plastic:
        return _MATERIAL_CATEGORIES["plastic"], "medium", "visual_evidence"
    if raw_has_metal:
        return _MATERIAL_CATEGORIES["metal"], "high", "keyword"
    if visual_has_metal or candidate_has_metal:
        return _MATERIAL_CATEGORIES["metal"], "medium", "visual_evidence"
    if raw_has_glass:
        return _MATERIAL_CATEGORIES["glass"], "high", "keyword"
    if visual_has_glass or candidate_has_glass:
        return _MATERIAL_CATEGORIES["glass"], "medium", "visual_evidence"

    if "hazardous" in special_flags and hinted_material == "Hazardous":
        return _MATERIAL_CATEGORIES["hazardous"], "high", "keyword"
    if "electronics" in special_flags and hinted_material == "Electronics":
        return _MATERIAL_CATEGORIES["electronics"], "high", "keyword"
    if hinted_material != UNKNOWN_VALUE:
        return hinted_material, "low", "vlm_hint"

    if "hazardous" in special_flags:
        return _MATERIAL_CATEGORIES["hazardous"], "high", "keyword"
    if "electronics" in special_flags:
        return _MATERIAL_CATEGORIES["electronics"], "high", "keyword"

    return UNKNOWN_VALUE, "low", "fallback"


def _map_disposal_category_hint(value: str) -> str:
    normalized_value = _clean_text(value)
    if _is_vague_hint(normalized_value):
        return UNKNOWN_VALUE

    for category_key, aliases in _DISPOSAL_CATEGORY_ALIASES.items():
        if normalized_value in aliases:
            return _APPROVED_DISPOSAL_CATEGORIES[category_key]

    return UNKNOWN_VALUE


def _map_routing_category_hint(value: str) -> str:
    normalized_value = _clean_text(value)
    if _is_vague_hint(normalized_value):
        return _ROUTING_CATEGORIES["unknown"]
    if normalized_value in _ROUTING_CATEGORIES:
        return _ROUTING_CATEGORIES[normalized_value]
    if normalized_value in {"battery", "batteries"}:
        return _ROUTING_CATEGORIES["batteries"]
    if _contains_any_term(normalized_value, ("electronics", "electronic", "e waste", "e-waste", "ewaste")):
        return _ROUTING_CATEGORIES["electronics"]
    if _contains_any_term(normalized_value, ("automotive", "vehicle", "car")):
        return _ROUTING_CATEGORIES["automotive"]
    if _contains_any_term(normalized_value, ("construction", "demolition", "building material")):
        return _ROUTING_CATEGORIES["construction"]
    if _contains_any_term(normalized_value, ("garden", "yard", "lawn", "organic", "compost")):
        return _ROUTING_CATEGORIES["garden"]
    if _contains_term(normalized_value, "glass"):
        return _ROUTING_CATEGORIES["glass"]
    if _contains_term(normalized_value, "paint"):
        return _ROUTING_CATEGORIES["paint"]
    if _contains_any_term(normalized_value, ("hazard", "hazardous", "chemical", "medical", "medicine")):
        return _ROUTING_CATEGORIES["hazardous"]
    if _contains_any_term(normalized_value, ("cardboard", "paper")):
        return _ROUTING_CATEGORIES["paper"]
    if _contains_any_term(normalized_value, ("metal", "aluminum", "steel")):
        return _ROUTING_CATEGORIES["metal"]
    if _contains_term(normalized_value, "plastic"):
        return _ROUTING_CATEGORIES["plastic"]
    if _contains_term(normalized_value, "household"):
        return _ROUTING_CATEGORIES["household"]
    if normalized_value in {"appliance", "appliances", "textile", "textiles", "fabric", "fabrics", "clothing", "clothes", "apparel"}:
        return _ROUTING_CATEGORIES["household"]
    if normalized_value in {"organic", "organics", "organic waste"}:
        return _ROUTING_CATEGORIES["garden"]
    mapped_disposal_category = _map_disposal_category_hint(normalized_value)
    if mapped_disposal_category != UNKNOWN_VALUE and _clean_text(mapped_disposal_category) != normalized_value:
        return _map_routing_category_hint(mapped_disposal_category)
    return _ROUTING_CATEGORIES["unknown"]


def _infer_routing_category_from_item(
    item_label: str,
    normalized_text: str,
    likely_material: str,
) -> str:
    item_text = _clean_text(f"{item_label} {normalized_text}")
    material_text = _clean_text(likely_material)

    if _contains_any_term(item_text, ("keyboard", "computer mouse", "calculator", "phone charger", "charger", "charging cable", "cable", "cord", "usb", "laptop", "computer", "monitor", "printer", "television", "tv", "tablet", "smartphone", "cell phone", "phone", "remote", "headphone", "earbud")):
        return _ROUTING_CATEGORIES["electronics"]
    if _contains_any_term(item_text, ("battery", "batteries", "lithium", "alkaline", "rechargeable", "vape")):
        return _ROUTING_CATEGORIES["batteries"]
    if _contains_term(item_text, "paint"):
        return _ROUTING_CATEGORIES["paint"]
    if _contains_any_term(item_text, ("propane", "motor oil", "medication", "medicine", "chemical", "aerosol", "cleaning spray", "light bulb")):
        return _ROUTING_CATEGORIES["hazardous"]
    if _contains_any_term(item_text, ("cardboard", "pizza box", "paper", "newspaper", "magazine", "book", "envelope")):
        return _ROUTING_CATEGORIES["paper"]
    if _contains_term(item_text, "glass"):
        return _ROUTING_CATEGORIES["glass"]
    if _contains_any_term(item_text, ("plastic", "pet", "pete")):
        return _ROUTING_CATEGORIES["plastic"]
    if _contains_any_term(item_text, ("metal", "aluminum", "aluminium", "steel")):
        return _ROUTING_CATEGORIES["metal"]
    if _contains_any_term(item_text, ("automotive", "tire", "car", "vehicle")):
        return _ROUTING_CATEGORIES["automotive"]
    if _contains_any_term(item_text, ("construction", "demolition", "drywall", "asphalt", "concrete")):
        return _ROUTING_CATEGORIES["construction"]
    if _is_organic_item(item_label, normalized_text) or _contains_any_term(
        item_text,
        ("leaves", "branches", "grass", "garden", "yard", "food scraps"),
    ):
        return _ROUTING_CATEGORIES["garden"]

    if material_text in _ROUTING_CATEGORIES and material_text not in {"unknown", "unsupported"}:
        return _ROUTING_CATEGORIES[material_text]
    if material_text == "cardboard":
        return _ROUTING_CATEGORIES["paper"]
    if _contains_any_term(material_text, ("plastic", "pet", "pete")):
        return _ROUTING_CATEGORIES["plastic"]
    if _contains_any_term(material_text, ("metal", "aluminum", "aluminium", "steel")):
        return _ROUTING_CATEGORIES["metal"]
    if _contains_term(material_text, "glass"):
        return _ROUTING_CATEGORIES["glass"]
    return _ROUTING_CATEGORIES["unknown"]


def _infer_broad_category(
    item_label: str,
    normalized_text: str,
    likely_material: str,
    raw_broad_category: str,
    special_flags: list[str],
) -> str:
    if "battery" in special_flags:
        return _ROUTING_CATEGORIES["batteries"]
    if "hazardous" in special_flags:
        return _ROUTING_CATEGORIES["hazardous"]
    if "electronics" in special_flags:
        return _ROUTING_CATEGORIES["electronics"]

    item_category = _infer_routing_category_from_item(item_label, normalized_text, likely_material)
    if item_category != _ROUTING_CATEGORIES["unknown"]:
        return item_category

    routed_hint = _map_routing_category_hint(raw_broad_category)
    if routed_hint != _ROUTING_CATEGORIES["unknown"]:
        return routed_hint

    if item_label in {UNKNOWN_VALUE, ""}:
        return _ROUTING_CATEGORIES["unknown"]
    return _ROUTING_CATEGORIES["unknown"]


def _infer_disposal_category(
    item_label: str,
    normalized_text: str,
    raw_broad_category: str,
    material_category: str,
    special_flags: list[str],
) -> str:
    if material_category == _MATERIAL_CATEGORIES["organic"] or _is_organic_item(
        item_label, normalized_text
    ):
        return _APPROVED_DISPOSAL_CATEGORIES["organic"]

    if "battery" in special_flags:
        return _APPROVED_DISPOSAL_CATEGORIES["battery"]
    if "hazardous" in special_flags:
        return _APPROVED_DISPOSAL_CATEGORIES["hazardous"]
    if "electronics" in special_flags:
        return _APPROVED_DISPOSAL_CATEGORIES["electronics"]

    hinted_category = _map_disposal_category_hint(raw_broad_category)
    if hinted_category != UNKNOWN_VALUE:
        return hinted_category

    if item_label in {UNKNOWN_VALUE, ""}:
        return UNKNOWN_VALUE
    return "Household item"


def _normalize_candidate_label(value: Any) -> str:
    return _clean_text(value)


def _labels_are_consistent(primary_label: str, candidate_label: str) -> bool:
    primary = _normalize_candidate_label(primary_label)
    candidate = _normalize_candidate_label(candidate_label)
    if not primary or not candidate:
        return False
    if primary == candidate:
        return True
    if _contains_term(primary, candidate) or _contains_term(candidate, primary):
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
        return not _contains_term(normalized_supported_label, "plastic")
    if material_category == "Plastic":
        return _contains_term(normalized_supported_label, "plastic") or _contains_term(
            normalized_supported_label, "yogurt container"
        )
    if material_category in {"Mixed Material", "Unknown"}:
        return not _contains_term(normalized_supported_label, "plastic")
    return True


def _resolve_supported_label_from_primary(
    item_label: str,
    raw_item_label: str,
    likely_material: str,
    material_category: str,
    material_confidence: str,
    material_source: str,
    visual_evidence: str,
) -> str | None:
    if item_label in {"", UNKNOWN_VALUE}:
        return None

    normalized_raw_item = _clean_text(raw_item_label)
    normalized_likely_material = _clean_text(likely_material)
    normalized_visual_evidence = _clean_text(visual_evidence)

    if item_label == "Water bottle":
        raw_has_plastic = _contains_any_term(normalized_raw_item, _PLASTIC_HINT_TERMS)
        visual_has_plastic = _contains_any_term(
            normalized_visual_evidence, _PLASTIC_HINT_TERMS
        )
        likely_material_has_plastic = _contains_any_term(
            normalized_likely_material, _PLASTIC_HINT_TERMS
        )
        plastic_evidence_is_strong = raw_has_plastic or visual_has_plastic
        if material_category != "Plastic" or not plastic_evidence_is_strong:
            return None
        if material_source == "vlm_hint" and likely_material_has_plastic:
            return None

    if item_label == "Pen" and material_category == "Plastic":
        if material_confidence == "low" or material_source == "vlm_hint":
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
    visual_evidence = recognition_details.get("visual_evidence", "")
    visual_observations = _normalize_visual_observations(
        recognition_details.get("visual_observations", [])
    )
    visual_observation_text = _visual_observation_text(visual_observations)

    normalized_text = _clean_text(raw_item_label)
    condition_flags, special_flags = _extract_flags(
        normalized_text,
        visual_observations,
        special_context=" ".join(
            [str(likely_material or ""), str(raw_broad_category or "")]
        ),
    )
    metadata_special_flags = list(special_flags)
    item_label, normalization_source = _normalize_item_label(normalized_text)
    identity_route, identity_material = _primary_identity_profile(item_label)
    _, identity_special_flags = _extract_flags(normalized_text, [])
    if identity_route is not None:
        allowed_metadata_special_flags = set(identity_special_flags)
        if identity_route == "electronics":
            allowed_metadata_special_flags.add("electronics")
        elif identity_route == "batteries":
            allowed_metadata_special_flags.add("battery")
        special_flags = [
            flag
            for flag in special_flags
            if flag not in {"battery", "electronics", "hazardous"}
            or flag in allowed_metadata_special_flags
        ]
        for flag in allowed_metadata_special_flags:
            if flag not in special_flags:
                special_flags.append(flag)
        if not any(
            flag in special_flags for flag in {"battery", "electronics", "hazardous"}
        ):
            special_flags = [
                flag for flag in special_flags if flag != "dropoff_recommended"
            ]
        if special_flags and any(
            flag in special_flags for flag in {"battery", "electronics", "hazardous"}
        ) and "dropoff_recommended" not in special_flags:
            special_flags.append("dropoff_recommended")

    primary_material, secondary_materials, structured_material_confidence = (
        _structured_materials(visual_observations)
    )
    identity_conflicts = _metadata_conflicts_with_identity(
        identity_route=identity_route,
        identity_material=identity_material,
        likely_material=likely_material,
        broad_category=raw_broad_category,
        structured_material=primary_material,
        metadata_special_flags=metadata_special_flags,
    )
    material_category, material_confidence, material_source = _infer_material_details(
        item_label,
        normalized_text,
        str(likely_material or ""),
        str(visual_evidence or ""),
        candidates,
        condition_flags,
        special_flags,
        structured_primary_material=primary_material,
        structured_material_confidence=structured_material_confidence,
    )
    if identity_material is not None:
        if material_category != identity_material:
            material_category = identity_material
            material_confidence = "high"
            material_source = "item_identity"
        if primary_material not in {UNKNOWN_VALUE, identity_material}:
            primary_material = UNKNOWN_VALUE
            secondary_materials = []
    elif identity_route == "electronics" and material_category in {
        "Battery",
        "Cardboard",
        "Ceramic",
        "Fabric/Textile",
        "Hazardous",
        "Organic",
        "Paper",
    }:
        if "likely_material_conflicts_with_primary_identity" not in identity_conflicts:
            identity_conflicts.append("likely_material_conflicts_with_primary_identity")
        material_category = UNKNOWN_VALUE
        material_confidence = "low"
        material_source = "identity_metadata_conflict"
        primary_material = UNKNOWN_VALUE
        secondary_materials = []
    if "battery" in special_flags:
        if primary_material not in {UNKNOWN_VALUE, _MATERIAL_CATEGORIES["battery"]}:
            secondary_materials = [primary_material, *secondary_materials]
        primary_material = _MATERIAL_CATEGORIES["battery"]
    if primary_material == UNKNOWN_VALUE:
        primary_material = material_category
    secondary_materials = [
        material
        for material in secondary_materials
        if material != primary_material
    ]
    broad_category = _infer_broad_category(
        item_label,
        normalized_text,
        str(likely_material or ""),
        str(raw_broad_category or ""),
        special_flags,
    )
    routed_raw_category = _map_routing_category_hint(str(raw_broad_category or ""))
    if identity_route is not None and (
        identity_route in {"batteries", "electronics", "garden", "glass", "paper"}
        or routed_raw_category not in {"unknown", "unsupported", identity_route}
    ):
        broad_category = identity_route
    disposal_category = _infer_disposal_category(
        item_label,
        normalized_text,
        str(raw_broad_category or ""),
        material_category,
        special_flags,
    )
    identity_disposal_category = {
        "Battery": "Battery",
        "Cardboard": "Cardboard",
        "Ceramic": "Household item",
        "Fabric/Textile": "Textiles",
        "Glass": "Glass",
        "Organic": "Organic",
        "Paper": "Paper",
    }.get(identity_material or "")
    if identity_disposal_category is not None:
        disposal_category = identity_disposal_category
    search_item = build_canonical_search_label(
        item_label,
        broad_category=broad_category,
    )

    matched_supported_label = None
    if item_label not in {"", UNKNOWN_VALUE}:
        matched_supported_label = _resolve_supported_label_from_primary(
            item_label,
            str(raw_item_label or ""),
            str(likely_material or ""),
            material_category,
            material_confidence,
            material_source,
            str(visual_evidence or ""),
        )
    if matched_supported_label is None:
        matched_supported_label = _resolve_supported_label_from_candidates(
            item_label,
            material_category,
            candidates,
        )

    normalized_payload = {
        "normalized_item": item_label,
        "search_item": search_item,
        "disposal_category": disposal_category,
        "item_label": item_label,
        "material_category": material_category,
        "primary_material": primary_material,
        "secondary_materials": secondary_materials,
        "original_vlm_broad_category": raw_broad_category,
        "original_vlm_likely_material": likely_material,
        "material_confidence": material_confidence,
        "material_source": material_source,
        "broad_category": broad_category,
        "condition_flags": condition_flags,
        "special_handling_flags": special_flags,
        "visual_observations": visual_observations,
        "visual_observation_text": visual_observation_text,
        "matched_supported_label": matched_supported_label,
        "normalization_source": normalization_source,
        "identity_conflicts": list(dict.fromkeys(identity_conflicts)),
    }

    enriched_details = {
        **recognition_details,
        "visual_observations": visual_observations,
        "normalized": normalized_payload,
    }

    logger.info(
        "Open recognition normalized. raw_label=%s recognized_item=%s search_item=%s disposal_category=%s material_category=%s material_confidence=%s material_source=%s broad_category=%s condition_flags=%s special_flags=%s observation_count=%s matched_supported_label=%s identity_conflicts=%s",
        raw_item_label,
        normalized_payload["normalized_item"],
        normalized_payload["search_item"],
        normalized_payload["disposal_category"],
        normalized_payload["material_category"],
        normalized_payload["material_confidence"],
        normalized_payload["material_source"],
        normalized_payload["broad_category"],
        normalized_payload["condition_flags"],
        normalized_payload["special_handling_flags"],
        len(visual_observations),
        normalized_payload["matched_supported_label"],
        normalized_payload["identity_conflicts"],
    )

    return enriched_details


def labels_are_consistent_for_matching(primary_label: str, candidate_label: str) -> bool:
    return _labels_are_consistent(primary_label, candidate_label)
