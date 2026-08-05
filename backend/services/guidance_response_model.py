from __future__ import annotations

import re
from typing import Any, TypedDict
from urllib.parse import urlparse


class GuidanceSummary(TypedDict):
    action_type: str
    destination: str | None
    qualifier: str | None


class GuidancePreparation(TypedDict):
    required: bool
    steps: list[str]
    no_preparation_message: str | None


class GuidanceReference(TypedDict):
    source_title: str
    url: str
    supports_claim: str


class StructuredGuidance(TypedDict):
    summary: GuidanceSummary
    disposal_steps: list[str]
    preparation: GuidancePreparation
    important_notes: list[str]
    reasoning: str
    references: list[GuidanceReference]


_PREPARATION_ACTION = re.compile(
    r"\b(empty|rinse|wash|clean|dry|drain|remove|detach|separate|sort|bag|wrap|"
    r"package|pack|seal|close|cap|secure|tape|protect|wipe|erase|delete|back up|"
    r"disconnect|keep|leave)\b",
    re.IGNORECASE,
)
_ROUTE_ACTION = re.compile(
    r"\b(schedule|appointment|visit|call|contact|take|bring|deliver|drop[ -]?off|"
    r"find|choose|travel|drive|curbside|collection|trash|recycl(?:e|ing)|compost)\b",
    re.IGNORECASE,
)
_PACKAGING_ACTION = re.compile(
    r"\b(bag|wrap|package|pack|seal|secure|tape|protect)\b",
    re.IGNORECASE,
)
_IMPORTANT_NOTE = re.compile(
    r"(?:\bfee\b|\bcost\b|\bcharge\w*\b|\bpaid\b|\$\s*\d|"
    r"\brestrict\w*\b|\bprohibit\w*\b|\bnot accepted\b|\bdoes not accept\b|"
    r"\bcannot\b|\bcan't\b|\bmust not\b|\bdo not\b|\bonly\b|\blimit\w*\b|"
    r"\bresiden\w*\b|\bproof of (?:residency|address)\b|"
    r"\bappointment\w*\b|\bschedul\w*\b|\bcall ahead\b|"
    r"\bsafe\w*\b|\bhazard\w*\b|\bfire\b|\bleak\w*\b|\bdamag\w*\b|"
    r"\bterminal\w*\b|\bflammable\b|\btoxic\b|\bsharp\w*\b)",
    re.IGNORECASE,
)
_IGNORED_RELEVANCE_TERMS = {
    "and", "for", "item", "material", "other", "that", "the", "this", "with"
}


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [normalized for item in value if (normalized := _text(item)) is not None]


def _key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    return re.sub(
        r"\b(dropoff|takeback)\b",
        lambda match: "drop off" if match.group(1) == "dropoff" else "take back",
        normalized,
    ).strip()


def obvious_duplicate(first: str | None, second: str | None) -> bool:
    if not first or not second:
        return False
    left = _key(first)
    right = _key(second)
    if not left or not right:
        return False
    return left == right or (
        min(len(left), len(right)) >= 24
        and (left in right or right in left)
    )


def _unique_against(values: list[str], against: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if any(obvious_duplicate(value, existing) for existing in [*against, *result]):
            continue
        result.append(value)
    return result


def is_preparation_action(value: str) -> bool:
    if not _PREPARATION_ACTION.search(value):
        return False
    return not _ROUTE_ACTION.search(value) or bool(_PACKAGING_ACTION.search(value))


def _meaningful_terms(value: str | None) -> set[str]:
    return {
        term
        for term in _key(value or "").split()
        if len(term) >= 4 and term not in _IGNORED_RELEVANCE_TERMS
    }


def _note_applies(value: str, item: str | None, category: str | None) -> bool:
    looks_like_unrelated_list = value.count(",") >= 2 or bool(
        re.search(r"\b(such as|including|listed as|other accepted)\b", value, re.IGNORECASE)
    )
    if not looks_like_unrelated_list:
        return True
    relevant = _meaningful_terms(item) | _meaningful_terms(category)
    return bool(relevant & _meaningful_terms(value))


def _short_reason(value: Any) -> str:
    reason = _text(value) or ""
    first_sentence = re.split(r"(?<=[.!?])\s+", reason, maxsplit=1)[0]
    return first_sentence[:220].rstrip()


def _valid_reference_url(value: Any) -> str | None:
    url = _text(value)
    if url is None:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _references(value: Any) -> list[GuidanceReference]:
    if not isinstance(value, list):
        return []
    result: list[GuidanceReference] = []
    seen_urls: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("source_title") or raw.get("title"))
        url = _valid_reference_url(raw.get("url"))
        claim = _text(
            raw.get("supports_claim")
            or raw.get("support_description")
            or raw.get("description")
        )
        if not title or not url or not claim:
            continue
        url_key = url.casefold().rstrip("/")
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        result.append({"source_title": title, "url": url, "supports_claim": claim})
    return result


def post_process_structured_guidance(
    value: Any,
    *,
    item: str | None = None,
    category: str | None = None,
) -> StructuredGuidance | None:
    """Normalize the section contract and remove obvious cross-section repetition."""
    if not isinstance(value, dict):
        return None
    raw_summary = value.get("summary")
    raw_preparation = value.get("preparation")
    if not isinstance(raw_summary, dict) or not isinstance(raw_preparation, dict):
        return None

    action_type = _text(raw_summary.get("action_type"))
    if action_type is None:
        return None
    destination = _text(raw_summary.get("destination"))
    qualifier = _text(raw_summary.get("qualifier"))
    if obvious_duplicate(qualifier, action_type) or obvious_duplicate(qualifier, destination):
        qualifier = None

    raw_preparation_steps = [
        step
        for step in _strings(raw_preparation.get("steps"))
        if is_preparation_action(step)
    ]
    if qualifier and any(
        obvious_duplicate(qualifier, step) for step in raw_preparation_steps
    ):
        # Keep an imperative action in Preparation instead of consuming it as
        # the summary's qualifier.
        qualifier = None
    summary_values = [action_type, destination, qualifier]
    preparation_steps = raw_preparation_steps
    preparation_steps = _unique_against(preparation_steps, summary_values)
    disposal_steps = _unique_against(
        _strings(value.get("disposal_steps"))[:4],
        preparation_steps,
    )

    notes = [
        note
        for note in _strings(value.get("important_notes"))
        if _IMPORTANT_NOTE.search(note) and _note_applies(note, item, category)
    ]
    notes = _unique_against(notes, [*summary_values, *preparation_steps])

    return {
        "summary": {
            "action_type": action_type,
            "destination": destination,
            "qualifier": qualifier,
        },
        "disposal_steps": disposal_steps,
        "preparation": {
            "required": bool(preparation_steps),
            "steps": preparation_steps,
            # Missing preparation evidence is not evidence that no preparation is needed.
            "no_preparation_message": (
                None
                if preparation_steps
                else _text(raw_preparation.get("no_preparation_message"))
            ),
        },
        "important_notes": notes,
        "reasoning": _short_reason(value.get("reasoning")),
        "references": _references(value.get("references")),
    }
