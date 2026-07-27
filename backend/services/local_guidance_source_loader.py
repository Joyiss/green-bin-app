from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

FORSYTH_COUNTY_JURISDICTION_ID = "forsyth_county_ga"
_DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "local_guidance"
    / "forsyth_county_local_disposal_rules.json"
)
_PILOT_CONFIG_PATH = _DATA_PATH.with_name("forsyth_county_pilot_config.json")
_JURISDICTION_FILES = {
    FORSYTH_COUNTY_JURISDICTION_ID: (_DATA_PATH, _PILOT_CONFIG_PATH),
}
_CACHE: dict[str, tuple[int, dict[str, Any] | None]] = {}


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        normalized
        for item in value
        if (normalized := _text(item)) is not None
    ]


def _valid_https_url(value: Any) -> bool:
    candidate = _text(value)
    if candidate is None:
        return False
    parsed = urlparse(candidate)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _validate_fee_payload(rule: dict[str, Any]) -> None:
    fees = rule.get("fees")
    if fees is None:
        return
    if not isinstance(fees, dict) or not _text(fees.get("currency")):
        raise ValueError(f"Rule {rule['rule_id']} has invalid fees.")
    line_items = fees.get("line_items")
    if not isinstance(line_items, list) or not line_items:
        raise ValueError(f"Rule {rule['rule_id']} has no normalized fee line items.")
    for item in line_items:
        if (
            not isinstance(item, dict)
            or not _text(item.get("label"))
            or not isinstance(item.get("amount"), (int, float))
            or float(item["amount"]) < 0
            or not _text(item.get("unit"))
        ):
            raise ValueError(f"Rule {rule['rule_id']} has an invalid fee line item.")


def _normalized_pilot_fees(
    rule_id: str,
    fees: Any,
) -> dict[str, Any] | None:
    if not isinstance(fees, dict):
        return None
    if isinstance(fees.get("line_items"), list):
        return dict(fees)
    currency = _text(fees.get("currency"))
    if currency is None:
        return None

    if rule_id == "fc_tires":
        definitions = (
            ("off_rim", "Tire off rim", "each", None, None),
            ("on_rim", "Tire on rim", "each", None, None),
        )
    elif rule_id == "fc_electronics":
        definitions = (
            (
                "television_each",
                "Television",
                "each",
                ["television", "tv"],
                None,
            ),
            (
                "other_electronic_each",
                "Other electronic",
                "each",
                None,
                ["television", "tv"],
            ),
            (
                "other_electronics_unlimited",
                "Other electronics",
                "unlimited",
                None,
                ["television", "tv"],
            ),
        )
    else:
        return dict(fees)

    line_items: list[dict[str, Any]] = []
    for key, label, unit, applies_to, excludes in definitions:
        amount = fees.get(key)
        if not isinstance(amount, (int, float)):
            continue
        item: dict[str, Any] = {
            "label": label,
            "amount": amount,
            "unit": unit,
        }
        if applies_to:
            item["applies_to"] = applies_to
        if excludes:
            item["excludes"] = excludes
        line_items.append(item)
    return {"currency": currency, "line_items": line_items}


