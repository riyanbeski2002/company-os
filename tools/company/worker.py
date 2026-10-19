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
import harness
import staffing

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

# Deliberately narrower than the matching agent/*.md `tools:` line, which also
# lists ListAgents/SendMessage for the interactive-tmux-pane case (see
# agents/company-pm.md, "Coordinating with other sessions"). A headless run
# has nobody watching to receive a ping and no legitimate reason to reach
# outside its own worktree, so this dict — not the frontmatter — is what
# `--allowedTools` is actually built from below, and it stays fixed at the
# original six-or-fewer tools. Keep it that way; widening this dict is a real
# increase in a headless worker's reach, not just a documentation update.
ROLE_TOOLS = {
    "backend-engineer": "Read,Grep,Glob,Edit,Write,Bash",
    "frontend-engineer": "Read,Grep,Glob,Edit,Write,Bash",
    "video-editor": "Read,Grep,Glob,Edit,Write,Bash",
    "code-reviewer": "Read,Grep,Glob,Bash",
    "qa-engineer": "Read,Grep,Glob,Bash",
    "security-reviewer": "Read,Grep,Glob,Bash",
}

# KNOWN_ISSUES #3: security-reviewer-201 ran 11 clean turns and emitted
# neither SECURITY_REVIEW_PASSED nor SECURITY_REVIEW_FAILED. The gate was
# silently re-run under a new actor name, paying for the review twice — a
# reviewer ending cleanly with no verdict looked identical to success. The
# fix below makes that impossible to miss: if a gate role's worker exits
# without a matching verdict event, that is GATE_NO_VERDICT, not "done."
GATE_VERDICT_EVENTS = {
    "code-reviewer": ("REVIEW_PASSED", "REVIEW_FAILED"),
    "qa-engineer": ("QA_PASSED", "QA_FAILED"),
    "security-reviewer": ("SECURITY_REVIEW_PASSED", "SECURITY_REVIEW_FAILED"),
}


class WorkerError(RuntimeError):
    pass


def gave_no_verdict(events: list[dict], task_id: str, actor: str, role: str) -> tuple | None:
    """None if the actor emitted its gate's verdict on this task; otherwise
    the (pass_event, fail_event) pair it was expected to emit. Pure and
    testable on purpose — the launch() call site can't be unit-tested without
    a real subprocess, this can."""
    pair = GATE_VERDICT_EVENTS.get(role)
    if not pair:
        return None
    pass_ev, fail_ev = pair
    for ev in events:
        if ev.get("task") == task_id and ev.get("actor") == actor \
                and ev.get("event") in (pass_ev, fail_ev):
            return None
    return pair


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
    _link_loaded_skills(repo, wt)
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


def _link_loaded_skills(repo: Path, wt: Path) -> None:
    """Carry currently-`load`ed capability skills (tools/capability.py) into
    the worktree, same reasoning as _copy_worktree_includes: Claude Code's own
    skill-discovery scans the *worktree's* skills/, not the main checkout's,
    so a worker otherwise can't see a skill loaded in the main checkout even
    though it CAN already read anything under external/ (that's resolved via
    $CLAUDE_PLUGIN_ROOT, which always points at the main checkout regardless
    of worktree — see agents/company-pm.md).

    skills/<id> entries created by `capability.py load` are symlinks into
    external/<id>/... (itself gitignored, main-checkout-only); we recreate
    the same symlink, pointing at the *main repo's* absolute path, so the
    worktree doesn't need its own external/ clone.
    """
    src_skills = repo / "skills"
    if not src_skills.is_dir():
        return
    dst_skills = wt / "skills"
    for entry in src_skills.iterdir():
        if not entry.is_symlink():
            continue  # vendored real skills (e.g. skills/claudedesignskills/) are
                      # tracked in git and already present via the worktree checkout
        target = entry.resolve()
        dst = dst_skills / entry.name
        if dst.exists() or dst.is_symlink():
            continue
        dst_skills.mkdir(parents=True, exist_ok=True)
        dst.symlink_to(target)


