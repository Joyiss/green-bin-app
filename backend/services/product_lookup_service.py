from __future__ import annotations

from typing import Any

import requests

try:
    from ..classifier import build_selected_item_prediction
except ImportError:
    from classifier import build_selected_item_prediction


OPEN_FOOD_FACTS_API_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}"
OPEN_FOOD_FACTS_FIELDS = (
    "code,status,status_verbose,product_name,brands,categories,categories_tags,"
    "packaging,packaging_tags,quantity,generic_name"
)
OPEN_FOOD_FACTS_USER_AGENT = "GreenBin/0.1 (student project; contact: local-dev)"
OPEN_FOOD_FACTS_TIMEOUT_SECONDS = 5
OPEN_FOOD_FACTS_SOURCE = "open_food_facts"
KEYWORD_MATCH_CONFIDENCE = 0.85


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def _normalize_list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    normalized_values: list[str] = []
    for item in value:
        normalized_item = _normalize_text(item)
        if normalized_item:
            normalized_values.append(normalized_item)
    return normalized_values


def _has_useful_identifying_fields(
    *,
    product_name: str,
    brand: str,
    category: str,
    packaging: str,
    quantity: str,
    generic_name: str,
    raw_categories: list[str],
    raw_packaging_tags: list[str],
) -> bool:
    return any(
        (
            product_name,
            brand,
            category,
            packaging,
            quantity,
            generic_name,
        )
    ) or bool(raw_categories) or bool(raw_packaging_tags)


