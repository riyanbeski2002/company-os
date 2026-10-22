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

from eventlog import (GOAL_EVENTS, ROUTINE_EVENTS, EventLog, EvidenceError,  # noqa: E402
                      canonical, make_event)
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
    # capability-registry.yaml (2026-08-24) is company-os's own canonical,
    # public registry now, not a per-repo template — see the comment at the
    # top of that file. Auto-copying it here would silently hand every
    # newly onboarded repo all of Riyan's company-os-specific approvals;
    # a new repo starts with its own empty registry instead, same as
    # before this file existed at all.
    NEVER_AUTO_COPY = {"capability-registry.yaml"}
    copied = []
    if defaults.is_dir():
        for src in sorted(defaults.glob("*.yaml")):
            if src.name in NEVER_AUTO_COPY:
                continue
            dst = root / "config" / src.name
            if not dst.exists():
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
                copied.append(dst.name)

    _ensure_line(repo / ".gitignore", ".company/worktrees/")
    _ensure_line(repo / ".gitignore", ".company/state/")
    _ensure_line(repo / ".worktreeinclude", ".env")
    _ensure_line(repo / ".worktreeinclude", ".env.local")

    # Advisory only — never edits .gitignore for events.jsonl. Whether a repo
    # tracks its log is that repo's own decision (company-os's own .gitignore
    # deliberately ignores it); new onboards are just told the recommended
    # default. On stderr so stdout stays one JSON document.
    import gitutil
    log_git = gitutil.event_log_git_state(repo)
    print(_event_log_git_note(log_git), file=sys.stderr)

    emit({"ok": True, "repo": str(repo), "company_root": str(root),
          "configs_installed": copied, "event_log_git": log_git})


def _event_log_git_note(log_git: dict) -> str:
    rel = ".company/events/events.jsonl"
    if log_git["state"] == "tracked":
        return f"note: {rel} is tracked in git — your remote backs it up."
    if log_git["state"] == "untracked":
        return (f"note: {rel} is not ignored, so git will track it once added. "
                f"company-os never commits on your behalf: `git add {rel}` and "
                f"commit it yourself at least once after the first events are "
                f"written, for a free backup via your remote.")
    if log_git["state"] == "ignored":
        return (f"note: {rel} would be excluded by this repo's existing .gitignore "
                f"(matched by: {log_git['pattern']}). company-os recommends tracking "
                f"the event log in git for a free backup via your remote. If you "
                f"want that, add an explicit `!{rel}` negation to your .gitignore "
                f"yourself — but git cannot re-include a file whose parent directory "
                f"is excluded, so a directory ignore like `.company/` must become "
                f"`.company/*` + `!.company/events/` + `.company/events/*` + "
                f"`!{rel}`. Nothing was changed; leaving it ignored is a valid choice.")
    return f"note: could not determine whether git tracks {rel}."


def _ensure_line(path: Path, line: str):
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if line not in existing:
        with open(path, "a", encoding="utf-8") as fh:
            if existing and existing[-1].strip():
                fh.write("\n")
            fh.write(line + "\n")


LAUNCHER_ONLY_EVENTS = {"WORKER_STARTED", "WORKER_EXITED", "WORKER_HEARTBEAT",
                        # Supplies a WORKER_EXITED's tokens to costs.py, so a
                        # forged one is a forged WORKER_EXITED by another name.
                        "TOKENS_BACKFILLED",
                        # Disregards recorded lessons: a worker that could forge
                        # one could quarantine its own real lessons to hide them.
                        "LESSONS_QUARANTINED"}
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
    if args.type in GOAL_EVENTS:
        # ADR-006 §5: works like LAUNCHER_ONLY_EVENTS, but the one writer is
        # `company goal`, which owns these events' history-dependent rules
        # (parent level, one open mission, retro-link reasons) and refuses
        # to run inside a launched worker.
        die(f"{args.type!r} may only be recorded through `company goal`, never "
           f"through raw `company event` — that command owns its validation.", 2)
    if args.type in ROUTINE_EVENTS:
        # Same shape as goal events: `company routine` owns the cron check and
        # the one-fire-per-slot rule, and refuses to run inside a worker — a
        # worker must never schedule its own future work.
        die(f"{args.type!r} may only be recorded through `company routine`, never "
           f"through raw `company event` — that command owns its validation.", 2)
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
    root = company_root(args)
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8")) if args.spec \
        else json.loads(sys.stdin.read())
    try:
        plan = plan_spec(root, spec, allow_overlap=args.allow_overlap,
                         allow_tier_escalation=args.allow_tier_escalation,
                         allow_duplicate=args.allow_duplicate)
    except ValueError as exc:
        die(str(exc), 1)
    if not plan["ok"]:
        emit(plan, 3)

    project = plan["project"]
    (root / "projects").mkdir(parents=True, exist_ok=True)
    (root / "projects" / f"{project}.json").write_text(
        canonical({k: v for k, v in plan.items() if k != "ok"}), encoding="utf-8")
    emit(plan)


