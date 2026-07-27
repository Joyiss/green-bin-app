from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote_plus

try:
    from .local_guidance_source_loader import load_local_guidance
except ImportError:
    from services.local_guidance_source_loader import load_local_guidance


def _normalize(value: Any) -> str:
    normalized = str(value or "").casefold().replace("_", " ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                for key in ("label", "item_label", "value", "evidence"):
                    if isinstance(item.get(key), str):
                        values.append(item[key])
        return values
    return []


def _classification_evidence(
    classification: dict[str, Any],
) -> tuple[str, str, str]:
    recognition = classification.get("recognition_details")
    recognition = recognition if isinstance(recognition, dict) else {}
    normalized = recognition.get("normalized")
    normalized = normalized if isinstance(normalized, dict) else {}
    item_values: list[str] = []
    for value in (
        classification.get("item"),
        recognition.get("raw_item_label"),
        normalized.get("normalized_item"),
        normalized.get("item_label"),
        normalized.get("matched_supported_label"),
    ):
        item_values.extend(_text_values(value))
    item_values.extend(_text_values(classification.get("candidates")))
    item_values.extend(_text_values(recognition.get("candidates")))
    item_values.extend(_text_values(recognition.get("visual_observations")))
    item_values.extend(_text_values(normalized.get("visual_observations")))

    category_values: list[str] = []
    for value in (
        classification.get("category"),
        classification.get("recognized_material_category"),
        classification.get("recognized_broad_category"),
        recognition.get("likely_material"),
        recognition.get("broad_category"),
        normalized.get("material_category"),
        normalized.get("primary_material"),
        normalized.get("disposal_category"),
        normalized.get("broad_category"),
        normalized.get("visual_observation_text"),
    ):
        category_values.extend(_text_values(value))
    raw = " ".join([*item_values, *category_values])
    return raw, _normalize(raw), _normalize(" ".join(item_values))


def _contains_phrase(evidence: str, phrase: Any) -> bool:
    normalized = _normalize(phrase)
    if not normalized:
        return False
    return re.search(rf"(?:^|\s){re.escape(normalized)}(?:$|\s)", evidence) is not None


def _extract_resin_codes(raw_evidence: str, evidence: str) -> set[str]:
    codes = {
        match.group(1)
        for match in re.finditer(
            r"(?:#|resin\s*code\s*|plastic\s*number\s*)([1-7])\b",
            raw_evidence.casefold(),
        )
    }
    if _contains_phrase(evidence, "pet") or _contains_phrase(evidence, "pet 1"):
        codes.add("1")
    if _contains_phrase(evidence, "hdpe") or _contains_phrase(evidence, "hdpe 2"):
        codes.add("2")
    return codes


def _requirement_status(
    requirement: dict[str, Any],
    *,
    raw_evidence: str,
    evidence: str,
) -> tuple[bool, str | None]:
    field = _normalize(requirement.get("field")).replace(" ", "_")
    allowed = {
        _normalize(value)
        for value in requirement.get("allowed_values") or []
        if _normalize(value)
    }
    if field == "resin_code":
        observed = _extract_resin_codes(raw_evidence, evidence)
        return bool(observed & allowed), str(requirement.get("message") or "").strip() or None
    return False, str(requirement.get("message") or "").strip() or None


def _resolved_sources(dataset: dict[str, Any], rule: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for source_id in rule.get("source_ids") or []:
        source = dataset["sources"].get(source_id)
        if isinstance(source, dict):
            sources.append({"source_id": source_id, **source})
    return sources


def _allowed_destinations(
    dataset: dict[str, Any], rule: dict[str, Any]
) -> list[dict[str, Any]]:
    destinations: list[dict[str, Any]] = []
    program = dataset["program_index"].get(rule.get("program_id")) or {}
    hours = program.get("hours")
    payment = program.get("payment")
    for location_id in rule.get("allowed_location_ids") or []:
        location = dataset["location_index"].get(location_id)
        if not isinstance(location, dict):
            continue
        address = str(location.get("address") or "").strip()
        destinations.append(
            {
                "location_id": location_id,
                "name": location.get("name"),
                "address": address,
                "phone": location.get("phone"),
                "hours": hours,
                "payment": payment,
                "directions_url": (
                    "https://www.google.com/maps/search/?api=1&query="
                    + quote_plus(address)
                    if address
                    else None
                ),
            }
        )
    return destinations


def _applicable_fees(rule: dict[str, Any], evidence: str) -> dict[str, Any] | None:
    fees = rule.get("fees")
    if not isinstance(fees, dict):
        return None
    line_items: list[dict[str, Any]] = []
    for item in fees.get("line_items") or []:
        applies_to = item.get("applies_to") or []
        excludes = item.get("excludes") or []
        if applies_to and not any(_contains_phrase(evidence, value) for value in applies_to):
            continue
        if excludes and any(_contains_phrase(evidence, value) for value in excludes):
            continue
        line_items.append(
            {
                key: item.get(key)
                for key in ("label", "amount", "unit")
                if item.get(key) is not None
            }
        )
    return {
        "currency": fees.get("currency"),
        "line_items": line_items,
    } if line_items else None


def match_local_guidance(
    classification: dict[str, Any],
    jurisdiction_id: str | None,
) -> dict[str, Any]:
    dataset = load_local_guidance(jurisdiction_id)
    if dataset is None:
        return {"status": "no_match", "dataset": None}

    raw_evidence, evidence, item_evidence = _classification_evidence(classification)
    candidates: list[dict[str, Any]] = []
    for rule_id in dataset["approved_rule_ids"]:
        rule = dataset["rule_index"][rule_id]
        match = rule.get("match") or {}
        excluded_terms = [
            term
            for term in match.get("exclude_terms") or []
            if _contains_phrase(evidence, term)
        ]
        include_terms = [
            term
            for term in match.get("include_terms") or []
            if _contains_phrase(evidence, term)
        ]
        if excluded_terms:
            candidates.append(
                {
                    "status": "excluded",
                    "rule": rule,
                    "priority": int(match.get("priority") or 0),
                    "matched_terms": excluded_terms,
                    "missing_messages": [],
                }
            )
            continue
        if not include_terms:
            continue

        missing_messages: list[str] = []
        if not any(_contains_phrase(item_evidence, term) for term in include_terms):
            missing_messages.append(
                "Confirm the exact item type before using this local program."
            )
        for requirement in match.get("required_evidence") or []:
            if not isinstance(requirement, dict):
                continue
            satisfied, message = _requirement_status(
                requirement,
                raw_evidence=raw_evidence,
                evidence=evidence,
            )
            if not satisfied and requirement.get("on_missing") == "conditional":
                missing_messages.append(
                    message or "Confirm the item meets the local acceptance requirement."
                )
        candidates.append(
            {
                "status": "conditional" if missing_messages else "applicable",
                "rule": rule,
                "priority": int(match.get("priority") or 0),
                "matched_terms": include_terms,
                "missing_messages": missing_messages,
            }
        )

    if not candidates:
        return {
            "status": "no_match",
            "dataset": dataset,
            "rules_version": dataset["rules_version"],
        }

    status_rank = {"excluded": 3, "applicable": 2, "conditional": 1}
    selected = max(
        candidates,
        key=lambda candidate: (
            candidate["priority"],
            status_rank[candidate["status"]],
            max((len(_normalize(term)) for term in candidate["matched_terms"]), default=0),
        ),
    )
    rule = selected["rule"]
    program = dataset["program_index"][rule["program_id"]]
    destinations = _allowed_destinations(dataset, rule)
    sources = _resolved_sources(dataset, rule)
    fees = _applicable_fees(rule, evidence)
    applicability = selected["status"]
    item = str(classification.get("item") or "This item").strip() or "This item"

    if applicability == "excluded":
        disposal_action = "Check local guidance"
        summary = (
            f"{item} is not accepted in this Forsyth County program stream."
        )
        decision = "not_accepted"
    elif applicability == "conditional":
        disposal_action = "Check local guidance"
        summary = (
            f"Forsyth County accepts {item} only when the listed local requirement is confirmed."
        )
        decision = rule.get("decision")
    else:
        disposal_action = "Drop off"
        summary = f"{item} is accepted through {program.get('name')}."
        decision = rule.get("decision")

    preparation = list(rule.get("preparation") or [])
    if applicability == "conditional":
        preparation = [*selected["missing_messages"], *preparation]
    restrictions = list(rule.get("restrictions") or [])
    local_guidance = {
        "dataset_id": dataset["dataset_id"],
        "rules_version": dataset["rules_version"],
        "rule_id": rule["rule_id"],
        "program_id": rule["program_id"],
        "decision": decision,
        "applicability": applicability,
        "local_action": rule.get("action"),
        "preparation": preparation,
        "restrictions": restrictions,
        "fees": fees,
        "sources": sources,
        "earth911_material_label": rule.get("earth911_material_label"),
        "allowed_location_names": [
            destination["name"] for destination in destinations if destination.get("name")
        ],
        "destinations": destinations,
    }
    source_names = [str(source.get("title")) for source in sources if source.get("title")]
    source_urls = [str(source.get("url")) for source in sources if source.get("url")]
    guidance = {
        "disposal_action": disposal_action,
        "material_code": None,
        "impact_level": "Local Guidance",
        "summary": summary,
        "steps": preparation,
        "warnings": restrictions,
        "guidance_source": "local_rules",
        "local_guidance": local_guidance,
        "guidance_metadata": {
            "jurisdiction_id": dataset["jurisdiction_id"],
            "local_rules_version": dataset["rules_version"],
            "applicable_local_rule_ids": [rule["rule_id"]],
            "local_rule_applicability": applicability,
            "source_names": source_names,
            "source_urls": source_urls,
            "location_search_recommended": applicability != "excluded",
            "final_generation_path": "local_rules",
        },
    }
    return {
        "status": applicability,
        "dataset": dataset,
        "rules_version": dataset["rules_version"],
        "guidance": guidance,
    }
