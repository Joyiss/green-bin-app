from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_SUPABASE_CLIENT: Client | None = None
_TABLE_NAME = "scan_usage_daily"
_MAX_INCREMENT_RETRIES = 4
logger = logging.getLogger(__name__)


class ScanUsageLimitReachedError(Exception):
    """Raised when today's usage is already at the configured limit."""


class ScanUsageRepositoryError(RuntimeError):
    """Raised when usage cannot be checked or incremented safely."""


def _get_supabase_client() -> Client | None:
    global _SUPABASE_CLIENT

    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        logger.info("Supabase scan usage unavailable because credentials are missing.")
        return None

    try:
        _SUPABASE_CLIENT = create_client(supabase_url, supabase_key)
    except Exception as exc:
        logger.warning("Failed to create Supabase scan usage client: %s", exc)
        return None

    return _SUPABASE_CLIENT


def _response_data(response: Any) -> Any:
    return getattr(response, "data", None)


def _first_row(rows: Any) -> dict[str, Any] | None:
    if not isinstance(rows, list) or not rows:
        return None

    row = rows[0]
    return row if isinstance(row, dict) else None


def _scan_count(row: dict[str, Any] | None) -> int:
    if row is None:
        return 0

    try:
        return int(row.get("scan_count") or 0)
    except (TypeError, ValueError):
        raise ScanUsageRepositoryError("Supabase scan usage row had invalid scan_count.")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _fetch_usage_row(
    client: Client,
    *,
    client_id_hash: str,
    usage_date: date,
) -> dict[str, Any] | None:
    try:
        response = (
            client.table(_TABLE_NAME)
            .select("id,scan_count")
            .eq("client_id_hash", client_id_hash)
            .eq("usage_date", usage_date.isoformat())
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise ScanUsageRepositoryError(f"Failed to fetch daily scan usage: {exc}") from exc

    return _first_row(_response_data(response))


def _insert_first_usage_row(
    client: Client,
    *,
    client_id_hash: str,
    usage_date: date,
) -> int | None:
    payload = {
        "client_id_hash": client_id_hash,
        "usage_date": usage_date.isoformat(),
        "scan_count": 1,
        "updated_at": _now_iso(),
    }

    try:
        response = client.table(_TABLE_NAME).insert(payload).execute()
    except Exception:
        return None

    row = _first_row(_response_data(response))
    return _scan_count(row) if row is not None else 1


def _compare_and_increment_usage_row(
    client: Client,
    *,
    client_id_hash: str,
    usage_date: date,
    current_count: int,
) -> int | None:
    next_count = current_count + 1

    try:
        response = (
            client.table(_TABLE_NAME)
            .update({"scan_count": next_count, "updated_at": _now_iso()})
            .eq("client_id_hash", client_id_hash)
            .eq("usage_date", usage_date.isoformat())
            .eq("scan_count", current_count)
            .execute()
        )
    except Exception as exc:
        raise ScanUsageRepositoryError(f"Failed to update daily scan usage: {exc}") from exc

    row = _first_row(_response_data(response))
    if row is None:
        return None

    return _scan_count(row)


def increment_daily_scan_usage(
    *,
    client_id_hash: str,
    usage_date: date,
    daily_limit: int,
) -> int:
    client = _get_supabase_client()
    if client is None:
        raise ScanUsageRepositoryError("Supabase scan usage client is unavailable.")

    inserted_count = _insert_first_usage_row(
        client,
        client_id_hash=client_id_hash,
        usage_date=usage_date,
    )
    if inserted_count is not None:
        return inserted_count

    for _ in range(_MAX_INCREMENT_RETRIES):
        row = _fetch_usage_row(
            client,
            client_id_hash=client_id_hash,
            usage_date=usage_date,
        )
        current_count = _scan_count(row)

        if current_count >= daily_limit:
            raise ScanUsageLimitReachedError

        incremented_count = _compare_and_increment_usage_row(
            client,
            client_id_hash=client_id_hash,
            usage_date=usage_date,
            current_count=current_count,
        )
        if incremented_count is not None:
            return incremented_count

    raise ScanUsageRepositoryError("Failed to safely increment daily scan usage.")