def plan_spec(root: Path, spec: dict, *, allow_overlap: bool = False,
              allow_tier_escalation: bool = False, allow_duplicate: bool = False) -> dict:
    """The body of `company plan`, callable by `company routine fire`: the
    staffing plan for `spec`, with `ok` False and a `refusal` when a check
    refuses it. Writes nothing. Raises ValueError for a malformed spec or a
    goal that can't be linked."""
    import staffing
    cfg = staffing.load_config(root, "risk-triggers.yaml")
    qg = staffing.load_config(root, "quality-gates.yaml")

    project = spec.get("project")
    if not project:
        raise ValueError("plan spec needs a 'project'")
    request = spec.get("request", "")
    # ADR-006 §3: a spec-level `goal` is stamped onto every task lacking one,
    # the same way `project` is. Never an input to staffing.evaluate() (§6):
    # "grow payments revenue" must not fire the payments trigger.
    goal = spec.get("goal")
    tasks = spec.get("tasks")
    if not tasks:
        raise ValueError("plan spec needs a non-empty 'tasks' list")

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
        if goal and not task.get("goal"):
            task["goal"] = goal
        task["triggers_fired"] = [t["trigger"] for t in verdict["triggers_fired"]]
        task["fast_path"] = verdict["fast_path"]
        if verdict["downgraded_triggers"]:
            # A keyword matched but every owned path was presentational
            # content -- recorded on the task itself, not just the one-off
            # evaluate() call, so a later audit of this plan can see a gate
            # was deliberately not forced and why, not just that it wasn't.
            task["downgraded_triggers"] = verdict["downgraded_triggers"]
        if additions:
            task["gates_added_by_pm"] = additions
        planned.append(task)

    linked_goals = sorted({t["goal"] for t in planned if t.get("goal")})
    if linked_goals:
        import goals as goals_mod
        defs = goals_mod.definitions(EventLog(root).read())
        for gid in linked_goals:
            d = defs.get(gid)
            if not d or d["closed"] or d.get("level") == "mission":
                raise ValueError(
                    f"plan links tasks to {gid!r}, which is "
                    + ("not a defined goal" if not d else "closed" if d["closed"]
                       else "the mission — link an objective or key_result")
                    + " (see `company goal tree`)")

    tier2 = [t for t in planned if t.get("tier") == 2]
    parallel = [t for t in tier2 if not t.get("depends_on")]
    collisions = staffing.predict_overlap(parallel)
    band = staffing.size_band(len(tier2))

    # This project's still-live tasks from EARLIER plans, not just this
    # batch — both checks below exist because a batch-local view already
    # missed real incidents (finos-5a: same fix staffed 3x across 3 waves;
    # resolve-os: 18 tasks across 6 waves in ~29h, each wave its own PR).
    events = EventLog(root).read()
    existing = [t for t in taskstate.fold(events).values()
               if t.get("project") == project]

    cross_plan_joins = staffing.join_existing_gate_groups(planned, existing)
    default_group_id, default_grouped_tasks = staffing.default_gate_group(planned, project)
    duplicates = staffing.find_duplicate_staffing(planned, existing)
    # Informational only, never a refusal: work that looks like it was done
    # before (resolved tasks, this project) and lessons whose text overlaps a
    # new title (every project in this log — a lesson exists to cross them).
    import lessons as lessons_mod
    similar_resolved = staffing.find_similar_resolved_work(planned, existing)
    matching_lessons = staffing.find_matching_lessons(
        planned, lessons_mod.fold(events))

    plan = {
        "project": project, "request": request, "tasks": planned,
        "staffing": band, "tier2_workers": len(tier2),
        "gates_forced_by_risk_table": forced,
        "predicted_file_overlap": collisions,
        "tier_escalations_without_reason": unreasoned_escalations,
        "cross_plan_gate_joins": cross_plan_joins,
        "default_gate_group": default_group_id,
        "default_gate_group_tasks": default_grouped_tasks,
        "possible_duplicate_staffing": duplicates,
        "similar_resolved_work": similar_resolved,
        "matching_lessons": matching_lessons,
    }

    if collisions and not allow_overlap:
        plan["ok"] = False
        plan["refusal"] = (
            "parallel tasks have overlapping file ownership — sequence them with "
            "depends_on, split the globs, or pass --allow-overlap"
        )
    elif unreasoned_escalations and not allow_tier_escalation:
        plan["ok"] = False
        plan["refusal"] = (
            "fast_path recommends Tier 0 for one or more tasks (no risk trigger, "
            "diff in-bounds) but they're staffed above it with no recorded reason — "
            "set 'tier_reason' on the task, or pass --allow-tier-escalation"
        )
    elif duplicates and not allow_duplicate:
        plan["ok"] = False
        plan["refusal"] = (
            "one or more planned tasks closely match the title of a still-live "
            "task already in this project — check its status before staffing the "
            "same fix twice under a different id, or pass --allow-duplicate if "
            "this genuinely is separate work"
        )
    else:
        plan["ok"] = True
    return plan


def _task_created_data(task: dict) -> dict:
    """A planned task's TASK_CREATED payload — shared by `staff` and
    `routine fire` so both create tasks the same way."""
    import worker as worker_mod
    tid = task["id"]
    data = {k: v for k, v in task.items() if k not in ("id", "project")}
    if task.get("tier") == 2 and not data.get("branch"):
        data["branch"] = f"task/{tid.split('-')[-1]}-{worker_mod.slug(task.get('title', tid))}"
    return data


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

        data = _task_created_data(task)
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

# Turn budgets (2026-09-14, cost audit): `_diff_summary_for_gate` already hands
# a gate role the actual patch specifically so it doesn't have to rediscover it
# via its own Read/Grep/Bash — so it needs far fewer turns than an implementer
# building something from scratch. Measured 2026-09-14: gate roles were the
# majority of a day's launches (66 of 99) and 64% of its cache_creation tokens,
# all riding the same 60-turn ceiling as an implementer. This is a starting
# number, not a settled one — treat it the way packet.py's TOKEN_BUDGET is
# treated: raise it only against measured GATE_NO_VERDICT/timeout evidence,
# never on suspicion.
GATE_MAX_TURNS = 15
IMPLEMENTER_MAX_TURNS = 60


