#!/usr/bin/env python3
"""PreToolUse hook: no worker reads a secret, ever (D5's ownership guard did
not cover this — it only watches Write/Edit/NotebookEdit).

A worker's worktree legitimately contains `.env` — `.worktreeinclude` copies
it in so the app and its test suite can run. That is not the same as an agent
being allowed to `Read` or `Grep` it: file contents an agent reads sit in its
transcript, and from there can end up in a report, a commit message, or an
escalation. The global settings on this machine had zero deny rules for this
(`"deny": []`) — nothing stopped it.

Bash is covered separately in protect_branches.py's ESCAPE_PATTERNS-style
check, because `cat .env` bypasses the Read tool entirely; tool-level denial
alone is not a sandbox, same caveat as everywhere else in this system.

Fires in EVERY session, not just a spawned worker (2026-10-21, ECC donation:
its hooks.json registers PreToolUse unconditionally rather than scoping to a
"worker" concept company-os's own README had flagged as a residual gap --
the PM's or an advisor's own session reading a secret is exactly as bad as a
worker's). $COMPANY_TASK is read only to attribute the event-log record to a
real actor when one exists; its absence no longer short-circuits the guard.
When no git repo can be found at all (a tool call made outside any project
checkout) there is nothing to protect, so this allows rather than denying a
question that doesn't apply.
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
from policy import SECRET_GLOBS  # noqa: E402,F401  (re-exported for tests)

WATCHED = {"Read", "Grep"}


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
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        allow()
    if payload.get("tool_name") not in WATCHED:
        allow()
    tool_input = payload.get("tool_input") or {}
    reason = policy.check_read(tool_input.get("file_path") or tool_input.get("path"))
    if reason:
        deny(reason)
    allow()


if __name__ == "__main__":
    main()
