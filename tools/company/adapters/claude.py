"""`claude -p --output-format json`: one JSON object on stdout.

The same reading worker.py did inline before the adapter layer existed (find
the first `{`, parse from there, so banner text is tolerated; anything
unparseable is an empty result), now mapped onto the normalized keys.
"""

from __future__ import annotations

import json

USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens")


def parse(raw: str, exit_code: int | None) -> dict:
    start = raw.find("{")
    try:
        r = json.loads(raw[start:]) if start >= 0 else {}
    except json.JSONDecodeError:
        r = {}
    if not isinstance(r, dict):
        r = {}
    usage = r.get("usage") or {}
    return {
        "session_id": r.get("session_id"),
        "is_error": r.get("is_error"),
        "terminal_reason": r.get("terminal_reason"),
        "structured_output": r.get("structured_output"),
        "text": r.get("result"),
        # Claude Code's client-side estimate of the API price; on a
        # subscription nothing is billed. Recorded as an estimate, upstream.
        "cost_usd": r.get("total_cost_usd"),
        "num_turns": r.get("num_turns"),
        "usage": {k: usage.get(k) or 0 for k in USAGE_KEYS},
    }