def _resolve_max_turns(explicit: int | None, role: str) -> int:
    if explicit is not None:
        return explicit
    return GATE_MAX_TURNS if role in GATE_ROLES else IMPLEMENTER_MAX_TURNS


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
    events = EventLog(root).read()
    tasks = taskstate.fold(events)
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

    # ESC-026 (Riyan, 2026-09-11: "go with A"). Computed before render() —
    # not after, where it used to live — because find_handoff needs the
    # actor this launch will actually use, not a placeholder. A relaunch
    # addressed to the actor by name ("backend-engineer-231") only matches
    # if that name exists before the lookup runs.
    actor = args.actor or f"{args.role}-{task['id'].split('-')[-1]}"

    # find_handoff/handoff_text (packet.py) already had the mechanism to
    # embed a handoff's actual content into the packet — nothing here ever
    # called it, so `company handoff` wrote a file every worker was blind
    # to. See packet.py's own ESC-026 comment for the fuller cost.
    handoff_path = packet_mod.find_handoff(root, task["id"], actor, args.role)
    handoff_text = handoff_path.read_text() if handoff_path else None

    # cmd_plan already shows the PM which recorded lessons overlap a task's
    # title; the worker actually doing the task never saw them. Same match,
    # best overlap first (stable, so ties stay oldest-first); render() bounds it.
    import lessons as lessons_mod
    import staffing
    matching_lessons = sorted(
        staffing.find_matching_lessons([task], lessons_mod.fold(events)),
        key=lambda hit: -hit["overlap"])

    try:
        body = packet_mod.render(
            task, why=args.why or "Requested by the CEO.",
            diff_summary=_diff_summary_for_gate(repo, root, task, args.role, worker_mod),
            contracts=contracts, handoff_target=args.handoff_to,
            max_turns=_resolve_max_turns(args.max_turns, args.role), timeout_s=args.timeout,
            verify=verify_command(root, args.verify),
            baseline=_baseline(root, task.get("project")),
            handoff_text=handoff_text, lessons=matching_lessons)
    except (packet_mod.PacketTooLarge, ValueError) as exc:
        die(str(exc), 1)

    if args.dry_run:
        emit({"ok": True, "task": task["id"], "dry_run": True,
              "packet_tokens": packet_mod.estimate_tokens(body), "packet": body,
              "handoff_used": str(handoff_path) if handoff_path else None})

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
        if args.model:
            argv += ["--model", args.model]
        if args.effort:
            argv += ["--effort", args.effort]

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
                                   timeout=args.timeout,
                                   model_override=args.model, effort_override=args.effort,
                                   override_reason=args.why)
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
    import re
    import worker as worker_mod
    import gategroup
    import packet as packet_mod

    # args.group lands directly in a worktree path and a git branch name
    # (gategroup.py) — unvalidated, "../../anything" would escape
    # .company/worktrees/. Same bar as a task id or branch slug elsewhere.
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.group or ""):
        die(f"gate_group {args.group!r} must be alphanumeric plus ._- only "
            f"(it's used directly in a worktree path and a branch name)", 1)

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
        wt = gategroup.build_group_review(repo, root, args.group, group_tasks, base,
                                          role=args.role)
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
        baseline=baseline, max_turns=_resolve_max_turns(args.max_turns, args.role),
        timeout_s=args.timeout)

    if args.dry_run:
        emit({"ok": True, "group": args.group, "dry_run": True,
              "tasks": [t["id"] for t in group_tasks],
              "packet_tokens": packet_mod.estimate_tokens(body), "packet": body})

    actor = args.actor or f"{args.role}-group-{args.group}"

    if args.detach:
        # Same reason `company run --detach` exists: a PM running as
        # `claude -p` cannot outlive its own turn, and a group review can
        # run as long as any solo gate.
        import subprocess
        argv = [sys.executable, str(Path(__file__).resolve()),
                "--root", str(root), "gate-group", args.group, "--role", args.role,
                "--actor", actor, "--timeout", str(args.timeout)]
        if args.why:
            argv += ["--why", args.why]
        if args.tasks:
            argv += ["--tasks", *args.tasks]
        if args.max_concurrent:
            argv += ["--max-concurrent", str(args.max_concurrent)]

        state = root / "state" / "workers" / actor
        state.mkdir(parents=True, exist_ok=True)
        out = open(state / "detached.json", "w")
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True,
                                env={**os.environ, "COMPANY_PROJECT": project})
        emit({"ok": True, "detached": True, "group": args.group, "actor": actor,
              "supervisor_pid": proc.pid, "result_file": str(state / "detached.json"),
              "note": "poll `company status`; the review survives this turn ending"})

    # Same concurrency cap as a solo gate — a group launch is still one
    # process, but nothing before this enforced budgets.yaml's cap on it.
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
            event="DEPENDENCY_WAITING", actor=actor, project=project,
            data={"gate_group": args.group, "reason": "concurrency cap",
                  "cap": cap, "queued_s": queued_s}))

    try:
        result = worker_mod.launch_group(repo, root, args.group, group_tasks, wt, body,
                                         args.role, actor, project, timeout=args.timeout)
    except worker_mod.WorkerError as exc:
        slots.release(slot)
        die(str(exc), 1)
    finally:
        slots.release(slot)

    taskstate.rebuild(root)
    result["packet_tokens"] = packet_mod.estimate_tokens(body)
    result["queued_s"] = queued_s
    result["concurrency_cap"] = cap
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
    import escalations as esc_mod

    root = company_root(args)
    project = args.project or os.environ.get("COMPANY_PROJECT")
    tasks = _project_tasks(root, project)
    events = EventLog(root).read()
    stalls = {**render.detect_stale_tasks(tasks),
             **render.detect_stalls(root, tasks, events),
             **render.detect_resting_tasks(tasks),
             **render.gates_with_no_verdict(events, tasks)}

    # Tiered early warning (paperclip donation, 2026-10-21): "suspicious"
    # (1-2 days silent) surfaces here even when a task hasn't yet crossed
    # detect_stale_tasks's 48h "critical" cutoff into `stalls` above -- the
    # whole point is catching it before it needs the stronger label.
    blockers = {t["id"]: esc_mod.blocking_escalation_for_task(events, t["id"]) for t in tasks}
    early_warning = {k: v for k, v in render.detect_early_warning_tasks(tasks, blockers).items()
                      if k not in stalls}

    if args.json:
        emit({"project": project, "progress": render.project_progress(tasks),
              "progress_pct": render.project_progress_pct(tasks),
              "tasks": tasks, "escalations": _escalations(root, project),
              "stalled": stalls, "early_warning": early_warning})
    print(render.status(project or "all projects", tasks, _escalations(root, project), stalls))
    if early_warning:
        print("\nEarly warning (not yet critical):")
        for task_id, reason in early_warning.items():
            print(f"  {task_id}: {reason}")
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
        # Fail-closed on ANY check_done reason, not a substring allowlist
        # (2026-10-21, ECC donation -- `orch-review.workflow.js`'s pattern:
        # a review dimension that errors/returns nothing forces
        # CHANGES_REQUESTED, never a silent pass). The allowlist this
        # replaced was written before gate_roles existed and was never
        # updated when the actor-role-verification reason was added later
        # (commit a7674b1) -- that reason's wording doesn't contain "diff",
        # "test", "self-certified", or "not satisfied", so a forged-actor
        # gate bypass that check_done correctly detects was silently NOT
        # blocking a real merge. Treating check_done's output as
        # authoritative, rather than re-deriving which of its reasons
        # "count," is what makes a future new reason type block by
        # construction instead of needing this list kept in sync forever.
        if reasons and not args.force:
            results.append({"task": tid, "merged": False,
                            "reason": "gates not satisfied", "detail": reasons})
            continue

        conflicts = integrate_mod.detect_concurrent_glob_conflicts(tasks, tid)
        if conflicts and not args.force:
            EventLog(root).append(make_event(
                event="TASK_BLOCKED", actor=args.actor, project=task["project"], task=tid,
                data={"stage": "integration", "reason": "concurrent owned-glob conflict",
                      "detail": conflicts}))
            results.append({"task": tid, "merged": False,
                            "reason": "another task is still active in an overlapping "
                                      "owned path", "detail": conflicts})
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
    import staffing
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
    events_path = root / "events" / "events.jsonl"
    check("company initialised", events_path.exists(), str(root), fatal=True)

    # The log is the only authoritative state there is: one corrupt line
    # stops every other command, and a torn tail stops every append. Both are
    # reported here, never raised — surfacing them is this command's job.
    if events_path.exists():
        try:
            integrity = EventLog(root).integrity()
        except TimeoutError as exc:
            check("event log integrity", False,
                  f"skipped — {exc}; a writer is holding it, re-run doctor")
        else:
            found, total = integrity["problems"], integrity["problem_count"]
            check("event log integrity", not total,
                  f"{integrity['events']} events, seq contiguous, trailing newline"
                  if not total else
                  "; ".join(found[:3]) + (f"; and {total - 3} more" if total > 3 else "")
                  + f" — {events_path} needs repair by hand (or restore from "
                    f"`company backup`) before any run",
                  fatal=True)

        import backup
        newest = backup.latest(backup.default_dir(root))
        if newest:
            with open(newest, "rb") as fh:
                saved = sum(1 for _ in fh)
            with open(events_path, "rb") as fh:
                live = sum(1 for _ in fh)
            check("event log backed up", True,
                  f"{newest} ({max(live - saved, 0)} event(s) appended since)")
        else:
            check("event log backed up", False,
                  f"no backup in {backup.default_dir(root)} — events.jsonl is the only "
                  f"copy of this repo's state. Run `company backup`.")

        # Informational, never a failure: an ignore rule is the repo's own
        # decision (company-os ignores its own log on purpose), not a defect.
        import gitutil
        log_git = gitutil.event_log_git_state(repo)
        check("event log tracked in git", True, {
            "tracked": "tracked — your remote backs it up",
            "ignored": f"not tracked (ignored, matched by: {log_git['pattern']}) — "
                       f"the repo's own choice; your remote does not back it up",
            "untracked": "not tracked (never added, not ignored) — `git add` and "
                         "commit it for a free backup via your remote",
        }.get(log_git["state"], "unknown — git could not say"))

    try:
        base = _baseline(root, args.project or os.environ.get("COMPANY_PROJECT"))
    except ValueError:
        check("baseline recorded", False,
              "unreadable — the event log is corrupt, see event log integrity")
    else:
        check("baseline recorded", base is not None,
              f"exit {base['exit_code']}, green={base['green']}" if base else
              "none — run `company baseline` so red repos are judged fairly")

    # Self-hosted only (see staffing.config_drift's own docstring for the
    # real incident this check exists because of).
    if repo == staffing.PLUGIN_CONFIG.parent:
        drifted = staffing.config_drift(repo, root)
        check("self-hosted config in sync", not drifted,
              "in sync" if not drifted else
              f"{', '.join(drifted)} differ(s) between config/ (maintained) and "
              f".company/config/ (what actually governs launches here) — a plugin "
              f"policy change did not take effect on this repo. Sync them; do not "
              f"assume a fix to config/ is live until .company/config/ matches it.")

    emit({"ok": not problems, "repo": str(repo), "stack": detected["stack"],
          "checks": checks, "blocking": problems},
         0 if not problems else 1)


