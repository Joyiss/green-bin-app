from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_SUPABASE_CLIENT: Client | None = None
_TABLE_NAME = "scan_feedback"
logger = logging.getLogger(__name__)


class FeedbackRepositoryUnavailable(RuntimeError):
    pass


def _get_supabase_client() -> Client | None:
    global _SUPABASE_CLIENT

    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        logger.info(
            "Scan feedback storage unavailable because service-role credentials are missing."
        )
        return None

    try:
        _SUPABASE_CLIENT = create_client(supabase_url, supabase_key)
    except Exception as exc:
        logger.warning("Failed to create scan feedback client: %s", type(exc).__name__)
        return None
    return _SUPABASE_CLIENT


def _require_client() -> Client:
    client = _get_supabase_client()
    if client is None:
        raise FeedbackRepositoryUnavailable("Scan feedback storage is unavailable.")
    return client


def _first_row(response: Any) -> dict[str, Any] | None:
    rows = getattr(response, "data", None)
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    return row if isinstance(row, dict) else None


def upsert_scan_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    """Store result-sheet feedback with the server-side Supabase client."""
    try:
        response = (
            _require_client()
            .table(_TABLE_NAME)
            .upsert(payload, on_conflict="request_id")
            .execute()
        )
    except FeedbackRepositoryUnavailable:
        raise
    except Exception as exc:
        raise FeedbackRepositoryUnavailable(
            f"Could not store scan feedback: {exc}"
        ) from exc

    row = _first_row(response)
    if row is None:
        raise FeedbackRepositoryUnavailable("Scan feedback upsert returned no row.")
    return row
