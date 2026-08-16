from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger(__name__)
_SUPABASE_CLIENT: Client | None = None
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ServiceProviderRepositoryError(RuntimeError):
    pass


def normalize_key_field(value: Any) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def provider_key(name: str, city: str, county: str | None, state: str) -> str:
    normalized = "\x1f".join(
        normalize_key_field(value) for value in (name, city, county, state)
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def cache_key(name: str, city: str, county: str | None, state: str) -> str:
    return provider_key(name, city, county, state)


def _client() -> Client:
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ServiceProviderRepositoryError("Service-provider storage is unavailable.")
    try:
        _SUPABASE_CLIENT = create_client(url, key)
    except Exception as exc:
        raise ServiceProviderRepositoryError("Service-provider storage is unavailable.") from exc
    return _SUPABASE_CLIENT


def _rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        raise ServiceProviderRepositoryError("Unexpected service-provider response.")
    return [row for row in data if isinstance(row, dict)]


def _first(response: Any) -> dict[str, Any] | None:
    rows = _rows(response)
    return rows[0] if rows else None


def current_provider(
    *, client_id_hash: str, city: str, county: str | None, state: str
) -> dict[str, Any] | None:
    if not _HASH_PATTERN.fullmatch(client_id_hash):
        raise ServiceProviderRepositoryError("Invalid client hash.")
    try:
        response = (
            _client().table("service_providers")
            .select("id,canonical_name,raw_input_name,services,city,state,county,status,evidence_urls,verified_at,created_at,updated_at")
            .eq("client_id_hash", client_id_hash)
            .order("verified_at", desc=True)
            .execute()
        )
    except Exception as exc:
        raise ServiceProviderRepositoryError("Could not load service provider.") from exc
    target = (
        normalize_key_field(city),
        normalize_key_field(county),
        normalize_key_field(state),
    )
    for row in _rows(response):
        candidate = (
            normalize_key_field(row.get("city")),
            normalize_key_field(row.get("county")),
            normalize_key_field(row.get("state")),
        )
        if candidate == target:
            return row
    return None


def current_restriction(client_id_hash: str, now: datetime) -> dict[str, Any] | None:
    try:
        response = (
            _client().table("service_provider_limit_state")
            .select("failure_cooldown_until,last_successful_confirmation_at")
            .eq("client_id_hash", client_id_hash)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise ServiceProviderRepositoryError("Could not load provider restrictions.") from exc
    row = _first(response)
    if not row:
        return None
    failure_until = _timestamp(row.get("failure_cooldown_until"))
    if failure_until and failure_until > now:
        return {"reason": "failed_attempts", "retry_at": failure_until.isoformat()}
    last_success = _timestamp(row.get("last_successful_confirmation_at"))
    if last_success and last_success + timedelta(hours=24) > now:
        return {
            "reason": "successful_confirmation",
            "retry_at": (last_success + timedelta(hours=24)).isoformat(),
        }
    return None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def get_cached_verification(key: str, now: datetime) -> dict[str, Any] | None:
    try:
        response = (
            _client().table("service_provider_verification_cache")
            .select("id,result,expires_at")
            .eq("cache_key", key)
            .gt("expires_at", now.isoformat())
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise ServiceProviderRepositoryError("Could not read provider cache.") from exc
    return _first(response)


def store_cached_verification(
    *, key: str, name: str, city: str, county: str | None, state: str,
    result: dict[str, Any], now: datetime,
) -> dict[str, Any]:
    payload = {
        "cache_key": key,
        "normalized_input_name": normalize_key_field(name),
        "normalized_city": normalize_key_field(city),
        "normalized_county": normalize_key_field(county),
        "normalized_state": normalize_key_field(state),
        "result": result,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "updated_at": now.isoformat(),
    }
    try:
        response = (
            _client().table("service_provider_verification_cache")
            .upsert(payload, on_conflict="cache_key")
            .execute()
        )
    except Exception as exc:
        raise ServiceProviderRepositoryError("Could not store provider cache.") from exc
    row = _first(response)
    if row is None:
        raise ServiceProviderRepositoryError("Provider cache returned no row.")
    return row


def _rpc_row(name: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = _client().rpc(name, params).execute()
    except Exception as exc:
        raise ServiceProviderRepositoryError(f"Provider operation {name} failed.") from exc
    row = _first(response)
    if row is None:
        raise ServiceProviderRepositoryError(f"Provider operation {name} returned no row.")
    return row


def reserve_verification(*, client_id_hash: str, key: str, now: datetime) -> dict[str, Any]:
    return _rpc_row("reserve_service_provider_verification", {
        "p_client_id_hash": client_id_hash, "p_provider_key": key,
        "p_now": now.isoformat(),
    })


def finalize_verification(
    *, client_id_hash: str, key: str, status: str, now: datetime,
) -> dict[str, Any]:
    return _rpc_row("finalize_service_provider_verification", {
        "p_client_id_hash": client_id_hash, "p_provider_key": key,
        "p_status": status, "p_now": now.isoformat(),
    })


def release_verification(*, client_id_hash: str, key: str, now: datetime) -> None:
    try:
        _client().rpc("release_service_provider_verification", {
            "p_client_id_hash": client_id_hash, "p_provider_key": key,
            "p_now": now.isoformat(),
        }).execute()
    except Exception as exc:
        logger.warning("Provider reservation release failed. error_type=%s", type(exc).__name__)


def confirm_provider(
    *, client_id_hash: str, verification_id: str, raw_input_name: str, now: datetime,
) -> dict[str, Any]:
    return _rpc_row("confirm_service_provider", {
        "p_client_id_hash": client_id_hash,
        "p_verification_id": verification_id,
        "p_raw_input_name": raw_input_name,
        "p_now": now.isoformat(),
    })
