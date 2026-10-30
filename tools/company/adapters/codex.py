"""`codex exec --json`: newline-delimited JSON events on stdout.

Event shapes were read from paperclip's codex-local adapter (packages/
adapters/codex-local/src/server/parse.ts, MIT) during the 2026-10-19 donor
review and live-smoke-tested on codex-cli 0.163.0 — including the one
correction that test caught: `turn.completed` usage DOES carry
`cache_write_input_tokens`. Moved here unchanged from codex_adapter.py's
inline parsing, which is now a thin shim over this module.
"""

from __future__ import annotations

import json


def parse(raw: str, exit_code: int | None) -> dict:
    session_id = None
    agent_text = ""
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    is_error = exit_code not in (0, None)
    terminal_reason = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # a non-JSON stray line is not fatal to the rest
        if not isinstance(event, dict):
            continue

        etype = event.get("type")
        if etype == "thread.started":
            session_id = event.get("thread_id")
        elif etype == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                agent_text += item.get("text") or ""
        elif etype in ("turn.completed", "turn.failed", "error"):
            u = event.get("usage") or {}
            cached = u.get("cached_input_tokens") or 0
            usage = {
                # Codex's input_tokens includes its own cache hits; split
                # them back out so input and cache_read are disjoint, as in
                # Claude's accounting.
                "input": max((u.get("input_tokens") or 0) - cached, 0),
                "output": u.get("output_tokens") or 0,
                "cache_read": cached,
                "cache_creation": u.get("cache_write_input_tokens") or 0,
            }
            if etype != "turn.completed":
                is_error = True
                terminal_reason = etype

    # The structured reply is free text Codex can't constrain the shape of
    # (no --json-schema equivalent is used yet; `--output-schema` exists but
    # is unverified live — milestone M3). Found the same tolerant way as
    # Claude's: first `{` onward.
    structured = None
    start = agent_text.find("{")
    if start != -1:
        try:
            parsed = json.loads(agent_text[start:])
            structured = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            structured = None

    return {
        "session_id": session_id,
        "is_error": is_error,
        "terminal_reason": terminal_reason,
        "structured_output": structured,
        "cost_usd": None,  # Codex reports tokens only, never a cost estimate
        "num_turns": None,
        "usage": {
            "input_tokens": usage["input"],
            "output_tokens": usage["output"],
            "cache_read_input_tokens": usage["cache_read"],
            "cache_creation_input_tokens": usage["cache_creation"],
        },
    }