def cmd_costs(args):
    """What this consumed, and what it delivered.

    On a Claude subscription these runs are NOT billed in dollars — they draw
    down plan usage. So tokens lead, and the dollar figure is reported only as
    what the same work would have cost through the API, clearly labelled.
    Aggregation itself lives in costs.py (pure, directly unit-testable); this
    just adds the task-delivery context only cli.py's helpers have.
    """
    import costs as costs_mod
    root = company_root(args)
    project = args.project or os.environ.get("COMPANY_PROJECT")
    events = EventLog(root).read()

    result = costs_mod.aggregate(events, project)

    tasks = _project_tasks(root, project)
    done = [t for t in tasks if t.get("status") in ("DONE", "MERGED")]

    emit({
        "project": project,
        "billed_to": "Claude subscription — no dollar charge for these runs",
        "worker_runs": result["worker_runs"],
        "tasks_delivered": len(done),
        "tokens": result["tokens"],
        "tokens_per_delivered_task": (
            {k: round(v / len(done)) for k, v in result["tokens"].items()} if done else None),
        "wall_clock_minutes": result["wall_clock_minutes"],
        "api_equivalent_usd": result["api_equivalent_usd"],
        "by_actor": costs_mod.ranked(result["by_actor"], "actor"),
        "by_task": costs_mod.ranked(result["by_task"], "task"),
        "untasked": result["untasked"],
        "runs_with_unestimated_cost": result["runs_with_unestimated_cost"],
        "runs_with_backfilled_tokens": result["runs_with_backfilled_tokens"],
        "notes": [
            "api_equivalent_usd is Claude Code's CLIENT-SIDE ESTIMATE of what this "
            "work would have cost through the API. It is not a bill and nothing "
            "was charged: workers run on your claude.ai login, so they draw down "
            "subscription usage instead.",
            "cache_read is normally the largest number by far, because a non-bare "
            "worker re-reads its cached context every turn. It is the figure that "
            "matters when you start hitting plan limits.",
            f"{result['worker_runs']} worker runs produced {len(done)} delivered "
            "tasks. Most runs "
            "are gates and fixes rather than waste — a gated task legitimately "
            "costs one implementation plus one run per gate. Watch the ratio over "
            "time, not its absolute value.",
            "Runs logged before token capture existed report zero tokens; only "
            "the api_equivalent_usd figure survives for those, unless "
            "`company backfill-tokens` reconstructed them from their stdout.json "
            f"({result['runs_with_backfilled_tokens']} runs here were).",
            "by_task splits a gate-group run's cost evenly across every task it "
            "covered — an explicit estimate, not a measured per-task split; "
            "'split_across_tasks' on an entry names how many tasks shared that run.",
            "avg_cache_read_per_turn/avg_output_per_turn on a by_actor entry are "
            "only as reliable as num_turns capture — check runs_missing_turns "
            "before trusting them for a role with many pre-capture runs.",
            f"runs_with_unestimated_cost: {result['runs_with_unestimated_cost']}. A "
            "harness that reports tokens but no cost estimate (e.g. the codex "
            "adapter — Codex's API has no cost figure to report) still has its "
            "tokens counted in `tokens`/by_actor/by_task above, but contributes "
            "$0 to api_equivalent_usd — a non-zero count here means the dollar "
            "figure understates true spend by that many runs' worth, not that "
            "nothing happened.",
        ],
    })


def cmd_backfill_tokens(args):
    """KNOWN_ISSUES #1's outstanding half: give pre-capture WORKER_EXITED
    events real tokens from their stdout.json, by appending TOKENS_BACKFILLED
    — never by editing the original line. Safe to re-run; see backfill.py.

    A run that can't be reconstructed is warned about on stderr, one line
    each, as well as listed in the JSON: nothing is filled with a guess, and
    a project with gaps should be able to see exactly which runs and why.
    """
    import backfill
    root = company_root(args)
    project = args.project or os.environ.get("COMPANY_PROJECT")
    result = backfill.run(root, project, dry_run=args.dry_run)
    for miss in result["unreconstructable"]:
        print(f"warning: cannot reconstruct tokens for WORKER_EXITED seq={miss['seq']} "
              f"({miss['actor']}): {miss['reason']}", file=sys.stderr)
    emit({"ok": True, **result})


