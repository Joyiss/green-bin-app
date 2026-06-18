from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_SUPABASE_CLIENT: Client | None = None
_TABLE_NAME = "recognition_cache"


def _get_supabase_client() -> Client:
    global _SUPABASE_CLIENT

    if _SUPABASE_CLIENT is None:
        supabase_url = os.getenv("SUPABASE_URL")
        if not supabase_url:
            raise RuntimeError("SUPABASE_URL is not set. Add it to backend/.env.")

        supabase_key = os.getenv("SUPABASE_KEY")
        if not supabase_key:
            raise RuntimeError("SUPABASE_KEY is not set. Add it to backend/.env.")

        try:
            _SUPABASE_CLIENT = create_client(supabase_url, supabase_key)
        except Exception as exc:
            raise RuntimeError(f"Failed to create Supabase client: {exc}") from exc

    return _SUPABASE_CLIENT


def _response_data(response: Any) -> Any:
    return getattr(response, "data", None)


def _first_row_or_error(rows: Any, error_prefix: str, missing_message: str) -> dict[str, Any]:
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"{error_prefix}: {missing_message}")

    first_row = rows[0]
    if not isinstance(first_row, dict):
        raise RuntimeError(f"{error_prefix}: Supabase returned an unexpected row shape.")

    return dict(first_row)


def save_recognition_record(
    *,
    item_label: str,
    recognition_source: str,
    phash: str | None = None,
    clip_embedding: list[float] | None = None,
    confidence: float | None = None,
    verified: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "phash": phash,
        "clip_embedding": clip_embedding,
        "item_label": item_label,
        "recognition_source": recognition_source,
        "confidence": confidence,
        "verified": verified,
        "metadata": metadata or {},
    }

    try:
        response = (
            _get_supabase_client()
            .table(_TABLE_NAME)
            .insert(payload)
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to save recognition cache record: {exc}") from exc

    return _first_row_or_error(
        _response_data(response),
        "Failed to save recognition cache record",
        "Supabase did not return the inserted row.",
    )


def get_recognition_record_by_id(record_id: str) -> dict[str, Any] | None:
    try:
        response = (
            _get_supabase_client()
            .table(_TABLE_NAME)
            .select("*")
            .eq("id", record_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch recognition cache record by id: {exc}") from exc

    if response is None:
        return None

    row = _response_data(response)
    if row is None:
        return None
    if not isinstance(row, dict):
        raise RuntimeError(
            "Failed to fetch recognition cache record by id: "
            "Supabase returned an unexpected row shape."
        )

    return dict(row)


def find_recognition_records_by_phash(phash: str) -> list[dict[str, Any]]:
    try:
        response = (
            _get_supabase_client()
            .table(_TABLE_NAME)
            .select("*")
            .eq("phash", phash)
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to find recognition cache records by phash: {exc}") from exc

    rows = _response_data(response)
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise RuntimeError(
            "Failed to find recognition cache records by phash: "
            "Supabase returned an unexpected row shape."
        )

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError(
                "Failed to find recognition cache records by phash: "
                "Supabase returned an unexpected row shape."
            )
        normalized_rows.append(dict(row))

    return normalized_rows


def delete_recognition_record_by_id(record_id: str) -> dict[str, Any] | None:
    try:
        response = (
            _get_supabase_client()
            .table(_TABLE_NAME)
            .delete()
            .eq("id", record_id)
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to delete recognition cache record by id: {exc}") from exc

    rows = _response_data(response)
    if rows is None:
        return None
    if not isinstance(rows, list):
        raise RuntimeError(
            "Failed to delete recognition cache record by id: "
            "Supabase returned an unexpected row shape."
        )
    if not rows:
        return None

    first_row = rows[0]
    if not isinstance(first_row, dict):
        raise RuntimeError(
            "Failed to delete recognition cache record by id: "
            "Supabase returned an unexpected row shape."
        )

    return dict(first_row)
