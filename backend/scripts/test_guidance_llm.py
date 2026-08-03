from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.guidance_llm_service import (  # noqa: E402
    _current_llm_settings,
    _extract_json_object,
    _text_llm_request,
)
from services.gemini_text_client import GeminiTextError  # noqa: E402


def main() -> int:
    settings = _current_llm_settings()
    print(f"provider={settings.get('provider')}")
    print(f"model={settings.get('model')}")
    print(f"timeout_seconds={float(settings.get('timeout_seconds')):.1f}")
    print(f"api_key_present={bool(settings.get('api_key'))}")

    if settings.get("provider") != "google_ai_studio":
        print("failure=Gemini text provider is not selected")
        return 1
    if not settings.get("api_key"):
        print("failure=GEMINI_API_KEY is missing")
        return 1

    prompt = (
        "Return exactly one JSON object and nothing else: "
        '{"ok": true, "message": "guidance llm smoke test"}'
    )
    started_at = time.monotonic()
    try:
        raw_text = _text_llm_request(prompt, settings=settings, mode="smoke_test")
        payload = _extract_json_object(raw_text)
    except GeminiTextError as exc:
        elapsed_seconds = time.monotonic() - started_at
        print(f"success=false elapsed_seconds={elapsed_seconds:.2f}")
        print(f"failure_class={exc.__class__.__name__}")
        print(f"failure_reason={exc.failure_reason}")
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        elapsed_seconds = time.monotonic() - started_at
        print(f"success=false elapsed_seconds={elapsed_seconds:.2f}")
        print(f"failure_class={exc.__class__.__name__}")
        return 1

    elapsed_seconds = time.monotonic() - started_at
    print(f"success=true elapsed_seconds={elapsed_seconds:.2f}")
    print(f"response_keys={sorted(str(key) for key in payload.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
