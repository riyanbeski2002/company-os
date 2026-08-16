#!/usr/bin/env python3
"""PreToolUse hook: deterministic Bash guardrails (D5, §9).

Blocks the small set of commands that are irreversible or exfiltrating, in a
worker that cannot be talked out of them. Natural-language instructions are
not a mechanism for things that MUST NOT happen.

Inert outside a Company OS worker ($COMPANY_TASK unset).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "company"))

PROTECTED_BRANCHES = ("main", "master", "develop", "integration")

# `guard_secrets.py` blocks the Read/Grep tools; a worker can trivially read
# the same file's contents via Bash instead (`cat .env`, `head secrets.yaml`).
# Deliberately not exhaustive — obfuscated reads (`python3 -c "print(open(...))"`,
# base64 pipelines) are not caught, same pattern-matching caveat as
# ESCAPE_PATTERNS below. This catches the common, unobfuscated shapes.
SECRET_READ_TOOLS = r"(?:cat|less|more|head|tail|od|xxd|strings|bat)"
SECRET_FILE_PATTERN = (
    r"(\.env\b|\.env\.\S*|secrets?\S*\.(?:json|ya?ml)|"
    r"\bsecrets/\S+|\bkeys/\S+\.(?:json|pem|key)|id_rsa\S*|\.pem\b|credentials\.json)"
)

RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bgit\s+push\b.*(--force\b|--force-with-lease\b|\s-f\b)"),
     "force-push"),
    (re.compile(r"\bgit\s+push\b.*\s(?::|\+)"),
     "branch deletion or forced ref update via push refspec"),
    (re.compile(r"\bgit\s+branch\b.*\s-D\b"),
     "forced branch deletion"),
    (re.compile(r"\bgit\s+reset\b.*--hard\b.*\borigin/(?:%s)\b" % "|".join(PROTECTED_BRANCHES)),
     "hard reset onto a protected branch"),
    (re.compile(r"\bgit\s+checkout\b\s+(?:%s)\b" % "|".join(PROTECTED_BRANCHES)),
     "checking out a protected branch (a task worker stays on its own branch)"),
    # Only root-ish targets. `rm -rf /tmp/scratch` is ordinary work — an earlier
    # version of this rule blocked a reviewer's mutation-testing scratch dir.
    (re.compile(r"\brm\s+(?:-[a-zA-Z]*[rf][a-zA-Z]*\s+)+"
                r"(?:/|~|\$HOME|\.\.?|/[A-Za-z0-9_.-]+)/?\*?(?:\s|$)"),
     "recursive delete of a root, home, or top-level path"),
    (re.compile(r"\bgit\s+(commit|add)\b.*(\.env\b|\.env\.|id_rsa|\.pem\b|credentials\.json|secrets?\.(json|ya?ml))"),
     "committing a secret or environment file"),
    (re.compile(r"\b%s\b[^;|&\n]*%s" % (SECRET_READ_TOOLS, SECRET_FILE_PATTERN)),
     "reading a secret or environment file's contents via shell "
     "(the Read/Grep tools are already blocked for this — see guard_secrets.py)"),
    (re.compile(r"\bgit\s+worktree\s+remove\b"),
     "worktree removal (worktrees are preserved on failure, never auto-deleted)"),
]


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


# Absolute-path write targets. The ownership hook only sees Write/Edit/
# NotebookEdit, so without this a worker could write anywhere via a shell
# redirect. This catches the common shapes; it is NOT a complete sandbox —
# see the "residual gap" note in the README.
ESCAPE_PATTERNS = [
    re.compile(r">>?\s*(/[^\s;|&>]+)"),                 # > /abs  and  >> /abs
    re.compile(r"\btee\s+(?:-a\s+)?(/[^\s;|&]+)"),      # tee /abs
    re.compile(r"\b(?:cp|mv|install)\s+[^;|&]*?\s(/[^\s;|&]+)\s*(?:$|[;|&])"),
    re.compile(r"\bcd\s+(/[^\s;|&]+)"),                 # cd /abs
]

# Writable-anyway locations: scratch space a reviewer or test run legitimately
# uses, and the event log the worker is required to append to.
ESCAPE_ALLOW_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "/dev/")


def find_escape(command: str, worktree: str, company_root: str) -> str | None:
    for pattern in ESCAPE_PATTERNS:
        for target in pattern.findall(command):
            path = os.path.normpath(target)
            if path.startswith(ESCAPE_ALLOW_PREFIXES) or path in ("/dev/null",):
                continue
            if worktree and (path == worktree or path.startswith(worktree + "/")):
                continue
            if company_root and (path == company_root or path.startswith(company_root + "/")):
                continue
            return path
    return None


def main() -> None:
    task_id = os.environ.get("COMPANY_TASK")
    if not task_id:
        sys.exit(0)
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command") or ""

    worktree = os.path.normpath(os.environ.get("COMPANY_REPO", "")) if os.environ.get("COMPANY_REPO") else ""
    croot = os.path.normpath(os.environ.get("COMPANY_ROOT", "")) if os.environ.get("COMPANY_ROOT") else ""
    escaped = find_escape(command, worktree, croot)
    if escaped:
        record(task_id, command, "shell write outside the worktree")
        deny(
            f"Company OS worktree guard: this command writes to {escaped}, which is "
            f"outside your worktree ({worktree}). Your entire working copy is the "
            f"worktree; use a path inside it, or /tmp for scratch. This block is "
            f"recorded in the event log."
        )

    for pattern, label in RULES:
        if pattern.search(command):
            record(task_id, command, label)
            deny(
                f"Company OS branch guard: blocked {label}. "
                f"This is a hard guardrail, not a preference — it is recorded in "
                f"the event log. If this action is genuinely required, raise an "
                f"escalation instead of rephrasing the command."
            )
    sys.exit(0)


def record(task_id: str, command: str, label: str) -> None:
    try:
        from eventlog import EventLog, make_event
        root = Path(os.environ["COMPANY_ROOT"])
        task = json.loads((root / "tasks" / f"{task_id}.json").read_text(encoding="utf-8"))
        EventLog(root).append(make_event(
            event="BRANCH_GUARD_BLOCKED",
            actor=os.environ.get("COMPANY_ACTOR", task.get("owner", "unknown")),
            project=task.get("project", "unknown"),
            task=task_id,
            data={"rule": label, "command": command[:500]},
        ))
    except Exception:
        pass


if __name__ == "__main__":
    main()