def cmd_quarantine_lessons(args):
    """Disregard test-fixture LESSON_RECORDED events that leaked into the real
    log (project "p", via test_lessons.py/test_onboard.py running inside a
    worker session) by appending one LESSONS_QUARANTINED correction — never by
    editing the original lines. Safe to re-run; see quarantine.py.

    Seqs are re-derived from the live log, not hardcoded. `--expect N` refuses
    to proceed if the log doesn't hold exactly N contaminated entries, so a log
    that has drifted since the count was taken is reported, not quarantined
    blindly.
    """
    import quarantine
    root = company_root(args)
    try:
        result = quarantine.run(root, project=args.project,
                                evidence_commit=args.evidence_commit,
                                expect=args.expect, dry_run=args.dry_run)
    except ValueError as exc:
        die(str(exc), 2)
    emit({"ok": True, **result})


def cmd_backup(args):
    """Snapshot events.jsonl outside the repo, under the append lock — see
    backup.py. Cheap (one file copy) and safe to re-run: an unchanged log
    writes nothing new.

    Manual by design, not wired into any other verb: every verb is exercised
    by the test suite as a real subprocess against the operator's real $HOME,
    so an automatic backup would quietly write into ~/.company-backups on
    every test run. `company doctor` reports instead whether a backup exists
    and how many events it is behind, so a missing one is visible at preflight.

    To restore: copy a backup over .company/events/events.jsonl by hand, then
    `company rebuild --verify`.
    """
    import backup
    root = company_root(args)
    try:
        result = backup.run(root, dest=args.dest)
    except FileNotFoundError as exc:
        die(str(exc))
    for problem in result["problems"]:
        print(f"warning: backed-up log is not intact: {problem}", file=sys.stderr)
    emit({"ok": True, **result})


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
        # Advisors read; they never touch a worktree. They read the repo itself
        # with a read-only tool set, from a sandboxed scratch cwd (see
        # worker.launch_readonly).
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
            source_ref = lessons.parse_source_ref(args.source_ref) \
                if args.source_ref else None
            data = lessons.record(root, project=project, pattern=args.pattern,
                                  evidence=args.evidence, fix=args.fix, actor=actor,
                                  skill=args.skill, source_ref=source_ref)
        except ValueError as exc:
            die(str(exc), 2)
        emit({"ok": True, **data})
    else:
        project = args.project or os.environ.get("COMPANY_PROJECT")
        events = EventLog(root).read()
        found = lessons.fold(events, project, skill=args.skill)
        if args.search:
            # The same word-overlap match cmd_plan runs against a task title,
            # run against free text instead; one shared word is enough here.
            import staffing
            hits = staffing.find_matching_lessons(
                [{"id": "search", "title": args.search}], found, min_shared=1)
            overlap = {h["lesson"]: h["overlap"] for h in hits}
            found = sorted((l for l in found if l["id"] in overlap),
                           key=lambda l: -overlap[l["id"]])
        out = {"ok": True, "lessons": found}
        if not args.skill:
            out["skills_needing_a_patch"] = lessons.skills_with_repeated_lessons(events)
        emit(out)


def cmd_escalate(args):
    """Ask the CEO for something the PM cannot do or decide — or, with
    --list, query what's already been raised instead of raising a new one."""
    import escalations
    root = company_root(args)

    if args.list:
        # Deliberately does not require --project — "what's still waiting on
        # Riyan" is usually a cross-project question, and demanding a project
        # just to read a list is the same needless friction flagged
        # elsewhere (finos-5a: `company event` requiring --project with only
        # one project in cwd).
        events = EventLog(root).read()
        everything = escalations.all_escalations(events)
        items = list(everything.values())
        if args.list != "all":
            items = [e for e in items if e.get("status") == args.list]
        if args.project:
            items = [e for e in items if e.get("project") == args.project]
        items.sort(key=lambda e: (not e.get("blocking"), e.get("id", "")))
        emit({"ok": True, "filter": args.list, "count": len(items), "escalations": items})

    if not args.kind or not args.need:
        die("--kind and --need are required to raise an escalation "
           "(use --list to query existing ones instead)", 1)
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


def cmd_team(args):
    """`company team show <name>` — print a team bundle (teams/<name>.yaml).
    Read-only and advisory: never creates a task, loads a skill, or writes
    to the event log (see teams/README.md for why)."""
    import teams
    try:
        team = teams.load_team(args.name)
    except teams.TeamError as e:
        die(str(e), 1)
    problems = teams.validate(team)
    print(teams.render(team, problems))
    raise SystemExit(0)


# --- goals (ADR-006) -------------------------------------------------------

def _refuse_inside_worker(verb: str, group: str = "goal",
                          why: str = "goals are set and assessed by Riyan or the PM, "
                                     "never by the work being measured"):
    """A launched Tier-2 worker defining its own objective, or grading its own
    outcome, is self-certification; one scheduling a routine is a worker
    choosing its own future work. $COMPANY_ACTOR is set only by the launcher,
    so its presence is the one actor boundary enforceable today."""
    actor = os.environ.get("COMPANY_ACTOR")
    if actor:
        die(f"`company {group} {verb}` refuses to run inside a launched worker "
            f"($COMPANY_ACTOR={actor!r}) — {why}.", 2)


def _json_arg(name: str, raw: str | None):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        die(f"{name} is not valid JSON: {exc}")


def _goal_policy(root: Path) -> dict:
    """budgets.yaml's goal_budgets. A repo onboarded before ADR-006 has a
    copied budgets.yaml without the block, so the plugin default fills in."""
    import staffing
    import yaml
    policy = staffing.load_config(root, "budgets.yaml").get("goal_budgets")
    default = staffing.PLUGIN_CONFIG / "budgets.yaml"
    if policy is None and default.exists():
        policy = (yaml.safe_load(default.read_text(encoding="utf-8")) or {}).get("goal_budgets")
    return policy or {}


def _goal_views(root: Path) -> tuple[dict, dict]:
    import goals as goals_mod
    events = EventLog(root).read()
    tasks = taskstate.fold(events)
    return goals_mod.fold(events, tasks), tasks


def _goal_append(root: Path, args, event: str, data: dict, evidence: dict | None = None) -> dict:
    import goals as goals_mod
    try:
        written = goals_mod.append(root, event=event, actor=args.actor or "company-pm",
                                   data=data, evidence=evidence)
    except EvidenceError as exc:
        die(str(exc), 2)
    except ValueError as exc:
        die(str(exc), 1)
    taskstate.rebuild(root)
    return written


