from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

try:
    from ..repositories import scan_usage_repository
except ImportError:
    from repositories import scan_usage_repository

DEFAULT_DAILY_SCAN_LIMIT = 5
DEFAULT_MONTHLY_SCAN_LIMIT = 20
_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_FALSE_ENV_VALUES = {"0", "false", "no", "off"}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanRateLimitMetadata:
    daily_limit: int
    daily_scans_remaining: int
    daily_reset_at: str
    monthly_limit: int
    monthly_scans_remaining: int
    monthly_reset_at: str

    @property
    def scans_remaining(self) -> int:
        return self.daily_scans_remaining

    @property
    def reset_at(self) -> str:
        return self.daily_reset_at

    def to_response_payload(self) -> dict[str, int | str]:
        return {
            "daily_limit": self.daily_limit,
            "daily_scans_remaining": self.daily_scans_remaining,
            "daily_reset_at": self.daily_reset_at,
            "monthly_limit": self.monthly_limit,
            "monthly_scans_remaining": self.monthly_scans_remaining,
            "monthly_reset_at": self.monthly_reset_at,
            "scans_remaining": self.daily_scans_remaining,
            "reset_at": self.daily_reset_at,
        }


class MissingScanClientIdError(Exception):
    pass


class DailyScanLimitReachedError(Exception):
    def __init__(self, metadata: ScanRateLimitMetadata):
        self.metadata = metadata
        super().__init__("Daily scan limit reached.")


class MonthlyScanLimitReachedError(Exception):
    def __init__(self, metadata: ScanRateLimitMetadata):
        self.metadata = metadata
        super().__init__("Monthly scan limit reached.")


class ScanRateLimitUnavailableError(RuntimeError):
    pass


def _positive_limit_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed_value = int(raw_value.strip())
    except (AttributeError, TypeError, ValueError):
        return default
    return parsed_value if parsed_value > 0 else default


def get_daily_scan_limit() -> int:
    return _positive_limit_from_env("DAILY_SCAN_LIMIT", DEFAULT_DAILY_SCAN_LIMIT)


def get_monthly_scan_limit() -> int:
    return _positive_limit_from_env("MONTHLY_SCAN_LIMIT", DEFAULT_MONTHLY_SCAN_LIMIT)


def require_scan_client_id() -> bool:
    raw_value = os.getenv("REQUIRE_SCAN_CLIENT_ID")
    if raw_value is None:
        return False
    normalized_value = raw_value.strip().casefold()
    if normalized_value in _TRUE_ENV_VALUES:
        return True
    if normalized_value in _FALSE_ENV_VALUES:
        return False
    return False


def hash_client_id(client_id: str) -> str:
    return hashlib.sha256(client_id.encode("utf-8")).hexdigest()


def _today_utc() -> date:
    return datetime.now(UTC).date()


def _daily_reset_at(usage_date: date) -> str:
    next_day = usage_date + timedelta(days=1)
    reset_at = datetime.combine(next_day, time.min, tzinfo=UTC)
    return reset_at.isoformat().replace("+00:00", "Z")


def _monthly_reset_at(usage_date: date) -> str:
    if usage_date.month == 12:
        next_month = date(usage_date.year + 1, 1, 1)
    else:
        next_month = date(usage_date.year, usage_date.month + 1, 1)
    reset_at = datetime.combine(next_month, time.min, tzinfo=UTC)
    return reset_at.isoformat().replace("+00:00", "Z")


def _metadata_for_counts(
    *,
    daily_count: int,
    monthly_count: int,
    daily_limit: int,
    monthly_limit: int,
    usage_date: date,
) -> ScanRateLimitMetadata:
    return ScanRateLimitMetadata(
        daily_limit=daily_limit,
        daily_scans_remaining=max(0, daily_limit - daily_count),
        daily_reset_at=_daily_reset_at(usage_date),
        monthly_limit=monthly_limit,
        monthly_scans_remaining=max(0, monthly_limit - monthly_count),
        monthly_reset_at=_monthly_reset_at(usage_date),
    )


def _raise_if_limit_reached(
    metadata: ScanRateLimitMetadata,
    *,
    limit_period: scan_usage_repository.ScanLimitPeriod | None = None,
) -> None:
    if limit_period == "daily" or (
        limit_period is None and metadata.daily_scans_remaining == 0
    ):
        raise DailyScanLimitReachedError(metadata)
    if limit_period == "monthly" or (
        limit_period is None and metadata.monthly_scans_remaining == 0
    ):
        raise MonthlyScanLimitReachedError(metadata)


def _normalized_client_hash(client_id: str | None) -> str | None:
    normalized_client_id = client_id.strip() if isinstance(client_id, str) else ""
    if normalized_client_id:
        return hash_client_id(normalized_client_id)
    if require_scan_client_id():
        raise MissingScanClientIdError
    logger.info("Skipping scan limits because client id is missing and not required.")
    return None


def _handle_repository_error(exc: scan_usage_repository.ScanUsageRepositoryError) -> None:
    if require_scan_client_id():
        raise ScanRateLimitUnavailableError(str(exc)) from exc
    logger.warning("Skipping scan limits because usage tracking failed: %s", exc)


def check_scan_limits(client_id: str | None) -> ScanRateLimitMetadata | None:
    client_id_hash = _normalized_client_hash(client_id)
    if client_id_hash is None:
        return None
    usage_date = _today_utc()
    daily_limit = get_daily_scan_limit()
    monthly_limit = get_monthly_scan_limit()
    try:
        usage = scan_usage_repository.get_scan_usage(
            client_id_hash=client_id_hash,
            usage_date=usage_date,
        )
    except scan_usage_repository.ScanUsageRepositoryError as exc:
        _handle_repository_error(exc)
        return None
    metadata = _metadata_for_counts(
        daily_count=usage.daily_count,
        monthly_count=usage.monthly_count,
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
        usage_date=usage_date,
    )
    _raise_if_limit_reached(metadata)
    return metadata


def consume_scan(client_id: str | None) -> ScanRateLimitMetadata | None:
    """Atomically count one successfully built scan and return remaining usage."""
    client_id_hash = _normalized_client_hash(client_id)
    if client_id_hash is None:
        return None
    usage_date = _today_utc()
    daily_limit = get_daily_scan_limit()
    monthly_limit = get_monthly_scan_limit()
    try:
        reservation = scan_usage_repository.reserve_scan_usage(
            client_id_hash=client_id_hash,
            usage_date=usage_date,
            daily_limit=daily_limit,
            monthly_limit=monthly_limit,
        )
    except scan_usage_repository.ScanUsageRepositoryError as exc:
        _handle_repository_error(exc)
        return None
    metadata = _metadata_for_counts(
        daily_count=reservation.daily_count,
        monthly_count=reservation.monthly_count,
        daily_limit=daily_limit,
        monthly_limit=monthly_limit,
        usage_date=usage_date,
    )
    if not reservation.allowed:
        _raise_if_limit_reached(metadata, limit_period=reservation.limit_period)
    return metadata
