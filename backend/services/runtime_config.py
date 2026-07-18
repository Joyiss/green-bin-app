from __future__ import annotations

import os


_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_FALSE_ENV_VALUES = {"0", "false", "no", "off"}


def env_flag(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized_value = raw_value.strip().casefold()
    if normalized_value in _TRUE_ENV_VALUES:
        return True
    if normalized_value in _FALSE_ENV_VALUES:
        return False
    return default


def is_clip_enabled() -> bool:
    return env_flag("ENABLE_CLIP", default=True)


def is_clip_warmup_enabled() -> bool:
    return env_flag("ENABLE_CLIP_WARMUP", default=True)
