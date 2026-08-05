from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import requests

try:
    from tavily import TavilyClient
except ImportError:  # The guarded import keeps non-Tavily test environments usable.
    TavilyClient = None  # type: ignore[assignment]

try:
    from ..repositories import tavily_budget_repository
    from . import request_context
    from .guidance_key_service import normalize_guidance_phrase
    from .open_label_normalizer import (
        build_canonical_search_label,
        is_meaningful_search_label,
    )
except ImportError:
    from repositories import tavily_budget_repository
    from services import request_context
    from services.guidance_key_service import normalize_guidance_phrase
    from services.open_label_normalizer import (
        build_canonical_search_label,
        is_meaningful_search_label,
    )

logger = logging.getLogger(__name__)

DEFAULT_TAVILY_DAILY_CREDIT_LIMIT = 100
DEFAULT_TAVILY_MONTHLY_CREDIT_LIMIT = 1000
DEFAULT_TAVILY_TIMEOUT_SECONDS = 10.0
MAX_QUERY_LENGTH = 399
MAX_DIAGNOSTIC_CONTENT_CHARS = 12000
MAX_RAW_CONTENT_CHARS_FOR_EXTRACTION = 50000
MAX_TAVILY_SOURCE_CONTEXT_CHARS = 2400
MAX_TAVILY_CONCISE_CONTENT_CHARS = 1000
MAX_TAVILY_RAW_EXCERPT_CHARS = 1500
RAW_EXCERPT_WINDOW_CHARS = 360
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_LOCATION_FIELDS = ("city", "county", "state", "country", "waste_provider")
_LOCALITY_FIELDS = ("city", "county", "state", "waste_provider")
_GENERIC_ITEM_NAMES = {
    "item",
    "object",
    "thing",
    "unknown object",
    "unknown",
    "product",
    "material",
    "container",
    "packaging",
    "recyclable",
    "waste",
    "trash",
}
_CONDITION_TERMS = {
    "battery",
    "broken",
    "clean",
    "contaminated",
    "dirty",
    "dry",
    "empty",
    "food_soiled",
    "hazardous",
    "leaking",
    "opened",
    "pressurized",
    "rechargeable",
    "reusable",
    "wet",
}
_QUERY_CONDITION_TERMS = {
    "broken",
    "contaminated",
    "leaking",
    "pressurized",
    "rechargeable",
}
_GENERIC_MATERIAL_TERMS = {
    "battery",
    "batteries",
    "container",
    "electronics",
    "mixed material",
    "organic",
    "packaging",
    "recyclable",
    "trash",
    "unknown",
    "waste",
}
_BRAND_HINT_TERMS = {"brand", "model", "series"}
_BATTERY_CHEMISTRY_TERMS = (
    "alkaline",
    "button cell",
    "lead acid",
    "lithium",
    "lithium ion",
    "lithium-ion",
    "nickel cadmium",
    "nimh",
)
_EXTRACTION_RELATED_TERMS_BY_CATEGORY = {
    "battery": (
        "alkaline",
        "button cell",
        "lead acid",
        "lead-acid",
        "lithium",
        "lithium ion",
        "lithium-ion",
        "rechargeable",
        "drop-off",
        "accepted",
        "prohibited",
        "household hazardous waste",
    ),
    "electronics": (
        "electronics",
        "e-waste",
        "drop-off",
        "accepted",
        "prohibited",
        "recycle",
    ),
    "plastic": (
        "plastic",
        "bottle",
        "container",
        "accepted",
        "prohibited",
        "empty",
        "clean",
        "dry",
    ),
    "textile": (
        "clothing",
        "textile",
        "donate",
        "reuse",
        "recycle",
        "drop-off",
        "accepted",
    ),
    "organic": (
        "compost",
        "yard waste",
        "food scraps",
        "accepted",
        "prohibited",
    ),
}
_EXTRACTION_ACTION_TERMS = (
    "accept",
    "accepted",
    "drop off",
    "drop-off",
    "prohibit",
    "prohibited",
    "not accepted",
    "recycle",
    "trash",
    "curbside",
    "collection",
    "convenience center",
    "household hazardous waste",
)
_BOILERPLATE_LINE_PATTERNS = (
    r"^\s*(skip to|go to|back to|breadcrumb|section menu|quick links|popular pages|related tags)\b",
    r"^\s*(contact|connect|mobile apps|social media|privacy policy|terms of use)\s*$",
    r"^\s*(copyright|©|\(c\))\b",
    r"^\s*(accept cookies|reject cookies|we use cookies)\b",
    r"^\s*(print this page|share this page|search)\b",
    r"^\s*\[[^\]]{0,80}\]\([^)]*\)\s*$",
    r"^\s*!\[[^\]]*\]\([^)]*\)\s*$",
    r"^\s*(\*|\+|-)\s*\[[^\]]{0,80}\]\([^)]*\)\s*$",
)
_UNTRUSTED_INSTRUCTION_TERMS = (
    "ignore previous",
    "ignore all instructions",
    "system prompt",
    "developer message",
    "assistant message",
    "reveal the prompt",
    "api key",
    "execute this code",
)
_REJECTED_SOURCE_DOMAINS = (
    "reddit.",
    "facebook.",
    "instagram.",
    "x.com",
    "twitter.",
    "tiktok.",
    "youtube.",
    "pinterest.",
    "medium.",
    "blogspot.",
    "wordpress.",
)
_LOW_QUALITY_SOURCE_TERMS = (
    "affiliate links",
    "sponsored content",
    "click here to learn more",
    "top 10",
    "best recycling near me",
    "seo content",
)
_DIRECTORY_SOURCE_TERMS = (
    "directory",
    "provider listings",
    "facility listings",
    "find a recycler",
    "recycling guide",
)
_RETAIL_CONTEXT_TERMS = (
    "retailer",
    "retail store",
    "in store",
    "participating stores",
    "store locations",
    "trade in",
)
_TAKEBACK_EVIDENCE_TERMS = (
    "take back",
    "takeback",
    "trade in",
    "in store recycling",
    "stores accept",
    "participating stores accept",
)
_DIRECT_SERVICE_SOURCE_TERMS = (
    "charity",
    "donation center",
    "non-profit",
    "nonprofit",
    "recycler",
    "recycling center",
    "reuse center",
    "service provider",
    "waste company",
    "disposal facility",
    "transfer station",
    "collection service",
)
_OWN_SERVICE_EVIDENCE_TERMS = (
    "we accept",
    "our facility",
    "our facilities",
    "our service",
    "our services",
    "our locations",
    "accepted at our",
    "schedule a pickup",
    "drop off at",
)
_DISPOSAL_CHANNEL_TERMS = (
    "collection",
    "curbside",
    "drop off",
    "pickup",
    "recycling center",
    "take back",
    "takeback",
)
_OPERATIONAL_DETAIL_TERMS = (
    "appointment",
    "available",
    "bring",
    "eligible",
    "fee",
    "hours",
    "limit",
    "location",
    "place",
    "requirement",
    "resident",
    "schedule",
)
_SAFETY_CONTEXT_TERMS = (
    "fire risk",
    "handling",
    "hazard",
    "safety",
)
_UNSAFE_DISPOSAL_ACTIONS = (
    "burn",
    "dump into",
    "dump in",
    "pour down",
    "pour into",
    "bury",
    "abandon",
)
_UNSAFE_DISPOSAL_INSTRUCTION_TERMS = (
    "can",
    "just",
    "must",
    "recommend",
    "safe to",
    "should",
    "simply",
)
_NEGATED_INSTRUCTION_TERMS = (
    "avoid",
    "cannot",
    "do not",
    "don't",
    "illegal",
    "must not",
    "never",
    "not allowed",
    "not safe",
    "prohibited",
    "should not",
    "unsafe",
)
_NATIONAL_APPLICABILITY_TERMS = (
    "nationwide",
    "national program",
    "across the united states",
    "all stores",
)
_OFFICIAL_SERVICE_TERMS = (
    "city",
    "county",
    "state",
    "sanitation",
    "utilities",
    "utility",
    "environmental",
    "recycling",
    "solid waste",
    "waste management",
    "public works",
)
_COMMERCIAL_PROVIDER_TERMS = (
    "trash pickup",
    "waste services",
    "disposal services",
    "dumpster",
    "roll off",
    "residential service",
    "commercial service",
)
_STATEWIDE_TERMS = (
    "statewide",
    "state-wide",
    "state program",
    "state rule",
    "state law",
    "state agency",
    "all residents",
)
_CORE_DISPOSAL_ACTIONS = (
    "recycle",
    "trash",
    "compost",
    "drop-off",
    "check local guidance",
)
_GENERIC_DISPOSAL_RELEVANCE_TERMS = {
    "accept",
    "accepted",
    "collection",
    "disposal",
    "drop off",
    "recycle",
    "recycling",
    "take back",
    "takeback",
    "trash",
    "waste",
}
_CONTAINING_CATEGORY_TERMS = {
    "appliances": ("appliance", "appliances"),
    "battery": ("battery", "batteries"),
    "batteries": ("battery", "batteries"),
    "cardboard": ("cardboard",),
    "electronics": (
        "electronic",
        "electronics",
        "electronic waste",
        "e waste",
        "computer peripheral",
        "computer peripherals",
    ),
    "fabric textile": ("fabric", "textile", "textiles", "clothing"),
    "glass": ("glass",),
    "organic": ("food scraps", "food waste", "organic", "organics"),
    "paper": ("paper",),
    "textiles": ("fabric", "textile", "textiles", "clothing"),
}
LOCAL_PRIMARY = "LOCAL_PRIMARY"
OFFICIAL_SUPPORTING = "OFFICIAL_SUPPORTING"
DISCOVERY_ONLY = "DISCOVERY_ONLY"
REJECTED = "REJECTED"

