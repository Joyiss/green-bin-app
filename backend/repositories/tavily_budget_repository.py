from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_SUPABASE_CLIENT: Client | None = None
_RESERVATION_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


class TavilyBudgetRepositoryError(RuntimeError):
    """Raised when a Tavily budget reservation cannot be made safely."""


@dataclass(frozen=True)
class TavilyBudgetReservation:
    allowed: bool
    daily_count: int
    monthly_count: int
    daily_reset_at: str
    monthly_reset_at: str


def _get_supabase_client() -> Client | None:
    global _SUPABASE_CLIENT

    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        logger.info("Supabase Tavily budget tracking unavailable because credentials are missing.")
        return None

    try:
        _SUPABASE_CLIENT = create_client(supabase_url, supabase_key)
    except Exception as exc:
        raise TavilyBudgetRepositoryError(
            f"Failed to create Supabase Tavily budget client: {type(exc).__name__}"
        ) from exc

    return _SUPABASE_CLIENT


def _response_data(response: Any) -> Any:
    return getattr(response, "data", None)


def _first_row(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, dict):
        return value
    return None


def _integer(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise TavilyBudgetRepositoryError(
            f"Tavily budget reservation returned invalid {field}."
        ) from exc
    if parsed < 0:
        raise TavilyBudgetRepositoryError(
            f"Tavily budget reservation returned invalid {field}."
        )
    return parsed


def reserve_tavily_search_budget(
    *,
    daily_limit: int,
    monthly_limit: int,
    now_utc: datetime | None = None,
) -> TavilyBudgetReservation:
    client = _get_supabase_client()
    if client is None:
        raise TavilyBudgetRepositoryError("Supabase Tavily budget client is unavailable.")

    reservation_time = now_utc or datetime.now(UTC)
    if reservation_time.tzinfo is None:
        reservation_time = reservation_time.replace(tzinfo=UTC)
    reservation_time = reservation_time.astimezone(UTC)

    try:
        # The database RPC is transactionally atomic across backend instances. The
        # process lock avoids unnecessary overlapping RPCs inside one worker.
        with _RESERVATION_LOCK:
            response = client.rpc(
                "reserve_tavily_search_budget",
                {
                    "p_daily_limit": daily_limit,
                    "p_monthly_limit": monthly_limit,
                    "p_now": reservation_time.isoformat(),
                },
            ).execute()
    except Exception as exc:
        raise TavilyBudgetRepositoryError(
            f"Failed to reserve Tavily search budget: {type(exc).__name__}"
        ) from exc

    row = _first_row(_response_data(response))
    if row is None or not isinstance(row.get("allowed"), bool):
        raise TavilyBudgetRepositoryError(
            "Tavily budget reservation returned an unexpected response."
        )

    daily_reset_at = str(row.get("daily_reset_at") or "").strip()
    monthly_reset_at = str(row.get("monthly_reset_at") or "").strip()
    if not daily_reset_at or not monthly_reset_at:
        raise TavilyBudgetRepositoryError(
            "Tavily budget reservation omitted reset timestamps."
        )

    return TavilyBudgetReservation(
        allowed=row["allowed"],
        daily_count=_integer(row.get("daily_count"), "daily_count"),
        monthly_count=_integer(row.get("monthly_count"), "monthly_count"),
        daily_reset_at=daily_reset_at,
        monthly_reset_at=monthly_reset_at,
    )
