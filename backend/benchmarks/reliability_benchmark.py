from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PIL import Image

from services import (
    guidance_cache_service,
    guidance_retrieval_service,
    guidance_service,
    recognition_router,
    vlm_service,
)
from services.guidance_key_service import normalize_guidance_phrase


BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "reliability_cases.json"
CHECK_NAMES = {
    "label",
    "prohibited_label",
    "material",
    "category",
    "condition",
    "guidance_action",
    "prohibited_action",
    "clarification",
}


class BenchmarkConfigurationError(ValueError):
    pass


def _normalize(value: Any) -> str:
    return normalize_guidance_phrase(value) or ""


def _tokens(value: Any) -> list[str]:
    normalized = _normalize(value)
    return normalized.split() if normalized else []


def _contains_whole_term(value: Any, term: Any) -> bool:
    value_tokens = _tokens(value)
    term_tokens = _tokens(term)
    if not value_tokens or not term_tokens or len(term_tokens) > len(value_tokens):
        return False
    width = len(term_tokens)
    return any(
        value_tokens[index : index + width] == term_tokens
        for index in range(len(value_tokens) - width + 1)
    )


def _labels_match(left: Any, right: Any) -> bool:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return left_tokens == right_tokens or sorted(left_tokens) == sorted(right_tokens)


def _matches_any(value: Any, expected_values: list[Any]) -> bool:
    return any(
        _labels_match(value, expected)
        or _contains_whole_term(value, expected)
        or _contains_whole_term(expected, value)
        for expected in expected_values
    )


def _require_string_list(case: dict[str, Any], field: str) -> None:
    value = case.get(field)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise BenchmarkConfigurationError(
            f"Case {case.get('id')!r} must define non-empty strings in {field}."
        )


