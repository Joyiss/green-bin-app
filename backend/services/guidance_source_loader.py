from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_SOURCE_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "trusted_guidance_sources.json"
)
_GUIDANCE_SOURCE_CACHE: dict[str, list[dict[str, Any]]] = {}


def reset_guidance_source_cache() -> None:
    _GUIDANCE_SOURCE_CACHE.clear()


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None

    normalized_value = str(value).strip()
    return normalized_value or None


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        normalized_value = value.strip()
        return [normalized_value] if normalized_value else []

    return []


def _normalize_source_url(value: Any) -> str | None:
    normalized_value = _normalize_optional_string(value)
    if normalized_value is None:
        return None

    markdown_match = re.fullmatch(r"\[[^\]]+\]\((https?://[^)]+)\)", normalized_value)
    if markdown_match:
        return markdown_match.group(1).strip()

    if normalized_value.startswith("http://") or normalized_value.startswith("https://"):
        return normalized_value

    embedded_match = re.search(r"(https?://[^\s)]+)", normalized_value)
    if embedded_match:
        return embedded_match.group(1).strip()

    return normalized_value


def _normalize_applies_to(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        value = {}

    return {
        "item_labels": _normalize_string_list(value.get("item_labels")),
        "materials": _normalize_string_list(value.get("materials")),
        "categories": _normalize_string_list(value.get("categories")),
        "condition_flags": _normalize_string_list(value.get("condition_flags")),
    }


def _normalize_chunk(raw_chunk: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw_chunk, dict):
        return None

    normalized_chunk = {
        "id": _normalize_optional_string(raw_chunk.get("id")) or f"chunk-{index}",
        "title": _normalize_optional_string(raw_chunk.get("title")),
        "source_name": _normalize_optional_string(raw_chunk.get("source_name")),
        "source_url": _normalize_source_url(raw_chunk.get("source_url")),
        "source_type": _normalize_optional_string(raw_chunk.get("source_type")),
        "location_scope": _normalize_optional_string(raw_chunk.get("location_scope")),
        "generalizable": bool(raw_chunk.get("generalizable", False)),
        "requires_location_check": bool(
            raw_chunk.get("requires_location_check", False)
        ),
        "applies_to": _normalize_applies_to(raw_chunk.get("applies_to")),
        "content": _normalize_optional_string(raw_chunk.get("content")),
        "disposal_actions_supported": _normalize_string_list(
            raw_chunk.get("disposal_actions_supported")
        ),
        "warnings": _normalize_string_list(raw_chunk.get("warnings")),
        "limitations": _normalize_string_list(raw_chunk.get("limitations")),
        "confidence": _normalize_optional_string(raw_chunk.get("confidence")),
        "verified": bool(raw_chunk.get("verified", False)),
        "source_grounded": bool(raw_chunk.get("source_grounded", True)),
        "human_reviewed": bool(raw_chunk.get("human_reviewed", False)),
        "review_status": _normalize_optional_string(raw_chunk.get("review_status"))
        or "generated_from_sources",
    }

    return normalized_chunk


def _extract_raw_chunks(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        chunks = payload.get("chunks")
        if isinstance(chunks, list):
            return chunks
    return []


def load_trusted_guidance_chunks(
    *,
    force_reload: bool = False,
    file_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    resolved_path = Path(file_path) if file_path is not None else _DEFAULT_SOURCE_FILE
    cache_key = str(resolved_path.resolve())

    if not force_reload and cache_key in _GUIDANCE_SOURCE_CACHE:
        return list(_GUIDANCE_SOURCE_CACHE[cache_key])

    try:
        raw_text = resolved_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Trusted guidance source file was not found: %s", resolved_path)
        _GUIDANCE_SOURCE_CACHE[cache_key] = []
        return []
    except OSError as exc:
        logger.warning(
            "Trusted guidance source file could not be read: %s error=%s",
            resolved_path,
            exc,
        )
        _GUIDANCE_SOURCE_CACHE[cache_key] = []
        return []

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Trusted guidance source file contained malformed JSON: %s error=%s",
            resolved_path,
            exc,
        )
        _GUIDANCE_SOURCE_CACHE[cache_key] = []
        return []

    normalized_chunks: list[dict[str, Any]] = []
    for index, raw_chunk in enumerate(_extract_raw_chunks(payload), start=1):
        normalized_chunk = _normalize_chunk(raw_chunk, index)
        if normalized_chunk is not None:
            normalized_chunks.append(normalized_chunk)

    _GUIDANCE_SOURCE_CACHE[cache_key] = normalized_chunks
    return list(normalized_chunks)