def _apply_pilot_config(payload: Any, config: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(config, dict):
        raise ValueError("Local guidance data and pilot config must be objects.")
    jurisdiction_id = _text(config.get("jurisdiction_id"))
    schema_version = _text(config.get("schema_version"))
    config_rules_version = _text(config.get("rules_version"))
    if (
        jurisdiction_id != FORSYTH_COUNTY_JURISDICTION_ID
        or schema_version is None
        or config_rules_version is None
    ):
        raise ValueError("Forsyth pilot config has invalid identity fields.")

    accepted_statuses = set(_string_list(config.get("accepted_dataset_review_statuses")))
    dataset_review_status = _text(payload.get("review_status"))
    if dataset_review_status not in accepted_statuses:
        raise ValueError(
            f"Dataset review status {dataset_review_status!r} is not enabled for the pilot."
        )

    generated_at = _text(payload.get("generated_at"))
    payload["schema_version"] = schema_version
    payload["rules_version"] = (
        f"{config_rules_version}-{generated_at}"
        if generated_at
        else config_rules_version
    )
    payload["jurisdiction_id"] = jurisdiction_id

    location_config = config.get("locations")
    if not isinstance(location_config, dict):
        raise ValueError("Forsyth pilot config has no location mapping.")
    location_ids_by_name: dict[str, str] = {}
    for name, values in location_config.items():
        if not isinstance(values, dict) or not _text(values.get("location_id")):
            raise ValueError(f"Pilot location {name!r} is invalid.")
        location_ids_by_name[str(name)] = str(values["location_id"])

    programs = payload.get("programs")
    if not isinstance(programs, list):
        raise ValueError("Local guidance dataset must contain programs.")
    for program in programs:
        if not isinstance(program, dict):
            continue
        raw_locations = program.get("locations")
        if not isinstance(raw_locations, list):
            continue
        object_locations: list[dict[str, Any]] = []
        referenced_location_ids: list[str] = []
        for location in raw_locations:
            if isinstance(location, dict):
                name = _text(location.get("name"))
                values = location_config.get(name or "")
                if not isinstance(values, dict):
                    raise ValueError(
                        f"Program location {name!r} has no pilot location mapping."
                    )
                object_locations.append({**location, **values})
            elif isinstance(location, str):
                location_id = location_ids_by_name.get(location.strip())
                if location_id is None:
                    raise ValueError(
                        f"Program location {location!r} has no pilot location mapping."
                    )
                referenced_location_ids.append(location_id)
        program["locations"] = object_locations
        if referenced_location_ids:
            program["location_ids"] = referenced_location_ids

    rule_config = config.get("rules")
    rules = payload.get("rules")
    if not isinstance(rule_config, dict) or not isinstance(rules, list):
        raise ValueError("Forsyth pilot config or dataset has no rules.")
    configured_rule_ids = set(rule_config)
    found_rule_ids: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_id = _text(rule.get("rule_id"))
        values = rule_config.get(rule_id or "")
        if not isinstance(values, dict):
            continue
        found_rule_ids.add(rule_id or "")
        rule.update(values)
        rule["review_status"] = "pilot_approved"
        normalized_fees = _normalized_pilot_fees(rule_id or "", rule.get("fees"))
        if normalized_fees is not None:
            rule["fees"] = normalized_fees
    missing_rules = sorted(configured_rule_ids - found_rule_ids)
    if missing_rules:
        raise ValueError(
            f"Dataset is missing configured pilot rules: {','.join(missing_rules)}."
        )
    return payload


def _normalize_dataset(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Local guidance dataset must be an object.")

    required_root = (
        "schema_version",
        "rules_version",
        "dataset_id",
        "jurisdiction_id",
    )
    if any(_text(payload.get(key)) is None for key in required_root):
        raise ValueError("Local guidance dataset is missing version or identity fields.")
    if payload["jurisdiction_id"] != FORSYTH_COUNTY_JURISDICTION_ID:
        raise ValueError("Local guidance dataset has an unexpected jurisdiction.")

    programs = payload.get("programs")
    rules = payload.get("rules")
    sources = payload.get("sources")
    if not isinstance(programs, list) or not isinstance(rules, list):
        raise ValueError("Local guidance dataset must contain programs and rules.")
    if not isinstance(sources, dict):
        raise ValueError("Local guidance dataset must contain sources.")

    normalized_sources: dict[str, dict[str, Any]] = {}
    for source_id, source in sources.items():
        if (
            not _text(source_id)
            or not isinstance(source, dict)
            or not _text(source.get("title"))
            or not _text(source.get("publisher"))
            or not _valid_https_url(source.get("url"))
        ):
            raise ValueError(f"Local guidance source {source_id!r} is invalid.")
        normalized_sources[str(source_id)] = dict(source)

    program_index: dict[str, dict[str, Any]] = {}
    location_index: dict[str, dict[str, Any]] = {}
    for program in programs:
        if not isinstance(program, dict):
            raise ValueError("Local guidance program must be an object.")
        program_id = _text(program.get("program_id"))
        if program_id is None or program_id in program_index:
            raise ValueError("Local guidance program IDs must be unique.")
        for source_id in _string_list(program.get("source_ids")):
            if source_id not in normalized_sources:
                raise ValueError(f"Program {program_id} references unknown source {source_id}.")
        program_index[program_id] = dict(program)
        for location in program.get("locations") or []:
            if not isinstance(location, dict):
                raise ValueError(f"Program {program_id} has an invalid location.")
            location_id = _text(location.get("location_id"))
            if (
                location_id is None
                or location_id in location_index
                or not _text(location.get("name"))
                or not _text(location.get("address"))
            ):
                raise ValueError(f"Program {program_id} has an invalid location.")
            location_index[location_id] = dict(location)

    for program_id, program in program_index.items():
        for location_id in _string_list(program.get("location_ids")):
            if location_id not in location_index:
                raise ValueError(
                    f"Program {program_id} references unknown location {location_id}."
                )

    rule_index: dict[str, dict[str, Any]] = {}
    approved_rule_ids: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Local guidance rule must be an object.")
        rule_id = _text(rule.get("rule_id"))
        program_id = _text(rule.get("program_id"))
        if rule_id is None or rule_id in rule_index:
            raise ValueError("Local guidance rule IDs must be unique.")
        if program_id not in program_index:
            raise ValueError(f"Rule {rule_id} references unknown program {program_id}.")
        for source_id in _string_list(rule.get("source_ids")):
            if source_id not in normalized_sources:
                raise ValueError(f"Rule {rule_id} references unknown source {source_id}.")
        for location_id in _string_list(rule.get("allowed_location_ids")):
            if location_id not in location_index:
                raise ValueError(f"Rule {rule_id} references unknown location {location_id}.")
        if rule.get("review_status") == "pilot_approved":
            if rule.get("time_sensitive") is True:
                raise ValueError(f"Time-sensitive rule {rule_id} cannot be pilot approved.")
            if not isinstance(rule.get("match"), dict):
                raise ValueError(f"Approved rule {rule_id} has no structured match policy.")
            _validate_fee_payload(rule)
            approved_rule_ids.append(rule_id)
        rule_index[rule_id] = dict(rule)

    return {
        **payload,
        "program_index": program_index,
        "location_index": location_index,
        "rule_index": rule_index,
        "approved_rule_ids": approved_rule_ids,
        "sources": normalized_sources,
    }


def load_local_guidance(
    jurisdiction_id: str | None,
    *,
    force_reload: bool = False,
) -> dict[str, Any] | None:
    normalized_id = _text(jurisdiction_id)
    paths = _JURISDICTION_FILES.get(normalized_id or "")
    if paths is None:
        return None
    path, config_path = paths

    try:
        modified_ns = max(path.stat().st_mtime_ns, config_path.stat().st_mtime_ns)
        cache_key = str(path)
        cached = _CACHE.get(cache_key)
        if not force_reload and cached is not None and cached[0] == modified_ns:
            return cached[1]
        payload = json.loads(path.read_text(encoding="utf-8"))
        config = json.loads(config_path.read_text(encoding="utf-8"))
        dataset = _normalize_dataset(_apply_pilot_config(payload, config))
        _CACHE[cache_key] = (modified_ns, dataset)
        return dataset
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "Local guidance unavailable. jurisdiction_id=%s error=%s",
            normalized_id,
            str(exc)[:240],
        )
        if path.exists() and config_path.exists():
            modified_ns = max(path.stat().st_mtime_ns, config_path.stat().st_mtime_ns)
            _CACHE[str(path)] = (modified_ns, None)
        return None


def get_local_rule(
    jurisdiction_id: str | None,
    rule_id: str | None,
    *,
    approved_only: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    dataset = load_local_guidance(jurisdiction_id)
    normalized_rule_id = _text(rule_id)
    if dataset is None or normalized_rule_id is None:
        return None
    rule = dataset["rule_index"].get(normalized_rule_id)
    if not isinstance(rule, dict):
        return None
    if approved_only and normalized_rule_id not in dataset["approved_rule_ids"]:
        return None
    return dataset, rule


def clear_local_guidance_cache_for_tests() -> None:
    _CACHE.clear()
