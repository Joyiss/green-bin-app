from __future__ import annotations

from typing import Any


class CacheRepository:
    """Placeholder cache abstraction for future semantic-cache work."""

    def get(self, _key: str) -> Any | None:
        return None

    def set(self, _key: str, _value: Any) -> None:
        return None
