#!/usr/bin/env python3
"""PreToolUse hook: enforce per-task file ownership (D5).

"Please don't touch backend/" is not a mechanism. This is.

Inert outside a Company OS worker: with $COMPANY_TASK unset it exits 0
immediately, so ordinary sessions are unaffected.

Fails closed. If the task view can't be read, the write is denied rather than
waved through — a broken guard that silently allows is worse than no guard.
"""

# Claude Code shim (2026-10-30, harness-agnostic M2): the policy itself now
# lives in hooks/policy.py, shared with every other harness's shim
# (hooks/guard.py). This file only translates Claude's PreToolUse payload in
# and policy's reason out as Claude's deny shape.

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import policy  # noqa: E402

WATCHED = {"Write", "Edit", "NotebookEdit", "MultiEdit"}


def allow() -> None:
    sys.exit(0)


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main() -> None:
    if not os.environ.get("COMPANY_TASK"):
        allow()
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        allow()
    if payload.get("tool_name") not in WATCHED:
        allow()
    reason = policy.check_write((payload.get("tool_input") or {}).get("file_path"))
    if reason:
        deny(reason)
    allow()


if __name__ == "__main__":
    main()