# --- launch -----------------------------------------------------------------

def build_env(repo: Path, company_root: Path, task: dict, actor: str,
              worktree: Path, thinking: bool = True,
              harness_spec: dict | None = None) -> dict:
    """Build the worker's environment.

    COMPANY_REPO is the *worktree*, not the main checkout: the worker's whole
    world is its worktree, so owned globs like `api/approvals/**` must resolve
    against it. Pointing this at the main checkout makes every path look like
    `.company/worktrees/TASK-101/api/...` and blocks the worker from its own
    files.

    Vendor-specific env stripping (a stale ANTHROPIC_API_KEY silently
    overriding the claude.ai login, the parent session's own identity
    leaking into the child) is the harness's own policy now, not hardcoded
    here — see config/harness.yaml's `strip_env`. A harness_spec of None
    resolves the configured default, so existing callers that built env
    before a role/harness was known keep working unchanged.
    """
    env = dict(os.environ)
    spec = harness_spec or harness.resolve(harness.load_config(company_root), None)
    env = harness.apply_env(spec, env)

    env.update({
        "COMPANY_TASK": task["id"],
        "COMPANY_ACTOR": actor,
        "COMPANY_ROOT": str(company_root),
        "COMPANY_REPO": str(worktree),
        "COMPANY_MAIN_REPO": str(repo),
        "COMPANY_PROJECT": task.get("project", ""),
        "PATH": f"{PLUGIN_ROOT / 'bin'}:{env.get('PATH', '')}",
    })
    if not thinking:
        # No CLI flag for thinking exists (checked `claude -p --help`,
        # v2.1.239) — MAX_THINKING_TOKENS=0 is the actual lever, reserved for
        # mechanical, ungated work where thinking is pure cost (D11 / §2,
        # efficiency addendum v1).
        env["MAX_THINKING_TOKENS"] = "0"
    return env


def build_command(task: dict, role: str, model: str | None = None,
                   effort: str | None = None, skip_permissions: bool = False,
                   harness_spec: dict | None = None, company_root: Path | None = None) -> list[str]:
    """Fill the role's configured harness command template (config/harness.yaml).

    Model/effort come from staffing.yaml's tier policy (D11), not a default —
    switching either mid-task busts the prompt cache and re-prefills the
    whole conversation at full price, so this is set once at launch and never
    changed by a running worker. skip_permissions exists only for ESC-009
    (2026-10-17: Claude Code's own sensitive-file prompt blocks headless
    writes under .company/worktrees/<TASK>/ even with --permission-mode
    acceptEdits) — the ownership hook and protect_branches.py still fully
    constrain what a worker can touch; this only removes Claude Code's own
    extra prompt on top of them, and a harness without that flag configured
    just ignores the request.
    """
    spec = harness_spec or harness.resolve(harness.load_config(company_root or PLUGIN_ROOT), role)
    return harness.build_command(
        spec, role=role, plugin_root=PLUGIN_ROOT,
        allowed_tools=ROLE_TOOLS.get(role, "Read,Grep,Glob,Bash"),
        schema=RESULT_SCHEMA, model=model, effort=effort,
        skip_permissions=skip_permissions,
    )


CLAIM_STALE_AFTER_S = 7200  # comfortably above any real launch timeout — a
# claim older than this without being released means its owning process died
# without ever reaching launch()'s `finally` (a hard kill), not that it lost
# a fair race to a concurrent competitor.