def cmd_goal_define(args):
    import goals as goals_mod
    _refuse_inside_worker("define")
    root = company_root(args)
    events = EventLog(root).read()
    if args.id:
        prior = goals_mod.definitions(events).get(args.id) or die(
            f"no goal {args.id!r} to revise — omit --id to define a new one")
        # A revision is written as a complete definition, so the fold's
        # "last wins" never has to merge partial events.
        data = {k: v for k, v in prior.items() if k not in ("closed", "reason")}
    else:
        if not args.level or not args.title:
            die("--level and --title are required to define a new goal")
        data = {"id": goals_mod.next_id(events)}
    for field, value in (("level", args.level), ("title", args.title), ("parent", args.parent),
                         ("measure", _json_arg("--measure", args.measure)),
                         ("budget", _json_arg("--budget", args.budget)),
                         ("reason", args.reason)):
        if value is not None:
            data[field] = value
    written = _goal_append(root, args, "GOAL_DEFINED", data)
    emit({"ok": True, "seq": written["seq"], "goal": data["id"], "revised": bool(args.id),
          "file": str(goals_mod.goal_path(root, data["id"]))})


def cmd_goal_link(args):
    _refuse_inside_worker("link")
    root = company_root(args)
    if bool(args.goal) == bool(args.unlink):
        die("give a goal id to link to, or --unlink — not both, not neither")
    data = {"goal": None if args.unlink else args.goal, "tasks": args.tasks}
    if args.reason:
        data["reason"] = args.reason
    known = taskstate.fold(EventLog(root).read())
    for tid in args.tasks:
        if tid not in known:
            print(f"warning: {tid!r} is not a task in this log — it will show as "
                  f"unknown_tasks, not be linked", file=sys.stderr)
    written = _goal_append(root, args, "GOAL_LINKED", data)
    emit({"ok": True, "seq": written["seq"], **data})


def cmd_goal_assess(args):
    _refuse_inside_worker("assess")
    root = company_root(args)
    data = {"goal": args.goal, "verdict": args.verdict}
    if args.measured_value is not None:
        try:
            value = json.loads(args.measured_value)
        except json.JSONDecodeError:
            value = args.measured_value
        data["measured"] = {"value": value, **({"as_of": args.as_of} if args.as_of else {})}
    if args.method:
        data["method"] = args.method
    written = _goal_append(root, args, "OUTCOME_ASSESSED", data, _parse_evidence(args.evidence))
    emit({"ok": True, "seq": written["seq"], **data, "evidence": written.get("evidence")})


def cmd_goal_close(args):
    _refuse_inside_worker("close")
    root = company_root(args)
    data = {"goal": args.goal, "disposition": args.disposition, "reason": args.reason}
    if args.superseded_by:
        data["superseded_by"] = args.superseded_by
    written = _goal_append(root, args, "GOAL_CLOSED", data)
    emit({"ok": True, "seq": written["seq"], **data})


def cmd_goal_tree(args):
    import goals as goals_mod
    root = company_root(args)
    views, _ = _goal_views(root)
    if args.json:
        emit({"goals": goals_mod.tree(views)})
    print(goals_mod.render_tree(views, _goal_policy(root)))
    raise SystemExit(0)


def cmd_goal_show(args):
    import goals as goals_mod
    root = company_root(args)
    views, tasks = _goal_views(root)
    goal = views.get(args.goal) or die(f"no goal {args.goal!r} in the event log")
    emit({**goal,
          "linked_tasks": [{k: tasks[t].get(k) for k in ("id", "status", "project", "title")}
                           for t in goal["tasks"]],
          "budget_status": goals_mod.budget_status(goal, _goal_policy(root))})


def cmd_goal_gaps(args):
    import goals as goals_mod
    root = company_root(args)
    views, tasks = _goal_views(root)
    emit(goals_mod.gaps(views, tasks, _goal_policy(root)))


ROUTINE_WHY = "routines are scheduled by Riyan or the PM, never by a worker choosing its own future work"


def _routine_now(args):
    import routines as routines_mod
    from datetime import datetime, timezone
    try:
        return routines_mod.parse_time(args.now) if args.now else datetime.now(timezone.utc)
    except ValueError as exc:
        die(f"--now is not an ISO 8601 time: {exc}")


def cmd_routine_define(args):
    import routines as routines_mod
    _refuse_inside_worker("define", "routine", ROUTINE_WHY)
    root = company_root(args)
    events = EventLog(root).read()
    if args.id and args.id in routines_mod.fold(events):
        # A redefinition is written whole, so the fold's "last wins" never
        # has to merge partial events.
        prior = routines_mod.fold(events)[args.id]
        data = {k: prior[k] for k in ("id", "cron", "spec", "enabled")}
    else:
        if not args.cron or not args.spec:
            die("--cron and --spec are required to define a new routine")
        data = {"id": args.id or routines_mod.next_id(events), "enabled": True}
    if args.spec:
        raw = args.spec
        if not raw.lstrip().startswith("{"):
            try:
                raw = Path(raw).read_text(encoding="utf-8")
            except OSError as exc:
                die(f"--spec: {exc}")
        data["spec"] = _json_arg("--spec", raw)
    for field, value in (("cron", args.cron), ("enabled", args.enabled), ("reason", args.reason)):
        if value is not None:
            data[field] = value
    try:
        written = routines_mod.define(root, actor=args.actor or "company-pm", data=data)
    except ValueError as exc:
        die(str(exc), 1)
    emit({"ok": True, "seq": written["seq"], "routine": data["id"],
          "enabled": data["enabled"], "cron": data["cron"]})


def cmd_routine_list(args):
    import routines as routines_mod
    views = routines_mod.fold(EventLog(company_root(args)).read())
    emit({"ok": True, "routines": [
        {"id": rid, "cron": r["cron"], "enabled": r["enabled"],
         "project": r["spec"].get("project"), "fired": len(r["fired"]),
         "last_fired_slot": r["fired"][-1]["slot"] if r["fired"] else None}
        for rid, r in sorted(views.items())]})


def cmd_routine_due(args):
    import routines as routines_mod
    now = _routine_now(args)
    views = routines_mod.fold(EventLog(company_root(args)).read())
    emit({"ok": True, "now": routines_mod.slot_id(now), "due": routines_mod.due(views, now)})


