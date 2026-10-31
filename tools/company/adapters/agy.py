"""`agy --print=<prompt> --output-format json`: one JSON object on stdout.

Shape recorded from live runs on agy 1.4.12 (2026-10-31; tests/
test_adapters.py carries them verbatim): conversation_id, status
("SUCCESS" on a clean run), response (the reply text), num_turns, usage
({input,output,thinking,cache_read,total}_tokens), structured_output when
--json-schema was given, and denied_actions when headless mode auto-denied a
tool that needed a permission prompt.
"""

from __future__ import annotations

import json


def parse(raw: str, exit_code: int | None) -> dict:
    data = None
    start = raw.find("{")
    if start != -1:
        try:
            data = json.loads(raw[start:])
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict):
        data = {}

    failed_exit = exit_code not in (0, None)
    status = data.get("status")
    if not data:
        # No result printed: unknown, unless the exit code says it failed.
        is_error, terminal_reason = (True, "no_result") if failed_exit else (None, None)
    elif status != "SUCCESS" or failed_exit:
        is_error, terminal_reason = True, (status or "no_status").lower()
    elif data.get("denied_actions"):
        # Exits SUCCESS even when headless mode auto-denied a tool and the
        # work was silently cut short (observed live) — that is not success.
        is_error, terminal_reason = True, "permission_denied"
    else:
        is_error, terminal_reason = False, None

    structured = data.get("structured_output")
    u = data.get("usage") or {}
    cache_read = u.get("cache_read_tokens") or 0
    return {
        "session_id": data.get("conversation_id"),
        "is_error": is_error,
        "terminal_reason": terminal_reason,
        "structured_output": structured if isinstance(structured, dict) else None,
        "cost_usd": None,  # agy reports tokens only, never a cost estimate
        "num_turns": data.get("num_turns"),
        "usage": {
            # Not yet observed with a cache hit, so whether input_tokens
            # includes cache reads is unconfirmed; this mirrors codex's split.
            "input_tokens": max((u.get("input_tokens") or 0) - cache_read, 0),
            "output_tokens": u.get("output_tokens") or 0,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": 0,
        },
    }
