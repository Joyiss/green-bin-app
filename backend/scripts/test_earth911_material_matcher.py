from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.earth911_material_resolver import resolve_earth911_material  # noqa: E402


def _earth911_request(endpoint: str, params: dict[str, Any]) -> Any:
    api_key = str(os.getenv("EARTH911_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("EARTH911_API_KEY is missing.")
    base_url = os.getenv("EARTH911_BASE_URL", "https://api.earth911.com").rstrip("/")
    response = requests.get(
        f"{base_url}/{endpoint}",
        params={"api_key": api_key, **params},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("result", [])


def main() -> int:
    load_dotenv(BACKEND_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Resolve an item against the Earth911 catalog without searching locations."
    )
    parser.add_argument("label")
    parser.add_argument("--category")
    args = parser.parse_args()

    print(f"llm_matching_enabled={os.getenv('ENABLE_EARTH911_LLM_MATCHING', 'false')}")
    result = resolve_earth911_material(
        args.label,
        {"material_category": args.category} if args.category else None,
        _earth911_request,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
