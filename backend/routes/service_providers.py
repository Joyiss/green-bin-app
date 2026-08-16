from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

try:
    from ..repositories import service_provider_repository
    from ..services import scan_rate_limit_service, service_provider_verification_service
except ImportError:
    from repositories import service_provider_repository
    from services import scan_rate_limit_service, service_provider_verification_service

router = APIRouter(prefix="/service-providers", tags=["service-providers"])


class ProviderLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=1, max_length=120)
    county: str | None = Field(default=None, max_length=120)

    @field_validator("city", "state")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Location value is required.")
        return normalized

    @field_validator("county")
    @classmethod
    def normalize_county(cls, value: str | None) -> str | None:
        return " ".join((value or "").strip().split()) or None


class VerifyProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_name: str = Field(min_length=1, max_length=200)
    location: ProviderLocation

    @field_validator("service_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Service name is required.")
        return normalized


class ConfirmProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verification_id: UUID
    raw_input_name: str = Field(min_length=1, max_length=200)

    @field_validator("raw_input_name")
    @classmethod
    def normalize_raw_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Provider name is required.")
        return normalized


def _client_hash(raw_client_id: str | None) -> str:
    normalized = (raw_client_id or "").strip()
    if not normalized:
        raise HTTPException(status_code=422, detail={"error": "client_id_required"})
    return scan_rate_limit_service.hash_client_id(normalized)


def _cooldown(exc: service_provider_verification_service.ProviderCooldown) -> HTTPException:
    return HTTPException(status_code=429, detail={
        "error": "provider_cooldown",
        "cooldown_reason": exc.reason,
        "retry_at": exc.retry_at,
    })


@router.get("/current")
def get_current_provider(
    city: str = Query(min_length=1, max_length=120),
    state: str = Query(min_length=1, max_length=120),
    county: str | None = Query(default=None, max_length=120),
    x_greenbin_client_id: str | None = Header(None, alias="X-GreenBin-Client-Id"),
) -> dict:
    client_id_hash = _client_hash(x_greenbin_client_id)
    try:
        provider = service_provider_repository.current_provider(
            client_id_hash=client_id_hash, city=city, county=county, state=state
        )
        restriction = service_provider_repository.current_restriction(
            client_id_hash, datetime.now(UTC)
        )
    except service_provider_repository.ServiceProviderRepositoryError:
        raise HTTPException(status_code=503, detail={"error": "provider_storage_unavailable"})
    return {"provider": provider, "restriction": restriction}


@router.post("/verify")
def verify_provider(
    request: VerifyProviderRequest,
    x_greenbin_client_id: str | None = Header(None, alias="X-GreenBin-Client-Id"),
) -> dict:
    client_id_hash = _client_hash(x_greenbin_client_id)
    try:
        return service_provider_verification_service.verify_provider(
            client_id_hash=client_id_hash,
            service_name=request.service_name,
            city=request.location.city,
            county=request.location.county,
            state=request.location.state,
        )
    except service_provider_verification_service.ProviderCooldown as exc:
        raise _cooldown(exc)
    except service_provider_verification_service.ProviderUnavailable:
        raise HTTPException(status_code=503, detail={"error": "provider_verification_unavailable"})


@router.post("/confirm")
def confirm_provider(
    request: ConfirmProviderRequest,
    x_greenbin_client_id: str | None = Header(None, alias="X-GreenBin-Client-Id"),
) -> dict:
    client_id_hash = _client_hash(x_greenbin_client_id)
    try:
        provider = service_provider_verification_service.confirm_provider(
            client_id_hash=client_id_hash,
            verification_id=str(request.verification_id),
            raw_input_name=request.raw_input_name,
        )
    except service_provider_verification_service.ProviderCooldown as exc:
        raise _cooldown(exc)
    except service_provider_verification_service.ProviderConfirmationConflict:
        raise HTTPException(status_code=409, detail={"error": "provider_confirmation_invalid"})
    return {"provider": provider}
