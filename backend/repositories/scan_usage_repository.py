from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_SUPABASE_CLIENT: Client | None = None
_RESERVATION_LOCK = threading.Lock()
_TABLE_NAME = "scan_usage_daily"
logger = logging.getLogger(__name__)

ScanLimitPeriod = Literal["daily", "monthly"]


class ScanUsageRepositoryError(RuntimeError):
    """Raised when scan usage cannot be checked or incremented safely."""


@dataclass(frozen=True)
class ScanUsageSnapshot:
    daily_count: int
    monthly_count: int


@dataclass(frozen=True)
class ScanUsageReservation:
    allowed: bool
    daily_count: int
    monthly_count: int
    limit_period: ScanLimitPeriod | None


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


def _first_row(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, dict):
        return value
    return None


def _non_negative_integer(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ScanUsageRepositoryError(
            f"Scan usage response returned invalid {field}."
        ) from exc
    if parsed < 0:
        raise ScanUsageRepositoryError(
            f"Scan usage response returned invalid {field}."
        )
    return parsed


def _next_month(usage_date: date) -> date:
    if usage_date.month == 12:
        return date(usage_date.year + 1, 1, 1)
    return date(usage_date.year, usage_date.month + 1, 1)


def get_scan_usage(
    *,
    client_id_hash: str,
    usage_date: date,
) -> ScanUsageSnapshot:
    client = _get_supabase_client()
    if client is None:
        raise ScanUsageRepositoryError("Supabase scan usage client is unavailable.")

    month_start = usage_date.replace(day=1)
    next_month = _next_month(usage_date)
    try:
        response = (
            client.table(_TABLE_NAME)
            .select("usage_date,scan_count")
            .eq("client_id_hash", client_id_hash)
            .gte("usage_date", month_start.isoformat())
            .lt("usage_date", next_month.isoformat())
            .execute()
        )
    except Exception as exc:
        raise ScanUsageRepositoryError(f"Failed to fetch scan usage: {exc}") from exc

    rows = _response_data(response)
    if not isinstance(rows, list):
        raise ScanUsageRepositoryError("Scan usage query returned an unexpected response.")

    daily_count = 0
    monthly_count = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ScanUsageRepositoryError("Scan usage query returned an invalid row.")
        scan_count = _non_negative_integer(row.get("scan_count"), "scan_count")
        monthly_count += scan_count
        if row.get("usage_date") == usage_date.isoformat():
            daily_count = scan_count

    return ScanUsageSnapshot(
        daily_count=daily_count,
        monthly_count=monthly_count,
    )


def reserve_scan_usage(
    *,
    client_id_hash: str,
    usage_date: date,
    daily_limit: int,
    monthly_limit: int,
) -> ScanUsageReservation:
    client = _get_supabase_client()
    if client is None:
        raise ScanUsageRepositoryError("Supabase scan usage client is unavailable.")

    reservation_time = datetime.combine(usage_date, datetime.min.time(), tzinfo=UTC)
    try:
        # The RPC takes a per-user transaction-scoped advisory lock, so the
        # check-and-increment remains atomic across workers and backend instances.
        with _RESERVATION_LOCK:
            response = client.rpc(
                "reserve_scan_usage",
                {
                    "p_client_id_hash": client_id_hash,
                    "p_daily_limit": daily_limit,
                    "p_monthly_limit": monthly_limit,
                    "p_now": reservation_time.isoformat(),
                },
            ).execute()
    except Exception as exc:
        raise ScanUsageRepositoryError(
            f"Failed to reserve scan usage: {type(exc).__name__}"
        ) from exc

    row = _first_row(_response_data(response))
    if row is None or not isinstance(row.get("allowed"), bool):
        raise ScanUsageRepositoryError(
            "Scan usage reservation returned an unexpected response."
        )

    raw_period = row.get("limit_period")
    limit_period: ScanLimitPeriod | None
    if raw_period in {"daily", "monthly"}:
        limit_period = raw_period
    elif raw_period is None:
        limit_period = None
    else:
        raise ScanUsageRepositoryError(
            "Scan usage reservation returned an invalid limit period."
        )

    if row["allowed"] and limit_period is not None:
        raise ScanUsageRepositoryError(
            "Allowed scan usage reservation unexpectedly included a limit period."
        )
    if not row["allowed"] and limit_period is None:
        raise ScanUsageRepositoryError(
            "Rejected scan usage reservation omitted its limit period."
        )

    return ScanUsageReservation(
        allowed=row["allowed"],
        daily_count=_non_negative_integer(row.get("daily_count"), "daily_count"),
        monthly_count=_non_negative_integer(
            row.get("monthly_count"), "monthly_count"
        ),
        limit_period=limit_period,
    )