OFFICIAL_PRIMARY_ROLE = "official_primary"
DIRECT_SERVICE_PROVIDER_ROLE = "direct_service_provider"
RETAILER_TAKEBACK_ROLE = "retailer_takeback"
REPUTABLE_SUPPORTING_ROLE = "reputable_supporting"
DISCOVERY_ONLY_ROLE = "discovery_only"

_OFFICIAL_CLAIM_SCOPE = (
    "jurisdiction_wide_rules",
    "laws",
    "curbside_policies",
    "public_programs",
)
_PROVIDER_CLAIM_SCOPE = (
    "own_accepted_items",
    "own_services",
    "own_locations",
    "own_fees",
    "own_hours",
    "own_limits",
)
_RETAILER_CLAIM_SCOPE = (
    "own_takeback_program",
    "own_accepted_items",
    "own_locations",
    "own_fees",
    "own_hours",
    "own_limits",
)
_SUPPORTING_CLAIM_SCOPE = ("supporting_context",)
_DISCOVERY_CLAIM_SCOPE = ("source_discovery",)
_STATE_ABBREVIATIONS = {
    "alabama": "al",
    "alaska": "ak",
    "arizona": "az",
    "arkansas": "ar",
    "california": "ca",
    "colorado": "co",
    "connecticut": "ct",
    "delaware": "de",
    "florida": "fl",
    "georgia": "ga",
    "hawaii": "hi",
    "idaho": "id",
    "illinois": "il",
    "indiana": "in",
    "iowa": "ia",
    "kansas": "ks",
    "kentucky": "ky",
    "louisiana": "la",
    "maine": "me",
    "maryland": "md",
    "massachusetts": "ma",
    "michigan": "mi",
    "minnesota": "mn",
    "mississippi": "ms",
    "missouri": "mo",
    "montana": "mt",
    "nebraska": "ne",
    "nevada": "nv",
    "new hampshire": "nh",
    "new jersey": "nj",
    "new mexico": "nm",
    "new york": "ny",
    "north carolina": "nc",
    "north dakota": "nd",
    "ohio": "oh",
    "oklahoma": "ok",
    "oregon": "or",
    "pennsylvania": "pa",
    "rhode island": "ri",
    "south carolina": "sc",
    "south dakota": "sd",
    "tennessee": "tn",
    "texas": "tx",
    "utah": "ut",
    "vermont": "vt",
    "virginia": "va",
    "washington": "wa",
    "west virginia": "wv",
    "wisconsin": "wi",
    "wyoming": "wy",
}


@dataclass(frozen=True)
class _LocalBudgetState:
    day: date
    month: tuple[int, int]
    daily_count: int
    monthly_count: int


@dataclass(frozen=True)
class _SourceRecord:
    position: int
    title: str
    url: str
    domain: str
    organization: str
    snippet: str
    content: str
    relevance_score: float
    raw_content: str = ""


@dataclass(frozen=True)
class _SourceValidation:
    title: str | None
    url: str
    domain: str
    organization: str | None
    trust_level: str
    source_role: str
    claim_scope: tuple[str, ...]
    applicability_label: str
    rejection_reasons: tuple[str, ...]
    location_matches: dict[str, bool]
    content: str
    excerpt: str
    relevance_score: float


