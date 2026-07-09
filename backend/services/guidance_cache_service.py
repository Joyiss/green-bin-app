from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

try:
    from ..repositories import disposal_guidance_repository
    from .guidance_key_service import normalize_guidance_key
    from .guidance_llm_service import GUIDANCE_PROMPT_VERSION
except ImportError:
    from repositories import disposal_guidance_repository
    from services.guidance_key_service import normalize_guidance_key
    from services.guidance_llm_service import GUIDANCE_PROMPT_VERSION

logger = logging.getLogger(__name__)

CACHE_KEY_VERSION = "guidance_cache_v1"
SOURCE_CORPUS_VERSION = "green_bin_rag_sources_v1"
SOURCE_GROUNDED_CACHE_POLICY = "source_grounded"
STATIC_RULES_CACHE_POLICY = "static_rules"
SOURCE_GROUNDED_CACHEABLE_SOURCES = {
    "json_rag_llm_generated",
    "json_rag_direct_generated",
}


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    result: list[str] = []
    for item in value:
        normalized = _normalize_optional_string(item)
        if normalized:
            result.append(normalized)
    return result


def _stable_sorted_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    normalized_values: list[str] = []
    for value in _normalize_string_list(values):
        normalized = value.strip()
        dedupe_key = normalized.casefold()
        if normalized and dedupe_key not in seen:
            seen.add(dedupe_key)
            normalized_values.append(normalized)
    return sorted(normalized_values, key=str.casefold)


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        normalized = _normalize_optional_string(value)
        if normalized:
            return normalized
    return None


def _normalized_details(classification: dict[str, Any]) -> dict[str, Any]:
    recognition_details = classification.get("recognition_details")
    if not isinstance(recognition_details, dict):
        return {}
    normalized = recognition_details.get("normalized")
    if not isinstance(normalized, dict):
        return {}
    return normalized


def _hash_payload(payload: dict[str, Any]) -> str:
    raw_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


def _retrieved_chunk_ids(retrieval_results: list[dict[str, Any]]) -> list[str]:
    return _stable_sorted_strings(
        [
            result.get("chunk_id") or result.get("chunk", {}).get("id")
            for result in retrieval_results
            if isinstance(result, dict)
        ]
    )


def _retrieval_location_scope(retrieval_results: list[dict[str, Any]]) -> str:
    scopes = _stable_sorted_strings(
        [
            result.get("chunk", {}).get("location_scope")
            for result in retrieval_results
            if isinstance(result.get("chunk"), dict)
        ]
    )
    return "|".join(scopes) if scopes else "national_or_location_check"


def _source_fingerprint(retrieved_chunk_ids: list[str]) -> str:
    return _hash_payload(
        {
            "source_corpus_version": SOURCE_CORPUS_VERSION,
            "retrieved_chunk_ids": retrieved_chunk_ids,
        }
    )


def _metadata_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_source_grounded_cache_context(
    *,
    classification: dict[str, Any],
    retrieval_inputs: dict[str, Any],
    retrieval_results: list[dict[str, Any]],
    llm_context: dict[str, Any],
) -> dict[str, Any] | None:
    retrieved_chunk_ids = _retrieved_chunk_ids(retrieval_results)
    if not retrieved_chunk_ids:
        return None

    normalized = _normalized_details(classification)
    normalized_item = _first_non_empty(
        normalized.get("normalized_item"),
        normalized.get("item_label"),
        llm_context.get("normalized_item_label"),
        classification.get("item"),
        retrieval_inputs.get("item_label"),
    )
    if not normalized_item:
        return None

    disposal_category = _first_non_empty(
        normalized.get("disposal_category"),
        classification.get("category"),
        retrieval_inputs.get("category"),
    )
    material_category = _first_non_empty(
        normalized.get("material_category"),
        classification.get("recognized_material_category"),
        retrieval_inputs.get("material"),
    )
    broad_category = _first_non_empty(
        normalized.get("broad_category"),
        classification.get("recognized_broad_category"),
        llm_context.get("broad_category"),
    )
    condition_flags = _stable_sorted_strings(llm_context.get("condition_flags"))
    special_handling_flags = _stable_sorted_strings(llm_context.get("special_flags"))
    source_fingerprint = _source_fingerprint(retrieved_chunk_ids)
    location_scope = _retrieval_location_scope(retrieval_results)

    cache_key_input = {
        "cache_key_version": CACHE_KEY_VERSION,
        "normalized_item_key": normalize_guidance_key(normalized_item),
        "disposal_category_key": normalize_guidance_key(disposal_category),
        "material_category_key": normalize_guidance_key(material_category),
        "broad_category_key": normalize_guidance_key(broad_category),
        "condition_flags": condition_flags,
        "special_handling_flags": special_handling_flags,
        "location_scope": location_scope,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "source_corpus_version": SOURCE_CORPUS_VERSION,
        "source_fingerprint": source_fingerprint,
        "prompt_version": GUIDANCE_PROMPT_VERSION,
        "cache_policy": SOURCE_GROUNDED_CACHE_POLICY,
    }

    return {
        "cache_key": _hash_payload(cache_key_input),
        "cache_key_input": cache_key_input,
        "cache_key_version": CACHE_KEY_VERSION,
        "cache_policy": SOURCE_GROUNDED_CACHE_POLICY,
        "normalized_item": normalized_item,
        "normalized_item_key": cache_key_input["normalized_item_key"],
        "disposal_category": disposal_category,
        "disposal_category_key": cache_key_input["disposal_category_key"],
        "material_category": material_category,
        "material_category_key": cache_key_input["material_category_key"],
        "broad_category": broad_category,
        "broad_category_key": cache_key_input["broad_category_key"],
        "condition_flags": condition_flags,
        "special_handling_flags": special_handling_flags,
        "location_scope": location_scope,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "source_corpus_version": SOURCE_CORPUS_VERSION,
        "source_fingerprint": source_fingerprint,
    }


