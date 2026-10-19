#!/usr/bin/env python3
"""Codex CLI adapter for company-os's harness seam (config/harness.yaml's
`codex` entry — see doc/BYO-MODEL.md for the contract this satisfies).

`codex exec --json` streams newline-delimited JSON events rather than
printing one final object, has no `--json-schema` equivalent to force a
structured reply, and reports token usage but no cost estimate. This script
normalizes that stream into the single RESULT_SCHEMA-shaped object
worker.py's `_read_result`/`_usage` already know how to read, so no
harness-specific code was needed in worker.py itself.

The invocation this wraps, and the event shapes it parses, were read
directly from paperclip's own codex-local adapter (packages/adapters/
codex-local/src/server/{codex-args.ts,parse.ts} — github.com/paperclipai/
paperclip, MIT) during the 2026-10-19 donor review, then smoke-tested
end-to-end on this machine (codex-cli 0.163.0) before being wired into
config/harness.yaml — not shipped on the strength of reading someone else's
source alone. One correction the live test caught that the written-up
research summary missed: `turn.completed`'s usage object DOES carry a real
`cache_write_input_tokens` field (0 in the smoke test, but present) — this
maps to RESULT_SCHEMA's `cache_creation_input_tokens`, it is not absent the
way the research pass reported.
"""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    extra_args = sys.argv[1:]  # harness.py's filled command tokens, minus
                                # the trailing "-" (stdin marker), added here
    packet = sys.stdin.read()

    proc = subprocess.run(
        ["codex", "exec", "--json", *extra_args, "-"],
        input=packet, capture_output=True, text=True,
    )

    session_id = None
    agent_text = ""
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    is_error = proc.returncode != 0
    terminal_reason = None

    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # a non-JSON stray line is not fatal to the rest

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
                # them back out so this matches Claude's accounting, where
                # input/cache_read are already disjoint.
                "input": max((u.get("input_tokens") or 0) - cached, 0),
                "output": u.get("output_tokens") or 0,
                "cache_read": cached,
                "cache_creation": u.get("cache_write_input_tokens") or 0,
            }
            if etype != "turn.completed":
                is_error = True
                terminal_reason = etype

    # The model's own structured answer (it was asked, via the packet/
    # persona text worker.py already sent on stdin, to reply with a
    # RESULT_SCHEMA-shaped JSON object) lives inside agent_text as free-form
    # text Codex has no way to constrain the shape of — find it the same
    # tolerant way worker.py's own _read_result does.
    start = agent_text.find("{")
    structured = {}
    if start != -1:
        try:
            structured = json.loads(agent_text[start:])
        except json.JSONDecodeError:
            structured = {}

    result = {
        **structured,
        "session_id": session_id,
        "is_error": is_error,
        "terminal_reason": terminal_reason,
        "total_cost_usd": None,  # Codex reports tokens only, never a cost estimate
        "usage": {
            "input_tokens": usage["input"],
            "output_tokens": usage["output"],
            "cache_read_input_tokens": usage["cache_read"],
            "cache_creation_input_tokens": usage["cache_creation"],
        },
    }
    print(json.dumps(result))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