def cmd_routine_fire(args):
    """Turn due routines into PLANNED tasks, through plan_spec() — the same
    mandatory gates, duplicate-work and goal checks `company plan` applies.
    Never launches anything. A slot fires once: ROUTINE_FIRED is appended
    before the tasks, and EventLog.append refuses a second one for the same
    (routine, slot) under its lock, so a concurrent fire becomes a no-op."""
    import routines as routines_mod
    from eventlog import ORG_PROJECT, DuplicateFireError
    _refuse_inside_worker("fire", "routine", ROUTINE_WHY)
    if bool(args.id) == bool(args.due):
        die("give a routine id to fire, or --due — not both, not neither")
    root = company_root(args)
    log = EventLog(root)
    now = _routine_now(args)
    views = routines_mod.fold(log.read())

    if args.due:
        targets = routines_mod.due(views, now)
    else:
        r = views.get(args.id) or die(f"no routine {args.id!r} is defined")
        if not r["enabled"]:
            die(f"routine {args.id!r} is disabled")
        slot = routines_mod.latest_slot(routines_mod.parse_cron(r["cron"]),
                                        routines_mod.parse_time(r["revised_at"]), now)
        if not slot:
            die(f"routine {args.id!r} has no scheduled slot since it was defined")
        targets = [{"routine": args.id, "slot": routines_mod.slot_id(slot)}]

    results, refused = [], False
    for target in targets:
        rid, slot = target["routine"], target["slot"]
        result = {"routine": rid, "slot": slot}
        results.append(result)
        if slot in routines_mod.fired_slots(views[rid]):
            # Checked before planning: this slot's own tasks would otherwise
            # trip the duplicate-staffing refusal and read as a failure.
            result["skipped"] = "already fired for this slot"
            continue
        try:
            plan = plan_spec(root, routines_mod.instantiate(views[rid]["spec"], slot))
        except ValueError as exc:
            plan = {"ok": False, "refusal": str(exc)}
        if not plan["ok"]:
            refused = True
            result.update({"ok": False, "refusal": plan["refusal"]})
            continue
        tasks = plan["tasks"]
        try:
            log.append(make_event(event="ROUTINE_FIRED", actor=args.actor or "company-pm",
                                  project=ORG_PROJECT,
                                  data={"routine": rid, "slot": slot,
                                        "tasks": [t["id"] for t in tasks]}))
        except DuplicateFireError:
            result["skipped"] = "already fired for this slot"
            continue
        existing = taskstate.fold(log.read())
        for task in tasks:
            if task["id"] not in existing:
                log.append(make_event(event="TASK_CREATED", actor=args.actor or "company-pm",
                                      project=task["project"], task=task["id"],
                                      data=_task_created_data(task)))
        result.update({"ok": True, "tasks": [t["id"] for t in tasks],
                       "gates": {t["id"]: t["gates"] for t in tasks}})

    taskstate.rebuild(root)
    emit({"ok": not refused, "now": routines_mod.slot_id(now), "fired": results},
         3 if refused else 0)


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


