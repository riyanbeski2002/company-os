"""Harness-neutral guard policy (docs/HARNESS-AGNOSTIC-MIGRATION.md §4.6, M2).

The three guards — ownership (writes), secrets (reads), commands (shell) —
used to live inside Claude Code PreToolUse scripts, entangled with Claude's
payload (`tool_name`/`tool_input`) and deny shape (`permissionDecision`). A
worker on any other harness ran with none of them. The policy itself never
depended on Claude: it is a path checked against globs and a command checked
against rules. It lives here now; each harness gets a thin shim that
translates its own hook payload into one of three calls and the returned
reason into its own deny format (guard_paths.py / guard_secrets.py /
protect_branches.py for Claude, guard.py for the others).

Each check returns None to allow, or the deny reason — after recording the
block in the event log (a block nobody can see is not enforcement). Moved
verbatim from the original scripts; their docstrings keep the history.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "company"))


# --- ownership (from guard_paths.py) ------------------------------------------

def check_write(target: str | None) -> str | None:
    """Per-task file ownership (D5). Worker-scoped: inert with $COMPANY_TASK
    unset. Fails closed — an unreadable task view denies, never guesses."""
    task_id = os.environ.get("COMPANY_TASK")
    if not task_id or not target:
        return None

    company_root = Path(os.environ.get("COMPANY_ROOT", ""))
    repo_root = os.environ.get("COMPANY_REPO") or str(company_root.parent)
    if not company_root.is_dir():
        return (f"Company OS ownership guard: COMPANY_ROOT is not readable "
                f"({company_root!r}), so ownership cannot be verified.")

    task_file = company_root / "tasks" / f"{task_id}.json"
    try:
        task = json.loads(task_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (f"Company OS ownership guard: cannot read the task view for "
                f"{task_id} ({exc}). Denying rather than guessing.")

    import pathrules

    rel = pathrules.relative_to_repo(target, repo_root)
    if rel is None:
        _record_ownership(company_root, task, task_id, target, "outside the repository")
        return (f"Company OS ownership guard: {target} is outside the repository "
                f"({repo_root}). Task {task_id} may only write inside its own worktree.")

    ok, reason = pathrules.check(rel, task.get("owned_globs"), task.get("forbidden_globs"))
    if ok:
        return None

    _record_ownership(company_root, task, task_id, rel, reason)
    return (
        f"Company OS ownership guard: {reason}. "
        f"Task {task_id} owns {task.get('owned_globs')} and is forbidden "
        f"{task.get('forbidden_globs')}. This block is recorded in the event log. "
        f"If this file genuinely needs to change, stop and raise an escalation "
        f"rather than working around the guard."
    )


def _record_ownership(company_root: Path, task: dict, task_id: str, path: str,
                      reason: str) -> None:
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


# --- secrets (from guard_secrets.py) ------------------------------------------

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




def check_read(target: str | None) -> str | None:
    """No session reads a secret file's contents. Fires in every session,
    not just workers; allows outside any repo (nothing to protect)."""
    if not target:
        return None
    task_id = os.environ.get("COMPANY_TASK")

    import pathrules

    if os.environ.get("COMPANY_ROOT"):
        company_root = Path(os.environ["COMPANY_ROOT"])
        repo_root = os.environ.get("COMPANY_REPO") or str(company_root.parent)
    else:
        repo = pathrules.resolve_repo_context()
        if repo is None:
            return None  # not inside any repo — nothing to protect
        company_root = repo / ".company"
        repo_root = str(repo)

    rel = pathrules.relative_to_repo(target, repo_root)
    if rel is None:
        return None  # reads outside the repo are not a secrets-exposure question

    hit = pathrules.matches_any(rel, SECRET_GLOBS)
    if not hit:
        return None

    _record_secret(company_root, task_id, rel, hit)
    return (
        f"Company OS secrets guard: {rel} matches {hit!r}. Workers may not "
        f"read secret or environment files directly — your test suite and "
        f"application can still consume them at runtime via Bash, but you may "
        f"not view their contents. This block is recorded in the event log. "
        f"If you genuinely need a value from it, raise an escalation."
    )


def _record_secret(company_root: Path, task_id: str | None, path: str, glob: str) -> None:
    try:
        from eventlog import EventLog, make_event
        actor, project = os.environ.get("COMPANY_ACTOR", "unknown"), "unknown"
        if task_id:
            task = json.loads((company_root / "tasks" / f"{task_id}.json").read_text(encoding="utf-8"))
            actor = os.environ.get("COMPANY_ACTOR", task.get("owner", "unknown"))
            project = task.get("project", "unknown")
        EventLog(company_root).append(make_event(
            event="SECRET_READ_BLOCKED",
            actor=actor,
            project=project,
            task=task_id,  # None for a non-worker (PM/advisor) session
            data={"path": path, "glob": glob},
        ))
    except Exception:
        pass


# --- commands (from protect_branches.py) ----------------------------------------

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
     "raw worktree removal — use `company cleanup`, which removes only finished "
     "worktrees, checkpoints uncommitted work first, and preserves failed ones"),
]


# Absolute-path write targets. The ownership hook only sees Write/Edit/
# NotebookEdit, so without this a worker could write anywhere via a shell
# redirect. This catches the common shapes; it is NOT a complete sandbox —
# see the "residual gap" note in the README.
#
# `cd` is deliberately NOT a write pattern: it's pure navigation, and the
# capability-registry workflow (external/<id>/, skills/<id>/) requires every
# worker to be able to `cd` into the MAIN checkout to read vetted capabilities
# there — that's the whole point of $CLAUDE_PLUGIN_ROOT/COMPANY_MAIN_REPO
# always pointing at it regardless of which worktree launched the worker (see
# agents/company-pm.md). A worker's writes are still fully blocked outside its
# worktree by the ownership hook (Write/Edit/NotebookEdit) and by the write
# patterns below for the shell-redirect escape those tools don't see — cd
# alone changes no bytes, so it gets its own, more permissive allowlist.
WRITE_ESCAPE_PATTERNS = [
    re.compile(r">>?\s*(/[^\s;|&>]+)"),                 # > /abs  and  >> /abs
    re.compile(r"\btee\s+(?:-a\s+)?(/[^\s;|&]+)"),      # tee /abs
    re.compile(r"\b(?:cp|mv|install)\s+[^;|&]*?\s(/[^\s;|&]+)\s*(?:$|[;|&])"),
]
CD_PATTERN = re.compile(r"\bcd\s+(/[^\s;|&]+)")

# Writable-anyway locations: scratch space a reviewer or test run legitimately
# uses, and the event log the worker is required to append to.
ESCAPE_ALLOW_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "/dev/")


def find_escape(command: str, worktree: str, company_root: str, main_repo: str = "") -> str | None:
    for pattern in WRITE_ESCAPE_PATTERNS:
        for target in pattern.findall(command):
            path = os.path.normpath(target)
            if path.startswith(ESCAPE_ALLOW_PREFIXES) or path in ("/dev/null",):
                continue
            if worktree and (path == worktree or path.startswith(worktree + "/")):
                continue
            if company_root and (path == company_root or path.startswith(company_root + "/")):
                continue
            return path
    for target in CD_PATTERN.findall(command):
        path = os.path.normpath(target)
        if path.startswith(ESCAPE_ALLOW_PREFIXES) or path in ("/dev/null",):
            continue
        if worktree and (path == worktree or path.startswith(worktree + "/")):
            continue
        if company_root and (path == company_root or path.startswith(company_root + "/")):
            continue
        if main_repo and (path == main_repo or path.startswith(main_repo + "/")):
            continue
        return path
    return None



def check_command(command: str | None) -> str | None:
    """Deterministic shell guardrails. RULES fire in every session; the
    worktree-escape check only where there IS a worktree (a spawned worker)."""
    command = command or ""
    task_id = os.environ.get("COMPANY_TASK")

    if task_id:
        worktree = os.path.normpath(os.environ.get("COMPANY_REPO", "")) if os.environ.get("COMPANY_REPO") else ""
        croot = os.path.normpath(os.environ.get("COMPANY_ROOT", "")) if os.environ.get("COMPANY_ROOT") else ""
        main_repo = os.path.normpath(os.environ.get("COMPANY_MAIN_REPO", "")) if os.environ.get("COMPANY_MAIN_REPO") else ""
        escaped = find_escape(command, worktree, croot, main_repo)
        if escaped:
            _record_command(task_id, command, "shell write outside the worktree")
            return (
                f"Company OS worktree guard: this command writes to {escaped}, which is "
                f"outside your worktree ({worktree}). Your entire working copy is the "
                f"worktree; use a path inside it, or /tmp for scratch. This block is "
                f"recorded in the event log."
            )

    for pattern, label in RULES:
        if pattern.search(command):
            _record_command(task_id, command, label)
            return (
                f"Company OS branch guard: blocked {label}. "
                f"This is a hard guardrail, not a preference — it is recorded in "
                f"the event log. If this action is genuinely required, raise an "
                f"escalation instead of rephrasing the command."
            )
    return None


def _record_command(task_id: str | None, command: str, label: str) -> None:
    try:
        from eventlog import EventLog, make_event
        import pathrules
        if os.environ.get("COMPANY_ROOT"):
            root = Path(os.environ["COMPANY_ROOT"])
        else:
            repo = pathrules.resolve_repo_context()
            if repo is None:
                return
            root = repo / ".company"
        actor, project = os.environ.get("COMPANY_ACTOR", "unknown"), "unknown"
        if task_id:
            task = json.loads((root / "tasks" / f"{task_id}.json").read_text(encoding="utf-8"))
            actor = os.environ.get("COMPANY_ACTOR", task.get("owner", "unknown"))
            project = task.get("project", "unknown")
        EventLog(root).append(make_event(
            event="BRANCH_GUARD_BLOCKED",
            actor=actor,
            project=project,
            task=task_id,  # None for a non-worker (PM/advisor) session
            data={"rule": label, "command": command[:500]},
        ))
    except Exception:
        pass
