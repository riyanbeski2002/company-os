"""Tier-2 worker lifecycle: worktree, launch, supervise, record (D2, D7).

A worker is a `claude -p` process we own. We get an exit code, a session id,
and a parseable result — which is the whole reason this tier exists rather than
`--bg`. A background session looks nicer and returns nothing checkable, and the
Evidence Rule is made of checkable things.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from eventlog import EventLog, make_event

PLUGIN_ROOT = Path(__file__).resolve().parents[2]

# Structured output contract. Forcing a schema means the worker's report is
# parsed, not interpreted.
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "commit": {"type": "string"},
        "tests_command": {"type": "string"},
        "tests_exit_code": {"type": "integer"},
        "contract_published": {"type": "boolean"},
        "blocked": {"type": "boolean"},
        "blocked_reason": {"type": "string"},
    },
    "required": ["summary", "blocked"],
}

ROLE_TOOLS = {
    "backend-engineer": "Read,Grep,Glob,Edit,Write,Bash",
    "frontend-engineer": "Read,Grep,Glob,Edit,Write,Bash",
    "code-reviewer": "Read,Grep,Glob,Bash",
    "qa-engineer": "Read,Grep,Glob,Bash",
    "security-reviewer": "Read,Grep,Glob,Bash",
}


class WorkerError(RuntimeError):
    pass


def slug(text: str, limit: int = 32) -> str:
    out = "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out[:limit].strip("-") or "task"


# --- worktree ---------------------------------------------------------------

def ensure_worktree(repo: Path, company_root: Path, task: dict) -> tuple[Path, str]:
    """Create the task's worktree and branch. Never removes an existing one."""
    tid = task["id"]
    branch = task.get("branch") or f"task/{tid.split('-')[-1]}-{slug(task.get('title', tid))}"
    wt = Path(task.get("worktree") or (company_root / "worktrees" / tid))

    if wt.exists():
        return wt, branch  # preserved from a previous run, by design

    base = task.get("base") or _default_base(repo)
    wt.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", str(wt), "-b", branch, base],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise WorkerError(f"git worktree add failed: {r.stderr.strip()}")

    _copy_worktree_includes(repo, wt)
    return wt, branch


def _default_base(repo: Path) -> str:
    for ref in ("main", "master"):
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", ref],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return ref
    return "HEAD"


def _copy_worktree_includes(repo: Path, wt: Path) -> None:
    """Carry gitignored local config into the worktree.

    Claude Code does this for worktrees it creates itself; ours are plain git
    worktrees, so we do it here.
    """
    spec = repo / ".worktreeinclude"
    if not spec.exists():
        return
    for line in spec.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for src in repo.glob(line):
            if src.is_file():
                dst = wt / src.relative_to(repo)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())


# --- launch -----------------------------------------------------------------

def build_env(repo: Path, company_root: Path, task: dict, actor: str,
              worktree: Path) -> dict:
    """Build the worker's environment.

    COMPANY_REPO is the *worktree*, not the main checkout: the worker's whole
    world is its worktree, so owned globs like `api/approvals/**` must resolve
    against it. Pointing this at the main checkout makes every path look like
    `.company/worktrees/TASK-101/api/...` and blocks the worker from its own
    files.
    """
    env = dict(os.environ)

    # An ANTHROPIC_API_KEY in the environment silently takes precedence over the
    # claude.ai login. Verified on this machine: with it set, `claude -p` returns
    # terminal_reason "api_error" with zero tokens consumed. Workers must use the
    # subscription session, so it is stripped rather than trusted.
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)

    # Don't let the parent session's identity leak into the worker.
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
                "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(var, None)

    env.update({
        "COMPANY_TASK": task["id"],
        "COMPANY_ACTOR": actor,
        "COMPANY_ROOT": str(company_root),
        "COMPANY_REPO": str(worktree),
        "COMPANY_MAIN_REPO": str(repo),
        "COMPANY_PROJECT": task.get("project", ""),
        "PATH": f"{PLUGIN_ROOT / 'bin'}:{env.get('PATH', '')}",
    })
    return env


