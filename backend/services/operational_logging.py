from __future__ import annotations

import hashlib
import logging
import math
import re


logger = logging.getLogger("greenbin.operations")
logger.setLevel(logging.INFO)

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_./:-]{1,64}$")


def _masked_request_id(request_id: object) -> str:
    raw_value = request_id if isinstance(request_id, str) else "missing"
    digest = hashlib.sha256(raw_value.encode("utf-8", errors="replace")).hexdigest()
    return f"rid-{digest[:16]}"


def _safe_token(value: object, fallback: str) -> str:
    normalized = str(value) if value is not None else ""
    return normalized if _SAFE_TOKEN.fullmatch(normalized) else fallback


def _safe_duration_ms(duration_ms: object) -> float:
    try:
        normalized = float(duration_ms)
    except (TypeError, ValueError):
        return 0.0
    return normalized if math.isfinite(normalized) and normalized >= 0 else 0.0


def log_operation(
    *,
    request_id: object,
    duration_ms: object,
    route: object | None = None,
    stage: object | None = None,
    status: object | None = None,
    outcome: object | None = None,
) -> None:
    fields = [f"request_id={_masked_request_id(request_id)}"]
    if route is not None:
        fields.append(f"route={_safe_token(route, 'unknown')}")
    if stage is not None:
        fields.append(f"stage={_safe_token(stage, 'unknown')}")
    if status is not None:
        fields.append(f"status={_safe_token(status, 'unknown')}")
    if outcome is not None:
        fields.append(f"outcome={_safe_token(outcome, 'unknown')}")
    fields.append(f"duration_ms={_safe_duration_ms(duration_ms):.1f}")
    logger.info("operation %s", " ".join(fields))
