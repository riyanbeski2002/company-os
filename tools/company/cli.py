#!/usr/bin/env python3
"""company — the only process that mutates Company OS state.

Every verb: JSON in, JSON out, meaningful exit codes, safe to call
concurrently. Workers see exactly two verbs: `event` and `handoff`.

Exit codes:
  0  ok
  1  usage / environment error
  2  evidence missing on an event (the log records facts, not claims)
  3  Evidence Rule refusal (an illegal state transition)
  4  replay mismatch (`rebuild --verify`)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eventlog import EventLog, EvidenceError, canonical, make_event  # noqa: E402
import taskstate  # noqa: E402

SCAFFOLD = [
    "config", "projects", "tasks", "handoffs", "decisions",
    "escalations", "events", "state/workers", "worktrees", "reports", "knowledge",
]


# --- environment ------------------------------------------------------------

def find_repo_root(start: Path | None = None) -> Path:
    """Locate the git repo root, refusing the two shapes that are never safe."""
    start = (start or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            root = candidate
            break
    else:
        die("not inside a git repository — Company OS requires one")

    if root == Path.home():
        die(
            f"refusing to operate on {root} — your home directory is itself a git "
            f"repository. A worktree operation here would be catastrophic. Run "
            f"Company OS inside a real project repo."
        )
    if _no_commits(root):
        die(
            f"refusing to operate on {root} — the repository has no commits, so "
            f"there is no base to branch task worktrees from. Make an initial "
            f"commit first."
        )
    return root


def _no_commits(root: Path) -> bool:
    import subprocess
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True,
    )
    return r.returncode != 0


def company_root(args) -> Path:
    if getattr(args, "root", None):
        return Path(args.root).resolve()
    env = os.environ.get("COMPANY_ROOT")
    if env:
        return Path(env).resolve()
    return find_repo_root() / ".company"


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def emit(obj, exit_code: int = 0):
    sys.stdout.write(canonical(obj))
    raise SystemExit(exit_code)


def _sole_project(root: Path) -> str | None:
    projects = sorted((root / "projects").glob("*.json"))
    return projects[0].stem if len(projects) == 1 else None


def load_project(root: Path, project: str | None) -> str:
    if project:
        return project
    env = os.environ.get("COMPANY_PROJECT")
    if env:
        return env
    sole = _sole_project(root)
    if sole:
        return sole
    die("--project is required (or set COMPANY_PROJECT)")


# --- verbs ------------------------------------------------------------------

def cmd_init(args):
    repo = find_repo_root()
    root = repo / ".company"
    for rel in SCAFFOLD:
        (root / rel).mkdir(parents=True, exist_ok=True)
    (root / "events" / "events.jsonl").touch(exist_ok=True)

    defaults = Path(__file__).resolve().parents[2] / "config"
    copied = []
    if defaults.is_dir():
        for src in sorted(defaults.glob("*.yaml")):
            dst = root / "config" / src.name
            if not dst.exists():
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                copied.append(dst.name)

    _ensure_line(repo / ".gitignore", ".company/worktrees/")
    _ensure_line(repo / ".gitignore", ".company/state/")
    _ensure_line(repo / ".worktreeinclude", ".env")
    _ensure_line(repo / ".worktreeinclude", ".env.local")

    emit({"ok": True, "repo": str(repo), "company_root": str(root),
          "configs_installed": copied})


def _ensure_line(path: Path, line: str):
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if line not in existing:
        with open(path, "a", encoding="utf-8") as fh:
            if existing and existing[-1].strip():
                fh.write("\n")
            fh.write(line + "\n")


LAUNCHER_ONLY_EVENTS = {"WORKER_STARTED", "WORKER_EXITED", "WORKER_HEARTBEAT"}
# Scoped tightly to the events the actor-role binding in taskstate.check_done
# actually trusts. TASK_CREATED/TASK_ASSIGNED/BASELINE_RECORDED are also only
# ever written in-process by staff/baseline today, but blocking them here too
# was broader than the vulnerability required and had a real cost: it broke
# an existing test's legitimate use of `company event ... TASK_CREATED` as
# fixture scaffolding. Widen this set only if a specific forgery of one of
# those event types is shown to defeat a real check, the same way this one did.


def cmd_event(args):
    """The worker-facing verb. Appends one event. Never mutates a task file.

    LAUNCHER_ONLY_EVENTS exist specifically so `check_done`'s actor-role
    binding (taskstate.py) has something a worker cannot forge: WORKER_STARTED
    is what proves an actor was actually launched as a given role on a given
    task. Before this check, a worker could `company event <task>
    WORKER_STARTED --data '{"role":"code-reviewer"}'` against itself and
    defeat that binding immediately — live-reproduced, see KNOWN_ISSUES.md.
    These event types are only ever written by worker.py's own in-process
    EventLog.append() call (the trusted launcher) or emit_exit.py's SessionEnd
    hook, never through this CLI verb.
    """
    root = company_root(args)
    if args.type in LAUNCHER_ONLY_EVENTS:
        die(f"{args.type!r} may only be recorded by the trusted launcher, "
           f"never by a worker's own `company event` call — that distinction "
           f"is what makes it trustworthy evidence.", 2)
    data = json.loads(args.data) if args.data else None
    evidence = None
    if args.evidence:
        evidence = args.evidence if isinstance(args.evidence, dict) else _parse_evidence(args.evidence)

    if args.type == "IMPLEMENTATION_READY" and evidence and evidence.get("commit"):
        reason = _reject_noop_diff(root, args.task, evidence["commit"])
        if reason:
            die(reason, 3)

    # $COMPANY_ACTOR is assigned by the launcher and OVERRIDES any --actor the
    # worker supplies. Identity is the hinge of the Evidence Rule: if a worker
    # could name itself, it could name itself "code-reviewer" and sign off on
    # its own change. A worker does not get to choose who it is.
    assigned = os.environ.get("COMPANY_ACTOR")
    if assigned and args.actor and args.actor != assigned:
        print(f"note: ignoring --actor {args.actor!r}; this worker is {assigned!r}",
              file=sys.stderr)

    ev = make_event(
        event=args.type,
        actor=assigned or args.actor or "unknown",
        project=load_project(root, args.project),
        task=args.task,
        data=data,
        evidence=evidence,
    )
    try:
        written = EventLog(root).append(ev)
    except EvidenceError as exc:
        die(str(exc), 2)
    except ValueError as exc:
        die(str(exc), 1)

    if not args.no_rebuild:
        taskstate.rebuild(root)
    emit({"ok": True, "seq": written["seq"], "event": written["event"],
          "task": written.get("task")})


def _parse_evidence(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    if len(raw) in (7, 8, 40) and all(c in "0123456789abcdef" for c in raw.lower()):
        return {"commit": raw}
    if raw.startswith("exit "):
        return {"exit_code": int(raw.split()[1])}
    return {"log": raw}


def _reject_noop_diff(root: Path, task_id: str, sha: str) -> str | None:
    """None if `sha` is a real commit ahead of the task's base ref; otherwise
    the reason IMPLEMENTATION_READY must be refused.

    Evidence Rule gap, live-reproduced on the finos repo 17 Aug: a Tier-2
    worker reported IMPLEMENTATION_READY with evidence {"tests": "exit 0",
    "diff": <sha>} where <sha> was the worktree's unmodified merge-base with
    main — zero commits, clean tree, tests trivially green because nothing
    had changed. `evidence.commit` being present and well-formed was treated
    as proof of work; it only proves a SHA was typed. `git rev-list --count
    base..sha` is what actually distinguishes a completed task from a no-op
    that self-reported completion, so it is checked here instead of trusted
    from the worker's own report.

    Only enforced when there is a real worktree to check against — a task
    with no recorded worktree, or one whose worktree was never actually
    checked out (most unit-test fixtures), has nothing this function can
    verify, and it is not this check's job to invent distrust of missing
    infrastructure.
    """
    p = taskstate.task_path(root, task_id)
    if not p.exists():
        return None  # no task view yet (e.g. IMPLEMENTATION_READY before rebuild) — nothing to compare against
    task = json.loads(p.read_text(encoding="utf-8"))

    worktree = Path(task.get("worktree") or (root / "worktrees" / task_id))
    if not (worktree / ".git").exists():
        return None  # not a real checkout — nothing to verify

    import subprocess
    import worker as worker_mod
    base = task.get("base") or worker_mod._default_base(root.parent)

    r = subprocess.run(
        ["git", "-C", str(worktree), "rev-list", "--count", f"{base}..{sha}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return (
            f"IMPLEMENTATION_READY refused: {sha!r} could not be verified against "
            f"{base!r} in {worktree} ({r.stderr.strip() or 'git rev-list failed'}) — "
            f"an unverifiable commit is not evidence."
        )
    if r.stdout.strip() == "0":
        return (
            f"IMPLEMENTATION_READY refused: {sha} is 0 commits ahead of {base!r} in "
            f"{worktree} — a worktree with no new commits is not completed work, no "
            f"matter what the test run reports."
        )
    return None


def cmd_rebuild(args):
    root = company_root(args)
    count, mismatches = taskstate.rebuild(root, verify=args.verify)
    if args.verify and mismatches:
        emit({"ok": False, "tasks": count, "mismatches": mismatches}, 4)
    emit({"ok": True, "tasks": count, "verified": bool(args.verify)})


def cmd_task_show(args):
    root = company_root(args)
    p = taskstate.task_path(root, args.id)
    if not p.exists():
        die(f"no such task {args.id!r} — run `company rebuild` if the log has it")
    emit(json.loads(p.read_text(encoding="utf-8")))


def cmd_task_advance(args):
    """The only mover of task state, and the enforcer of the Evidence Rule."""
    root = company_root(args)
    tasks = taskstate.fold(EventLog(root).read())
    task = tasks.get(args.id)
    if not task:
        die(f"no such task {args.id!r} in the event log")

    target = args.to.upper()
    if target not in taskstate.LIFECYCLE and target not in taskstate.OFF_PATH:
        die(f"{target!r} is not a lifecycle state")

    if target == "DONE":
        import baseline as baseline_mod
        import staffing
        base = baseline_mod.latest(EventLog(root).read(), task.get("project"))
        gate_roles = {g: spec["actor_role"]
                     for g, spec in staffing.load_config(root, "quality-gates.yaml")["gates"].items()}
        reasons = taskstate.check_done(task, base, gate_roles)
        if reasons:
            EventLog(root).append(make_event(
                event="TASK_BLOCKED", actor=args.actor or "company-cli",
                project=task["project"], task=args.id,
                data={"attempted_transition": "DONE", "reasons": reasons},
            ))
            taskstate.rebuild(root)
            emit({"ok": False, "task": args.id, "refused_transition": "DONE",
                  "reasons": reasons}, 3)

    EventLog(root).append(make_event(
        event="TASK_COMPLETED" if target == "DONE" else "STATUS_CHANGED",
        actor=args.actor or "company-cli", project=task["project"], task=args.id,
        data={"from": task["status"], "to": target},
    ))
    taskstate.rebuild(root)
    emit({"ok": True, "task": args.id, "from": task["status"], "to": target})


def cmd_handoff(args):
    """The second and last worker-facing verb."""
    root = company_root(args)
    tasks = taskstate.fold(EventLog(root).read())
    task = tasks.get(args.task) or die(f"no such task {args.task!r}")
    path = root / "handoffs" / f"{args.task}-{args.frm}-to-{args.to}.md"
    body = sys.stdin.read() if args.stdin else (args.body or "")
    if not body.strip():
        die("handoff body is empty — a handoff transfers results, so it needs content")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")

    EventLog(root).append(make_event(
        event="HANDOFF_WRITTEN",
        actor=args.actor or args.frm, project=task["project"], task=args.task,
        data={"to": args.to, "from": args.frm},
        evidence={"log": str(path.relative_to(root.parent))},
    ))
    taskstate.rebuild(root)
    emit({"ok": True, "handoff": str(path)})


def cmd_gates(args):
    """Deterministic gate lookup. The PM calls this; it cannot be argued with."""
    import staffing
    root = company_root(args)
    cfg = staffing.load_config(root, "risk-triggers.yaml")
    qg = staffing.load_config(root, "quality-gates.yaml")
    result = staffing.evaluate(cfg, args.request or "", args.paths or [],
                                files_touched=args.files_touched, diff_lines=args.diff_lines)
    result["gates"] = staffing.order_gates(result["gates"], qg)
    emit(result)


def cmd_plan(args):
    """Turn a proposed task graph into a staffing plan.

    The PM decomposes the request (that is judgment). This applies the risk
    table on top, forcing every mandatory gate onto every task whether the PM
    asked for it or not, and refuses to plan parallel work with overlapping
    file ownership.
    """
    import staffing
    root = company_root(args)
    cfg = staffing.load_config(root, "risk-triggers.yaml")
    qg = staffing.load_config(root, "quality-gates.yaml")

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8")) if args.spec \
        else json.loads(sys.stdin.read())
    project = spec.get("project") or die("plan spec needs a 'project'")
    request = spec.get("request", "")
    tasks = spec.get("tasks") or die("plan spec needs a non-empty 'tasks' list")

    planned, forced, unreasoned_escalations = [], [], []
    for task in tasks:
        verdict = staffing.evaluate(cfg, f"{request} {task.get('title', '')}",
                                    task.get("owned_globs"),
                                    files_touched=task.get("files_touched"),
                                    diff_lines=task.get("diff_lines"))
        mandatory = staffing.order_gates(verdict["gates"], qg)
        final, additions = staffing.reconcile(
            task.get("gates"), mandatory, task.get("gate_reason"))
        unrequested = [g for g in mandatory if g not in (task.get("gates") or [])]
        if unrequested:
            forced.append({"task": task["id"], "gates": unrequested,
                           "because": [t["trigger"] for t in verdict["triggers_fired"]]})

        # D9 (efficiency addendum v1): fast_path said this task's own numbers
        # (no trigger hit, diff in-bounds) belong at Tier 0, PM inline — yet
        # here it is anyway, staffed as Tier 2+. That is the same kind of
        # scope addition a gate the table didn't ask for is, and needs the
        # same recorded reason `reconcile()` already requires for those.
        if verdict["fast_path"] and int(task.get("tier") or 0) >= 1 and not task.get("tier_reason"):
            unreasoned_escalations.append({
                "task": task["id"], "tier": task.get("tier"),
                "predicted": {"files_touched": task.get("files_touched"),
                             "diff_lines": task.get("diff_lines")},
            })

        task = dict(task)
        task["gates"] = staffing.order_gates(final, qg)
        task["project"] = project
        task["triggers_fired"] = [t["trigger"] for t in verdict["triggers_fired"]]
        task["fast_path"] = verdict["fast_path"]
        if additions:
            task["gates_added_by_pm"] = additions
        planned.append(task)

    tier2 = [t for t in planned if t.get("tier") == 2]
    parallel = [t for t in tier2 if not t.get("depends_on")]
    collisions = staffing.predict_overlap(parallel)
    band = staffing.size_band(len(tier2))

    plan = {
        "project": project, "request": request, "tasks": planned,
        "staffing": band, "tier2_workers": len(tier2),
        "gates_forced_by_risk_table": forced,
        "predicted_file_overlap": collisions,
        "tier_escalations_without_reason": unreasoned_escalations,
    }

    if collisions and not args.allow_overlap:
        plan["ok"] = False
        plan["refusal"] = (
            "parallel tasks have overlapping file ownership — sequence them with "
            "depends_on, split the globs, or pass --allow-overlap"
        )
        emit(plan, 3)

    if unreasoned_escalations and not args.allow_tier_escalation:
        plan["ok"] = False
        plan["refusal"] = (
            "fast_path recommends Tier 0 for one or more tasks (no risk trigger, "
            "diff in-bounds) but they're staffed above it with no recorded reason — "
            "set 'tier_reason' on the task, or pass --allow-tier-escalation"
        )
        emit(plan, 3)

    (root / "projects").mkdir(parents=True, exist_ok=True)
    (root / "projects" / f"{project}.json").write_text(canonical(plan), encoding="utf-8")
    plan["ok"] = True
    emit(plan)


def cmd_staff(args):
    """Apply a plan: create tasks in the log and their worktrees on disk."""
    import worker as worker_mod
    root = company_root(args)
    repo = root.parent
    project = load_project(root, args.project)
    plan_file = root / "projects" / f"{project}.json"
    if not plan_file.exists():
        die(f"no plan for {project!r} — run `company plan` first")
    plan = json.loads(plan_file.read_text(encoding="utf-8"))

    log = EventLog(root)
    existing = taskstate.fold(log.read())
    staffed = []

    for task in plan["tasks"]:
        tid = task["id"]
        if tid in existing:
            staffed.append({"task": tid, "skipped": "already in the event log"})
            continue

        data = {k: v for k, v in task.items() if k not in ("id", "project")}
        if task.get("tier") == 2 and not data.get("branch"):
            data["branch"] = f"task/{tid.split('-')[-1]}-{worker_mod.slug(task.get('title', tid))}"
        log.append(make_event(event="TASK_CREATED", actor="company-pm",
                              project=project, task=tid, data=data))

        entry = {"task": tid, "tier": task.get("tier"), "gates": task.get("gates")}
        if task.get("tier") == 2:
            owner = task.get("owner") or f"{task.get('role', 'backend-engineer')}-{tid.split('-')[-1]}"
            log.append(make_event(event="TASK_ASSIGNED", actor="company-pm",
                                  project=project, task=tid,
                                  data={"owner": owner, "branch": data["branch"]}))
            view = taskstate.fold(log.read())[tid]
            try:
                wt, branch = worker_mod.ensure_worktree(repo, root, view)
                entry.update({"owner": owner, "branch": branch, "worktree": str(wt)})
            except worker_mod.WorkerError as exc:
                entry["error"] = str(exc)
        staffed.append(entry)

    taskstate.rebuild(root)
    emit({"ok": True, "project": project, "staffed": staffed})


GATE_ROLES = {"code-reviewer", "qa-engineer", "security-reviewer"}


def _diff_summary_for_gate(repo, root, task, role, worker_mod):
    """Hand a gate role the actual patch, not just a pointer to go find it
    (CFO audit + Riyan, 2026-08-24). Only computed for gate roles — the
    implementer's own first launch has nothing to diff yet, and calling this
    then would just be wasted git calls around an empty worktree.
    """
    if role not in GATE_ROLES:
        return None
    import gitutil
    wt, _branch = worker_mod.ensure_worktree(repo, root, task)
    base = task.get("base") or worker_mod._default_base(repo)
    return gitutil.diff_patch_or_stat(wt, base)


def cmd_run(args):
    """Launch a Tier-2 worker for one task and supervise it to completion."""
    import packet as packet_mod
    import worker as worker_mod

    root = company_root(args)
    repo = root.parent
    tasks = taskstate.fold(EventLog(root).read())
    task = tasks.get(args.task) or die(f"no such task {args.task!r} in the event log")

    contracts = _contracts_for(tasks, task)
    unmet = [d for d in (task.get("depends_on") or [])
             if tasks.get(d, {}).get("status") not in ("DONE", "INTEGRATION")
             and not any(c["task"] == d for c in contracts)]
    if unmet and not args.force:
        EventLog(root).append(make_event(
            event="DEPENDENCY_WAITING", actor=args.actor or task.get("owner", "pm"),
            project=task["project"], task=task["id"],
            data={"waiting_on": unmet,
                  "reason": "dependency has neither completed nor published a contract"},
        ))
        taskstate.rebuild(root)
        emit({"ok": False, "task": task["id"], "waiting_on": unmet,
              "hint": "let the dependency publish a CONTRACT_PUBLISHED event, or pass --force"}, 3)

    try:
        body = packet_mod.render(
            task, why=args.why or "Requested by the CEO.",
            diff_summary=_diff_summary_for_gate(repo, root, task, args.role, worker_mod),
            contracts=contracts, handoff_target=args.handoff_to,
            max_turns=args.max_turns, timeout_s=args.timeout,
            verify=verify_command(root, args.verify),
            baseline=_baseline(root, task.get("project")))
    except (packet_mod.PacketTooLarge, ValueError) as exc:
        die(str(exc), 1)

    if args.dry_run:
        emit({"ok": True, "task": task["id"], "dry_run": True,
              "packet_tokens": packet_mod.estimate_tokens(body), "packet": body})

    actor = args.actor or f"{args.role}-{task['id'].split('-')[-1]}"

    if args.detach:
        # A PM running as `claude -p` cannot outlive its own turn: Claude Code
        # kills background Bash tasks a few seconds after the turn's final
        # result. A worker launched from the PM's shell dies with it, mid-edit.
        # Detaching puts the supervisor in its own session so in-flight work
        # survives the turn that started it, and the PM polls `company status`.
        import subprocess
        argv = [sys.executable, str(Path(__file__).resolve()),
                "--root", str(root), "run", args.task, "--role", args.role,
                "--actor", actor, "--timeout", str(args.timeout)]
        if args.why:
            argv += ["--why", args.why]
        if args.force:
            argv += ["--force"]
        if args.max_concurrent:
            argv += ["--max-concurrent", str(args.max_concurrent)]

        state = root / "state" / "workers" / actor
        state.mkdir(parents=True, exist_ok=True)
        out = open(state / "detached.json", "w")
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True,
                                env={**os.environ, "COMPANY_PROJECT": task["project"]})
        emit({"ok": True, "detached": True, "task": task["id"], "actor": actor,
              "supervisor_pid": proc.pid, "result_file": str(state / "detached.json"),
              "note": "poll `company status`; the worker survives this turn ending"})

    import slots
    import staffing
    budgets = staffing.load_config(root, "budgets.yaml")
    cap = args.max_concurrent or budgets.get("max_concurrent_workers", 4)
    try:
        slot, queued_s = slots.acquire(
            root, actor, cap, timeout=budgets.get("queue_timeout_s", 1800))
    except slots.SlotTimeout as exc:
        die(str(exc), 1)

    if queued_s > 0:
        EventLog(root).append(make_event(
            event="DEPENDENCY_WAITING", actor=actor, project=task["project"],
            task=task["id"],
            data={"reason": "concurrency cap", "cap": cap, "queued_s": queued_s}))

    try:
        result = worker_mod.launch(repo, root, task, body, args.role, actor,
                                   timeout=args.timeout)
    except worker_mod.WorkerError as exc:
        slots.release(slot)
        die(str(exc), 1)
    finally:
        slots.release(slot)

    taskstate.rebuild(root)
    result["packet_tokens"] = packet_mod.estimate_tokens(body)
    result["queued_s"] = queued_s
    result["concurrency_cap"] = cap
    emit(result, 0 if not result.get("is_error") else 1)


def cmd_gate_group(args):
    """One gate launch covering several tasks that touch the same core,
    instead of one launch per task (Riyan, 2026-08-24 — efficiency addendum
    v1: 'not every task deserves its own gate... one review pass instead of
    3'). Does not weaken the Evidence Rule: every task in the group still
    needs its own verdict event, checked individually after the launch.

    v1 scope: a dependency chain / sequential group only. Tasks are merged
    into the review worktree in the order found (task-creation order, unless
    --tasks gives an explicit order) — this is NOT a topological merge of
    genuinely parallel siblings with disjoint history. A group whose tasks
    don't merge cleanly in that order refuses outright rather than guessing.
    """
    import worker as worker_mod
    import gategroup
    import packet as packet_mod

    root = company_root(args)
    repo = root.parent
    all_tasks = taskstate.fold(EventLog(root).read())

    group_tasks = [t for t in all_tasks.values() if t.get("gate_group") == args.group]
    if args.tasks:
        order = args.tasks
        by_id = {t["id"]: t for t in group_tasks}
        missing = [tid for tid in order if tid not in by_id]
        if missing:
            die(f"{missing} not found, or don't carry gate_group={args.group!r}", 1)
        group_tasks = [by_id[tid] for tid in order]
    if not group_tasks:
        die(f"no tasks found with gate_group={args.group!r}", 1)
    if len(group_tasks) < 2:
        die(f"gate_group={args.group!r} has only 1 task — run `company run` "
            f"directly, grouping is for 2+ tasks reviewed together", 1)

    projects = {t.get("project") for t in group_tasks}
    if len(projects) > 1:
        die(f"gate_group={args.group!r} spans multiple projects: {sorted(projects)}", 1)
    project = projects.pop()

    # Preflight: every task needs its own implementation + real test
    # evidence already — the gate-event reasons are expected here (that's
    # what this launch is about to satisfy) and filtered out.
    baseline = _baseline(root, project)
    blocking = []
    for t in group_tasks:
        reasons = [r for r in taskstate.check_done(t, baseline=baseline) if not r.startswith("gate ")]
        if reasons:
            blocking.append({"task": t["id"], "reasons": reasons})
    if blocking:
        emit({"ok": False, "group": args.group,
              "refusal": "not every task in this group is implementation-complete yet",
              "blocking": blocking}, 3)

    base = next((t.get("base") for t in group_tasks if t.get("base")), None) \
        or worker_mod._default_base(repo)

    try:
        wt = gategroup.build_group_review(repo, root, args.group, group_tasks, base)
    except gategroup.GroupMergeConflict as exc:
        EventLog(root).append(make_event(
            event="TASK_BLOCKED", actor=args.actor or "pm", project=project,
            task=exc.task_id,
            data={"stage": "gate_group_merge", "gate_group": args.group, "detail": exc.detail}))
        die(str(exc), 1)

    import gitutil
    diff_summary = gitutil.diff_patch_or_stat(wt, base)

    body = packet_mod.render_group(
        group_tasks, group_id=args.group,
        why=args.why or "Requested by the CEO.",
        diff_summary=diff_summary, verify=verify_command(root, args.verify),
        baseline=baseline, max_turns=args.max_turns, timeout_s=args.timeout)

    if args.dry_run:
        emit({"ok": True, "group": args.group, "dry_run": True,
              "tasks": [t["id"] for t in group_tasks],
              "packet_tokens": packet_mod.estimate_tokens(body), "packet": body})

    actor = args.actor or f"{args.role}-group-{args.group}"
    result = worker_mod.launch_group(repo, root, args.group, group_tasks, wt, body,
                                     args.role, actor, project, timeout=args.timeout)

    taskstate.rebuild(root)
    result["packet_tokens"] = packet_mod.estimate_tokens(body)
    emit(result, 0 if not result.get("is_error") and not result.get("missing_verdict") else 1)


def _contracts_for(tasks: dict, task: dict) -> list[dict]:
    out = []
    for dep in task.get("depends_on") or []:
        for name in (tasks.get(dep) or {}).get("contracts") or []:
            out.append({"task": dep, "name": name, "summary": f"published by {dep}"})
    return out


def _project_tasks(root: Path, project: str | None):
    tasks = list(taskstate.fold(EventLog(root).read()).values())
    if project:
        tasks = [t for t in tasks if t.get("project") == project]
    return tasks


def _baseline(root: Path, project: str | None = None) -> dict | None:
    import baseline as baseline_mod
    return baseline_mod.latest(EventLog(root).read(), project)


def _escalations(root: Path, project: str | None = None) -> list[dict]:
    """Open escalations, derived from the log — not from whatever files exist."""
    import escalations as esc_mod
    items = list(esc_mod.fold(EventLog(root).read()).values())
    if project:
        items = [e for e in items if e.get("project") == project]
    return sorted(items, key=lambda e: (not e.get("blocking"), e["id"]))


def cmd_status(args):
    import render
    root = company_root(args)
    project = args.project or os.environ.get("COMPANY_PROJECT")
    tasks = _project_tasks(root, project)
    events = EventLog(root).read()
    stalls = {**render.detect_stalls(root, tasks, events),
             **render.gates_with_no_verdict(events)}
    if args.json:
        emit({"project": project, "progress": render.project_progress(tasks),
              "tasks": tasks, "escalations": _escalations(root, project), "stalled": stalls})
    print(render.status(project or "all projects", tasks, _escalations(root, project), stalls))
    raise SystemExit(0)


def cmd_report(args):
    import render
    root = company_root(args)
    project = args.project or os.environ.get("COMPANY_PROJECT")
    tasks = _project_tasks(root, project)
    text = render.report(project or "all projects", tasks, _escalations(root, project))
    out = root / "reports" / f"{project or 'all'}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    raise SystemExit(0)


def cmd_integrate(args):
    import integrate as integrate_mod
    import staffing
    root = company_root(args)
    repo = root.parent
    tasks = taskstate.fold(EventLog(root).read())
    gate_roles = {g: spec["actor_role"]
                 for g, spec in staffing.load_config(root, "quality-gates.yaml")["gates"].items()}

    verify = verify_command(root, args.test_command)
    if not verify:
        die("no verify command — run `company detect --write` first", 1)

    targets = [args.task] if args.task else [
        t["id"] for t in tasks.values()
        if (t.get("evidence") or {}).get("diff")
        and not (t.get("evidence") or {}).get("merged")
    ]
    if not targets:
        emit({"ok": True, "merged": [], "note": "nothing ready to integrate"})

    results = []
    for tid in sorted(targets):
        task = tasks.get(tid) or die(f"no such task {tid!r}")
        reasons = taskstate.check_done(task, _baseline(root, task.get("project")), gate_roles)
        blocking = [r for r in reasons if "diff" in r or "test" in r or "self-certified" in r
                    or "not satisfied" in r]
        if blocking and not args.force:
            results.append({"task": tid, "merged": False,
                            "reason": "gates not satisfied", "detail": blocking})
            continue
        try:
            results.append(integrate_mod.integrate(
                repo, root, task, verify, actor=args.actor,
                baseline=_baseline(root, task.get("project"))))
        except RuntimeError as exc:
            results.append({"task": tid, "merged": False, "reason": str(exc)})

    taskstate.rebuild(root)
    ok = all(r.get("merged") for r in results)
    emit({"ok": ok, "results": results}, 0 if ok else 3)


def _project_config(root: Path) -> dict:
    import staffing
    try:
        return staffing.load_config(root, "project.yaml")
    except FileNotFoundError:
        return {}


def verify_command(root: Path, override: str | None = None) -> str | None:
    if override:
        return override
    return _project_config(root).get("verify")


def cmd_detect(args):
    """Identify the stack and the strongest available verify command."""
    import detect
    import yaml
    root = company_root(args)
    repo = root.parent
    result = detect.detect(repo)

    if args.write:
        cfg = root / "config" / "project.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        existing = _project_config(root)
        merged = {**existing,
                  "stack": result["stack"],
                  "default_branch": result["default_branch"],
                  "verify": existing.get("verify") or result["verify"],
                  "verify_strategy": result["verify_strategy"],
                  "verify_strength": result["verify_strength"],
                  # PUBLIC | INTERNAL | CONFIDENTIAL | SECRET. Governs what
                  # capability-curator may put in an external research query —
                  # see skills/capability-curator/SKILL.md. Defaults to the
                  # conservative middle tier; Riyan edits this file directly
                  # to change it, same as `verify`.
                  "data_classification": existing.get("data_classification", "INTERNAL")}
        cfg.write_text(yaml.safe_dump(merged, sort_keys=True), encoding="utf-8")
        result["written"] = str(cfg)
    emit(result)


def cmd_baseline(args):
    """Record how the repo behaves BEFORE any work, so 'no worse' is provable.

    Deliberately does NOT call `load_project` (and its `die` on zero projects):
    a baseline is a fact about the repo, not about a project's task graph, and
    it has to be recordable during onboarding — before `company plan` has ever
    run and before any `.company/projects/*.json` exists at all. Tagging it
    "unassigned" is honest; refusing to record it here would make the
    documented onboarding order (init, detect, baseline, doctor) impossible to
    complete on a repo with no history.
    """
    import baseline as baseline_mod
    root = company_root(args)
    repo = root.parent
    project = (args.project or os.environ.get("COMPANY_PROJECT")
              or _sole_project(root) or "unassigned")
    verify = verify_command(root, args.verify)
    if not verify:
        die("no verify command — run `company detect --write`, or pass --verify", 1)

    try:
        result = baseline_mod.record(root, repo, project=project, verify=verify,
                                     timeout=args.timeout)
    except baseline_mod.BaselineInProgress as exc:
        die(str(exc), 1)
    taskstate.rebuild(root)
    out = {k: v for k, v in result.items() if k != "output_tail"}
    if not result["green"]:
        out["note"] = (
            "This repo is RED before any work started. Tasks will be judged as "
            "'no worse than this', not 'green'. The pre-existing failures remain "
            "your problem — Company OS will not quietly adopt them as acceptable."
        )
    emit(out)


def cmd_doctor(args):
    """Preflight: is this repo safe to point Company OS at?"""
    import subprocess

    import detect
    root = company_root(args)
    repo = root.parent
    checks, problems = [], []

    def check(name, ok, detail, fatal=False):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok and fatal:
            problems.append(f"{name}: {detail}")

    check("git repo", (repo / ".git").exists(), str(repo), fatal=True)
    check("not $HOME", repo != Path.home(), str(repo), fatal=True)

    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    check("has commits", head.returncode == 0, head.stdout.strip()[:12] or "none",
          fatal=True)

    dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip().splitlines()
    check("working tree clean", not dirty,
          "clean" if not dirty else
          f"{len(dirty)} uncommitted paths — worktrees branch from a committed ref, "
          f"so this work will NOT be visible to workers and is at risk if you "
          f"later reset. Commit or stash before a run.")

    branch = subprocess.run(["git", "-C", str(repo), "branch", "--show-current"],
                            capture_output=True, text=True).stdout.strip()
    check("current branch", True, branch or "detached")

    # A local branch that is behind its upstream is a silent staffing hazard:
    # the PM reasons from files/history that look incomplete or stale (a merged
    # PR reads as an unbuilt stub, a schema migration that already landed reads
    # as missing) and either re-does finished work or misjudges what is safe to
    # build next. Caught live 2026-08-17 on ht-workspace: local main was one
    # merged PR behind origin/main; a "getProfile is still a stub" read was
    # wrong until `git pull --ff-only` caught it up. Fetch is read-only and
    # cheap; skip entirely if there is no upstream or no network.
    upstream = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        capture_output=True, text=True,
    ).stdout.strip()
    if upstream:
        fetch = subprocess.run(
            ["git", "-C", str(repo), "fetch", "--quiet"],
            capture_output=True, text=True, timeout=15,
        )
        if fetch.returncode == 0:
            counts = subprocess.run(
                ["git", "-C", str(repo), "rev-list", "--left-right", "--count",
                 f"HEAD...{upstream}"],
                capture_output=True, text=True,
            ).stdout.strip()
            ahead, behind = (counts.split() + ["0", "0"])[:2]
            check("up to date with remote", behind == "0",
                  "in sync" if behind == "0" else
                  f"local {branch or 'HEAD'} is {behind} commit(s) behind {upstream} — "
                  f"`git pull --ff-only` before reasoning about what's built or staffing "
                  f"work, or you will judge merged work as missing/stale.")
        else:
            check("up to date with remote", True,
                  "fetch failed/unreachable — skipped, not blocking")
    else:
        check("up to date with remote", True, "no upstream configured — skipped")

    spaces = [p for p in subprocess.run(
        ["git", "-C", str(repo), "ls-files"], capture_output=True, text=True
    ).stdout.splitlines() if " " in p]
    check("paths without spaces", not spaces,
          "ok" if not spaces else
          f"{len(spaces)} tracked paths contain spaces (e.g. {spaces[0]!r}). "
          f"Ownership globs and shell commands must quote them.")

    detected = detect.detect(repo)
    configured = verify_command(root)
    check("verify command", bool(configured or detected["verify"]),
          configured or detected["verify"] or
          "none found — the Evidence Rule cannot judge anything without one",
          fatal=True)
    if detected.get("verify_strength") == "syntax-only" and not configured:
        check("verify strength", False, detected["warning"])
    check("company initialised", (root / "events" / "events.jsonl").exists(),
          str(root), fatal=True)

    base = _baseline(root, args.project or os.environ.get("COMPANY_PROJECT"))
    check("baseline recorded", base is not None,
          f"exit {base['exit_code']}, green={base['green']}" if base else
          "none — run `company baseline` so red repos are judged fairly")

    emit({"ok": not problems, "repo": str(repo), "stack": detected["stack"],
          "checks": checks, "blocking": problems},
         0 if not problems else 1)


def cmd_costs(args):
    """What this consumed, and what it delivered.

    On a Claude subscription these runs are NOT billed in dollars — they draw
    down plan usage. So tokens lead, and the dollar figure is reported only as
    what the same work would have cost through the API, clearly labelled.
    """
    root = company_root(args)
    project = args.project or os.environ.get("COMPANY_PROJECT")
    events = EventLog(root).read()

    by_actor: dict[str, dict] = {}
    totals = {"output": 0, "input": 0, "cache_read": 0, "cache_creation": 0}
    estimate = 0.0
    seconds = 0.0

    for ev in events:
        if ev.get("event") != "WORKER_EXITED":
            continue
        if project and ev.get("project") != project:
            continue
        data = ev.get("data") or {}
        # `cost_usd` is the pre-V2 field name; read both so old logs still fold.
        cost = data.get("cost_usd_estimate", data.get("cost_usd"))
        tokens = data.get("tokens") or {}
        if cost is None and not tokens:
            continue

        entry = by_actor.setdefault(ev["actor"], {
            "runs": 0, "output_tokens": 0, "cache_read_tokens": 0,
            "seconds": 0.0, "usd_equivalent": 0.0, "tasks": []})
        entry["runs"] += 1
        entry["output_tokens"] += tokens.get("output", 0)
        entry["cache_read_tokens"] += tokens.get("cache_read", 0)
        entry["seconds"] = round(entry["seconds"] + (data.get("elapsed_s") or 0), 1)
        entry["usd_equivalent"] = round(entry["usd_equivalent"] + (cost or 0), 4)
        if ev.get("task") and ev["task"] not in entry["tasks"]:
            entry["tasks"].append(ev["task"])

        for k in totals:
            totals[k] += tokens.get(k, 0)
        estimate += cost or 0
        seconds += data.get("elapsed_s") or 0

    tasks = _project_tasks(root, project)
    done = [t for t in tasks if t.get("status") in ("DONE", "MERGED")]
    runs = sum(e["runs"] for e in by_actor.values())

    emit({
        "project": project,
        "billed_to": "Claude subscription — no dollar charge for these runs",
        "worker_runs": runs,
        "tasks_delivered": len(done),
        "tokens": totals,
        "tokens_per_delivered_task": (
            {k: round(v / len(done)) for k, v in totals.items()} if done else None),
        "wall_clock_minutes": round(seconds / 60, 1),
        "api_equivalent_usd": round(estimate, 2),
        "by_actor": dict(sorted(by_actor.items(),
                                key=lambda kv: -kv[1]["output_tokens"])),
        "notes": [
            "api_equivalent_usd is Claude Code's CLIENT-SIDE ESTIMATE of what this "
            "work would have cost through the API. It is not a bill and nothing "
            "was charged: workers run on your claude.ai login, so they draw down "
            "subscription usage instead.",
            "cache_read is normally the largest number by far, because a non-bare "
            "worker re-reads its cached context every turn. It is the figure that "
            "matters when you start hitting plan limits.",
            f"{runs} worker runs produced {len(done)} delivered tasks. Most runs "
            "are gates and fixes rather than waste — a gated task legitimately "
            "costs one implementation plus one run per gate. Watch the ratio over "
            "time, not its absolute value.",
            "Runs logged before token capture existed report zero tokens; only "
            "the api_equivalent_usd figure survives for those.",
        ],
    })


def cmd_advise(args):
    """Run the executive panel: expertise the CEO does not have to supply."""
    import advise
    import worker as worker_mod
    root = company_root(args)
    repo = root.parent
    project = load_project(root, args.project)

    officers = [args.officer] if args.officer else list(advise.OFFICERS)
    for o in officers:
        if o not in advise.OFFICERS:
            die(f"unknown officer {o!r}; expected one of {sorted(advise.OFFICERS)}")

    if args.show:
        findings = advise.fold(EventLog(root).read(), project)
        if args.json:
            emit({"project": project, "findings": findings})
        print(advise.render(findings))
        raise SystemExit(0)

    results = []
    for officer in officers:
        spec = advise.OFFICERS[officer]
        actor = f"{officer}-advisor"
        packet = (
            f"{spec['brief']}\n\n"
            f"Repository: {repo}\nProject: {project}\n\n"
            f"File each finding with:\n"
            f"  company advise-finding --officer {officer} --severity high|medium|low \\\n"
            f"    --finding \"...\" --evidence \"...\" --recommendation \"...\"\n\n"
            f"Escalate anything that is genuinely the CEO's call with "
            f"`company escalate`. Report only what you verified; label the rest."
        )
        # Advisors read; they never touch a worktree, so they run in the repo
        # itself with a read-only tool set.
        try:
            result = worker_mod.launch_readonly(
                repo, root, project, packet, spec["agent"], actor,
                timeout=args.timeout)
        except worker_mod.WorkerError as exc:
            results.append({"officer": officer, "error": str(exc)})
            continue
        results.append({"officer": officer, "exit_code": result["exit_code"],
                        "elapsed_s": result["elapsed_s"]})

    taskstate.rebuild(root)
    findings = advise.fold(EventLog(root).read(), project)
    if args.json:
        emit({"ok": True, "ran": results, "findings": findings})
    print(advise.render(findings))
    raise SystemExit(0)


def cmd_advise_finding(args):
    """Officer-facing: file one finding. The advisory equivalent of `company event`."""
    import advise
    root = company_root(args)
    project = load_project(root, args.project)
    officer = args.officer
    actor = os.environ.get("COMPANY_ACTOR")
    try:
        data = advise.record_finding(
            root, project=project, officer=officer, severity=args.severity,
            finding=args.finding, evidence=args.evidence,
            recommendation=args.recommendation,
            verified=not args.unverified, actor=actor)
    except ValueError as exc:
        die(str(exc), 2)
    taskstate.rebuild(root)
    emit({"ok": True, **data})


READONLY_ROLES = ("cfo-advisor", "ciso-advisor", "cto-advisor", "coo-advisor",
                  "code-reviewer", "qa-engineer", "security-reviewer")


def cmd_lesson(args):
    """Record a repeatable pattern, or list what's already been recorded.

    `--pattern` present -> record. Absent -> list, oldest first, so a fresh
    session can check what this repo has already learned before repeating it.

    Recording is refused for the 7 read-only officer/reviewer roles: none of
    their prompts document using `company lesson`, and COO's audit caught
    exactly the failure mode this prevents — cto-advisor, mid-exploration,
    called it 47 times with placeholder junk ('a repeated pattern'/'f'/'e')
    while poking at what the command does, permanently polluting the
    append-only log under a fake project. A read-only role has no legitimate
    reason to write ANY state-mutating event; this closes the one gap that
    let it happen by accident rather than by design.
    """
    import lessons
    root = company_root(args)
    if args.pattern:
        actor_for_check = args.actor or os.environ.get("COMPANY_ACTOR") or ""
        if any(actor_for_check == r or actor_for_check.startswith(r + "-") for r in READONLY_ROLES):
            die(f"{actor_for_check!r} is a read-only role and may not record a "
               f"lesson — recording is for company-pm and implementers only. "
               f"If you found something worth proposing, use capability-curator's "
               f"escalation flow instead of exploring against the live event log.", 2)
        if not args.evidence or not args.fix:
            die("--pattern requires --evidence and --fix", 1)
        project = load_project(root, args.project)
        actor = args.actor or os.environ.get("COMPANY_ACTOR")
        try:
            data = lessons.record(root, project=project, pattern=args.pattern,
                                  evidence=args.evidence, fix=args.fix, actor=actor,
                                  skill=args.skill)
        except ValueError as exc:
            die(str(exc), 2)
        emit({"ok": True, **data})
    else:
        project = args.project or os.environ.get("COMPANY_PROJECT")
        events = EventLog(root).read()
        out = {"ok": True, "lessons": lessons.fold(events, project, skill=args.skill)}
        if not args.skill:
            out["skills_needing_a_patch"] = lessons.skills_with_repeated_lessons(events)
        emit(out)


def cmd_escalate(args):
    """Ask the CEO for something the PM cannot do or decide."""
    import escalations
    root = company_root(args)
    project = load_project(root, args.project)
    try:
        esc = escalations.raise_escalation(
            root, project=project, actor=args.actor or "company-pm", kind=args.kind,
            need=args.need, detail=args.detail or "", blocking=not args.non_blocking,
            task=args.task, options=args.option, commands=args.command)
    except ValueError as exc:
        die(str(exc), 1)
    escalations.write_views(root, EventLog(root).read())
    taskstate.rebuild(root)
    emit({"ok": True, **esc,
          "file": str(root / "escalations" / f"{esc['id']}.md")})


def cmd_resolve(args):
    import escalations
    root = company_root(args)
    project = load_project(root, args.project)
    try:
        out = escalations.resolve(root, args.id, actor=args.actor or "riyan",
                                  project=project, resolution=args.resolution)
    except KeyError as exc:
        die(str(exc), 1)
    escalations.write_views(root, EventLog(root).read())
    taskstate.rebuild(root)
    emit({"ok": True, **out})


def cmd_gallery(args):
    """Plan the tmux gallery, or open it. Display only — never the bus."""
    import gallery
    import render
    root = company_root(args)
    project = args.project or os.environ.get("COMPANY_PROJECT")
    tasks = _project_tasks(root, project)

    if args.script or args.open:
        text = gallery.script(root, tasks)
        path = root / "state" / "gallery.sh"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
        if args.open:
            os.execv("/bin/bash", ["bash", str(path)])
        print(text)
        raise SystemExit(0)

    emit(gallery.plan(root, tasks))


def cmd_stop(args):
    import worker as worker_mod
    root = company_root(args)
    stopped = worker_mod.stop_all(root, args.project)
    emit({"ok": True, "stopped": stopped,
          "note": "worktrees preserved — nothing was deleted"})


def _session_actor(args) -> str | None:
    return args.actor or os.environ.get("COMPANY_ACTOR") or os.environ.get("CLAUDE_CODE_SESSION_ID")


def cmd_session_announce(args):
    """Record what this top-level session is doing, so a peer session checking
    `company session list` sees it before staffing overlapping work."""
    import sessions
    root = company_root(args)
    globs = [g.strip() for g in args.globs.split(",") if g.strip()] if args.globs else []
    try:
        record = sessions.announce(root, _session_actor(args), args.doing, globs)
    except ValueError as exc:
        die(str(exc), 1)
    emit({"ok": True, **record})


def cmd_session_list(args):
    root = company_root(args)
    import sessions
    emit({"ok": True, "sessions": sessions.list_active(root)})


def cmd_session_done(args):
    import sessions
    root = company_root(args)
    actor = _session_actor(args)
    cleared = sessions.done(root, actor)
    emit({"ok": True, "actor": actor, "cleared": cleared})


def cmd_session_ping(args):
    """Fallback for when SendMessage isn't bound yet or is erroring — push a
    tagged message straight into a peer's tmux pane. Prefer SendMessage;
    reach for this only when it's unavailable, and only when the peer is
    known to be a tmux pane."""
    import sessions
    try:
        sent = sessions.ping_via_tmux(args.target, args.message, _session_actor(args))
    except RuntimeError as exc:
        die(str(exc), 1)
    emit({"ok": True, "target": args.target, "sent": sent})


def cmd_onboard(args):
    """init + detect + baseline + doctor, in the order that makes each one valid.

    The four-command chain was the correct sequence from the start — detect
    needs init's scaffold, baseline needs detect's verify command, doctor needs
    both. Chaining them by hand is just a place to typo or skip a step. This
    runs each as the real `company <verb>` subprocess (so behaviour can never
    drift from running them separately) and stops at the first failure with the
    reason, rather than plowing on to a doctor check that was never going to
    pass.
    """
    import subprocess

    exe = [sys.executable, str(Path(__file__).resolve())]
    root_flag = ["--root", args.root] if args.root else []
    steps = [("init", []), ("detect", ["--write"]), ("baseline", []), ("doctor", [])]

    for name, extra in steps:
        print(f"── {name} " + "─" * (40 - len(name)))
        result = subprocess.run(exe + root_flag + [name] + extra)
        if result.returncode not in (0,) and name != "doctor":
            emit({"ok": False, "stopped_at": name, "exit_code": result.returncode,
                  "note": f"`company {name}` failed — fix that before continuing, "
                          f"rather than run the remaining steps against a broken state."},
                 result.returncode)
        if name == "doctor":
            raise SystemExit(result.returncode)


def build_parser():
    p = argparse.ArgumentParser(prog="company", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="path to .company/ (default: discovered from cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="scaffold .company/ in this repo").set_defaults(fn=cmd_init)

    e = sub.add_parser("event", help="append an event to the log (worker-facing)")
    e.add_argument("task", nargs="?")
    e.add_argument("type")
    e.add_argument("--data", help="JSON object")
    e.add_argument("--evidence", help="commit SHA, path, 'exit N', or JSON object")
    e.add_argument("--actor", help="defaults to $COMPANY_ACTOR")
    e.add_argument("--project")
    e.add_argument("--no-rebuild", action="store_true")
    e.set_defaults(fn=cmd_event)

    r = sub.add_parser("rebuild", help="replay events into task views")
    r.add_argument("--verify", action="store_true",
                   help="compare against disk instead of writing; exit 4 on mismatch")
    r.set_defaults(fn=cmd_rebuild)

    t = sub.add_parser("task", help="inspect or advance a task")
    tsub = t.add_subparsers(dest="taskcmd", required=True)
    ts = tsub.add_parser("show")
    ts.add_argument("id")
    ts.set_defaults(fn=cmd_task_show)
    ta = tsub.add_parser("advance", help="enforces the Evidence Rule")
    ta.add_argument("id")
    ta.add_argument("--to", required=True)
    ta.add_argument("--actor")
    ta.set_defaults(fn=cmd_task_advance)

    h = sub.add_parser("handoff", help="write a handoff (worker-facing)")
    h.add_argument("task")
    h.add_argument("--to", required=True)
    h.add_argument("--from", dest="frm", required=True)
    h.add_argument("--body")
    h.add_argument("--stdin", action="store_true")
    h.add_argument("--actor")
    h.set_defaults(fn=cmd_handoff)

    g = sub.add_parser("gates", help="deterministic risk-table lookup")
    g.add_argument("--request", help="the request text")
    g.add_argument("--paths", nargs="*", help="owned globs the work touches")
    g.add_argument("--files-touched", type=int,
                    help="predicted file count — enables the D9 fast-path check")
    g.add_argument("--diff-lines", type=int,
                    help="predicted changed-line count — enables the D9 fast-path check")
    g.set_defaults(fn=cmd_gates)

    pl = sub.add_parser("plan", help="apply the risk table to a proposed task graph")
    pl.add_argument("--spec", help="path to a plan JSON (default: stdin)")
    pl.add_argument("--allow-overlap", action="store_true",
                    help="plan anyway despite predicted file collisions")
    pl.add_argument("--allow-tier-escalation", action="store_true",
                    help="plan anyway despite an unreasoned Tier 0 -> staffed escalation (D9)")
    pl.set_defaults(fn=cmd_plan)

    sf = sub.add_parser("staff", help="apply a plan: tasks, branches, worktrees")
    sf.add_argument("--project")
    sf.set_defaults(fn=cmd_staff)

    rn = sub.add_parser("run", help="launch a Tier-2 worker for one task")
    rn.add_argument("task")
    rn.add_argument("--role", required=True, help="agent name, e.g. backend-engineer")
    rn.add_argument("--actor", help="worker id (default: <role>-<task number>)")
    rn.add_argument("--why", help="one line: why this matters, in business terms")
    rn.add_argument("--handoff-to", default="pm")
    rn.add_argument("--max-turns", type=int, default=60)
    rn.add_argument("--timeout", type=int, default=1800, help="wall-clock seconds")
    rn.add_argument("--max-concurrent", type=int,
                    help="override the concurrency cap from budgets.yaml")
    rn.add_argument("--verify", help="override the configured verify command")
    rn.add_argument("--detach", action="store_true",
                    help="return immediately; the worker survives the calling turn "
                         "(required when launching from a `claude -p` PM)")
    rn.add_argument("--force", action="store_true",
                    help="launch even with unmet dependencies")
    rn.add_argument("--dry-run", action="store_true",
                    help="render and measure the packet without launching")
    rn.set_defaults(fn=cmd_run)

    gg = sub.add_parser("gate-group",
                        help="one gate launch for several tasks that touch the same core, "
                             "instead of one per task")
    gg.add_argument("group", help="the gate_group value shared by the tasks")
    gg.add_argument("--role", required=True, choices=sorted(GATE_ROLES))
    gg.add_argument("--tasks", nargs="+",
                    help="explicit task id order (default: task-creation order)")
    gg.add_argument("--actor", help="default: <role>-group-<group>")
    gg.add_argument("--why", help="one line: why this matters, in business terms")
    gg.add_argument("--max-turns", type=int, default=60)
    gg.add_argument("--timeout", type=int, default=1800, help="wall-clock seconds")
    gg.add_argument("--verify", help="override the configured verify command")
    gg.add_argument("--dry-run", action="store_true",
                    help="render and measure the packet without launching")
    gg.set_defaults(fn=cmd_gate_group)

    sx = sub.add_parser("status", help="derived state — never estimated")
    sx.add_argument("--project")
    sx.add_argument("--json", action="store_true")
    sx.set_defaults(fn=cmd_status)

    rp = sub.add_parser("report", help="executive summary: outcomes, not activity")
    rp.add_argument("--project")
    rp.set_defaults(fn=cmd_report)

    ig = sub.add_parser("integrate", help="rebase, test, and merge on green only")
    ig.add_argument("--task", help="default: every task with a diff and no merge")
    ig.add_argument("--test-command", help="override the configured verify command")
    ig.add_argument("--actor", default="integration")
    ig.add_argument("--force", action="store_true",
                    help="integrate even with unsatisfied gates")
    ig.set_defaults(fn=cmd_integrate)

    dt = sub.add_parser("detect", help="identify the stack and a verify command")
    dt.add_argument("--write", action="store_true",
                    help="save to .company/config/project.yaml")
    dt.set_defaults(fn=cmd_detect)

    bl = sub.add_parser("baseline",
                        help="record how the repo behaves before any work starts")
    bl.add_argument("--verify", help="override the configured verify command")
    bl.add_argument("--project")
    bl.add_argument("--timeout", type=int, default=900)
    bl.set_defaults(fn=cmd_baseline)

    ct = sub.add_parser("costs", help="what this cost and what it delivered")
    ct.add_argument("--project")
    ct.set_defaults(fn=cmd_costs)

    dr = sub.add_parser("doctor", help="preflight a repo before pointing workers at it")
    dr.add_argument("--project")
    dr.set_defaults(fn=cmd_doctor)

    ob = sub.add_parser("onboard",
                        help="init + detect + baseline + doctor, in order, stop on first failure")
    ob.set_defaults(fn=cmd_onboard)

    ad = sub.add_parser("advise", help="run the executive panel (cto/ciso/cfo/coo)")
    ad.add_argument("--officer", choices=["cto", "ciso", "cfo", "coo"],
                    help="default: all four")
    ad.add_argument("--show", action="store_true",
                    help="print open findings without running anyone")
    ad.add_argument("--json", action="store_true")
    ad.add_argument("--project")
    ad.add_argument("--timeout", type=int, default=900)
    ad.set_defaults(fn=cmd_advise)

    af = sub.add_parser("advise-finding", help="officer-facing: file one finding")
    af.add_argument("--officer", required=True,
                    choices=["cto", "ciso", "cfo", "coo"])
    af.add_argument("--severity", required=True, choices=["high", "medium", "low"])
    af.add_argument("--finding", required=True)
    af.add_argument("--evidence", required=True)
    af.add_argument("--recommendation", required=True)
    af.add_argument("--unverified", action="store_true",
                    help="mark a suspicion you could not confirm")
    af.add_argument("--project")
    af.set_defaults(fn=cmd_advise_finding)

    ls = sub.add_parser("lesson", help="record a repeatable pattern, or list what's recorded")
    ls.add_argument("--pattern", help="what kept happening — provide to record a new lesson")
    ls.add_argument("--evidence", help="what actually happened (required with --pattern)")
    ls.add_argument("--fix", help="the fix that was actually applied (required with --pattern)")
    ls.add_argument("--actor")
    ls.add_argument("--project")
    ls.add_argument("--skill", help="tag this lesson to the skill/agent it's about — "
                    "2+ lessons on the same skill is the signal it needs a real patch")
    ls.set_defaults(fn=cmd_lesson)

    es = sub.add_parser("escalate", help="ask the CEO for something the PM cannot do")
    es.add_argument("--kind", required=True,
                    choices=sorted(["human_action", "decision", "approval",
                                    "information", "risk"]))
    es.add_argument("--need", required=True, help="plainly, what you want")
    es.add_argument("--detail", help="context the CEO needs to answer")
    es.add_argument("--option", action="append", help="repeatable; for --kind decision")
    es.add_argument("--command", action="append",
                    help="repeatable; an exact command the CEO can run")
    es.add_argument("--task")
    es.add_argument("--project")
    es.add_argument("--actor")
    es.add_argument("--non-blocking", action="store_true")
    es.set_defaults(fn=cmd_escalate)

    rs = sub.add_parser("resolve", help="CEO: answer an escalation")
    rs.add_argument("id")
    rs.add_argument("--resolution", required=True)
    rs.add_argument("--project")
    rs.add_argument("--actor")
    rs.set_defaults(fn=cmd_resolve)

    gl = sub.add_parser("gallery", help="plan or open the tmux viewing gallery")
    gl.add_argument("--project")
    gl.add_argument("--script", action="store_true", help="print the tmux script")
    gl.add_argument("--open", action="store_true", help="build and attach now")
    gl.set_defaults(fn=cmd_gallery)

    st = sub.add_parser("stop", help="halt every worker; preserve every worktree")
    st.add_argument("--project")
    st.set_defaults(fn=cmd_stop)

    se = sub.add_parser("session", help="who else is active on this checkout, and doing what")
    sesub = se.add_subparsers(dest="sessioncmd", required=True)
    sa = sesub.add_parser("announce", help="record what this session is doing")
    sa.add_argument("--doing", required=True, help="one line: what this session is working on")
    sa.add_argument("--globs", help="comma-separated globs this session owns, if known")
    sa.add_argument("--actor", help="defaults to $COMPANY_ACTOR or $CLAUDE_CODE_SESSION_ID")
    sa.set_defaults(fn=cmd_session_announce)
    sl = sesub.add_parser("list", help="every announced session, most-recent first")
    sl.set_defaults(fn=cmd_session_list)
    sd = sesub.add_parser("done", help="clear this session's entry")
    sd.add_argument("--actor", help="defaults to $COMPANY_ACTOR or $CLAUDE_CODE_SESSION_ID")
    sd.set_defaults(fn=cmd_session_done)
    sp = sesub.add_parser("ping", help="fallback: push a tagged message into a peer's tmux pane")
    sp.add_argument("--target", required=True, help="tmux pane target, e.g. ht-workspace:1.2")
    sp.add_argument("--message", required=True)
    sp.add_argument("--actor", help="defaults to $COMPANY_ACTOR or $CLAUDE_CODE_SESSION_ID")
    sp.set_defaults(fn=cmd_session_ping)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