def cached_guidance_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    guidance_source = _normalize_optional_string(row.get("guidance_source"))
    summary = _normalize_optional_string(row.get("summary"))
    steps = _normalize_string_list(row.get("steps"))

    if guidance_source is None or summary is None or not steps:
        return None

    metadata = {
        **_metadata_object(row.get("guidance_metadata")),
        "guidance_cache_hit": True,
        "guidance_cache_key": row.get("cache_key"),
        "cache_key_version": row.get("cache_key_version") or CACHE_KEY_VERSION,
    }
    warnings = _normalize_string_list(row.get("warnings"))
    guidance: dict[str, Any] = {
        "disposal_action": _normalize_optional_string(row.get("disposal_action")),
        "material_code": _normalize_optional_string(row.get("material_code")),
        "impact_level": _normalize_optional_string(row.get("impact_level")),
        "summary": summary,
        "steps": steps,
        "guidance_source": guidance_source,
        "guidance_metadata": metadata,
        "cache_hit": True,
    }
    if warnings:
        guidance["warnings"] = warnings
    return guidance


def get_cached_source_grounded_guidance(
    cache_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not cache_context:
        return None

    row = disposal_guidance_repository.get_guidance_by_cache_key(
        cache_context.get("cache_key")
    )
    if row is None:
        return None

    guidance = cached_guidance_from_row(row)
    if guidance is None:
        return None
    if guidance.get("guidance_source") not in SOURCE_GROUNDED_CACHEABLE_SOURCES:
        return None
    if _normalize_optional_string(guidance.get("disposal_action")) is None:
        return None
    if not _normalize_string_list(row.get("retrieved_chunk_ids")):
        return None

    disposal_guidance_repository.record_guidance_cache_hit(row.get("id"))
    return guidance


def _retrieval_metadata(retrieval_results: list[dict[str, Any]]) -> dict[str, Any]:
    source_names: list[str] = []
    source_urls: list[str] = []
    source_claims: list[str] = []
    source_excerpts: list[str] = []
    limitations: list[str] = []
    matched_fields: dict[str, list[str]] = {}
    retrieval_scores: dict[str, float] = {}
    requires_location_check = False

    for result in retrieval_results[:3]:
        if not isinstance(result, dict):
            continue
        chunk = result.get("chunk")
        if not isinstance(chunk, dict):
            continue
        chunk_id = _normalize_optional_string(result.get("chunk_id") or chunk.get("id"))
        if chunk_id is None:
            continue

        for target, value in (
            (source_names, chunk.get("source_name")),
            (source_urls, chunk.get("source_url")),
            (source_claims, chunk.get("source_claim")),
            (source_excerpts, chunk.get("source_excerpt")),
        ):
            normalized = _normalize_optional_string(value)
            if normalized and normalized not in target:
                target.append(normalized)

        for limitation in _normalize_string_list(chunk.get("limitations")):
            if limitation not in limitations:
                limitations.append(limitation)

        matched_fields[chunk_id] = _normalize_string_list(result.get("matched_fields"))
        try:
            retrieval_scores[chunk_id] = float(result.get("score") or 0.0)
        except (TypeError, ValueError):
            retrieval_scores[chunk_id] = 0.0

        requires_location_check = (
            requires_location_check
            or result.get("requires_location_check") is True
            or chunk.get("requires_location_check") is True
        )

    return {
        "source_names": source_names,
        "source_urls": source_urls,
        "source_claims": source_claims,
        "source_excerpts": source_excerpts,
        "limitations": limitations,
        "matched_fields": matched_fields,
        "retrieval_scores": retrieval_scores,
        "requires_location_check": requires_location_check,
    }


def source_grounded_guidance_is_cacheable(
    *,
    classification: dict[str, Any],
    guidance: dict[str, Any],
    cache_context: dict[str, Any] | None,
) -> bool:
    if classification.get("status") != "confident":
        return False
    if not cache_context or not cache_context.get("retrieved_chunk_ids"):
        return False
    if guidance.get("guidance_source") not in SOURCE_GROUNDED_CACHEABLE_SOURCES:
        return False
    if _normalize_optional_string(guidance.get("disposal_action")) is None:
        return False
    if _normalize_optional_string(guidance.get("summary")) is None:
        return False
    if not _normalize_string_list(guidance.get("steps")):
        return False
    return True


def build_cache_payload(
    *,
    classification: dict[str, Any],
    guidance: dict[str, Any],
    cache_context: dict[str, Any],
    retrieval_inputs: dict[str, Any],
    retrieval_results: list[dict[str, Any]],
    llm_context: dict[str, Any],
) -> dict[str, Any]:
    metadata = _metadata_object(guidance.get("guidance_metadata"))
    retrieval_metadata = _retrieval_metadata(retrieval_results)
    return {
        **cache_context,
        "guidance_source": guidance.get("guidance_source"),
        "final_generation_path": metadata.get("final_generation_path"),
        "disposal_action": guidance.get("disposal_action"),
        "material_code": guidance.get("material_code"),
        "impact_level": guidance.get("impact_level"),
        "summary": guidance.get("summary"),
        "steps": _normalize_string_list(guidance.get("steps")),
        "warnings": _normalize_string_list(guidance.get("warnings")),
        "guidance_metadata": metadata,
        "recognition_context": {
            "item": classification.get("item"),
            "category": classification.get("category"),
            "recognized_material_category": classification.get("recognized_material_category"),
            "recognized_broad_category": classification.get("recognized_broad_category"),
            "recognition_source": classification.get("recognition_source"),
            "trusted_guidance_available": classification.get("trusted_guidance_available"),
            "trusted_guidance_label": classification.get("trusted_guidance_label"),
            "normalized": _normalized_details(classification),
        },
        "retrieval_context": {
            "retrieval_inputs": retrieval_inputs,
            "llm_context": llm_context,
        },
        "source_names": retrieval_metadata["source_names"],
        "source_urls": retrieval_metadata["source_urls"],
        "source_claims": retrieval_metadata["source_claims"],
        "source_excerpts": retrieval_metadata["source_excerpts"],
        "limitations": retrieval_metadata["limitations"],
        "matched_fields": retrieval_metadata["matched_fields"],
        "retrieval_scores": retrieval_metadata["retrieval_scores"],
        "requires_location_check": retrieval_metadata["requires_location_check"],
        "prompt_version": metadata.get("prompt_version") or GUIDANCE_PROMPT_VERSION,
        "llm_provider": metadata.get("llm_provider"),
        "llm_model": metadata.get("llm_model"),
        "llm_mode": metadata.get("llm_mode"),
        "confidence": metadata.get("confidence"),
        "deterministic_fallback_used": bool(metadata.get("deterministic_fallback_used")),
    }


def write_source_grounded_guidance_if_cacheable(
    *,
    classification: dict[str, Any],
    guidance: dict[str, Any],
    cache_context: dict[str, Any] | None,
    retrieval_inputs: dict[str, Any],
    retrieval_results: list[dict[str, Any]],
    llm_context: dict[str, Any],
) -> None:
    if not source_grounded_guidance_is_cacheable(
        classification=classification,
        guidance=guidance,
        cache_context=cache_context,
    ):
        return

    payload = build_cache_payload(
        classification=classification,
        guidance=guidance,
        cache_context=cache_context or {},
        retrieval_inputs=retrieval_inputs,
        retrieval_results=retrieval_results,
        llm_context=llm_context,
    )
    disposal_guidance_repository.upsert_guidance_cache_row(payload)
