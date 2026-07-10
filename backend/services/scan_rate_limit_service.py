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

DEFAULT_DAILY_SCAN_LIMIT = 40
_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_FALSE_ENV_VALUES = {"0", "false", "no", "off"}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanRateLimitMetadata:
    daily_limit: int
    scans_remaining: int
    reset_at: str

    def to_response_payload(self) -> dict[str, int | str]:
        return {
            "daily_limit": self.daily_limit,
            "scans_remaining": self.scans_remaining,
            "reset_at": self.reset_at,
        }


class MissingScanClientIdError(Exception):
    pass


class DailyScanLimitReachedError(Exception):
    def __init__(self, metadata: ScanRateLimitMetadata):
        self.metadata = metadata
        super().__init__("Daily scan limit reached.")


class ScanRateLimitUnavailableError(RuntimeError):
    pass


def get_daily_scan_limit() -> int:
    raw_value = os.getenv("DAILY_SCAN_LIMIT")
    if raw_value is None:
        return DEFAULT_DAILY_SCAN_LIMIT

    try:
        parsed_value = int(raw_value.strip())
    except (AttributeError, TypeError, ValueError):
        return DEFAULT_DAILY_SCAN_LIMIT

    if parsed_value < 1:
        return DEFAULT_DAILY_SCAN_LIMIT

    return parsed_value


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


def _reset_at_for_usage_date(usage_date: date) -> str:
    next_day = usage_date + timedelta(days=1)
    reset_at = datetime.combine(next_day, time.min, tzinfo=UTC)
    return reset_at.isoformat().replace("+00:00", "Z")


def _metadata_for_count(*, scan_count: int, daily_limit: int, usage_date: date) -> ScanRateLimitMetadata:
    return ScanRateLimitMetadata(
        daily_limit=daily_limit,
        scans_remaining=max(0, daily_limit - scan_count),
        reset_at=_reset_at_for_usage_date(usage_date),
    )


def consume_daily_scan(client_id: str | None) -> ScanRateLimitMetadata | None:
    daily_limit = get_daily_scan_limit()
    normalized_client_id = client_id.strip() if isinstance(client_id, str) else ""

    if not normalized_client_id:
        if require_scan_client_id():
            raise MissingScanClientIdError
        logger.info("Skipping daily scan limit because client id is missing and not required.")
        return None

    usage_date = _today_utc()
    client_id_hash = hash_client_id(normalized_client_id)

    try:
        scan_count = scan_usage_repository.increment_daily_scan_usage(
            client_id_hash=client_id_hash,
            usage_date=usage_date,
            daily_limit=daily_limit,
        )
    except scan_usage_repository.ScanUsageLimitReachedError as exc:
        raise DailyScanLimitReachedError(
            _metadata_for_count(
                scan_count=daily_limit,
                daily_limit=daily_limit,
                usage_date=usage_date,
            )
        ) from exc
    except scan_usage_repository.ScanUsageRepositoryError as exc:
        if require_scan_client_id():
            raise ScanRateLimitUnavailableError(str(exc)) from exc
        logger.warning("Skipping daily scan limit because usage tracking failed: %s", exc)
        return None

    return _metadata_for_count(
        scan_count=scan_count,
        daily_limit=daily_limit,
        usage_date=usage_date,
    )