def cmd_pause(args):
    import worker as worker_mod
    root = company_root(args)
    paused = worker_mod.pause_task(root, args.task_id)
    if paused is None:
        emit({"ok": False, "task": args.task_id,
              "note": "no live worker is running this task — nothing to pause"}, exit_code=1)
    emit({"ok": True, "paused": paused,
          "note": "worktree preserved; every other worker keeps running"})


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
    pl.add_argument("--allow-duplicate", action="store_true",
                    help="plan anyway despite a title closely matching a still-live "
                         "task already in this project (finos-5a, cost audit)")
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
    rn.add_argument("--max-turns", type=int, default=None,
                    help="default: 60 for implementers, 15 for gate roles "
                         "(role already has the diff, doesn't need to rediscover it)")
    rn.add_argument("--timeout", type=int, default=1800, help="wall-clock seconds")
    rn.add_argument("--max-concurrent", type=int,
                    help="override the concurrency cap from budgets.yaml")
    rn.add_argument("--verify", help="override the configured verify command")
    rn.add_argument("--model", help="override staffing.yaml's tier policy model for this "
                                     "launch only (e.g. opus) -- requires --why, recorded "
                                     "in WORKER_STARTED as a policy_override, D11")
    rn.add_argument("--effort", help="override staffing.yaml's tier policy effort for this "
                                      "launch only -- requires --why, recorded the same way")
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
    gg.add_argument("--max-turns", type=int, default=None,
                    help="default: 15 (gate roles already have the combined diff)")
    gg.add_argument("--timeout", type=int, default=1800, help="wall-clock seconds")
    gg.add_argument("--verify", help="override the configured verify command")
    gg.add_argument("--detach", action="store_true",
                    help="return immediately; the review survives this turn ending "
                         "(required when launching from a `claude -p` PM)")
    gg.add_argument("--max-concurrent", type=int,
                    help="override the concurrency cap from budgets.yaml")
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
    ct.add_argument("--json", action="store_true", help="accepted; output is always JSON")
    ct.set_defaults(fn=cmd_costs)

    bf = sub.add_parser("backfill-tokens",
                        help="reconstruct pre-capture runs' tokens from stdout.json (append-only)")
    bf.add_argument("--project")
    bf.add_argument("--dry-run", action="store_true", help="report what would be appended")
    bf.set_defaults(fn=cmd_backfill_tokens)

    ql = sub.add_parser("quarantine-lessons",
                        help="disregard leaked test-fixture lessons via an append-only correction")
    ql.add_argument("--project", default="p",
                    help="the fixture project the leaked lessons were recorded under (default: p)")
    ql.add_argument("--evidence-commit",
                    help="commit SHA that root-caused the leak (recorded as evidence)")
    ql.add_argument("--expect", type=int,
                    help="refuse unless the log holds exactly this many contaminated entries")
    ql.add_argument("--dry-run", action="store_true", help="report what would be quarantined")
    ql.set_defaults(fn=cmd_quarantine_lessons)

    bk = sub.add_parser("backup",
                        help="snapshot the event log outside the repo, under the append lock")
    bk.add_argument("--dest", help="backup directory (default: ~/.company-backups/<repo>-<hash>/)")
    bk.set_defaults(fn=cmd_backup)

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
    ls.add_argument("--source-ref",
                    help="optional citation, type:ref or a JSON object — type is one of "
                         "commit (a SHA), test_run (a TEST_RUN seq), review (a review "
                         "event seq), task (a task id); e.g. commit:6f2fea7, test_run:318, "
                         "task:T-14. Omit it when there is no single source — most "
                         "lessons are field observations")
    ls.add_argument("--search", help="list mode: only lessons whose pattern/fix shares "
                    "words with this text, best match first")
    ls.set_defaults(fn=cmd_lesson)

    es = sub.add_parser("escalate", help="ask the CEO for something the PM cannot do")
    es.add_argument("--kind",
                    choices=sorted(["human_action", "decision", "approval",
                                    "information", "risk"]))
    es.add_argument("--need", help="plainly, what you want")
    es.add_argument("--detail", help="context the CEO needs to answer")
    es.add_argument("--option", action="append", help="repeatable; for --kind decision")
    es.add_argument("--command", action="append",
                    help="repeatable; an exact command the CEO can run")
    es.add_argument("--task")
    es.add_argument("--project")
    es.add_argument("--actor")
    es.add_argument("--non-blocking", action="store_true")
    es.add_argument("--list", choices=["open", "resolved", "all"],
                    help="query instead of raising — 'what's still waiting on "
                         "Riyan' without reading every .md file by hand "
                         "(finos-52, cost audit 2026-09-14)")
    es.add_argument("--json", action="store_true", help="accepted; --list is always JSON")
    es.set_defaults(fn=cmd_escalate)

    rs = sub.add_parser("resolve", help="CEO: answer an escalation")
    rs.add_argument("id")
    rs.add_argument("--resolution", required=True)
    rs.add_argument("--project")
    rs.add_argument("--actor")
    rs.set_defaults(fn=cmd_resolve)

    tm = sub.add_parser("team", help="read-only team-bundle info (teams/<name>.yaml)")
    tmsub = tm.add_subparsers(dest="teamcmd", required=True)
    tms = tmsub.add_parser("show", help="print a team bundle, flagging any stale references")
    tms.add_argument("name")
    tms.set_defaults(fn=cmd_team)

    go = sub.add_parser("goal", help="mission -> objectives -> key results, and outcomes (ADR-006)")
    gosub = go.add_subparsers(dest="goalcmd", required=True)
    gd = gosub.add_parser("define", help="define a goal, or revise one with --id and --reason")
    gd.add_argument("--id", help="revise this existing goal (default: assign the next G-NNN)")
    gd.add_argument("--level", choices=["mission", "objective", "key_result"])
    gd.add_argument("--title")
    gd.add_argument("--parent", help="the mission (for an objective) or an objective (for a key_result)")
    gd.add_argument("--measure", help='JSON, required for a key_result: {"metric","unit",'
                                      '"baseline","target","direction","how"}')
    gd.add_argument("--budget", help='JSON, e.g. {"output_tokens": 3000000} — report-only')
    gd.add_argument("--reason", help="required when revising")
    gd.add_argument("--actor", help="default: company-pm")
    gd.set_defaults(fn=cmd_goal_define)
    gk = gosub.add_parser("link", help="link tasks to a goal (or --unlink)")
    gk.add_argument("goal", nargs="?")
    gk.add_argument("--tasks", nargs="+", required=True)
    gk.add_argument("--unlink", action="store_true", help="clear these tasks' goal")
    gk.add_argument("--reason", help="required when any task is already terminal (retro-linking)")
    gk.add_argument("--actor", help="default: company-pm")
    gk.set_defaults(fn=cmd_goal_link)
    ga = gosub.add_parser("assess", help="record whether a goal's outcome was achieved, with evidence")
    ga.add_argument("goal")
    ga.add_argument("--verdict", required=True, choices=["achieved", "not_achieved", "inconclusive"])
    ga.add_argument("--evidence", required=True,
                    help="the measurement: a path or JSON object — a bare commit SHA is refused")
    ga.add_argument("--measured-value", help="required for a key_result unless inconclusive")
    ga.add_argument("--as-of", help="when the measurement was taken")
    ga.add_argument("--method", help="how it was measured")
    ga.add_argument("--actor", help="default: company-pm")
    ga.set_defaults(fn=cmd_goal_assess)
    gc = gosub.add_parser("close", help="close an abandoned or superseded goal")
    gc.add_argument("goal")
    gc.add_argument("--disposition", required=True, choices=["abandoned", "superseded"])
    gc.add_argument("--superseded-by")
    gc.add_argument("--reason", required=True)
    gc.add_argument("--actor", help="default: company-pm")
    gc.set_defaults(fn=cmd_goal_close)
    gt = gosub.add_parser("tree", help="the goal tree with delivery / outcome / spend")
    gt.add_argument("--json", action="store_true")
    gt.set_defaults(fn=cmd_goal_tree)
    gs = gosub.add_parser("show", help="one goal: tasks, assessments, flags, budget vs. spend")
    gs.add_argument("goal")
    gs.add_argument("--json", action="store_true", help="accepted; output is always JSON")
    gs.set_defaults(fn=cmd_goal_show)
    gg2 = gosub.add_parser("gaps", help="ungoaled tasks, unassessed and suspect outcomes")
    gg2.add_argument("--json", action="store_true", help="accepted; output is always JSON")
    gg2.set_defaults(fn=cmd_goal_gaps)

    ro = sub.add_parser("routine", help="recurring work: a plan spec on a cron schedule")
    rosub = ro.add_subparsers(dest="routinecmd", required=True)
    rd = rosub.add_parser("define", help="define a routine, or redefine one with --id and --reason")
    rd.add_argument("--id", help="R-NNN; redefines it if it exists (default: the next R-NNN)")
    rd.add_argument("--cron", help='5-field UTC cron, e.g. "*/15 * * * *" or "0 3 * * 1-5"')
    rd.add_argument("--spec", help="plan spec (same shape `company plan` takes): a JSON file path or inline JSON")
    en = rd.add_mutually_exclusive_group()
    en.add_argument("--enable", dest="enabled", action="store_true", default=None)
    en.add_argument("--disable", dest="enabled", action="store_false", default=None,
                    help="stop it firing — also how a routine is retired")
    rd.add_argument("--reason", help="required when redefining")
    rd.add_argument("--actor", help="default: company-pm")
    rd.set_defaults(fn=cmd_routine_define)
    rl = rosub.add_parser("list", help="every routine: cron, enabled, last fired slot")
    rl.set_defaults(fn=cmd_routine_list)
    ru = rosub.add_parser("due", help="which routines are due now (read-only)")
    ru.add_argument("--now", help="ISO 8601 time to evaluate at instead of the clock (UTC if naive)")
    ru.set_defaults(fn=cmd_routine_due)
    rf = rosub.add_parser("fire", help="turn a due routine into PLANNED tasks via the plan checks; never runs them")
    rf.add_argument("id", nargs="?")
    rf.add_argument("--due", action="store_true", help="fire every routine that is due")
    rf.add_argument("--now", help="ISO 8601 time to evaluate at instead of the clock (UTC if naive)")
    rf.add_argument("--actor", help="default: company-pm")
    rf.set_defaults(fn=cmd_routine_fire)

    gl = sub.add_parser("gallery", help="plan or open the tmux viewing gallery")
    gl.add_argument("--project")
    gl.add_argument("--script", action="store_true", help="print the tmux script")
    gl.add_argument("--open", action="store_true", help="build and attach now")
    gl.set_defaults(fn=cmd_gallery)

    st = sub.add_parser("stop", help="halt every worker; preserve every worktree")
    st.add_argument("--project")
    st.set_defaults(fn=cmd_stop)

    pu = sub.add_parser("pause", help="halt the one worker on a task; every other worker keeps running")
    pu.add_argument("task_id")
    pu.set_defaults(fn=cmd_pause)

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
