from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_SUPABASE_CLIENT: Client | None = None
_TABLE_NAME = "disposal_guidance"
logger = logging.getLogger(__name__)


def _get_supabase_client() -> Client | None:
    global _SUPABASE_CLIENT

    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        logger.info(
            "Supabase disposal guidance cache unavailable because credentials are missing."
        )
        return None

    try:
        _SUPABASE_CLIENT = create_client(supabase_url, supabase_key)
    except Exception as exc:
        logger.warning("Failed to create Supabase disposal guidance client: %s", exc)
        return None

    return _SUPABASE_CLIENT


def _response_data(response: Any) -> Any:
    return getattr(response, "data", None)


def _normalize_json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(key): _json_safe_value(nested) for key, nested in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe_value(item_method())
        except Exception:
            pass

    tolist_method = getattr(value, "tolist", None)
    if callable(tolist_method):
        try:
            return _json_safe_value(tolist_method())
        except Exception:
            pass

    return value


def _normalize_guidance_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        logger.warning("Disposal guidance cache returned an unexpected row shape.")
        return None

    normalized_row = dict(row)
    for key in (
        "cache_key_input",
        "guidance_metadata",
        "recognition_context",
        "retrieval_context",
        "matched_fields",
        "retrieval_scores",
    ):
        if key in normalized_row:
            normalized_row[key] = _normalize_json_value(normalized_row[key])

    return normalized_row


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    raw_value = value.strip()
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        logger.warning("Disposal guidance cache row had invalid expires_at: %s", value)
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_expired(row: dict[str, Any]) -> bool:
    expires_at = _parse_timestamp(row.get("expires_at"))
    if expires_at is None:
        return False
    return expires_at <= datetime.now(UTC)


def get_guidance_by_cache_key(cache_key: str | None) -> dict[str, Any] | None:
    if not cache_key:
        return None

    client = _get_supabase_client()
    if client is None:
        return None

    try:
        response = (
            client.table(_TABLE_NAME)
            .select("*")
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("Disposal guidance cache lookup failed: %s", exc)
        return None

    rows = _response_data(response)
    if not isinstance(rows, list) or not rows:
        return None

    row = _normalize_guidance_row(rows[0])
    if row is None or _is_expired(row):
        return None

    return row


def record_guidance_cache_hit(row_id: str | None) -> bool:
    if not row_id:
        return False

    client = _get_supabase_client()
    if client is None:
        return False

    try:
        client.rpc(
            "increment_disposal_guidance_hit_count",
            {"row_id": row_id},
        ).execute()
    except Exception as exc:
        logger.warning("Disposal guidance cache hit update failed: %s", exc)
        return False

    return True


def upsert_guidance_cache_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    client = _get_supabase_client()
    if client is None:
        return None

    safe_payload = _json_safe_value(payload)
    try:
        response = (
            client.table(_TABLE_NAME)
            .upsert(safe_payload, on_conflict="cache_key")
            .execute()
        )
    except Exception as exc:
        logger.warning("Disposal guidance cache upsert failed: %s", exc)
        return None

    rows = _response_data(response)
    if not isinstance(rows, list) or not rows:
        return None

    return _normalize_guidance_row(rows[0])