def claim_task(company_root: Path, task_id: str, actor: str) -> bool:
    """Atomically claim a task before launching, closing the race
    `live_worker_on` alone cannot.

    KNOWN_ISSUES #2: two `launch()` calls issued close together both read the
    filesystem (via live_worker_on) before either had written its own pid/
    started_task marker, so both observed "no live worker" and both
    proceeded — TASK-202 was implemented four times concurrently, 26.5% of a
    project's total tokens for a task whose merged diff was 101 lines. A
    check-then-act read is not a lock; `os.open(..., O_CREAT | O_EXCL)` is —
    the OS guarantees only one caller ever succeeds at creating the same path.

    First draft of this fix reclaimed a contested claim whenever
    live_worker_on found nothing live yet — which is exactly the state BOTH
    racing callers see while either is still mid-launch (neither has written
    its pid file), so the loser would immediately steal the winner's claim
    and reproduce the original bug. Age is the signal that's actually safe:
    a fresh claim might belong to a genuine concurrent competitor and must
    never be stolen; only a claim old enough that no real launch could still
    be legitimately holding it gets reclaimed.
    """
    live = live_worker_on(company_root, task_id)
    if live and live != actor:
        return False  # a fully-running worker (its own claim already released)

    claims = Path(company_root) / "state" / "claims"
    claims.mkdir(parents=True, exist_ok=True)
    claim_path = claims / f"{task_id}.claim"

    try:
        fd = os.open(str(claim_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, actor.encode())
        os.close(fd)
        return True
    except FileExistsError:
        pass

    holder = claim_path.read_text(encoding="utf-8").strip()
    if holder == actor:
        return True  # the same worker resuming its own claim, not a collision

    age = time.time() - claim_path.stat().st_mtime
    if age < CLAIM_STALE_AFTER_S:
        return False  # could be a genuine concurrent competitor — never steal it
    claim_path.write_text(actor, encoding="utf-8")  # leaked by a hard-killed process
    return True


def release_claim(company_root: Path, task_id: str) -> None:
    claim_path = Path(company_root) / "state" / "claims" / f"{task_id}.claim"
    claim_path.unlink(missing_ok=True)


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
           role: str, actor: str, timeout: int = 1800,
           model_override: str | None = None, effort_override: str | None = None,
           override_reason: str | None = None, skip_permissions: bool = False) -> dict:
    """Run one Tier-2 worker to completion. Returns a result record.

    model_override/effort_override replace staffing.yaml's tier policy for
    this one launch only — never persisted, never changes the policy for any
    other task. Per D11, escalating above policy needs a recorded reason;
    override_reason is required whenever either override is set and is
    written into WORKER_STARTED so the escalation is visible in the event
    log, not a silent one-off.

    Also refuses to start at all if this exact task has an open, blocking
    escalation (donor review, 2026-10-19 — real incident: VIDEO-LAUNCH-01
    was relaunched three times against the same unresolved environment
    blocker, ESC-009, each relaunch paying to reproduce the same failure
    with no new information). override_reason lets a caller who has
    confirmed the blocker is actually clear proceed anyway without first
    formally resolving the escalation — same discipline as the model/effort
    override above, not a separate mechanism.
    """
    if (model_override or effort_override or skip_permissions) and not override_reason:
        raise WorkerError(
            "model/effort/skip-permissions override requires --why (the reason is "
            "recorded in WORKER_STARTED, per D11's escalation-needs-a-reason discipline)")
    import escalations
    blocker = escalations.blocking_escalation_for_task(EventLog(company_root).read(), task["id"])
    if blocker and not override_reason:
        raise WorkerError(
            f"{blocker['id']} is an open, blocking escalation on {task['id']!r} "
            f"({blocker.get('need')!r}) — relaunching against the same unresolved "
            f"blocker just pays to reproduce the same failure. Resolve it first "
            f"(`company resolve {blocker['id']}`), or pass --why if you've confirmed "
            f"the blocker is actually clear and want to proceed without formally "
            f"resolving it yet."
        )
    if not claim_task(company_root, task["id"], actor):
        busy = live_worker_on(company_root, task["id"]) or "another worker"
        raise WorkerError(
            f"{busy} is already working in {task['id']}'s worktree. Two workers in "
            f"one worktree overwrite each other. Wait for it, or `company stop`."
        )
    try:
        log = EventLog(company_root)
        wt, branch = ensure_worktree(repo, company_root, task)

        state = company_root / "state" / "workers" / actor
        state.mkdir(parents=True, exist_ok=True)
        out_path, err_path = state / "stdout.json", state / "stderr.log"

        policy_cfg = staffing.load_config(company_root, "staffing.yaml")
        policy = dict(staffing.model_policy(policy_cfg, tier=2, gated=bool(task.get("gates")), role=role))
        if model_override:
            policy["model"] = model_override
        if effort_override:
            policy["effort"] = effort_override

        harness_spec = harness.resolve(harness.load_config(company_root), role)

        event_data = {"role": role, "tier": 2, "branch": branch, "worktree": str(wt),
                      "timeout_s": timeout, "model": policy.get("model"),
                      "effort": policy.get("effort"), "harness": harness_spec["_name"]}
        if model_override or effort_override or skip_permissions:
            event_data["policy_override"] = {
                "reason": override_reason,
                "model_override": model_override, "effort_override": effort_override,
                "skip_permissions": skip_permissions,
            }
        log.append(make_event(
            event="WORKER_STARTED", actor=actor, project=task.get("project", ""),
            task=task["id"], data=event_data,
        ))

        # A harness without Claude Code's own `--agent` persona loader never
        # sees agents/<role>.md at all, so its body has to travel in the
        # packet instead — the default `claude` harness skips this (it would
        # otherwise load the same persona twice, once natively and once
        # inline).
        worker_input = packet
        if not harness_spec.get("native_agent_loading"):
            worker_input = harness.load_persona(PLUGIN_ROOT, role) + "\n\n---\n\n" + packet

        started = time.monotonic()
        with open(out_path, "w") as out, open(err_path, "w") as err:
            proc = subprocess.Popen(
                build_command(task, role, model=policy.get("model"), effort=policy.get("effort"),
                              skip_permissions=skip_permissions, harness_spec=harness_spec),
                cwd=str(wt),
                env=build_env(repo, company_root, task, actor, wt,
                              thinking=bool(policy.get("thinking", True)), harness_spec=harness_spec),
                stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
            )
            (state / "pid").write_text(str(proc.pid))
            (state / "started_task").write_text(task["id"])
            # The pid + started_task markers above are now on disk, which is
            # what live_worker_on's ongoing liveness check relies on — the
            # claim's only job was covering the window before this point, so
            # it can be released now rather than held for the worker's whole
            # runtime (the `finally` below covers the failure paths too).
            release_claim(company_root, task["id"])
            try:
                # The packet is the worker's entire context. Closing stdin
                # matters: a process with an inherited open stdin blocks
                # forever waiting for EOF instead of running the prompt.
                proc.communicate(input=worker_input, timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                # SIGTERM, not SIGKILL: it aborts the turn cleanly, tears down
                # the child process tree, and still runs SessionEnd hooks
                # (exit 143).
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
                  # On a Claude subscription no dollars are charged for these
                  # runs; what is actually consumed is tokens against the
                  # plan's limits. `total_cost_usd` is Claude Code's client-
                  # side estimate of what the same work would have cost
                  # through the API, so it is recorded as an estimate and
                  # never presented as a bill.
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
        elif role in GATE_VERDICT_EVENTS:
            expected = gave_no_verdict(log.read(), task["id"], actor, role)
            if expected:
                log.append(make_event(
                    event="GATE_NO_VERDICT", actor=actor, project=task.get("project", ""),
                    task=task["id"],
                    data={"role": role, "expected_one_of": list(expected),
                          "exit_code": proc.returncode, "is_error": result.get("is_error"),
                          "terminal_reason": result.get("terminal_reason")},
                ))

        return {
            "actor": actor, "task": task["id"], "role": role, "branch": branch,
            "worktree": str(wt), "exit_code": proc.returncode, "timed_out": timed_out,
            "elapsed_s": elapsed, "session_id": session_id,
            "is_error": result.get("is_error"),
            "structured_output": result.get("structured_output"),
            "stdout": str(out_path), "stderr": str(err_path),
        }
    finally:
        # Covers every early-exit path above (ensure_worktree raising, etc.)
        # that never reached the release call in the normal path.
        release_claim(company_root, task["id"])


def launch_group(repo: Path, company_root: Path, group_id: str, tasks: list[dict],
                 worktree: Path, packet: str, role: str, actor: str, project: str,
                 timeout: int = 1800) -> dict:
    """Run one gate launch against a combined worktree covering several
    tasks (efficiency addendum v1, 2026-08-24 — grouped gating). Structurally
    `launch()`, minus per-task worktree creation (the caller already built
    the group's combined worktree via `gategroup.build_group_review`) and
    with the post-exit verdict check applied to EVERY task in the group, not
    one — a task that didn't get its own verdict event is GATE_NO_VERDICT,
    same as a solo gate, never silently covered by a sibling's review.
    """
    # Per-role claim (2026-09-09), matching gategroup's per-role worktree and
    # branch. Keyed on group_id alone, this claim re-serialized the three gate
    # roles even after their worktrees stopped colliding: the second role was
    # refused outright rather than running alongside the first. Review, qa and
    # security are independent read-only judgments of the same merge, so the
    # thing that must not run twice is one ROLE on one group, not the group.
    claim_id = f"gate-group-{group_id}-{role}"
    if not claim_task(company_root, claim_id, actor):
        busy = live_worker_on(company_root, claim_id) or "another worker"
        raise WorkerError(
            f"{busy} is already running the {role} gate on group {group_id!r}. "
            f"Wait for it, or `company stop`."
        )
    try:
        log = EventLog(company_root)
        state = company_root / "state" / "workers" / actor
        state.mkdir(parents=True, exist_ok=True)
        out_path, err_path = state / "stdout.json", state / "stderr.log"

        policy_cfg = staffing.load_config(company_root, "staffing.yaml")
        policy = staffing.model_policy(policy_cfg, tier=2, gated=True, role=role)
        task_ids = [t["id"] for t in tasks]
        harness_spec = harness.resolve(harness.load_config(company_root), role)

        log.append(make_event(
            event="WORKER_STARTED", actor=actor, project=project,
            data={"role": role, "tier": 2, "gate_group": group_id, "tasks": task_ids,
                  "worktree": str(worktree), "timeout_s": timeout,
                  "model": policy.get("model"), "effort": policy.get("effort"),
                  "harness": harness_spec["_name"]},
        ))

        env = build_env(repo, company_root, {"id": "", "project": project}, actor,
                        worktree, thinking=bool(policy.get("thinking", True)), harness_spec=harness_spec)
        env.pop("COMPANY_TASK", None)  # no single task — the worker cites task ids itself

        worker_input = packet
        if not harness_spec.get("native_agent_loading"):
            worker_input = harness.load_persona(PLUGIN_ROOT, role) + "\n\n---\n\n" + packet

        started = time.monotonic()
        with open(out_path, "w") as out, open(err_path, "w") as err:
            proc = subprocess.Popen(
                build_command({"id": claim_id}, role, model=policy.get("model"),
                              effort=policy.get("effort"), harness_spec=harness_spec),
                cwd=str(worktree), env=env,
                stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
            )
            (state / "pid").write_text(str(proc.pid))
            (state / "started_task").write_text(claim_id)
            release_claim(company_root, claim_id)
            try:
                proc.communicate(input=worker_input, timeout=timeout)
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
        session_id = result.get("session_id")
        if session_id:
            (state / "session_id").write_text(session_id)

        log.append(make_event(
            event="WORKER_EXITED", actor=actor, project=project,
            data={"gate_group": group_id, "tasks": task_ids,
                  "exit_code": proc.returncode, "timed_out": timed_out,
                  "elapsed_s": elapsed, "session_id": session_id,
                  "is_error": result.get("is_error"),
                  "terminal_reason": result.get("terminal_reason"),
                  "cost_usd_estimate": result.get("total_cost_usd"),
                  "tokens": _usage(result)},
        ))

        missing_verdict = []
        if role in GATE_VERDICT_EVENTS:
            current = log.read()
            for t in tasks:
                expected = gave_no_verdict(current, t["id"], actor, role)
                if expected:
                    missing_verdict.append(t["id"])
                    log.append(make_event(
                        event="GATE_NO_VERDICT", actor=actor, project=project,
                        task=t["id"],
                        data={"role": role, "expected_one_of": list(expected),
                              "gate_group": group_id, "exit_code": proc.returncode,
                              "is_error": result.get("is_error"),
                              "terminal_reason": result.get("terminal_reason")},
                    ))

        return {
            "actor": actor, "gate_group": group_id, "tasks": task_ids, "role": role,
            "worktree": str(worktree), "exit_code": proc.returncode, "timed_out": timed_out,
            "elapsed_s": elapsed, "session_id": session_id,
            "is_error": result.get("is_error"),
            "structured_output": result.get("structured_output"),
            "missing_verdict": missing_verdict,
            "stdout": str(out_path), "stderr": str(err_path),
        }
    finally:
        release_claim(company_root, claim_id)


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

    policy_cfg = staffing.load_config(company_root, "staffing.yaml")
    policy = staffing.model_policy(policy_cfg, tier=1, gated=False, role=role)
    harness_spec = harness.resolve(harness.load_config(company_root), role)

    log.append(make_event(
        event="WORKER_STARTED", actor=actor, project=project,
        data={"role": role, "tier": 1, "readonly": True, "timeout_s": timeout,
              "model": policy.get("model"), "effort": policy.get("effort"),
              "harness": harness_spec["_name"]}))

    env = build_env(repo, company_root, {"id": "", "project": project}, actor, repo,
                     thinking=bool(policy.get("thinking", True)), harness_spec=harness_spec)
    env.pop("COMPANY_TASK", None)   # not task-scoped; nothing to own

    cmd = harness.build_command(
        harness_spec, role=role, plugin_root=PLUGIN_ROOT,
        allowed_tools="Read,Grep,Glob,Bash", schema=None,
        model=policy.get("model"), effort=policy.get("effort"),
    )

    worker_input = packet
    if not harness_spec.get("native_agent_loading"):
        worker_input = harness.load_persona(PLUGIN_ROOT, role) + "\n\n---\n\n" + packet

    started = time.monotonic()
    with open(out_path, "w") as out, open(err_path, "w") as err:
        proc = subprocess.Popen(cmd, cwd=str(repo), env=env, stdin=subprocess.PIPE,
                                stdout=out, stderr=err, text=True)
        (state / "pid").write_text(str(proc.pid))
        try:
            proc.communicate(input=worker_input, timeout=timeout)
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


def pause_task(company_root: Path, task_id: str) -> dict | None:
    """`company pause <task>` — halt the one worker running `task_id`,
    leaving every other running worker untouched. The deliberate complement
    of `stop_all`'s "halt everything": useful now that several workers can
    run concurrently and stopping all of them to hold back one is real
    collateral damage (donor review, 2026-10-19 — paperclip distinguishes
    Stop/Pause/Cancel as separate actions; this is company-os's version,
    scoped to what's actually true here: SIGTERM and worktree preservation,
    same as `stop_all`, just aimed at one actor instead of every actor).

    Returns None if no live worker is running that task — same "nothing to
    do" signal `live_worker_on` already uses elsewhere, not an error.
    """
    workers = Path(company_root) / "state" / "workers"
    if not workers.is_dir():
        return None
    for pidfile in sorted(workers.glob("*/pid")):
        started = pidfile.parent / "started_task"
        if not started.exists() or started.read_text().strip() != task_id:
            continue
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            return {"actor": pidfile.parent.name, "pid": pid, "signal": "TERM", "task": task_id}
        except (ValueError, OSError, ProcessLookupError):
            return None
    return None
