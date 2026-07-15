from __future__ import annotations

import json
import logging
import os
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
        logger.warning(
            "Supabase guidance lookup unavailable because credentials are missing."
        )
        return None

    try:
        _SUPABASE_CLIENT = create_client(supabase_url, supabase_key)
    except Exception as exc:
        logger.warning("Failed to create Supabase guidance client: %s", exc)
        return None

    return _SUPABASE_CLIENT


def _response_data(response: Any) -> Any:
    return getattr(response, "data", None)


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
        if not normalized_value:
            return []

        try:
            parsed_value = json.loads(normalized_value)
        except json.JSONDecodeError:
            return [normalized_value]

        if isinstance(parsed_value, list):
            return [str(item).strip() for item in parsed_value if str(item).strip()]
        if isinstance(parsed_value, str) and parsed_value.strip():
            return [parsed_value.strip()]

    return []


def _normalize_guidance_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        logger.warning("Supabase guidance lookup returned an unexpected row shape.")
        return None

    return {
        "id": _normalize_optional_string(row.get("id")),
        "item_label": _normalize_optional_string(row.get("item_label")),
        "item_label_key": _normalize_optional_string(row.get("item_label_key")),
        "material_category": _normalize_optional_string(row.get("material_category")),
        "material_category_key": _normalize_optional_string(
            row.get("material_category_key")
        ),
        "disposal_action": _normalize_optional_string(row.get("disposal_action")),
        "material_code": _normalize_optional_string(row.get("material_code")),
        "impact_level": _normalize_optional_string(row.get("impact_level")),
        "summary": _normalize_optional_string(row.get("summary")),
        "steps": _normalize_string_list(row.get("steps")),
        "warnings": _normalize_string_list(row.get("warnings")),
        "accepted_in_curbside": row.get("accepted_in_curbside"),
        "requires_dropoff": row.get("requires_dropoff"),
        "source_name": _normalize_optional_string(row.get("source_name")),
        "source_url": _normalize_optional_string(row.get("source_url")),
        "location_scope": _normalize_optional_string(row.get("location_scope")),
        "created_at": _normalize_optional_string(row.get("created_at")),
        "updated_at": _normalize_optional_string(row.get("updated_at")),
    }


def _normalize_row_list(rows: Any) -> list[dict[str, Any]]:
    if rows is None:
        return []
    if not isinstance(rows, list):
        logger.warning("Supabase guidance lookup returned an unexpected row collection.")
        return []

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_row = _normalize_guidance_row(row)
        if normalized_row is not None:
            normalized_rows.append(normalized_row)

    return normalized_rows


def _select_first_by_column(column_name: str, value: str) -> dict[str, Any] | None:
    client = _get_supabase_client()
    if client is None:
        return None

    try:
        response = (
            client.table(_TABLE_NAME)
            .select("*")
            .eq(column_name, value)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("Supabase guidance lookup failed for %s=%s: %s", column_name, value, exc)
        return None

    rows = _normalize_row_list(_response_data(response))
    return rows[0] if rows else None


def get_guidance_by_item_label_key(item_label_key: str | None) -> dict[str, Any] | None:
    if not item_label_key:
        return None

    return _select_first_by_column("item_label_key", item_label_key)


def get_guidance_by_material_category_key(
    material_category_key: str | None,
) -> dict[str, Any] | None:
    if not material_category_key:
        return None

    return _select_first_by_column("material_category_key", material_category_key)


def get_general_fallback_guidance() -> dict[str, Any] | None:
    client = _get_supabase_client()
    if client is None:
        return None

    try:
        response = client.table(_TABLE_NAME).select("*").limit(100).execute()
    except Exception as exc:
        logger.warning("Supabase guidance fallback lookup failed: %s", exc)
        return None

    for row in _normalize_row_list(_response_data(response)):
        if not row.get("item_label_key") and not row.get("material_category_key"):
            return row

    return None
