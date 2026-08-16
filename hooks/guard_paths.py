#!/usr/bin/env python3
"""PreToolUse hook: enforce per-task file ownership (D5).

"Please don't touch backend/" is not a mechanism. This is.

Inert outside a Company OS worker: with $COMPANY_TASK unset it exits 0
immediately, so ordinary sessions are unaffected.

Fails closed. If the task view can't be read, the write is denied rather than
waved through — a broken guard that silently allows is worse than no guard.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "company"))

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
    task_id = os.environ.get("COMPANY_TASK")
    if not task_id:
        allow()

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        allow()

    if payload.get("tool_name") not in WATCHED:
        allow()

    target = (payload.get("tool_input") or {}).get("file_path")
    if not target:
        allow()

    company_root = Path(os.environ.get("COMPANY_ROOT", ""))
    repo_root = os.environ.get("COMPANY_REPO") or str(company_root.parent)
    if not company_root.is_dir():
        deny(f"Company OS ownership guard: COMPANY_ROOT is not readable "
             f"({company_root!r}), so ownership cannot be verified.")

    task_file = company_root / "tasks" / f"{task_id}.json"
    try:
        task = json.loads(task_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        deny(f"Company OS ownership guard: cannot read the task view for "
             f"{task_id} ({exc}). Denying rather than guessing.")

    import pathrules

    rel = pathrules.relative_to_repo(target, repo_root)
    if rel is None:
        record(company_root, task, task_id, target, "outside the repository")
        deny(f"Company OS ownership guard: {target} is outside the repository "
             f"({repo_root}). Task {task_id} may only write inside its own worktree.")

    ok, reason = pathrules.check(rel, task.get("owned_globs"), task.get("forbidden_globs"))
    if ok:
        allow()

    record(company_root, task, task_id, rel, reason)
    deny(
        f"Company OS ownership guard: {reason}. "
        f"Task {task_id} owns {task.get('owned_globs')} and is forbidden "
        f"{task.get('forbidden_globs')}. This block is recorded in the event log. "
        f"If this file genuinely needs to change, stop and raise an escalation "
        f"rather than working around the guard."
    )


def record(company_root: Path, task: dict, task_id: str, path: str, reason: str) -> None:
    """Log the violation. A block nobody can see is not enforcement."""
    try:
        from eventlog import EventLog, make_event
        EventLog(company_root).append(make_event(
            event="OWNERSHIP_BLOCKED",
            actor=os.environ.get("COMPANY_ACTOR", task.get("owner", "unknown")),
            project=task.get("project", "unknown"),
            task=task_id,
            data={"path": path, "reason": reason,
                  "owned_globs": task.get("owned_globs"),
                  "forbidden_globs": task.get("forbidden_globs")},
        ))
    except Exception:
        # Never let a logging failure convert a denial into an allow.
        pass


if __name__ == "__main__":
    main()
