#!/usr/bin/env python3
"""PreToolUse hook: deterministic Bash guardrails (D5, §9).

Blocks the small set of commands that are irreversible or exfiltrating, in a
worker that cannot be talked out of them. Natural-language instructions are
not a mechanism for things that MUST NOT happen.

The RULES below (force-push, protected-branch checkout, secret exfiltration
via shell, etc.) fire in EVERY session, not just a spawned worker (2026-10-21,
ECC donation — see guard_secrets.py's docstring for the same reasoning: a
force-push from the PM's own session is exactly as destructive as one from a
worker's). The worktree-escape check (find_escape) stays worker-scoped on
purpose: "worktree" is a concept that only exists for a spawned worker — a
PM/advisor session operates on the repo directly, not a disposable worktree,
so there is no equivalent escape to check for there.
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
from policy import (RULES, find_escape,  # noqa: E402,F401  (re-exported for tests)
                    PROTECTED_BRANCHES, WRITE_ESCAPE_PATTERNS, CD_PATTERN,
                    ESCAPE_ALLOW_PREFIXES)


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
        sys.exit(0)
    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    reason = policy.check_command((payload.get("tool_input") or {}).get("command"))
    if reason:
        deny(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