class TavilyBudgetGuard:
    """Process-local guard layered on top of the cross-instance database RPC."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: _LocalBudgetState | None = None

    def reserve(
        self,
        *,
        now_utc: datetime,
        daily_limit: int,
        monthly_limit: int,
    ) -> bool:
        normalized_now = (
            now_utc.replace(tzinfo=UTC)
            if now_utc.tzinfo is None
            else now_utc.astimezone(UTC)
        )
        current_day = normalized_now.date()
        current_month = (normalized_now.year, normalized_now.month)
        with self._lock:
            state = self._state
            daily_count = (
                state.daily_count if state is not None and state.day == current_day else 0
            )
            monthly_count = (
                state.monthly_count
                if state is not None and state.month == current_month
                else 0
            )
            if daily_count >= daily_limit or monthly_count >= monthly_limit:
                self._state = _LocalBudgetState(
                    current_day,
                    current_month,
                    daily_count,
                    monthly_count,
                )
                return False
            self._state = _LocalBudgetState(
                current_day,
                current_month,
                daily_count + 1,
                monthly_count + 1,
            )
            return True

    def reset_for_tests(self) -> None:
        with self._lock:
            self._state = None


_LOCAL_BUDGET_GUARD = TavilyBudgetGuard()


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(str(os.getenv(name) or "").strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(str(os.getenv(name) or "").strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _enabled() -> bool:
    value = str(os.getenv("ENABLE_TAVILY_LOCAL_GUIDANCE", "true")).strip().casefold()
    if value in _FALSE_VALUES:
        return False
    return value in _TRUE_VALUES


def _development_diagnostics_enabled() -> bool:
    if str(os.getenv("TAVILY_DIAGNOSTIC_CONTENT_LOGGING") or "").strip().casefold() in _FALSE_VALUES:
        return False
    for name in ("APP_ENV", "ENVIRONMENT", "NODE_ENV", "FLASK_ENV", "FASTAPI_ENV"):
        if str(os.getenv(name) or "").strip().casefold() in {"development", "dev", "local"}:
            return True
    return str(os.getenv("DEBUG") or "").strip().casefold() in _TRUE_VALUES


def _truncate_for_diagnostic_log(value: Any, *, max_chars: int = MAX_DIAGNOSTIC_CONTENT_CHARS) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}...[truncated {len(text) - max_chars} chars]"


def _redact_url_for_diagnostic_log(value: Any) -> str:
    url = "" if value is None else str(value).strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except ValueError:
        return "[redacted_invalid_url]"
    sensitive = (
        "access_token",
        "apikey",
        "api_key",
        "auth",
        "authorization",
        "client_id",
        "client_secret",
        "code",
        "key",
        "password",
        "secret",
        "session",
        "sig",
        "signature",
        "token",
    )
    if not parsed.query:
        return url
    query_parts = []
    for part in parsed.query.split("&"):
        key, separator, value_part = part.partition("=")
        if any(term in key.casefold() for term in sensitive):
            query_parts.append(f"{key}{separator}[redacted]")
        else:
            query_parts.append(f"{key}{separator}{value_part}" if separator else key)
    return parsed._replace(query="&".join(query_parts)).geturl()


def _redact_content_for_diagnostic_log(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", " ")
    text = re.sub(
        r"[-+]?\d{1,3}\.\d{3,}\s*[,/]\s*[-+]?\d{1,3}\.\d{3,}",
        "[redacted_coordinates]",
        text,
    )
    text = re.sub(
        r"(?i)\b(authorization|api[_-]?key|access[_-]?token|client[_-]?secret|secret|password)\b\s*[:=]\s*\S+",
        r"\1=[redacted]",
        text,
    )
    text = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[redacted_email]",
        text,
        flags=re.IGNORECASE,
    )
    return _truncate_for_diagnostic_log(text)


def _log_diagnostic(label: str, payload: dict[str, Any]) -> None:
    if not _development_diagnostics_enabled():
        return
    safe_payload = {"request_id": request_context.get_predict_request_id(), **payload}
    logger.info(
        "%s %s",
        label,
        json.dumps(safe_payload, ensure_ascii=True, sort_keys=True),
    )


def _text(value: Any, *, max_length: int = 120) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized or "@" in normalized or "://" in normalized:
        return None
    if re.search(
        r"[-+]?\d{1,3}\.\d{3,}\s*[,/]\s*[-+]?\d{1,3}\.\d{3,}",
        normalized,
    ) or re.fullmatch(r"[-+]?\d{1,3}(?:\.\d+)?", normalized):
        return None
    if re.search(r"(?:\+?\d[\s().-]*){8,}", normalized):
        return None
    return normalized[:max_length].strip() or None


def normalize_coarse_location(location: Any) -> dict[str, str]:
    if not isinstance(location, dict):
        return {}
    normalized: dict[str, str] = {}
    for field in _LOCATION_FIELDS:
        value = _text(location.get(field))
        if value:
            normalized[field] = value
    return normalized


def _normalized_details(classification: dict[str, Any]) -> dict[str, Any]:
    recognition = classification.get("recognition_details")
    recognition = recognition if isinstance(recognition, dict) else {}
    normalized = recognition.get("normalized")
    return normalized if isinstance(normalized, dict) else {}


def _normalized_item(classification: dict[str, Any]) -> str | None:
    normalized = _normalized_details(classification)
    for value in (
        normalized.get("normalized_item"),
        normalized.get("item_label"),
        classification.get("item"),
    ):
        text = _text(value, max_length=100)
        normalized_text = normalize_guidance_phrase(text)
        if normalized_text:
            return normalized_text
    return None


def _material(classification: dict[str, Any]) -> str | None:
    normalized = _normalized_details(classification)
    for value in (
        normalized.get("material"),
        normalized.get("material_category"),
        classification.get("recognized_material_category"),
        classification.get("category"),
    ):
        text = _text(value, max_length=80)
        if text and text.casefold() != "unknown":
            return text
    return None


def _category(classification: dict[str, Any]) -> str | None:
    normalized = _normalized_details(classification)
    for value in (
        normalized.get("disposal_category"),
        normalized.get("broad_category"),
        classification.get("category"),
    ):
        if text := _text(value, max_length=80):
            return text
    return None


def _condition_flags(classification: dict[str, Any]) -> list[str]:
    normalized = _normalized_details(classification)
    values = [
        *(normalized.get("condition_flags") or []),
        *(normalized.get("special_handling_flags") or []),
        *(normalized.get("special_flags") or []),
    ]
    flags: list[str] = []
    for value in values:
        key = (normalize_guidance_phrase(value) or "").replace(" ", "_")
        if key in _CONDITION_TERMS and key not in flags:
            flags.append(key)
    return flags[:3]


def _eligibility_reason(
    classification: dict[str, Any],
    *,
    clarification_required: bool,
    location: dict[str, str],
) -> str | None:
    if classification.get("status") != "confident":
        return "recognition_not_confident"
    if clarification_required:
        return "clarification_required"
    item = _specific_item_for_query(classification)
    if not is_meaningful_search_label(item):
        return "item_not_specific"
    if not location:
        return "missing_location"
    return None


def _normalized_tokens(value: Any) -> list[str]:
    normalized = normalize_guidance_phrase(value) or ""
    return [
        token
        for token in normalized.split()
        if len(token) >= 3 and token not in {"city", "county", "state", "waste"}
    ]


def _query_tokens(value: str) -> set[str]:
    return set(_normalized_tokens(value))


def _contains_battery_chemistry(value: str | None) -> bool:
    normalized = normalize_guidance_phrase(value) or ""
    return any(term.replace("-", " ") in normalized for term in _BATTERY_CHEMISTRY_TERMS)


def _dedupe_query_terms(parts: list[str]) -> list[str]:
    selected: list[str] = []
    selected_tokens: set[str] = set()
    for part in parts:
        normalized = normalize_guidance_phrase(part)
        if not normalized:
            continue
        tokens = _query_tokens(normalized)
        if selected and tokens and tokens.issubset(selected_tokens):
            continue
        selected.append(normalized)
        selected_tokens.update(tokens)
    return selected


def _specific_item_for_query(classification: dict[str, Any]) -> str:
    recognition = classification.get("recognition_details")
    recognition = recognition if isinstance(recognition, dict) else {}
    normalized = _normalized_details(classification)
    stored_search_item = normalize_guidance_phrase(normalized.get("search_item"))
    if stored_search_item and is_meaningful_search_label(stored_search_item):
        return stored_search_item

    candidates = [
        normalized.get("normalized_item"),
        normalized.get("item_label"),
        classification.get("item"),
        recognition.get("raw_item_label"),
    ]
    primary = next(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, str) and candidate.strip()
        ),
        "",
    )
    canonical = build_canonical_search_label(
        primary,
        broad_category=normalized.get("broad_category") or classification.get("category"),
    )
    clean_candidates = [canonical] if is_meaningful_search_label(canonical) else []
    if not clean_candidates:
        return ""

    battery_candidates = [
        candidate
        for candidate in clean_candidates
        if _query_tokens(candidate) & {"battery", "batteries"}
    ]
    if battery_candidates and not any(
        _contains_battery_chemistry(candidate) for candidate in battery_candidates
    ):
        rechargeable = any(flag == "rechargeable" for flag in _condition_flags(classification))
        if rechargeable:
            return "rechargeable battery"
        return min(battery_candidates, key=lambda value: len(_query_tokens(value)))

    return clean_candidates[0]


def _remove_brand_terms(item: str, classification: dict[str, Any]) -> str:
    normalized = _normalized_details(classification)
    brand_values = [
        normalize_guidance_phrase(value)
        for key, value in normalized.items()
        if any(hint in str(key).casefold() for hint in _BRAND_HINT_TERMS)
    ]
    result = item
    for brand in [value for value in brand_values if value]:
        result = re.sub(rf"(?<![a-z0-9]){re.escape(brand)}(?![a-z0-9])", " ", result)
    return re.sub(r"\s+", " ", result).strip() or item


def _material_adds_specificity(item: str, material: str | None) -> bool:
    normalized_material = normalize_guidance_phrase(material)
    if not normalized_material or normalized_material in _GENERIC_MATERIAL_TERMS:
        return False
    item_tokens = _query_tokens(item)
    material_tokens = _query_tokens(normalized_material)
    if not material_tokens or material_tokens.issubset(item_tokens):
        return False
    if item_tokens & {"battery", "batteries"} and not _contains_battery_chemistry(normalized_material):
        return False
    return True


def _item_phrase_for_query(classification: dict[str, Any]) -> str:
    item = _remove_brand_terms(_specific_item_for_query(classification), classification)
    parts = [item]
    item_tokens = _query_tokens(item)
    for flag in _condition_flags(classification):
        if flag in _QUERY_CONDITION_TERMS and flag not in item_tokens:
            parts.insert(0, flag.replace("_", " "))
    return " ".join(_dedupe_query_terms(parts))


def _location_phrase_for_query(location: dict[str, str]) -> str:
    city = _text(location.get("city"))
    county = _text(location.get("county"))
    state = _text(location.get("state"))
    country = _text(location.get("country"))
    country_needed = bool(country and country.casefold() not in {"us", "usa", "united states"})

    if city and state:
        parts = [city, state]
    elif county and state:
        parts = [county, state]
    elif city:
        parts = [city]
    elif county:
        parts = [county]
    elif state:
        parts = [state]
    else:
        parts = [country] if country else []

    if country_needed and country and country not in parts:
        parts.append(country)
    return ", ".join(parts)


def build_search_query(
    classification: dict[str, Any],
    location: dict[str, str],
) -> str:
    item = _item_phrase_for_query(classification)
    category = normalize_guidance_phrase(
        _category(classification) or _material(classification) or item
    ) or item
    location_phrase = _location_phrase_for_query(location)
    query = (
        f"{item} ({category}) disposal or recycling for residents in {location_phrase}: "
        "curbside rules, drop-off, take-back, accepted items, fees, appointments"
    )
    return re.sub(r"\s+", " ", query).strip()[:MAX_QUERY_LENGTH].rstrip()


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def _sanitize_untrusted_content(
    value: Any,
    *,
    max_length: int = 6000,
) -> str:
    if not isinstance(value, str):
        return ""
    safe_lines: list[str] = []
    current_length = 0
    for line in value.replace("\x00", " ").splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        lowered = normalized.casefold()
        if not normalized or any(term in lowered for term in _UNTRUSTED_INSTRUCTION_TERMS):
            continue
        safe_lines.append(normalized)
        current_length += len(normalized)
        if current_length >= max_length:
            break
    return "\n".join(safe_lines)[:max_length]


def _is_boilerplate_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", line).strip()
    if not normalized:
        return True
    if len(normalized) <= 2:
        return True
    if re.fullmatch(r"https?://\S+", normalized):
        return True
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in _BOILERPLATE_LINE_PATTERNS):
        return True
    words = re.findall(r"[A-Za-z]{3,}", normalized)
    if len(words) <= 2 and any(marker in normalized for marker in ("[", "](", "http")):
        return True
    return False


def _clean_content_for_llm(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    lines: list[str] = []
    seen: set[str] = set()
    for line in value.replace("\x00", " ").splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        lowered = normalized.casefold()
        if (
            not normalized
            or any(term in lowered for term in _UNTRUSTED_INSTRUCTION_TERMS)
            or _is_boilerplate_line(normalized)
        ):
            continue
        compact = re.sub(r"https?://\S+", "", normalized).strip()
        compact = re.sub(r"\[[^\]]{0,80}\]\([^)]*\)", "", compact).strip()
        compact = re.sub(r"\s+", " ", compact)
        key = normalize_guidance_phrase(compact) or compact.casefold()
        if not compact or key in seen:
            continue
        seen.add(key)
        lines.append(compact)
    return "\n".join(lines)


def _truncate_cleanly(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    trimmed = value[:max_length].rstrip()
    boundary = max(trimmed.rfind("\n"), trimmed.rfind(". "), trimmed.rfind("; "))
    if boundary >= max_length // 2:
        trimmed = trimmed[: boundary + 1].rstrip()
    return trimmed


def _context_terms_for_extraction(classification: dict[str, Any]) -> list[str]:
    details = _normalized_details(classification)
    candidates: list[Any] = [
        _normalized_item(classification),
        _specific_item_for_query(classification),
        _material(classification),
        _category(classification),
        classification.get("category"),
        classification.get("recognized_material_category"),
        details.get("disposal_category"),
        details.get("broad_category"),
        *_condition_flags(classification),
    ]
    terms: list[str] = []
    for candidate in candidates:
        normalized = normalize_guidance_phrase(candidate)
        if not normalized:
            continue
        terms.append(normalized)
        terms.extend(token for token in normalized.split() if len(token) >= 4)
    normalized_category = normalize_guidance_phrase(_category(classification) or classification.get("category"))
    normalized_material = normalize_guidance_phrase(_material(classification))
    for key, related_terms in _EXTRACTION_RELATED_TERMS_BY_CATEGORY.items():
        if key in {normalized_category, normalized_material} or key in " ".join(terms):
            terms.extend(related_terms)
    terms.extend(_EXTRACTION_ACTION_TERMS)
    return _dedupe_query_terms(terms)


def _line_score(line: str, terms: list[str]) -> tuple[int, list[str]]:
    normalized = normalize_guidance_phrase(line) or ""
    matched = [
        term
        for term in terms
        if term and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized)
    ]
    if not matched:
        return 0, []
    action_matches = set(matched) & set(_EXTRACTION_ACTION_TERMS)
    item_matches = set(matched) - set(_EXTRACTION_ACTION_TERMS)
    score = len(item_matches) * 3 + len(action_matches)
    return score, matched


def _relevant_raw_excerpts(
    raw_content: str,
    *,
    terms: list[str],
    concise_content: str,
    max_chars: int = MAX_TAVILY_RAW_EXCERPT_CHARS,
) -> tuple[str, list[str]]:
    cleaned = _clean_content_for_llm(raw_content)
    if not cleaned:
        return "", ["no_clean_raw_content"]
    lines = [line for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return "", ["no_clean_raw_content"]

    concise_key = normalize_guidance_phrase(concise_content) or ""
    scored: list[tuple[int, int, list[str]]] = []
    for index, line in enumerate(lines):
        score, matched = _line_score(line, terms)
        if score <= 0:
            continue
        normalized_line = normalize_guidance_phrase(line) or ""
        if concise_key and normalized_line and normalized_line in concise_key:
            score -= 1
        scored.append((score, index, matched))
    if not scored:
        return "", ["no_term_matches_in_raw_content"]

    selected_blocks: list[str] = []
    selected_reasons: list[str] = []
    used_indexes: set[int] = set()
    for score, index, matched in sorted(scored, key=lambda value: (-value[0], value[1])):
        if len("\n\n".join(selected_blocks)) >= max_chars:
            break
        start = max(0, index - 2)
        end = min(len(lines), index + 3)
        block_lines: list[str] = []
        for line_index in range(start, end):
            if line_index in used_indexes:
                continue
            line = lines[line_index]
            nearby_score, _ = _line_score(line, terms)
            is_short_heading = (
                line_index < index
                and len(line) <= 80
                and not re.search(r"[.!?]$", line)
                and any(_line_score(lines[next_index], terms)[0] > 0 for next_index in range(line_index + 1, end))
            )
            if line_index == index or nearby_score > 0 or is_short_heading:
                block_lines.append(line)
        if not block_lines:
            continue
        block = _truncate_cleanly("\n".join(block_lines), RAW_EXCERPT_WINDOW_CHARS)
        if not block:
            continue
        selected_blocks.append(block)
        used_indexes.update(range(start, end))
        selected_reasons.append(
            f"centered_on_terms:{','.join(matched[:6])}:line={index + 1}:score={score}"
        )

    excerpt = "\n\n".join(selected_blocks)
    return _truncate_cleanly(excerpt, max_chars), selected_reasons or ["selected_relevant_raw_excerpt"]


def _prepare_source_context_for_llm(
    record: _SourceRecord,
    *,
    validation: _SourceValidation,
    classification: dict[str, Any],
) -> tuple[str, str, list[str]]:
    snippet = _clean_content_for_llm(record.snippet)
    concise = _truncate_cleanly(snippet, MAX_TAVILY_CONCISE_CONTENT_CHARS)
    terms = _context_terms_for_extraction(classification)
    raw_excerpt, raw_reasons = _relevant_raw_excerpts(
        record.raw_content or record.content,
        terms=terms,
        concise_content=concise,
    )
    parts = [part for part in (concise, raw_excerpt) if part]
    final_content = _truncate_cleanly(
        "\n\n".join(parts) or validation.excerpt or validation.title or "",
        MAX_TAVILY_SOURCE_CONTEXT_CHARS,
    )
    reasons: list[str] = []
    if concise:
        reasons.append("tavily_content_primary")
    if raw_excerpt:
        reasons.extend(raw_reasons)
    if len("\n\n".join(parts)) > len(final_content):
        reasons.append("source_context_truncated_to_limit")
    if not raw_excerpt:
        reasons.extend(raw_reasons)
    return final_content, concise, list(dict.fromkeys(reasons))


def _log_prepared_source_context(
    *,
    record: _SourceRecord,
    validation: _SourceValidation,
    final_content: str,
    original_snippet: str,
    reasons: list[str],
) -> None:
    _log_diagnostic(
        "TAVILY_EXTRACTED_CONTEXT",
        {
            "position": record.position,
            "title": validation.title,
            "url": _redact_url_for_diagnostic_log(validation.url),
            "domain": validation.domain,
            "trust_level": validation.trust_level,
            "applicability_label": validation.applicability_label,
            "original_snippet": _redact_content_for_diagnostic_log(original_snippet),
            "final_excerpt": _redact_content_for_diagnostic_log(final_content),
            "selection_reasons": reasons,
            "original_snippet_chars": len(original_snippet),
            "original_raw_chars": len(record.raw_content or record.content),
            "final_excerpt_chars": len(final_content),
        },
    )


def _organization(title: str, host: str, location: dict[str, str]) -> str:
    for separator in (" | ", " - ", " - ", " -- "):
        parts = [part.strip() for part in title.split(separator) if part.strip()]
        if len(parts) > 1:
            return parts[-1][:160]
    provider = location.get("waste_provider")
    if provider and (normalize_guidance_phrase(provider) or "") in (normalize_guidance_phrase(title) or ""):
        return provider
    return host


def _log_raw_result(position: int, raw_result: Any) -> None:
    if not isinstance(raw_result, dict):
        _log_diagnostic(
            "TAVILY_RAW_RESULT",
            {
                "position": position,
                "raw_result_type": type(raw_result).__name__,
                "title": None,
                "url": None,
                "domain": None,
                "tavily_score": None,
                "content": "",
                "raw_content": "",
            },
        )
        return
    url = _redact_url_for_diagnostic_log(raw_result.get("url"))
    _log_diagnostic(
        "TAVILY_RAW_RESULT",
        {
            "position": position,
            "title": str(raw_result.get("title") or ""),
            "url": url,
            "domain": _host(url),
            "tavily_score": raw_result.get("score"),
            "content": _redact_content_for_diagnostic_log(raw_result.get("content")),
            "raw_content": _redact_content_for_diagnostic_log(raw_result.get("raw_content")),
        },
    )


def _log_source_record_rejected(
    *,
    position: int,
    title: str | None,
    url: str,
    domain: str,
    reasons: list[str],
) -> None:
    _log_diagnostic(
        "TAVILY_FILTERED_RESULT",
        {
            "position": position,
            "title": title,
            "url": _redact_url_for_diagnostic_log(url),
            "domain": domain,
            "trust_level": REJECTED,
            "applicability_label": "invalid_source",
            "accepted": False,
            "rejection_reasons": reasons,
        },
    )


def _source_records(raw_results: list[Any], location: dict[str, str]) -> list[_SourceRecord]:
    records: list[_SourceRecord] = []
    for position, raw_result in enumerate(raw_results[:5], start=1):
        _log_raw_result(position, raw_result)
        if not isinstance(raw_result, dict):
            _log_source_record_rejected(
                position=position,
                title=None,
                url="",
                domain="",
                reasons=["invalid_result_shape"],
            )
            continue
        title = _text(raw_result.get("title"), max_length=200)
        url = str(raw_result.get("url") or "").strip()
        domain = _host(url)
        rejection_reasons: list[str] = []
        if not domain:
            rejection_reasons.append("missing_domain")
        if rejection_reasons:
            _log_source_record_rejected(
                position=position,
                title=title,
                url=url,
                domain=domain,
                reasons=rejection_reasons,
            )
            continue
        raw_content = _sanitize_untrusted_content(
            raw_result.get("raw_content"),
            max_length=MAX_RAW_CONTENT_CHARS_FOR_EXTRACTION,
        )
        snippet = _sanitize_untrusted_content(raw_result.get("content"))[:1000]
        content = (raw_content or snippet)[:6000]
        try:
            relevance_score = float(raw_result.get("score"))
        except (TypeError, ValueError):
            relevance_score = 0.0
        records.append(
            _SourceRecord(
                position=position,
                title=title or domain,
                url=url,
                domain=domain,
                organization=_organization(title, domain, location),
                snippet=snippet,
                content=content,
                relevance_score=relevance_score,
                raw_content=raw_content,
            )
        )
    return records


def _matches_name(left: str | None, right: str | None) -> bool:
    left_norm = normalize_guidance_phrase(left) or ""
    right_norm = normalize_guidance_phrase(right) or ""
    if not left_norm or not right_norm:
        return False
    return left_norm == right_norm or left_norm in right_norm or right_norm in left_norm


def _haystack(record: _SourceRecord) -> str:
    return " ".join(
        value
        for value in (
            record.title,
            record.url,
            record.domain,
            record.organization,
            record.snippet,
            record.content,
        )
        if value
    )


def _normalized_haystack(record: _SourceRecord) -> str:
    return normalize_guidance_phrase(_haystack(record)) or ""


def _state_abbreviation(state: str | None) -> str | None:
    normalized = normalize_guidance_phrase(state)
    if not normalized:
        return None
    if len(normalized) == 2:
        return normalized
    return _STATE_ABBREVIATIONS.get(normalized)


def _wrong_state(record: _SourceRecord, selected_state: str | None) -> bool:
    selected = normalize_guidance_phrase(selected_state)
    if not selected:
        return False
    selected_abbr = _state_abbreviation(selected_state)
    text = _normalized_haystack(record)
    mentioned_states = {
        state
        for state in _STATE_ABBREVIATIONS
        if _term_in_text(state, text)
    }
    if mentioned_states and selected not in mentioned_states:
        return True
    domain_tokens = set(record.domain.casefold().replace("-", ".").split("."))
    state_domain_tokens = domain_tokens & set(_STATE_ABBREVIATIONS.values())
    return bool(state_domain_tokens and selected_abbr not in state_domain_tokens)


def _is_federal_source(record: _SourceRecord) -> bool:
    domain = record.domain.casefold()
    text = _normalized_haystack(record)
    return (
        domain == "epa.gov"
        or domain.endswith(".epa.gov")
        or domain == "usa.gov"
        or domain.endswith(".federalregister.gov")
        or _term_in_text("federal", text)
    )


def _term_in_text(term: str | None, text: str) -> bool:
    normalized = normalize_guidance_phrase(term)
    if not normalized:
        return False
    variants = {normalized}
    if normalized.endswith("y"):
        variants.add(normalized[:-1] + "ies")
    elif normalized.endswith("ies"):
        variants.add(normalized[:-3] + "y")
    elif normalized.endswith("s"):
        variants.add(normalized[:-1])
    else:
        variants.add(normalized + "s")
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(variant)}(?![a-z0-9])", text) is not None
        for variant in variants
        if variant
    )


def _source_matches_provider(record: _SourceRecord, location: dict[str, str]) -> bool:
    provider = normalize_guidance_phrase(location.get("waste_provider"))
    if not provider:
        return False
    text = _normalized_haystack(record)
    provider_tokens = [token for token in provider.split() if len(token) >= 2]
    if provider in text:
        return True
    domain = normalize_guidance_phrase(record.domain.replace(".", " ")) or ""
    return bool(provider_tokens) and all(token in domain for token in provider_tokens)


def _source_quality_rejection(record: _SourceRecord) -> str | None:
    text = _normalized_haystack(record)
    domain = record.domain.casefold()
    if any(term in domain for term in _REJECTED_SOURCE_DOMAINS):
        return "social_or_forum_source"
    if any(term in text for term in _LOW_QUALITY_SOURCE_TERMS):
        return "low_quality_or_seo_source"
    return None


def _is_government_domain(domain: str) -> bool:
    return domain.endswith(".gov") or ".gov/" in domain


def _looks_like_commercial_provider(record: _SourceRecord) -> bool:
    text = _normalized_haystack(record)
    if record.domain.endswith(".gov"):
        return False
    return any(term in text for term in _COMMERCIAL_PROVIDER_TERMS)


def _has_takeback_evidence(record: _SourceRecord) -> bool:
    text = _normalized_haystack(record)
    return any(term in text for term in _TAKEBACK_EVIDENCE_TERMS)


def _has_own_service_evidence(record: _SourceRecord) -> bool:
    text = _normalized_haystack(record)
    explicit_acceptance = bool(
        re.search(
            r"\b(?:accepts?|collects?|picks? up|offers?|provides?)\b.{0,100}"
            r"\b(?:drop off|recycl|dispos|collection|pickup|service|items?)\b",
            text,
        )
    )
    first_party_service = any(term in text for term in _OWN_SERVICE_EVIDENCE_TERMS)
    service_organization = _looks_like_commercial_provider(record) or any(
        term in text for term in _DIRECT_SERVICE_SOURCE_TERMS
    )
    return first_party_service or (explicit_acceptance and service_organization)


def _has_meaningful_disposal_information(record: _SourceRecord) -> bool:
    text = _normalized_haystack(record)
    explicit_disposition = bool(
        re.search(r"\b(?:accepts?|collects?)\b", text)
        or re.search(
            r"\b(?:is|are|may be|can be)\s+"
            r"(?:accepted|allowed|collected|not accepted|prohibited)\b",
            text,
        )
    )
    operational_details = any(term in text for term in _DISPOSAL_CHANNEL_TERMS) and any(
        term in text for term in _OPERATIONAL_DETAIL_TERMS
    )
    safety_context = any(term in text for term in _SAFETY_CONTEXT_TERMS) and any(
        term in text for term in ("disposal", "recycle", "recycling", "waste")
    )
    return (
        _has_takeback_evidence(record)
        or explicit_disposition
        or operational_details
        or safety_context
    )


def _content_statements(record: _SourceRecord) -> list[str]:
    content = "\n".join(
        value for value in (record.title, record.snippet, record.content) if value
    )
    return [
        normalized
        for statement in re.split(r"[\r\n.!?;]+", content)
        if (normalized := normalize_guidance_phrase(statement))
    ]


def _has_unsafe_disposal_instruction(record: _SourceRecord) -> bool:
    for statement in _content_statements(record):
        if not any(action in statement for action in _UNSAFE_DISPOSAL_ACTIONS):
            continue
        if any(term in statement for term in _NEGATED_INSTRUCTION_TERMS):
            continue
        starts_with_unsafe_action = any(
            statement.startswith(action) for action in _UNSAFE_DISPOSAL_ACTIONS
        )
        if starts_with_unsafe_action or any(
            re.search(
                rf"\b{re.escape(term)}\b.{{0,60}}\b{re.escape(action)}\b",
                statement,
            )
            for term in _UNSAFE_DISPOSAL_INSTRUCTION_TERMS
            for action in _UNSAFE_DISPOSAL_ACTIONS
        ):
            return True
    return False


def _source_relevance_targets(classification: dict[str, Any]) -> list[str]:
    values = (
        _specific_item_for_query(classification),
        _normalized_item(classification),
    )
    return list(
        dict.fromkeys(
            target
            for value in values
            if (target := normalize_guidance_phrase(value))
            and target not in _GENERIC_ITEM_NAMES
        )
    )


def _has_directly_contradictory_disposal_claims(
    record: _SourceRecord,
    classification: dict[str, Any],
) -> bool:
    targets = _source_relevance_targets(classification)
    for statement in _content_statements(record):
        for target in targets:
            escaped_target = re.escape(target)
            positive_then_negative = re.search(
                rf"\b(?:accepts?|collects?)\s+{escaped_target}\b.{{0,60}}"
                rf"\b(?:cannot|does not|do not)\s+accept\s+{escaped_target}\b",
                statement,
            )
            target_status_conflict = re.search(
                rf"\b{escaped_target}\b\s+(?:is|are)\s+accepted\b.{{0,60}}"
                rf"\b{escaped_target}\b\s+(?:is|are)\s+(?:not accepted|prohibited)\b",
                statement,
            )
            if positive_then_negative or target_status_conflict:
                return True
    return False


def _source_role(record: _SourceRecord, location: dict[str, str]) -> tuple[str, tuple[str, ...]]:
    text = _normalized_haystack(record)
    if _is_government_domain(record.domain):
        return OFFICIAL_PRIMARY_ROLE, _OFFICIAL_CLAIM_SCOPE
    if any(term in text for term in _DIRECTORY_SOURCE_TERMS):
        return DISCOVERY_ONLY_ROLE, _DISCOVERY_CLAIM_SCOPE
    if (
        _has_takeback_evidence(record)
        and any(term in text for term in _RETAIL_CONTEXT_TERMS)
    ):
        return RETAILER_TAKEBACK_ROLE, _RETAILER_CLAIM_SCOPE
    if _has_own_service_evidence(record):
        return DIRECT_SERVICE_PROVIDER_ROLE, _PROVIDER_CLAIM_SCOPE
    return REPUTABLE_SUPPORTING_ROLE, _SUPPORTING_CLAIM_SCOPE


def _different_named_jurisdiction(
    text: str,
    location_name: str | None,
    pattern: str,
) -> bool:
    selected = normalize_guidance_phrase(location_name)
    if not selected:
        return False
    for match in re.finditer(pattern, text, flags=re.IGNORECASE):
        found = normalize_guidance_phrase(match.group(1))
        if found and not _matches_name(found, selected):
            return True
    return False


def _applicability_label(
    record: _SourceRecord,
    location: dict[str, str],
) -> tuple[str, dict[str, bool], str | None]:
    matches = {field: False for field in _LOCALITY_FIELDS}
    text = _normalized_haystack(record)
    if _source_matches_provider(record, location):
        matches["waste_provider"] = True
        return "provider_exact", matches, None

    if _wrong_state(record, location.get("state")):
        return "jurisdiction_mismatch", matches, "wrong_state"
    if _is_federal_source(record):
        return "federal", matches, None

    city = normalize_guidance_phrase(location.get("city"))
    county = normalize_guidance_phrase(location.get("county"))
    state = normalize_guidance_phrase(location.get("state"))
    state_abbr = _state_abbreviation(location.get("state"))
    if _is_government_domain(record.domain) and state:
        domain_tokens = set(record.domain.replace("-", ".").split("."))
        state_match = _term_in_text(state, text) or bool(state_abbr and state_abbr in domain_tokens)
        statewide_match = any(term in text for term in _STATEWIDE_TERMS)
        if state_match and statewide_match:
            matches["state"] = True
            return "statewide", matches, None
    if city and _term_in_text(city, text) and (
        f"city of {city}" in text
        or "city" in text
        or city.replace(" ", "") in record.domain.replace("-", "").replace(".", "")
    ):
        matches["city"] = True
        return "city_exact", matches, None
    if county and _term_in_text(county, text) and "county" in text:
        matches["county"] = True
        return "county_exact", matches, None

    if _different_named_jurisdiction(text, location.get("city"), r"\bcity of ([a-z][a-z .'-]{2,80})"):
        return "jurisdiction_mismatch", matches, "different_city"
    if _different_named_jurisdiction(text, location.get("county"), r"\b([a-z][a-z .'-]{2,80}) county\b"):
        return "jurisdiction_mismatch", matches, "different_county"

    if _is_government_domain(record.domain) and state and (
        _term_in_text(state, text) or (state_abbr and state_abbr in set(record.domain.split(".")))
    ):
        matches["state"] = True
        return "state_official", matches, None

    if city and _term_in_text(city, text):
        matches["city"] = True
        return "jurisdiction_relevant", matches, None
    if county and _term_in_text(county, text):
        matches["county"] = True
        return "jurisdiction_relevant", matches, None
    if state and (
        _term_in_text(state, text)
        or bool(state_abbr and _term_in_text(state_abbr, text))
    ):
        matches["state"] = True
        return "state_relevant", matches, None
    if any(term in text for term in _NATIONAL_APPLICABILITY_TERMS):
        return "national", matches, None

    return "unknown", matches, "location_not_confirmed"


def _supporting_official_decision(record: _SourceRecord) -> bool:
    text = _normalized_haystack(record)
    domain = record.domain.casefold()
    if domain == "epa.gov" or domain.endswith(".epa.gov"):
        return True
    if _is_government_domain(domain):
        return True
    return "manufacturer" in text and any(
        term in text for term in ("safety", "disposal", "recycling", "recycle")
    )


def _source_is_related(
    record: _SourceRecord,
    classification: dict[str, Any],
) -> bool:
    text = normalize_guidance_phrase(
        " ".join(
            value
            for value in (record.title, record.snippet, record.content)
            if value
        )
    ) or ""
    waste_context = any(
        _term_in_text(term, text)
        for term in (*_GENERIC_DISPOSAL_RELEVANCE_TERMS, "compost")
    )
    if not waste_context:
        return False

    normalized = _normalized_details(classification)
    search_item = _specific_item_for_query(classification)
    recognized_item = _normalized_item(classification)
    relevance_terms: list[str] = []
    for value in (search_item, recognized_item):
        normalized_value = normalize_guidance_phrase(value)
        if not normalized_value or normalized_value in _GENERIC_ITEM_NAMES:
            continue
        relevance_terms.append(normalized_value)
        relevance_terms.extend(
            token
            for token in normalized_value.split()
            if len(token) >= 3
            and token not in _GENERIC_DISPOSAL_RELEVANCE_TERMS
            and token not in _GENERIC_ITEM_NAMES
        )

    category_values = {
        normalize_guidance_phrase(value) or ""
        for value in (
            normalized.get("disposal_category"),
            normalized.get("broad_category"),
            classification.get("category"),
            classification.get("recognized_material_category"),
        )
    }
    for category in category_values:
        relevance_terms.extend(_CONTAINING_CATEGORY_TERMS.get(category, ()))

    meaningful_terms = [
        term
        for term in dict.fromkeys(relevance_terms)
        if term and term not in _GENERIC_DISPOSAL_RELEVANCE_TERMS
    ]
    return any(_term_in_text(term, text) for term in meaningful_terms)


def _source_excerpt(record: _SourceRecord) -> str:
    excerpt = _text(record.snippet, max_length=700) or _text(record.content, max_length=700)
    return excerpt or ""


def _validation_result(
    record: _SourceRecord,
    *,
    classification: dict[str, Any],
    location: dict[str, str],
) -> _SourceValidation:
    applicability, matches, applicability_rejection = _applicability_label(record, location)
    source_role, claim_scope = _source_role(record, location)
    text = _normalized_haystack(record)
    reasons: list[str] = []
    if not _source_is_related(record, classification):
        reasons.append("unrelated_source")
        reasons.append("item_relevance_not_established")
    if (
        source_role != DISCOVERY_ONLY_ROLE
        and not _has_meaningful_disposal_information(record)
    ):
        reasons.append("meaningful_disposal_information_missing")
        reasons.append("generic_landing_page")
    if _has_unsafe_disposal_instruction(record):
        reasons.append("unsafe_disposal_instruction")
    if _has_directly_contradictory_disposal_claims(record, classification):
        reasons.append("internally_contradictory_disposal_claims")
    if quality_rejection := _source_quality_rejection(record):
        reasons.append(quality_rejection)
    if applicability_rejection and applicability_rejection != "location_not_confirmed":
        reasons.append(applicability_rejection)
    if applicability == "jurisdiction_mismatch":
        reasons.append("jurisdiction_mismatch")
    jurisdiction_applies = applicability in {
        "city_exact",
        "county_exact",
        "statewide",
        "provider_exact",
        "jurisdiction_relevant",
        "state_relevant",
        "national",
    }
    jurisdiction_neutral_support = (
        source_role == REPUTABLE_SUPPORTING_ROLE
        and "manufacturer" in text
        and _supporting_official_decision(record)
    )
    provider_claim_with_unconfirmed_location = source_role in {
        DIRECT_SERVICE_PROVIDER_ROLE,
        RETAILER_TAKEBACK_ROLE,
    }
    if not jurisdiction_applies and applicability not in {"federal", "state_official"}:
        if not jurisdiction_neutral_support and not provider_claim_with_unconfirmed_location:
            reasons.append(applicability_rejection or "location_not_confirmed")

    retail_context = any(term in text for term in _RETAIL_CONTEXT_TERMS)
    provider_context = (
        _source_matches_provider(record, location)
        or _looks_like_commercial_provider(record)
        or any(term in text for term in _DIRECT_SERVICE_SOURCE_TERMS)
    )
    if retail_context and source_role != RETAILER_TAKEBACK_ROLE:
        reasons.append("retailer_takeback_evidence_missing")
    if provider_context and source_role not in {
        DIRECT_SERVICE_PROVIDER_ROLE,
        RETAILER_TAKEBACK_ROLE,
        DISCOVERY_ONLY_ROLE,
    }:
        reasons.append("provider_service_evidence_missing")

    local_official = (
        source_role == OFFICIAL_PRIMARY_ROLE
        and applicability in {"city_exact", "county_exact", "statewide", "provider_exact"}
    )
    if reasons:
        trust_level = REJECTED
    elif source_role == DISCOVERY_ONLY_ROLE:
        trust_level = DISCOVERY_ONLY
    elif local_official:
        trust_level = LOCAL_PRIMARY
    elif source_role in {
        OFFICIAL_PRIMARY_ROLE,
        DIRECT_SERVICE_PROVIDER_ROLE,
        RETAILER_TAKEBACK_ROLE,
        REPUTABLE_SUPPORTING_ROLE,
    }:
        trust_level = OFFICIAL_SUPPORTING
    else:
        trust_level = REJECTED
        reasons.append("untrusted_source")

    return _SourceValidation(
        title=record.title,
        url=record.url,
        domain=record.domain,
        organization=record.organization,
        trust_level=trust_level,
        source_role=source_role,
        claim_scope=claim_scope,
        applicability_label=applicability,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
        location_matches=matches,
        content=record.content,
        excerpt=_source_excerpt(record),
        relevance_score=record.relevance_score,
    )


def _source_id(url: str, location: dict[str, str], item: str) -> str:
    fingerprint = "\x1f".join(
        [url, item, *(location.get(field, "") for field in _LOCATION_FIELDS)]
    )
    return "tavily-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]


def _accepted_result_to_evidence(
    record: _SourceRecord,
    validation: _SourceValidation,
    *,
    classification: dict[str, Any],
    location: dict[str, str],
) -> dict[str, Any] | None:
    item = _normalized_item(classification)
    if not item or not (record.raw_content or record.snippet or record.content):
        return None
    local_primary = validation.trust_level == LOCAL_PRIMARY
    provider_specific = validation.source_role in {
        DIRECT_SERVICE_PROVIDER_ROLE,
        RETAILER_TAKEBACK_ROLE,
    }
    guidance_applicable = local_primary or (
        provider_specific
        and validation.applicability_label
        in {"provider_exact", "jurisdiction_relevant", "state_relevant", "national"}
    )
    source_id = _source_id(record.url, location, item)
    source_metadata = {
        "title": validation.title,
        "organization": validation.organization or validation.domain,
        "url": validation.url,
        "trusted": validation.trust_level not in {REJECTED, DISCOVERY_ONLY},
        "local": local_primary,
        "status": (
            "trusted_local"
            if local_primary
            else "provider_specific"
            if validation.source_role == DIRECT_SERVICE_PROVIDER_ROLE
            else "retailer_specific"
            if validation.source_role == RETAILER_TAKEBACK_ROLE
            else "official_supporting"
            if validation.source_role == OFFICIAL_PRIMARY_ROLE
            else "reputable_supporting"
        ),
        "trust_level": validation.trust_level,
        "source_role": validation.source_role,
        "claim_scope": list(validation.claim_scope),
    }
    normalized_details = _normalized_details(classification)
    location_exact = any(
        validation.location_matches.get(field)
        for field in ("city", "county", "waste_provider")
    )
    source_content, source_excerpt, extraction_reasons = _prepare_source_context_for_llm(
        record,
        validation=validation,
        classification=classification,
    )
    _log_prepared_source_context(
        record=record,
        validation=validation,
        final_content=source_content,
        original_snippet=record.snippet,
        reasons=extraction_reasons,
    )

    chunk = {
        "id": source_id,
        "title": f"{validation.trust_level}: {validation.title}",
        "section": validation.trust_level,
        "source_name": validation.organization or validation.domain,
        "source_url": validation.url,
        "source_type": validation.source_role,
        "source_role": validation.source_role,
        "claim_scope": list(validation.claim_scope),
        "location_scope": ", ".join(location.values()),
        "generalizable": False,
        "requires_location_check": not guidance_applicable,
        "applies_to": {
            "item_labels": [item],
            "materials": [value for value in [_material(classification)] if value],
            "categories": [
                value
                for value in [
                    normalized_details.get("disposal_category"),
                    normalized_details.get("broad_category"),
                    classification.get("category"),
                ]
                if isinstance(value, str) and value.strip()
            ],
            "condition_flags": _condition_flags(classification),
        },
        "source_excerpt": source_excerpt or validation.excerpt,
        "source_claim": source_excerpt or validation.excerpt,
        "content": source_content,
        "disposal_actions_supported": list(_CORE_DISPOSAL_ACTIONS),
        "warnings": [],
        "limitations": [],
        "confidence": "high" if guidance_applicable else "medium",
        "verified": validation.trust_level not in {REJECTED, DISCOVERY_ONLY},
        "source_grounded": True,
        "human_reviewed": False,
        "review_status": (
            "tavily_local_primary_source"
            if local_primary
            else f"tavily_{validation.source_role}_source"
        ),
        "dynamic_source": "tavily",
        "untrusted_web_evidence": True,
        "decision_signals": {
            "tavily_trust_level": validation.trust_level,
            "applicability_label": validation.applicability_label,
            "source_role": validation.source_role,
            "claim_scope": list(validation.claim_scope),
            "source_context_extraction_reasons": extraction_reasons,
            "source_context_original_chars": len(record.raw_content or record.content),
            "source_context_final_chars": len(source_content),
        },
        "source_metadata": source_metadata,
    }
    return {
        "chunk": chunk,
        "chunk_id": source_id,
        "score": 100.0 + validation.relevance_score,
        "matched_fields": [
            "tavily_trusted_source",
            validation.trust_level,
            validation.source_role,
            (
                "location_exact"
                if location_exact
                else "statewide_rule"
                if local_primary
                else "provider_specific"
                if provider_specific
                else "reputable_supporting"
            ),
            validation.applicability_label,
        ],
        "requires_location_check": not guidance_applicable,
        "applicability": "applicable" if guidance_applicable else "conditional",
        "applicability_reason_codes": [
            "deterministic_source_filter",
            (
                "source_location_applies"
                if local_primary
                else "provider_specific_claim_applies"
                if guidance_applicable
                else "supporting_source_not_primary_local_authority"
            ),
        ],
        "source_conditions": {
            "required": _condition_flags(classification),
            "confirmed": _condition_flags(classification),
            "missing": [],
            "contradicted": [],
        },
    }


def _credit_usage(payload: Any) -> int | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("usage"), dict):
        return None
    try:
        credits = int(payload["usage"].get("credits"))
    except (TypeError, ValueError):
        return None
    return credits if credits >= 0 else None


def _safe_query_to_log(query: str) -> bool:
    if not query:
        return False
    if "@" in query or "://" in query:
        return False
    if re.search(r"[-+]?\d{1,3}\.\d{3,}\s*[,/]\s*[-+]?\d{1,3}\.\d{3,}", query):
        return False
    if re.search(r"(?:\+?\d[\s().-]*){8,}", query):
        return False
    return True


def _outcome(
    status: str,
    *,
    called: bool = False,
    call_count: int = 0,
    skip_reason: str | None = None,
    duration_ms: float = 0.0,
    result_count: int = 0,
    trusted_source_count: int = 0,
    credits: int | None = None,
    retrieval_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "called": called,
        "call_count": call_count,
        "skip_reason": skip_reason,
        "duration_ms": round(duration_ms, 1),
        "result_count": result_count,
        "trusted_source_count": trusted_source_count,
        "credits": credits,
        "retrieval_results": list(retrieval_results or []),
        "sources": [
            result["chunk"]["source_metadata"]
            for result in retrieval_results or []
            if isinstance(result.get("chunk"), dict)
            and isinstance(result["chunk"].get("source_metadata"), dict)
        ],
    }


def _log_outcome(outcome: dict[str, Any]) -> None:
    logger.info(
        "tavily_local_guidance request_id=%s status=%s called=%s skip_reason=%s "
        "duration_ms=%s result_count=%s trusted_source_count=%s reported_credit_usage=%s call_count=%s",
        request_context.get_predict_request_id(),
        outcome.get("status"),
        outcome.get("called"),
        outcome.get("skip_reason"),
        outcome.get("duration_ms"),
        outcome.get("result_count"),
        outcome.get("trusted_source_count"),
        outcome.get("credits"),
        outcome.get("call_count"),
    )


def _log_query(query: str) -> None:
    if _safe_query_to_log(query):
        _log_diagnostic(
            "TAVILY_SEARCH_REQUEST",
            {"search_query": query},
        )
        logger.info(
            "tavily_local_guidance_query request_id=%s query=%s",
            request_context.get_predict_request_id(),
            query,
        )


def _log_validation_result(position: int, validation: _SourceValidation) -> None:
    _log_diagnostic(
        "TAVILY_FILTERED_RESULT",
        {
            "position": position,
            "title": validation.title,
            "url": _redact_url_for_diagnostic_log(validation.url),
            "domain": validation.domain,
            "trust_level": validation.trust_level,
            "source_role": validation.source_role,
            "claim_scope": list(validation.claim_scope),
            "applicability_label": validation.applicability_label,
            "accepted": validation.trust_level not in {REJECTED, DISCOVERY_ONLY},
            "discovery_only": validation.source_role == DISCOVERY_ONLY_ROLE,
            "rejection_reasons": list(validation.rejection_reasons),
            "tavily_score": validation.relevance_score,
        },
    )
    logger.info(
        "tavily_local_guidance_result request_id=%s position=%s domain=%s "
        "trust_level=%s source_role=%s applicability_label=%s accepted=%s "
        "rejection_reasons=%s",
        request_context.get_predict_request_id(),
        position,
        validation.domain,
        validation.trust_level,
        validation.source_role,
        validation.applicability_label,
        validation.trust_level not in {REJECTED, DISCOVERY_ONLY},
        ",".join(validation.rejection_reasons),
    )


def log_tavily_skip(status: str, reason: str) -> None:
    _log_outcome(_outcome(status, skip_reason=reason))


def _get_client(api_key: str) -> Any:
    if TavilyClient is None:
        raise RuntimeError("tavily-python is not installed")
    return TavilyClient(api_key=api_key)


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, requests.Timeout)) or "timeout" in type(exc).__name__.casefold()


def _search_request(client: Any, *, query: str, timeout_seconds: float) -> Any:
    return client.search(
        query=query,
        topic="general",
        search_depth="basic",
        chunks_per_source=3,
        max_results=5,
        country="united states",
        include_answer=False,
        include_raw_content=False,
        include_images=False,
        auto_parameters=False,
        exact_match=False,
        include_usage=True,
        timeout=timeout_seconds,
    )


def _validated_search_results(
    payload: Any,
    *,
    classification: dict[str, Any],
    location: dict[str, str],
) -> tuple[int, list[dict[str, Any]], int]:
    results = payload.get("results") if isinstance(payload, dict) else None
    results = results if isinstance(results, list) else []
    records = _source_records(results, location)
    accepted: list[dict[str, Any]] = []
    local_primary_count = 0
    for record in records:
        validation = _validation_result(
            record,
            classification=classification,
            location=location,
        )
        _log_validation_result(record.position, validation)
        # Provider role, page type, exact wording, and unconfirmed applicability
        # are analyzer concerns. Reject here only deterministic blocked-domain or
        # obvious item/location mismatches.
        basic_rejections = {
            "social_or_forum_source",
            "wrong_state",
            "different_city",
            "different_county",
            "jurisdiction_mismatch",
            "unrelated_source",
            "item_relevance_not_established",
        }
        if set(validation.rejection_reasons) & basic_rejections:
            continue
        evidence = _accepted_result_to_evidence(
            record,
            validation,
            classification=classification,
            location=location,
        )
        if evidence is not None:
            accepted.append(evidence)
            if validation.trust_level == LOCAL_PRIMARY:
                local_primary_count += 1
    return len(results), accepted, local_primary_count


def search_local_guidance(
    classification: dict[str, Any],
    *,
    clarification_required: bool = False,
    manual_rule_applied: bool = False,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    if manual_rule_applied:
        outcome = _outcome("manual_local_rule", skip_reason="trusted_manual_rule")
        _log_outcome(outcome)
        return outcome

    location = normalize_coarse_location(classification.get("location"))
    logger.info(
        "tavily_search_identity request_id=%s recognized_item=%s search_item=%s",
        request_context.get_predict_request_id(),
        _normalized_item(classification),
        _specific_item_for_query(classification),
    )
    eligibility_reason = _eligibility_reason(
        classification,
        clarification_required=clarification_required,
        location=location,
    )
    if eligibility_reason:
        outcome = _outcome("tavily_disabled", skip_reason=eligibility_reason)
        _log_outcome(outcome)
        return outcome

    api_key = str(os.getenv("TAVILY_API_KEY") or "").strip()
    if not _enabled() or not api_key:
        outcome = _outcome(
            "tavily_disabled",
            skip_reason=(
                "feature_disabled" if not _enabled() else "missing_tavily_api_key"
            ),
        )
        _log_outcome(outcome)
        return outcome

    current_time = now_utc or datetime.now(UTC)
    daily_limit = _positive_int_env(
        "TAVILY_DAILY_CREDIT_LIMIT",
        DEFAULT_TAVILY_DAILY_CREDIT_LIMIT,
    )
    monthly_limit = _positive_int_env(
        "TAVILY_MONTHLY_CREDIT_LIMIT",
        DEFAULT_TAVILY_MONTHLY_CREDIT_LIMIT,
    )
    if not _LOCAL_BUDGET_GUARD.reserve(
        now_utc=current_time,
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
    ):
        outcome = _outcome("tavily_disabled", skip_reason="local_budget_limit_reached")
        _log_outcome(outcome)
        return outcome
    try:
        reservation = tavily_budget_repository.reserve_tavily_search_budget(
            daily_limit=daily_limit,
            monthly_limit=monthly_limit,
            now_utc=current_time,
        )
    except tavily_budget_repository.TavilyBudgetRepositoryError:
        outcome = _outcome("tavily_disabled", skip_reason="budget_tracking_unavailable")
        _log_outcome(outcome)
        return outcome
    if not reservation.allowed:
        outcome = _outcome("tavily_disabled", skip_reason="database_budget_limit_reached")
        _log_outcome(outcome)
        return outcome

    timeout_seconds = _positive_float_env(
        "TAVILY_TIMEOUT_SECONDS",
        DEFAULT_TAVILY_TIMEOUT_SECONDS,
    )
    try:
        client = _get_client(api_key)
    except Exception:
        outcome = _outcome("tavily_error", called=False, duration_ms=0.0)
        _log_outcome(outcome)
        return outcome

    request_started = perf_counter()
    accepted: list[dict[str, Any]] = []
    local_primary_count = 0
    result_count = 0
    reported_credits = 0
    has_reported_credits = False
    search_call_count = 0
    try:
        query = build_search_query(classification, location)
        _log_query(query)
        payload = _search_request(
            client,
            query=query,
            timeout_seconds=timeout_seconds,
        )
        search_call_count = 1
        payload_result_count, payload_accepted, payload_local_count = (
            _validated_search_results(
                payload,
                classification=classification,
                location=location,
            )
        )
        result_count += payload_result_count
        accepted.extend(payload_accepted)
        local_primary_count += payload_local_count
        payload_credits = _credit_usage(payload)
        if payload_credits is not None:
            reported_credits += payload_credits
            has_reported_credits = True
    except Exception as exc:
        status = "tavily_timeout" if _is_timeout(exc) else "tavily_error"
        outcome = _outcome(
            status,
            called=True,
            call_count=max(1, search_call_count),
            duration_ms=(perf_counter() - request_started) * 1000,
        )
        _log_outcome(outcome)
        return outcome
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                logger.info(
                    "Tavily client cleanup failed. request_id=%s",
                    request_context.get_predict_request_id(),
                )

    outcome = _outcome(
        (
            "tavily_verified_local"
            if local_primary_count
            else "tavily_official_supporting"
            if accepted
            else "tavily_insufficient_evidence"
        ),
        called=True,
        call_count=search_call_count,
        duration_ms=(perf_counter() - request_started) * 1000,
        result_count=result_count,
        trusted_source_count=local_primary_count,
        credits=reported_credits if has_reported_credits else None,
        retrieval_results=accepted,
    )
    _log_outcome(outcome)
    return outcome


def reset_tavily_budget_guard_for_tests() -> None:
    _LOCAL_BUDGET_GUARD.reset_for_tests()
