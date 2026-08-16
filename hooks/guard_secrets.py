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

Inert outside a Company OS worker ($COMPANY_TASK unset).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "company"))

WATCHED = {"Read", "Grep"}

# Deliberately independent of risk-triggers.yaml's "secrets" trigger: that
# table decides which GATES a task needs, not which physical files an agent
# may look inside regardless of task. Mirrors protect_branches.py's own
# commit-time pattern for the same file classes, so both guards agree on what
# counts as a secret.
SECRET_GLOBS = (
    "**/.env", "**/.env.*", "**/secrets/**", "**/keys/**",
    "**/id_rsa*", "**/*.pem", "**/credentials.json",
    "**/secrets.json", "**/secrets.yaml", "**/secrets.yml",
)


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
    task_id = os.environ.get("COMPANY_TASK")
    if not task_id:
        allow()

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        allow()

    if payload.get("tool_name") not in WATCHED:
        allow()

    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("path")
    if not target:
        allow()

    import pathrules

    company_root = Path(os.environ.get("COMPANY_ROOT", ""))
    repo_root = os.environ.get("COMPANY_REPO") or str(company_root.parent)
    rel = pathrules.relative_to_repo(target, repo_root)
    # Outside the repo entirely (e.g. reading /tmp scratch) is not this guard's
    # concern — the ownership guard already governs the repo boundary for
    # writes, and reads outside the repo are not a secrets-exposure question.
    if rel is None:
        allow()

    hit = pathrules.matches_any(rel, SECRET_GLOBS)
    if not hit:
        allow()

    record(company_root, task_id, rel, hit)
    deny(
        f"Company OS secrets guard: {rel} matches {hit!r}. Workers may not "
        f"read secret or environment files directly — your test suite and "
        f"application can still consume them at runtime via Bash, but you may "
        f"not view their contents. This block is recorded in the event log. "
        f"If you genuinely need a value from it, raise an escalation."
    )


def record(company_root: Path, task_id: str, path: str, glob: str) -> None:
    try:
        from eventlog import EventLog, make_event
        task = json.loads((company_root / "tasks" / f"{task_id}.json").read_text(encoding="utf-8"))
        EventLog(company_root).append(make_event(
            event="SECRET_READ_BLOCKED",
            actor=os.environ.get("COMPANY_ACTOR", task.get("owner", "unknown")),
            project=task.get("project", "unknown"),
            task=task_id,
            data={"path": path, "glob": glob},
        ))
    except Exception:
        pass


if __name__ == "__main__":
    main()