def get_product_by_barcode(barcode_value: str) -> dict[str, Any] | None:
    normalized_barcode = _normalize_text(barcode_value)
    if not normalized_barcode:
        return None

    try:
        response = requests.get(
            OPEN_FOOD_FACTS_API_URL.format(barcode=normalized_barcode),
            headers={"User-Agent": OPEN_FOOD_FACTS_USER_AGENT},
            params={"fields": OPEN_FOOD_FACTS_FIELDS},
            timeout=OPEN_FOOD_FACTS_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        response_json = response.json()
    except ValueError:
        return None

    if not isinstance(response_json, dict):
        return None

    status = response_json.get("status")
    if status is not None and status != 1:
        return None

    product = response_json.get("product")
    if not isinstance(product, dict):
        return None

    product_name = _normalize_text(product.get("product_name"))
    brand = _normalize_text(product.get("brands"))
    category = _normalize_text(product.get("categories"))
    packaging = _normalize_text(product.get("packaging"))
    quantity = _normalize_text(product.get("quantity"))
    generic_name = _normalize_text(product.get("generic_name"))
    raw_categories = _normalize_list_of_strings(product.get("categories_tags"))
    raw_packaging_tags = _normalize_list_of_strings(product.get("packaging_tags"))

    if not _has_useful_identifying_fields(
        product_name=product_name,
        brand=brand,
        category=category,
        packaging=packaging,
        quantity=quantity,
        generic_name=generic_name,
        raw_categories=raw_categories,
        raw_packaging_tags=raw_packaging_tags,
    ):
        return None

    return {
        "barcode_value": normalized_barcode,
        "product_name": product_name or None,
        "brand": brand or None,
        "category": category or None,
        "packaging": packaging or None,
        "quantity": quantity or None,
        "generic_name": generic_name or None,
        "source": OPEN_FOOD_FACTS_SOURCE,
        "raw_categories": raw_categories,
        "raw_packaging_tags": raw_packaging_tags,
    }


def _build_keyword_haystack(product: dict[str, Any]) -> str:
    parts = [
        _normalize_text(product.get("product_name")),
        _normalize_text(product.get("brand")),
        _normalize_text(product.get("category")),
        _normalize_text(product.get("packaging")),
        _normalize_text(product.get("quantity")),
        _normalize_text(product.get("generic_name")),
    ]
    parts.extend(_normalize_list_of_strings(product.get("raw_categories")))
    parts.extend(_normalize_list_of_strings(product.get("raw_packaging_tags")))
    return " | ".join(part.casefold() for part in parts if part)


def _build_packaging_haystack(product: dict[str, Any]) -> str:
    parts = [
        _normalize_text(product.get("packaging")),
    ]
    parts.extend(_normalize_list_of_strings(product.get("raw_packaging_tags")))
    return " | ".join(part.casefold() for part in parts if part)


def _contains_any(haystack: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in haystack for keyword in keywords)


def _is_supported_item_label(label: str) -> bool:
    return build_selected_item_prediction(label).get("status") == "confident"


def _build_label_match(item_label: str) -> dict[str, Any] | None:
    if not _is_supported_item_label(item_label):
        return None

    return {
        "item_label": item_label,
        "confidence": KEYWORD_MATCH_CONFIDENCE,
        "reason": "open_food_facts_keyword_match",
    }


def map_product_to_item_label(product: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(product, dict):
        return None

    packaging_haystack = _build_packaging_haystack(product)
    context_haystack = _build_keyword_haystack(product)

    if not packaging_haystack:
        return None

    beverage_terms = ("water", "bottled water", "sparkling water", "soda", "cola", "soft drink", "beverage", "drink")
    water_terms = ("water", "bottled water", "sparkling water")
    plastic_bottle_terms = (
        "plastic bottle",
        "plastic-bottle",
        "pet bottle",
        "pet-bottle",
        "en:plastic-bottle",
        "en:pet-bottle",
    )
    can_terms = (
        "aluminum can",
        "aluminium can",
        "metal can",
        "beverage can",
        "en:aluminum-can",
        "en:metal-can",
        "en:beverage-can",
        "en:can",
    )
    glass_bottle_terms = ("glass bottle", "en:glass-bottle")
    glass_jar_terms = ("glass jar", "en:glass-jar")
    carton_terms = (
        "carton",
        "beverage carton",
        "drink carton",
        "milk carton",
        "juice carton",
        "en:carton",
        "en:beverage-carton",
        "en:milk-carton",
        "en:juice-carton",
    )
    cardboard_terms = ("cardboard", "paperboard", "box", "en:box")
    plastic_bag_terms = ("plastic bag", "en:plastic-bag")
    wrapper_terms = ("wrapper", "pouch", "film", "en:wrapper", "en:pouch", "en:film")
    chip_context_terms = ("chips", "crisps", "snack", "snacks")
    candy_context_terms = ("candy", "chocolate", "sweet", "sweets", "bar", "dessert")
    cup_terms = ("plastic cup", "cup", "en:cup")
    detergent_terms = ("detergent", "laundry detergent", "fabric softener")
    shampoo_terms = ("shampoo", "conditioner")

    if _contains_any(packaging_haystack, glass_jar_terms):
        return _build_label_match("Glass jar")

    if _contains_any(packaging_haystack, glass_bottle_terms):
        return _build_label_match("Glass bottle")

    if _contains_any(packaging_haystack, can_terms):
        return _build_label_match("Soda can")

    if _contains_any(packaging_haystack, carton_terms):
        return _build_label_match("Drink carton")

    if _contains_any(packaging_haystack, cardboard_terms):
        return _build_label_match("Cardboard box")

    if _contains_any(packaging_haystack, plastic_bag_terms):
        return _build_label_match("Plastic bag")

    if _contains_any(packaging_haystack, plastic_bottle_terms) and _contains_any(
        context_haystack,
        water_terms,
    ):
        return _build_label_match("Plastic water bottle")

    if _contains_any(packaging_haystack, plastic_bottle_terms) and _contains_any(
        context_haystack,
        beverage_terms[3:],
    ):
        return _build_label_match("Soda bottle")

    if _contains_any(packaging_haystack, wrapper_terms) and _contains_any(
        context_haystack,
        chip_context_terms,
    ):
        return _build_label_match("Chip bag")

    if _contains_any(packaging_haystack, wrapper_terms) and _contains_any(
        context_haystack,
        candy_context_terms,
    ):
        return _build_label_match("Candy wrapper")

    if _contains_any(packaging_haystack, cup_terms) and _contains_any(
        context_haystack,
        ("yogurt", "yoghurt", "cup"),
    ):
        return _build_label_match("Plastic cup")

    if _contains_any(packaging_haystack, plastic_bottle_terms) and _contains_any(
        context_haystack,
        detergent_terms,
    ):
        return _build_label_match("Detergent bottle")

    if _contains_any(packaging_haystack, plastic_bottle_terms) and _contains_any(
        context_haystack,
        shampoo_terms,
    ):
        return _build_label_match("Shampoo bottle")

    return None