def build_command(task: dict, role: str) -> list[str]:
    return [
        "claude", "-p",
        # --agent is what makes this affordable. The agent file's `tools:` list
        # removes every other tool DEFINITION from context, not just permission
        # to call it. Measured on this machine: 36,151 tokens of base context
        # with no agent, 6,016 with a six-tool agent — and that difference is
        # re-read on every single turn.
        "--agent", role,
        "--plugin-dir", str(PLUGIN_ROOT),
        # Workers never call MCP tools, and their schemas are pure overhead.
        # Worth ~300 tokens/turn on top of the agent restriction.
        "--strict-mcp-config",
        "--output-format", "json",
        "--json-schema", json.dumps(RESULT_SCHEMA),
        "--permission-mode", "acceptEdits",
        "--allowedTools", ROLE_TOOLS.get(role, "Read,Grep,Glob,Bash"),
    ]


def live_worker_on(company_root: Path, task_id: str) -> str | None:
    """Another worker already in this task's worktree, if any.

    Two workers in one worktree overwrite each other's edits and produce a diff
    neither of them intended. Detached launches make this easy to do by accident,
    so it is checked rather than trusted.
    """
    import json as _json
    workers = Path(company_root) / "state" / "workers"
    if not workers.is_dir():
        return None
    for pidfile in sorted(workers.glob("*/pid")):
        try:
            pid = int(pidfile.read_text().strip())
        except (ValueError, OSError):
            continue
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            continue
        started = pidfile.parent / "started_task"
        if started.exists() and started.read_text().strip() == task_id:
            return pidfile.parent.name
    return None


