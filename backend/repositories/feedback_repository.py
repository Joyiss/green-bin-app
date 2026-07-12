from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_SUPABASE_CLIENT: Client | None = None
_TABLE_NAME = "closed_test_feedback"
_CORRECTION_TABLE_NAME = "closed_test_correction_context"
logger = logging.getLogger(__name__)


class FeedbackRepositoryUnavailable(RuntimeError):
    pass


class FeedbackContextNotFound(RuntimeError):
    pass


def _get_supabase_client() -> Client | None:
    global _SUPABASE_CLIENT

    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_role_key:
        logger.info(
            "Closed-test feedback storage unavailable because service-role credentials are missing."
        )
        return None

    try:
        _SUPABASE_CLIENT = create_client(supabase_url, service_role_key)
    except Exception as exc:
        logger.warning("Failed to create closed-test feedback client: %s", exc)
        return None
    return _SUPABASE_CLIENT


def _require_client() -> Client:
    client = _get_supabase_client()
    if client is None:
        raise FeedbackRepositoryUnavailable("Closed-test feedback storage is unavailable.")
    return client


def _first_row(response: Any) -> dict[str, Any] | None:
    rows = getattr(response, "data", None)
    if not isinstance(rows, list) or not rows:
        return None
    row = rows[0]
    return row if isinstance(row, dict) else None


def store_original_context(payload: dict[str, Any]) -> bool:
    try:
        response = (
            _require_client()
            .table(_TABLE_NAME)
            .upsert(payload, on_conflict="request_id")
            .execute()
        )
    except Exception as exc:
        logger.warning(
            "Closed-test prediction context was not stored. request_id=%s error_type=%s",
            payload.get("request_id"),
            type(exc).__name__,
        )
        return False
    return _first_row(response) is not None


def attach_correction_context(
    *,
    original_request_id: str,
    correction_request_id: str,
    corrected_item: str,
    guidance_context: dict[str, Any],
) -> bool:
    correction_payload = {
        "request_id": correction_request_id,
        "original_request_id": original_request_id,
        "corrected_item": corrected_item,
        **guidance_context,
    }
    try:
        response = (
            _require_client()
            .table(_CORRECTION_TABLE_NAME)
            .upsert(correction_payload, on_conflict="request_id")
            .execute()
        )
    except Exception as exc:
        logger.warning(
            "Closed-test correction context was not linked. request_id=%s correction_request_id=%s error_type=%s",
            original_request_id,
            correction_request_id,
            type(exc).__name__,
        )
        return False
    return _first_row(response) is not None


def get_correction_context(
    *, original_request_id: str, correction_request_id: str
) -> dict[str, Any]:
    try:
        response = (
            _require_client()
            .table(_CORRECTION_TABLE_NAME)
            .select("*")
            .eq("request_id", correction_request_id)
            .eq("original_request_id", original_request_id)
            .limit(1)
            .execute()
        )
    except FeedbackRepositoryUnavailable:
        raise
    except Exception as exc:
        raise FeedbackRepositoryUnavailable(
            f"Could not read closed-test correction context: {exc}"
        ) from exc
    row = _first_row(response)
    if row is None:
        raise FeedbackContextNotFound(correction_request_id)
    return row


def get_feedback_context(request_id: str) -> dict[str, Any]:
    try:
        response = (
            _require_client()
            .table(_TABLE_NAME)
            .select("*")
            .eq("request_id", request_id)
            .limit(1)
            .execute()
        )
    except FeedbackRepositoryUnavailable:
        raise
    except Exception as exc:
        raise FeedbackRepositoryUnavailable(
            f"Could not read closed-test feedback context: {exc}"
        ) from exc

    row = _first_row(response)
    if row is None:
        raise FeedbackContextNotFound(request_id)
    return row


def update_user_feedback(
    request_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        response = (
            _require_client()
            .table(_TABLE_NAME)
            .update(payload)
            .eq("request_id", request_id)
            .execute()
        )
    except FeedbackRepositoryUnavailable:
        raise
    except Exception as exc:
        raise FeedbackRepositoryUnavailable(
            f"Could not update closed-test feedback: {exc}"
        ) from exc

    row = _first_row(response)
    if row is None:
        raise FeedbackContextNotFound(request_id)
    return row
