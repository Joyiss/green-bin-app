from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

try:
    from ..services.phash_service import PHASH_THRESHOLD, phash_distance
except ImportError:
    from services.phash_service import PHASH_THRESHOLD, phash_distance

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_SUPABASE_CLIENT: Client | None = None
_TABLE_NAME = "recognition_cache"
logger = logging.getLogger(__name__)
_WARMUP_PHASH = "__green_bin_phash_warmup__"


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


def _normalize_metadata_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {
            str(key): _json_safe_value(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe_value(item_method())
        except Exception:
            pass

    tolist_method = getattr(value, "tolist", None)
    if callable(tolist_method):
        try:
            return _json_safe_value(tolist_method())
        except Exception:
            pass

    return value


def _normalize_cache_row(row: Any, error_prefix: str) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise RuntimeError(f"{error_prefix}: Supabase returned an unexpected row shape.")

    normalized_row = dict(row)
    if "metadata" in normalized_row:
        normalized_row["metadata"] = _normalize_metadata_value(normalized_row["metadata"])

    return normalized_row


def _first_row_or_error(rows: Any, error_prefix: str, missing_message: str) -> dict[str, Any]:
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"{error_prefix}: {missing_message}")

    return _normalize_cache_row(rows[0], error_prefix)


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
    payload = _json_safe_value({
        "phash": phash,
        "clip_embedding": clip_embedding,
        "item_label": item_label,
        "recognition_source": recognition_source,
        "confidence": confidence,
        "verified": verified,
        "metadata": metadata or {},
    })

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
    return _normalize_cache_row(
        row,
        "Failed to fetch recognition cache record by id",
    )


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
        normalized_rows.append(
            _normalize_cache_row(
                row,
                "Failed to find recognition cache records by phash",
            )
        )

    return normalized_rows


def _normalize_confidence(value: Any) -> float:
    try:
        if value is None:
            return float("-inf")
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _match_sort_key(row: dict[str, Any], distance: int, index: int) -> tuple[float, int, float, int]:
    return (
        float(distance),
        0 if bool(row.get("verified")) else 1,
        -_normalize_confidence(row.get("confidence")),
        index,
    )


def find_exact_phash_match(phash: str) -> dict[str, Any] | None:
    try:
        response = (
            _get_supabase_client()
            .table(_TABLE_NAME)
            .select("item_label,metadata")
            .eq("phash", phash)
            .order("verified", desc=True)
            .order("confidence", desc=True, nullsfirst=False)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to find exact recognition cache record by phash: {exc}") from exc

    rows = _response_data(response)
    if rows is None:
        return None
    if not isinstance(rows, list):
        raise RuntimeError(
            "Failed to find exact recognition cache record by phash: "
            "Supabase returned an unexpected row shape."
        )
    if not rows:
        return None

    best_exact_match = {
        **_normalize_cache_row(
            rows[0],
            "Failed to find exact recognition cache record by phash",
        ),
        "phash_distance": 0,
    }

    logger.info(
        "pHash exact match hit. query_phash=%s",
        phash,
    )
    return best_exact_match


def warmup_exact_phash_lookup() -> bool:
    """Warm the cached Supabase client and its underlying HTTP connection."""
    try:
        find_exact_phash_match(_WARMUP_PHASH)
        logger.info("Recognition cache exact-lookup startup warmup completed.")
        return True
    except Exception as exc:
        logger.warning(
            "Recognition cache exact-lookup startup warmup failed safely: %s",
            exc,
        )
        return False


def find_nearest_phash_match(
    phash: str,
    max_distance: int = PHASH_THRESHOLD,
    *,
    check_exact: bool = True,
) -> dict[str, Any] | None:
    if check_exact:
        exact_match = find_exact_phash_match(phash)
        if exact_match is not None:
            return exact_match

    try:
        response = (
            _get_supabase_client()
            .table(_TABLE_NAME)
            .select("*")
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to find nearest recognition cache record by phash: {exc}") from exc

    rows = _response_data(response)
    if rows is None:
        return None
    if not isinstance(rows, list):
        raise RuntimeError(
            "Failed to find nearest recognition cache record by phash: "
            "Supabase returned an unexpected row shape."
        )

    best_match: dict[str, Any] | None = None
    best_sort_key: tuple[float, int, float, int] | None = None
    checked_rows = 0
    best_distance_seen: int | None = None

    for index, row in enumerate(rows):
        normalized_row = _normalize_cache_row(
            row,
            "Failed to find nearest recognition cache record by phash",
        )
        candidate_phash = normalized_row.get("phash")
        if candidate_phash is None:
            continue
        if not isinstance(candidate_phash, str):
            raise RuntimeError(
                "Failed to find nearest recognition cache record by phash: "
                "Supabase returned an unexpected row shape."
            )

        try:
            distance = phash_distance(phash, candidate_phash)
        except Exception as exc:
            raise RuntimeError(
                "Failed to find nearest recognition cache record by phash: "
                f"invalid phash value: {exc}"
            ) from exc

        checked_rows += 1
        if best_distance_seen is None or distance < best_distance_seen:
            best_distance_seen = distance

        if distance > max_distance:
            continue

        sort_key = _match_sort_key(normalized_row, distance, index)
        if best_sort_key is None or sort_key < best_sort_key:
            best_sort_key = sort_key
            best_match = {
                **normalized_row,
                "phash_distance": distance,
            }

    logger.info(
        "pHash nearest lookup complete. query_phash=%s checked_rows=%s best_distance=%s within_threshold=%s threshold=%s",
        phash,
        checked_rows,
        best_distance_seen,
        best_match is not None,
        max_distance,
    )

    return best_match


def find_similar_embeddings(
    embedding: list[float],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find similar cached records by CLIP embedding via Supabase RPC.

    Requires a Postgres / pgvector function named `match_recognition_cache_by_embedding`
    that accepts `query_embedding` and `match_count`, and returns rows including:
    `id`, `item_label`, `similarity`, `confidence`, `verified`, and optional `metadata`.

    Example SQL contract:

        create or replace function match_recognition_cache_by_embedding(
            query_embedding vector,
            match_count integer default 5
        )
        returns table (
            id uuid,
            item_label text,
            similarity double precision,
            confidence double precision,
            verified boolean,
            metadata jsonb
        )
        language sql
        stable
        as $$
            select
                id,
                item_label,
                1 - (clip_embedding <=> query_embedding) as similarity,
                confidence,
                verified,
                metadata
            from recognition_cache
            where clip_embedding is not null
            order by clip_embedding <=> query_embedding
            limit match_count;
        $$;
    """
    try:
        response = (
            _get_supabase_client()
            .rpc(
                "match_recognition_cache_by_embedding",
                {
                    "query_embedding": embedding,
                    "match_count": limit,
                },
            )
            .execute()
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to find similar recognition cache records by embedding: {exc}") from exc

    rows = _response_data(response)
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise RuntimeError(
            "Failed to find similar recognition cache records by embedding: "
            "Supabase returned an unexpected row shape."
        )

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append(
            _normalize_cache_row(
                row,
                "Failed to find similar recognition cache records by embedding",
            )
        )

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

    return _normalize_cache_row(
        rows[0],
        "Failed to delete recognition cache record by id",
    )