def _validate_case(case: Any) -> dict[str, Any]:
    if not isinstance(case, dict):
        raise BenchmarkConfigurationError("Each reliability case must be an object.")
    case_id = case.get("id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise BenchmarkConfigurationError("Each reliability case must have an id.")

    for field in (
        "expected_labels",
        "acceptable_broader_labels",
        "prohibited_labels",
        "expected_materials",
        "expected_categories",
        "prohibited_disposal_actions",
    ):
        _require_string_list(case, field)

    visible_condition = case.get("visible_condition")
    if not isinstance(visible_condition, dict) or not isinstance(
        visible_condition.get("value"), str
    ):
        raise BenchmarkConfigurationError(
            f"Case {case_id!r} must define visible_condition.value."
        )
    if not isinstance(visible_condition.get("evidence"), str):
        raise BenchmarkConfigurationError(
            f"Case {case_id!r} must define visible_condition.evidence."
        )

    guidance = case.get("expected_guidance_behavior")
    if not isinstance(guidance, dict):
        raise BenchmarkConfigurationError(
            f"Case {case_id!r} must define expected_guidance_behavior."
        )
    for field in ("preferred_actions", "fallback_actions", "required_terms_any"):
        value = guidance.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise BenchmarkConfigurationError(
                f"Case {case_id!r} must define a string list for {field}."
            )
    if not isinstance(guidance.get("clarification"), str):
        raise BenchmarkConfigurationError(
            f"Case {case_id!r} must define expected clarification behavior."
        )

    known_failures = case.get("known_failures")
    if not isinstance(known_failures, list) or not all(
        isinstance(item, str) and item in CHECK_NAMES for item in known_failures
    ):
        raise BenchmarkConfigurationError(
            f"Case {case_id!r} has invalid known_failures."
        )
    if len(known_failures) != len(set(known_failures)):
        raise BenchmarkConfigurationError(
            f"Case {case_id!r} repeats a known failure."
        )

    fixture = case.get("recorded_vlm_response")
    if not isinstance(fixture, dict):
        raise BenchmarkConfigurationError(
            f"Case {case_id!r} must define recorded_vlm_response."
        )

    image_name = case.get("image")
    if image_name is not None:
        if not isinstance(image_name, str) or not image_name.strip():
            raise BenchmarkConfigurationError(
                f"Case {case_id!r} has an invalid image path."
            )
        image_path = BACKEND_ROOT / image_name
        if not image_path.is_file():
            raise BenchmarkConfigurationError(
                f"Case {case_id!r} image does not exist: {image_path}"
            )
    return case


def load_cases(path: Path | str = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    resolved_path = Path(path)
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkConfigurationError(
            f"Could not load reliability cases from {resolved_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise BenchmarkConfigurationError("Unsupported reliability benchmark schema.")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchmarkConfigurationError("Reliability benchmark has no cases.")

    cases = [_validate_case(case) for case in raw_cases]
    case_ids = [case["id"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise BenchmarkConfigurationError("Reliability benchmark case ids must be unique.")
    return cases


def _recorded_prediction(case: dict[str, Any]) -> dict[str, Any]:
    raw_output = json.dumps(case["recorded_vlm_response"], ensure_ascii=True)
    parsed = vlm_service._parse_open_detection_result(raw_output)
    return vlm_service.build_prediction_result(parsed)


def _live_prediction(case: dict[str, Any]) -> dict[str, Any]:
    image_name = case.get("image")
    if not isinstance(image_name, str):
        raise BenchmarkConfigurationError(
            f"Case {case['id']!r} is fixture-only and cannot run in live mode."
        )
    with Image.open(BACKEND_ROOT / image_name) as image:
        return dict(
            vlm_service.get_top_predictions(
                image.convert("RGB"),
                recognition_mode="open",
            )
        )


def _classification_from_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    normalized_prediction = recognition_router._normalize_open_prediction_result(
        prediction
    )
    classification = recognition_router._build_vlm_classification(
        normalized_prediction
    )
    classification = recognition_router._attach_recognition_details(
        classification,
        normalized_prediction,
    )
    return recognition_router._with_recognition_metadata(
        classification,
        cache_hit=False,
        recognition_source=recognition_router._open_vlm_recognition_source(
            normalized_prediction
        ),
    )


def _recognition_details(classification: dict[str, Any]) -> dict[str, Any]:
    value = classification.get("recognition_details")
    return value if isinstance(value, dict) else {}


def _normalized_result(classification: dict[str, Any]) -> dict[str, Any]:
    value = _recognition_details(classification).get("normalized")
    return value if isinstance(value, dict) else {}


def _legacy_recognition_confidence(
    classification: dict[str, Any],
) -> dict[str, Any]:
    explicit = classification.get("recognition_confidence")
    if isinstance(explicit, dict):
        return explicit
    details = _recognition_details(classification)
    candidates = details.get("candidates")
    top_score: float | None = None
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            try:
                top_score = float(candidate.get("confidence"))
            except (TypeError, ValueError):
                continue
            break
    return {
        "level": str(classification.get("status") or "unknown"),
        "score": top_score,
        "source": "legacy_vlm_status",
    }


def _guidance_confidence(response: dict[str, Any]) -> dict[str, Any]:
    explicit = response.get("guidance_confidence")
    if isinstance(explicit, dict):
        return explicit
    metadata = response.get("guidance_metadata")
    confidence = metadata.get("confidence") if isinstance(metadata, dict) else None
    return {
        "level": str(confidence or "unknown"),
        "source": "legacy_guidance_metadata",
    }


def _retrieval_snapshot(classification: dict[str, Any]) -> list[dict[str, Any]]:
    if classification.get("status") != "confident":
        return []
    inputs = guidance_service._build_retrieval_inputs(classification)
    results = guidance_retrieval_service.retrieve_guidance_chunks(**inputs) or []
    snapshots: list[dict[str, Any]] = []
    for result in results:
        chunk = result.get("chunk")
        if not isinstance(chunk, dict):
            chunk = {}
        snapshots.append(
            {
                "chunk_id": result.get("chunk_id"),
                "score": result.get("score"),
                "matched_fields": list(result.get("matched_fields") or []),
                "applicability": result.get("applicability", "not_evaluated"),
                "requires_location_check": bool(
                    result.get("requires_location_check")
                ),
                "source_name": chunk.get("source_name"),
                "limitations": list(chunk.get("limitations") or []),
            }
        )
    return snapshots


def _deterministic_guidance(classification: dict[str, Any]) -> dict[str, Any]:
    with (
        patch.dict(os.environ, {"ENABLE_LLM_GUIDANCE": "false"}),
        patch.object(
            guidance_cache_service,
            "get_cached_source_grounded_guidance",
            return_value=None,
        ),
        patch.object(
            guidance_cache_service,
            "write_source_grounded_guidance_if_cacheable",
            return_value=False,
        ),
    ):
        return guidance_service.build_prediction_response(classification)


def _condition_value(classification: dict[str, Any]) -> str:
    details = _recognition_details(classification)
    observations = details.get("visual_observations")
    if not isinstance(observations, list):
        return "unknown"
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        if _normalize(observation.get("aspect")) == "condition":
            return str(observation.get("value") or "unknown")
    return "unknown"


def _condition_flags(classification: dict[str, Any]) -> list[str]:
    value = _normalized_result(classification).get("condition_flags")
    if not isinstance(value, list):
        return []
    return [_normalize(item).replace(" ", "_") for item in value if _normalize(item)]


def _clarification_requested(
    response: dict[str, Any], classification: dict[str, Any]
) -> bool:
    clarification = response.get("clarification")
    if isinstance(clarification, dict) and isinstance(
        clarification.get("required"), bool
    ):
        return clarification["required"]
    return classification.get("status") != "confident"


def _evaluate_case(
    case: dict[str, Any],
    classification: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, bool]:
    predicted_item = str(classification.get("item") or "")
    normalized = _normalized_result(classification)
    expected_labels = [
        *case["expected_labels"],
        *case["acceptable_broader_labels"],
    ]
    label_ok = _matches_any(predicted_item, expected_labels)
    prohibited_label_ok = not any(
        _contains_whole_term(predicted_item, value)
        for value in case["prohibited_labels"]
    )

    material = (
        normalized.get("primary_material")
        or normalized.get("material_category")
        or normalized.get("material")
        or classification.get("recognized_material_category")
    )
    category_values = [
        normalized.get("disposal_category"),
        normalized.get("broad_category"),
        classification.get("category"),
        classification.get("recognized_broad_category"),
    ]
    material_ok = _matches_any(material, case["expected_materials"])
    category_ok = any(
        _matches_any(value, case["expected_categories"])
        for value in category_values
        if value
    )
    condition_ok = _matches_any(
        _condition_value(classification),
        [case["visible_condition"]["value"]],
    )
    prohibited_condition_flags = {
        _normalize(value).replace(" ", "_")
        for value in case.get("prohibited_condition_flags", [])
    }
    if prohibited_condition_flags & set(_condition_flags(classification)):
        condition_ok = False

    action = _normalize(response.get("disposal_action"))
    expected_guidance = case["expected_guidance_behavior"]
    preferred = {_normalize(value) for value in expected_guidance["preferred_actions"]}
    fallback = {_normalize(value) for value in expected_guidance["fallback_actions"]}
    required_terms = expected_guidance["required_terms_any"]
    clarification_requested = _clarification_requested(response, classification)
    expected_clarification = expected_guidance["clarification"].startswith("required")
    clarification_ok = (
        clarification_requested if expected_clarification else not clarification_requested
    )

    guidance_text = " ".join(
        [
            str(response.get("summary") or ""),
            *[str(step) for step in response.get("steps") or []],
        ]
    )
    if not action and expected_clarification and clarification_requested:
        guidance_action_ok = True
    elif action in preferred:
        guidance_action_ok = True
    elif action in fallback:
        guidance_action_ok = not required_terms or any(
            _contains_whole_term(guidance_text, term) for term in required_terms
        )
    else:
        guidance_action_ok = False

    prohibited_action_ok = not action or action not in {
        _normalize(value) for value in case["prohibited_disposal_actions"]
    }
    return {
        "label": label_ok,
        "prohibited_label": prohibited_label_ok,
        "material": material_ok,
        "category": category_ok,
        "condition": condition_ok,
        "guidance_action": guidance_action_ok,
        "prohibited_action": prohibited_action_ok,
        "clarification": clarification_ok,
    }


def _case_outcome(case: dict[str, Any], mode: str) -> dict[str, Any]:
    prediction = _live_prediction(case) if mode == "live" else _recorded_prediction(case)
    classification = _classification_from_prediction(prediction)
    retrieval = _retrieval_snapshot(classification)
    response = _deterministic_guidance(classification)
    checks = _evaluate_case(case, classification, response)
    known_failures = set(case["known_failures"])
    failed_checks = [name for name, passed in checks.items() if not passed]
    expected_failures = [name for name in failed_checks if name in known_failures]
    unexpected_failures = [name for name in failed_checks if name not in known_failures]
    resolved_expected_failures = [
        name for name in known_failures if checks.get(name) is True
    ]

    details = _recognition_details(classification)
    normalized = _normalized_result(classification)
    clarification_requested = _clarification_requested(response, classification)
    action = response.get("disposal_action")
    recognition_correct = checks["label"] and checks["prohibited_label"]
    confident_wrong = (
        classification.get("status") == "confident" and not recognition_correct
    )
    incorrect_action = not checks["guidance_action"] or not checks["prohibited_action"]
    return {
        "case_id": case["id"],
        "mode": mode,
        "image": case.get("image"),
        "predicted_item": classification.get("item"),
        "classification_status": classification.get("status"),
        "vlm_evidence": {
            "visual_evidence": details.get("visual_evidence"),
            "visual_observations": list(details.get("visual_observations") or []),
            "candidates": list(details.get("candidates") or []),
        },
        "normalized_result": normalized,
        "recognition_confidence": _legacy_recognition_confidence(classification),
        "retrieved_chunks": retrieval,
        "final_disposal_action": action,
        "guidance_source": response.get("guidance_source"),
        "guidance_confidence": _guidance_confidence(response),
        "clarification_requested": clarification_requested,
        "checks": checks,
        "expected_failures": sorted(expected_failures),
        "unexpected_failures": sorted(unexpected_failures),
        "resolved_expected_failures": sorted(resolved_expected_failures),
        "recognition_correct": recognition_correct,
        "confidently_wrong": confident_wrong,
        "incorrect_disposal_action": incorrect_action,
        "confidently_wrong_disposal_instruction": bool(
            confident_wrong and action and not clarification_requested
        ),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(outcomes)
    recognition_correct = sum(bool(item["recognition_correct"]) for item in outcomes)
    confidently_wrong = sum(bool(item["confidently_wrong"]) for item in outcomes)
    clarification_requests = sum(
        bool(item["clarification_requested"]) for item in outcomes
    )
    incorrect_actions = sum(
        bool(item["incorrect_disposal_action"]) for item in outcomes
    )
    confidently_wrong_instructions = sum(
        bool(item["confidently_wrong_disposal_instruction"]) for item in outcomes
    )
    return {
        "case_count": total,
        "recognition_correct": recognition_correct,
        "recognition_accuracy": _ratio(recognition_correct, total),
        "confidently_wrong": confidently_wrong,
        "confidently_wrong_rate": _ratio(confidently_wrong, total),
        "clarification_requests": clarification_requests,
        "clarification_rate": _ratio(clarification_requests, total),
        "incorrect_disposal_actions": incorrect_actions,
        "incorrect_disposal_action_rate": _ratio(incorrect_actions, total),
        "confidently_wrong_disposal_instructions": confidently_wrong_instructions,
        "confidently_wrong_disposal_instruction_rate": _ratio(
            confidently_wrong_instructions, total
        ),
    }


def run_benchmark(
    *,
    mode: str = "deterministic",
    cases_path: Path | str = DEFAULT_CASES_PATH,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    if mode not in {"deterministic", "live"}:
        raise BenchmarkConfigurationError(f"Unsupported benchmark mode: {mode}")
    cases = load_cases(cases_path)
    requested_ids = set(case_ids or [])
    if requested_ids:
        known_ids = {case["id"] for case in cases}
        missing_ids = sorted(requested_ids - known_ids)
        if missing_ids:
            raise BenchmarkConfigurationError(
                f"Unknown benchmark case ids: {', '.join(missing_ids)}"
            )
        cases = [case for case in cases if case["id"] in requested_ids]
    if mode == "live":
        cases = [case for case in cases if isinstance(case.get("image"), str)]

    outcomes = [_case_outcome(case, mode) for case in cases]
    unexpected_failure_count = sum(
        len(outcome["unexpected_failures"]) for outcome in outcomes
    )
    expected_failure_count = sum(
        len(outcome["expected_failures"]) for outcome in outcomes
    )
    return {
        "schema_version": 1,
        "mode": mode,
        "cases_path": str(Path(cases_path).resolve()),
        "metrics": _metrics(outcomes),
        "expected_failure_count": expected_failure_count,
        "unexpected_failure_count": unexpected_failure_count,
        "passed": unexpected_failure_count == 0,
        "outcomes": outcomes,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Green Bin reliability benchmark.")
    parser.add_argument(
        "--mode",
        choices=("deterministic", "live"),
        default="deterministic",
        help="Replay recorded fixtures or send representative images to the live open VLM.",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to the benchmark metadata JSON.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Run one case id; repeat to run several.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the JSON report. The report is always printed.",
    )
    parser.add_argument(
        "--strict-live",
        action="store_true",
        help="Return a failing exit code for live-mode regressions.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = run_benchmark(
            mode=args.mode,
            cases_path=args.cases,
            case_ids=args.case_ids,
        )
    except BenchmarkConfigurationError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2

    rendered = json.dumps(report, indent=2, ensure_ascii=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.mode == "live" and not args.strict_live:
        return 0
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