def launch(repo: Path, company_root: Path, task: dict, packet: str,
           role: str, actor: str, timeout: int = 1800) -> dict:
    """Run one Tier-2 worker to completion. Returns a result record."""
    busy = live_worker_on(company_root, task["id"])
    if busy and busy != actor:
        raise WorkerError(
            f"{busy} is already working in {task['id']}'s worktree. Two workers in "
            f"one worktree overwrite each other. Wait for it, or `company stop`."
        )
    log = EventLog(company_root)
    wt, branch = ensure_worktree(repo, company_root, task)

    state = company_root / "state" / "workers" / actor
    state.mkdir(parents=True, exist_ok=True)
    out_path, err_path = state / "stdout.json", state / "stderr.log"

    log.append(make_event(
        event="WORKER_STARTED", actor=actor, project=task.get("project", ""),
        task=task["id"],
        data={"role": role, "tier": 2, "branch": branch, "worktree": str(wt),
              "timeout_s": timeout},
    ))

    started = time.monotonic()
    with open(out_path, "w") as out, open(err_path, "w") as err:
        proc = subprocess.Popen(
            build_command(task, role), cwd=str(wt),
            env=build_env(repo, company_root, task, actor, wt),
            stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
        )
        (state / "pid").write_text(str(proc.pid))
        (state / "started_task").write_text(task["id"])
        try:
            # The packet is the worker's entire context. Closing stdin matters:
            # a `claude -p` process with an inherited open stdin blocks forever
            # waiting for EOF instead of running the prompt.
            proc.communicate(input=packet, timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            # SIGTERM, not SIGKILL: it aborts the turn cleanly, tears down the
            # child process tree, and still runs SessionEnd hooks (exit 143).
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
            timed_out = True

    elapsed = round(time.monotonic() - started, 1)
    result = _read_result(out_path)
    session_id = result.get("session_id")
    if session_id:
        (state / "session_id").write_text(session_id)

    log.append(make_event(
        event="WORKER_EXITED", actor=actor, project=task.get("project", ""),
        task=task["id"],
        data={"exit_code": proc.returncode, "timed_out": timed_out,
              "elapsed_s": elapsed, "session_id": session_id,
              "is_error": result.get("is_error"),
              "terminal_reason": result.get("terminal_reason"),
              # On a Claude subscription no dollars are charged for these runs;
              # what is actually consumed is tokens against the plan's limits.
              # `total_cost_usd` is Claude Code's client-side estimate of what
              # the same work would have cost through the API, so it is recorded
              # as an estimate and never presented as a bill.
              "cost_usd_estimate": result.get("total_cost_usd"),
              "tokens": _usage(result)},
    ))

    if timed_out:
        log.append(make_event(
            event="TASK_FAILED", actor=actor, project=task.get("project", ""),
            task=task["id"],
            data={"reason": f"wall-clock timeout after {timeout}s",
                  "worktree_preserved": str(wt)},
        ))

    return {
        "actor": actor, "task": task["id"], "role": role, "branch": branch,
        "worktree": str(wt), "exit_code": proc.returncode, "timed_out": timed_out,
        "elapsed_s": elapsed, "session_id": session_id,
        "is_error": result.get("is_error"),
        "structured_output": result.get("structured_output"),
        "stdout": str(out_path), "stderr": str(err_path),
    }


def _usage(result: dict) -> dict:
    """Token consumption — the thing a subscription actually meters.

    Cache reads usually dwarf output tokens, because a non-bare worker re-reads
    its cached context every turn. That is the number to watch when runs start
    hitting plan limits, not the dollar estimate.
    """
    u = result.get("usage") or {}
    return {
        "output": u.get("output_tokens") or 0,
        "input": u.get("input_tokens") or 0,
        "cache_read": u.get("cache_read_input_tokens") or 0,
        "cache_creation": u.get("cache_creation_input_tokens") or 0,
    }


def _read_result(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
        start = raw.find("{")
        return json.loads(raw[start:]) if start >= 0 else {}
    except (OSError, json.JSONDecodeError):
        return {}


def launch_readonly(repo: Path, company_root: Path, project: str, packet: str,
                    role: str, actor: str, timeout: int = 900) -> dict:
    """Run an advisory officer against the repo itself.

    No worktree and no branch: advisors read, they never write. They are also
    not bound to a task, so the ownership hook stays inert — which is safe here
    only because their agent files disallow Write and Edit outright.
    """
    log = EventLog(company_root)
    state = company_root / "state" / "workers" / actor
    state.mkdir(parents=True, exist_ok=True)
    out_path, err_path = state / "stdout.json", state / "stderr.log"

    log.append(make_event(
        event="WORKER_STARTED", actor=actor, project=project,
        data={"role": role, "tier": 1, "readonly": True, "timeout_s": timeout}))

    env = build_env(repo, company_root, {"id": "", "project": project}, actor, repo)
    env.pop("COMPANY_TASK", None)   # not task-scoped; nothing to own

    cmd = [
        "claude", "-p",
        "--agent", role,
        "--plugin-dir", str(PLUGIN_ROOT),
        "--strict-mcp-config",
        "--output-format", "json",
        "--permission-mode", "acceptEdits",
        "--allowedTools", "Read,Grep,Glob,Bash",
    ]

    started = time.monotonic()
    with open(out_path, "w") as out, open(err_path, "w") as err:
        proc = subprocess.Popen(cmd, cwd=str(repo), env=env, stdin=subprocess.PIPE,
                                stdout=out, stderr=err, text=True)
        (state / "pid").write_text(str(proc.pid))
        try:
            proc.communicate(input=packet, timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
            timed_out = True

    elapsed = round(time.monotonic() - started, 1)
    result = _read_result(out_path)
    log.append(make_event(
        event="WORKER_EXITED", actor=actor, project=project,
        data={"exit_code": proc.returncode, "timed_out": timed_out,
              "elapsed_s": elapsed, "readonly": True,
              "session_id": result.get("session_id"),
              "cost_usd_estimate": result.get("total_cost_usd"),
              "tokens": _usage(result)}))

    return {"actor": actor, "role": role, "exit_code": proc.returncode,
            "timed_out": timed_out, "elapsed_s": elapsed,
            "stdout": str(out_path), "stderr": str(err_path)}


def stop_all(company_root: Path, project: str | None = None) -> list[dict]:
    """`company stop` — halt every worker, preserve every worktree."""
    stopped = []
    workers = company_root / "state" / "workers"
    if not workers.is_dir():
        return stopped
    for pidfile in sorted(workers.glob("*/pid")):
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            stopped.append({"actor": pidfile.parent.name, "pid": pid, "signal": "TERM"})
        except (ValueError, OSError, ProcessLookupError):
            continue
    return stopped
