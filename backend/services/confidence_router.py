from __future__ import annotations

from typing import Any


MIN_TOP_SIMILARITY = 0.88
MIN_LABEL_AGREEMENT_COUNT = 3
MIN_LABEL_MARGIN = 0.12
TOP_K = 5


def _build_decision(
    *,
    use_cache: bool,
    item_label: str | None,
    reason: str,
    confidence: float | None,
    top_label: str | None,
    top_score: float | None,
    label_agreement_count: int,
    evaluated_count: int,
    best_competing_label: str | None,
    best_competing_score: float | None,
    margin: float | None,
) -> dict[str, Any]:
    return {
        "use_cache": use_cache,
        "item_label": item_label,
        "reason": reason,
        "confidence": confidence,
        "top_label": top_label,
        "top_score": top_score,
        "label_agreement_count": label_agreement_count,
        "evaluated_count": evaluated_count,
        "best_competing_label": best_competing_label,
        "best_competing_score": best_competing_score,
        "margin": margin,
    }


def _coerce_similarity(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None

    try:
        similarity = float(candidate["similarity"])
    except (KeyError, TypeError, ValueError):
        return None

    return {
        **candidate,
        "similarity": similarity,
    }


def _normalize_item_label(label: Any) -> tuple[str, str] | None:
    if not isinstance(label, str):
        return None

    display_label = label.strip()
    if not display_label or display_label.casefold() == "unknown":
        return None

    return (display_label.casefold(), display_label)


def evaluate_clip_candidates(candidates: list[dict]) -> dict[str, Any]:
    if not candidates:
        return _build_decision(
            use_cache=False,
            item_label=None,
            reason="no_clip_candidates",
            confidence=None,
            top_label=None,
            top_score=None,
            label_agreement_count=0,
            evaluated_count=0,
            best_competing_label=None,
            best_competing_score=None,
            margin=None,
        )

    sortable_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized_candidate = _coerce_similarity(candidate)
        if normalized_candidate is not None:
            sortable_candidates.append(normalized_candidate)

    evaluated_candidates = sorted(
        sortable_candidates,
        key=lambda candidate: candidate["similarity"],
        reverse=True,
    )[:TOP_K]
    evaluated_count = len(evaluated_candidates)

    grouped_candidates: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(evaluated_candidates):
        normalized_label = _normalize_item_label(candidate.get("item_label"))
        if normalized_label is None:
            continue

        normalized_key, display_label = normalized_label
        similarity = candidate["similarity"]
        group = grouped_candidates.get(normalized_key)

        if group is None:
            grouped_candidates[normalized_key] = {
                "label": display_label,
                "top_score": similarity,
                "count": 1,
                "first_index": index,
            }
            continue

        group["count"] += 1
        if similarity > group["top_score"]:
            group["top_score"] = similarity
            group["label"] = display_label

    if not grouped_candidates:
        return _build_decision(
            use_cache=False,
            item_label=None,
            reason="no_valid_clip_candidates",
            confidence=None,
            top_label=None,
            top_score=None,
            label_agreement_count=0,
            evaluated_count=evaluated_count,
            best_competing_label=None,
            best_competing_score=None,
            margin=None,
        )

    ranked_groups = sorted(
        grouped_candidates.values(),
        key=lambda group: (-group["top_score"], -group["count"], group["first_index"]),
    )
    top_group = ranked_groups[0]
    best_competing_group = ranked_groups[1] if len(ranked_groups) > 1 else None

    top_label = top_group["label"]
    top_score = top_group["top_score"]
    label_agreement_count = top_group["count"]
    best_competing_label = (
        best_competing_group["label"] if best_competing_group is not None else None
    )
    best_competing_score = (
        best_competing_group["top_score"] if best_competing_group is not None else None
    )
    margin = (
        top_score - best_competing_score
        if best_competing_score is not None
        else None
    )
    confidence = top_score

    if top_score < MIN_TOP_SIMILARITY:
        reason = "low_top_similarity"
        use_cache = False
        item_label = None
    elif label_agreement_count < MIN_LABEL_AGREEMENT_COUNT:
        reason = "weak_label_agreement"
        use_cache = False
        item_label = None
    elif margin is not None and margin < MIN_LABEL_MARGIN:
        reason = "small_label_margin"
        use_cache = False
        item_label = None
    else:
        reason = "strong_clip_agreement"
        use_cache = True
        item_label = top_label

    return _build_decision(
        use_cache=use_cache,
        item_label=item_label,
        reason=reason,
        confidence=confidence,
        top_label=top_label,
        top_score=top_score,
        label_agreement_count=label_agreement_count,
        evaluated_count=evaluated_count,
        best_competing_label=best_competing_label,
        best_competing_score=best_competing_score,
        margin=margin,
    )
