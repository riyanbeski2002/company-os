"""Operator and executive views (§12).

Both render derived state only. Progress is the fraction of acceptance criteria
verified by evidence — never a model's feeling about how far along it is. When
progress cannot be computed, these print "unknown" rather than a number that
would be believed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from eventlog import GATE_EVENT

DONE_ISH = {"DONE", "MERGED"}

MARK = {"done": "✓", "active": "●", "waiting": "○", "bad": "✗"}


def progress(task: dict) -> float | None:
    criteria = task.get("acceptance_criteria")
    if not criteria:
        return None
    met = [c for c in criteria if c in (task.get("criteria_met") or [])]
    if task.get("status") in DONE_ISH:
        return 1.0
    if not met:
        return 0.0
    return len(met) / len(criteria)


def project_progress_pct(tasks: list[dict]) -> int | None:
    """Mean known per-task progress as 0-100, or None when no task's
    progress can be computed — never a stand-in number."""
    values = [progress(t) for t in tasks]
    known = [v for v in values if v is not None]
    if not known:
        return None
    return round(100 * sum(known) / len(known))


def project_progress(tasks: list[dict]) -> str:
    pct = project_progress_pct(tasks)
    return "unknown" if pct is None else f"{pct}%"


def _age(ts: str) -> str:
    try:
        then = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "?"
    secs = int((datetime.now(timezone.utc) - then).total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h"


def workers_that_ended_cleanly(events: list[dict]) -> set[str]:
    """Actors whose last lifecycle event is a terminal one.

    A worker that finished and wrote WORKER_EXITED left a dead pid file behind,
    exactly like a crashed one. Only the log distinguishes them, so liveness
    alone must never be the stall signal.
    """
    last: dict[str, str] = {}
    for ev in events:
        name = ev.get("event")
        if name in ("WORKER_STARTED", "WORKER_EXITED", "TASK_FAILED"):
            last[ev.get("actor", "")] = name
    return {a for a, n in last.items() if n in ("WORKER_EXITED", "TASK_FAILED")}


def gates_with_no_verdict(events: list[dict], tasks: list[dict] | None = None) -> dict[str, str]:
    """Tasks whose gate worker exited without a PASSED/FAILED verdict.

    KNOWN_ISSUES #3: this looked identical to success — a gate worker ending
    cleanly with no verdict got silently re-run under a new actor name and
    paid for twice. GATE_NO_VERDICT events (worker.py) are the fix; this is
    what surfaces them rather than leaving them buried in the raw log.

    A GATE_NO_VERDICT is only actionable while the task hasn't otherwise
    resolved. Without this, a task that later got a clean re-run (or landed
    entirely, e.g. via a different gate) stayed permanently flagged as
    STALLED forever, even after reaching DONE/MERGED — a real bug, not a
    ledger-update someone forgot: found 12 Sep when a from-scratch audit
    showed all 37 "STALLED" tasks were in fact already merged to main, every
    one traced back to exactly this. A task is only genuinely still waiting
    on this verdict if its current status is not yet DONE_ISH.
    """
    out = {}
    for ev in events:
        if ev.get("event") != "GATE_NO_VERDICT":
            continue
        tid = ev.get("task")
        data = ev.get("data") or {}
        out[tid] = (
            f"{ev.get('actor')} ({data.get('role')}) exited cleanly but emitted "
            f"neither of {data.get('expected_one_of')} — the review did not happen, "
            f"even though nothing failed loudly. Investigate before re-running the gate."
        )
    if tasks is not None:
        done_ids = {t["id"] for t in tasks if t.get("status") in DONE_ISH}
        out = {tid: why for tid, why in out.items() if tid not in done_ids}
    return out


def detect_stalls(company_root, tasks: list[dict], events=None) -> dict[str, str]:
    """Evidence-based stall detection (§8), not impatience.

    A task is stalled when its worker process is gone but no terminal event was
    ever written. `kill -9` produces exactly this: SIGKILL skips SessionEnd, so
    the log's last word is WORKER_STARTED and the task looks busy forever.

    Long-running-but-productive work is never flagged — this checks liveness,
    not elapsed time.
    """
    import os
    from pathlib import Path

    stalls = {}
    ended = workers_that_ended_cleanly(events or [])
    workers = Path(company_root) / "state" / "workers"
    for task in tasks:
        if task.get("status") not in ("IN_PROGRESS", "REVIEW", "QA", "SECURITY_REVIEW"):
            continue
        owner = task.get("owner")
        if not owner or owner in ended:
            continue
        pidfile = workers / owner / "pid"
        if not pidfile.exists():
            continue
        try:
            pid = int(pidfile.read_text().strip())
        except (ValueError, OSError):
            continue
        try:
            os.kill(pid, 0)          # liveness probe only; sends no signal
        except ProcessLookupError:
            stalls[task["id"]] = (
                f"worker {owner} (pid {pid}) is gone and never wrote a terminal "
                f"event — killed, crashed, or OOM. Worktree is preserved; resume "
                f"or reassign."
            )
        except PermissionError:
            pass                     # alive, owned by another user
    return stalls


STALE_TASK_AGE_S = 48 * 3600  # 2 days with no event at all while "active".
# Complements detect_stalls() above, which only fires when this checkout
# still has a pid file to check against — cost audit, 2026-09-14: finos-52
# found 7 of 10 IN_PROGRESS tasks hadn't been touched in 3 weeks, and none
# of them were caught, because by the time anyone looks, whatever process
# trail they left is long gone (or never existed here — a different machine,
# a since-cleaned state dir). This needs no process check: staleness is just
# how long nothing happened, read straight off the task's own updated_at.
def detect_stale_tasks(tasks: list[dict], max_age_s: int = STALE_TASK_AGE_S) -> dict[str, str]:
    from datetime import datetime, timezone

    out = {}
    now = datetime.now(timezone.utc)
    for task in tasks:
        if task.get("status") not in ("IN_PROGRESS", "REVIEW", "QA", "SECURITY_REVIEW"):
            continue
        ts = task.get("updated_at")
        try:
            then = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        age_s = (now - then).total_seconds()
        if age_s > max_age_s:
            out[task["id"]] = (
                f"no event in {_age(ts)} while status is {task['status']!r} — "
                f"almost certainly a dead worker whose process trail is already "
                f"gone. Resume or reassign."
            )
    return out


SUSPICIOUS_TASK_AGE_S = 24 * 3600  # 1 day silent on an active task: not yet
# "almost certainly dead" (that's STALE_TASK_AGE_S/detect_stale_tasks's 48h),
# but worth a look before it gets there.


def classify_staleness(task: dict, now, blocking_escalation: dict | None = None,
                        suspicious_age_s: int = SUSPICIOUS_TASK_AGE_S,
                        critical_age_s: int = STALE_TASK_AGE_S) -> str:
    """Tiered silence-since-last-event classification (paperclip donation,
    2026-10-21 -- paperclip's active-run-watchdog classifies ok/suspicious/
    critical by time since a run's last output, rather than detect_stale_tasks'
    single binary cutoff here). Returns "ok", "suspicious", or "critical".

    `now` is always passed in, never read internally, so this stays a pure
    function testable without mocking the clock -- same discipline as every
    other fold/evaluate function in this codebase.

    `blocking_escalation`, when given, is this system's own real suppression
    signal (escalations.blocking_escalation_for_task), scoped down from
    paperclip's four-way snoozed/recovery-origin/blocked-source/dismissed
    gate to the one bucket company-os actually has data for: a task silent
    because it is legitimately waiting on a human decision never escalates
    past "suspicious", because reaching that wait was correct, not a failure.
    """
    if task.get("status") not in ("IN_PROGRESS", "REVIEW", "QA", "SECURITY_REVIEW"):
        return "ok"
    ts = task.get("updated_at")
    try:
        then = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "ok"
    age_s = (now - then).total_seconds()
    if age_s <= suspicious_age_s:
        return "ok"
    if blocking_escalation is not None:
        return "suspicious"
    return "critical" if age_s > critical_age_s else "suspicious"


def detect_early_warning_tasks(tasks: list[dict], blocking_escalations: dict, now=None) -> dict[str, str]:
    """The "suspicious" tier of classify_staleness, surfaced as its own
    dict — same shape as detect_stale_tasks/detect_resting_tasks above, so
    cmd_status can treat it identically. Deliberately excludes anything
    classify_staleness would call "critical": that's detect_stale_tasks'
    job, this one is strictly the earlier warning.

    `blocking_escalations` maps task id -> blocking escalation dict (or
    absent/None), the caller's job since it already has the event log.
    """
    out = {}
    now = now or datetime.now(timezone.utc)
    for task in tasks:
        tier = classify_staleness(task, now, blocking_escalation=blocking_escalations.get(task["id"]))
        if tier == "suspicious":
            out[task["id"]] = (
                f"no event in {_age(task.get('updated_at'))} while status is "
                f"{task['status']!r} — not yet critical, worth a look before it is."
            )
    return out


RESTING_TASK_AGE_S = 24 * 3600  # 1 day with no revisit while deliberately off-path.
# detect_stale_tasks/detect_stalls above only ever fire on IN_PROGRESS/REVIEW/
# QA/SECURITY_REVIEW — work that is SUPPOSED to be actively running, so
# silence there is itself the anomaly. BLOCKED/WAITING/ESCALATED/FAILED are
# the opposite case: reaching one of them was often the CORRECT decision, so
# nothing here claims the stop was wrong. It generalizes GATE_NO_VERDICT
# (worker.py) — a gate role going silent is one specific way a task stops
# moving without anyone noticing — to any resting status: the failure mode
# this catches is nobody ever coming back to look, not the stop itself.
# Modeled on paperclip's "task watchdog" concept (github.com/paperclipai/
# paperclip), scoped down for a single-user CLI with no issue-tree/subtree
# concept to hang a per-task opt-in flag on — running `company status` at all
# is the opt-in here, the same way `company advise` is opt-in by invocation.
RESTING_STATUSES = {"BLOCKED", "WAITING", "ESCALATED", "FAILED"}


def detect_resting_tasks(tasks: list[dict], max_age_s: int = RESTING_TASK_AGE_S) -> dict[str, str]:
    from datetime import datetime, timezone

    out = {}
    now = datetime.now(timezone.utc)
    for task in tasks:
        if task.get("status") not in RESTING_STATUSES:
            continue
        ts = task.get("updated_at")
        try:
            then = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        age_s = (now - then).total_seconds()
        if age_s > max_age_s:
            out[task["id"]] = (
                f"resting at {task['status']!r} for {_age(ts)} with nobody revisiting it — "
                f"reaching this status may have been correct, but confirm it's still "
                f"waiting on something real, not just forgotten."
            )
    return out


def _mark(task: dict) -> str:
    status = task.get("status")
    if status in DONE_ISH:
        return MARK["done"]
    if status in ("FAILED", "BLOCKED", "ESCALATED"):
        return MARK["bad"]
    if status in ("IN_PROGRESS", "REVIEW", "QA", "SECURITY_REVIEW", "INTEGRATION"):
        return MARK["active"]
    return MARK["waiting"]


def status(project: str, tasks: list[dict], escalations: list[str],
           stalls: dict[str, str] | None = None) -> str:
    stalls = stalls or {}
    lines = [f"{project} — {project_progress(tasks)}"]

    if stalls:
        lines.append("")
        lines.append("  STALLED")
        for tid, why in stalls.items():
            lines.append(f"    ! {tid}: {why}")

    # Waiting on the CEO comes first. A blocking ask nobody notices is the same
    # as being stuck, and the point of asking was not to be stuck.
    blocking = [e for e in escalations if e.get("blocking")]
    waiting = [e for e in escalations if not e.get("blocking")]

    for group, label in ((blocking, "NEEDS YOU — BLOCKING"), (waiting, "NEEDS YOU")):
        if not group:
            continue
        lines.append("")
        lines.append(f"  {label}")
        for e in group:
            lines.append(f"    {e['id']}  [{e['kind']}]  {e['need']}")
            if e.get("task"):
                lines.append(f"          on {e['task']}, raised by {e.get('raised_by')}")
            for i, opt in enumerate(e.get("options") or [], 1):
                lines.append(f"          {i}. {opt}")
            for cmd in e.get("commands") or []:
                lines.append(f"          $ {cmd}")
            lines.append(f"          → company resolve {e['id']} --resolution \"...\"")

    lines.append("")
    for task in sorted(tasks, key=lambda t: t["id"]):
        dept = (task.get("department") or "—").split("/")[-1]
        detail = []
        ev = task.get("evidence") or {}
        if ev.get("diff"):
            detail.append(f"{MARK['done']} committed")
        if ev.get("tests"):
            detail.append(f"{MARK['done']} tests ({ev['tests']})")
        elif task.get("last_test_failure"):
            detail.append(f"{MARK['bad']} tests ({task['last_test_failure']})")
        failed = task.get("gates_failed") or {}
        for gate in task.get("gates") or []:
            if ev.get(gate):
                detail.append(f"{MARK['done']} {gate} by {ev.get(f'{gate}_actor')}")
            elif gate in failed:
                n = len(failed[gate].get("findings") or [])
                detail.append(f"{MARK['bad']} {gate} FAILED by {failed[gate]['actor']}"
                              + (f" ({n} findings)" if n else ""))
            else:
                detail.append(f"{MARK['waiting']} {gate} pending")

        lines.append(
            f"  {_mark(task)} {task['id']}  {dept:<10} {task.get('title', '')}"
        )
        shown = "STALLED" if task["id"] in stalls else task["status"]
        lines.append(
            f"      {shown:<20} {_age(task.get('updated_at', ''))} since last event"
        )
        if detail:
            lines.append("      " + " · ".join(detail))

    blocked = [t["id"] for t in tasks if t.get("status") in ("BLOCKED", "FAILED")]
    lines.append("")
    lines.append(f"  Blocked  {', '.join(blocked) if blocked else 'none'}"
                 f"      Escalations  {len(escalations) or 'none'}")
    lines.append(f"  Next     {_next_action(tasks, escalations)}")
    return "\n".join(lines)


def _next_action(tasks: list[dict], escalations: list[dict] | None = None) -> str:
    for e in escalations or ():
        if e.get("blocking"):
            return f"you — {e['id']}: {e['need']}"
    for task in sorted(tasks, key=lambda t: t["id"]):
        ev = task.get("evidence") or {}
        if task.get("status") in DONE_ISH:
            continue
        failed = task.get("gates_failed") or {}
        if failed:
            gate, info = next(iter(failed.items()))
            n = len(info.get("findings") or [])
            return (f"{task['id']} → fix {n} {gate} finding{'s' if n != 1 else ''} "
                    f"from {info['actor']}, then re-review")
        if not ev.get("diff"):
            return f"{task['id']} → implementation"
        if not ev.get("tests"):
            return f"{task['id']} → green test run"
        for gate in task.get("gates") or []:
            if not ev.get(gate):
                return f"{task['id']} → {gate} ({GATE_EVENT[gate]} from an independent actor)"
        return f"{task['id']} → integration"
    return "nothing outstanding"


def report(project: str, tasks: list[dict], escalations: list[dict] | None = None) -> str:
    """Executive summary: outcomes, not activity. No agent chatter."""
    done = [t for t in tasks if t.get("status") in DONE_ISH]
    outstanding = [t for t in tasks if t not in done]

    lines = [f"# {project}", "",
             f"**{project_progress(tasks)} complete** — {len(done)} of {len(tasks)} "
             f"work items delivered.", ""]

    waiting_on_you = [e for e in (escalations or ()) if e.get("blocking")]
    if waiting_on_you:
        lines.append("## Waiting on you")
        for e in waiting_on_you:
            lines.append(f"- **{e['need']}** ({e['kind']}, {e['id']})")
        lines.append("")

    if done:
        lines.append("## Delivered")
        for t in sorted(done, key=lambda t: t["id"]):
            ev = t.get("evidence") or {}
            proof = []
            if ev.get("tests"):
                proof.append(f"tests {ev['tests']}")
            for gate in t.get("gates") or []:
                if ev.get(gate):
                    proof.append(f"{gate} passed independently")
            lines.append(f"- **{t.get('title')}** — {', '.join(proof) or 'no evidence recorded'}")
        lines.append("")

    if outstanding:
        lines.append("## Outstanding")
        for t in sorted(outstanding, key=lambda t: t["id"]):
            p = progress(t)
            pct = "unknown" if p is None else f"{round(p * 100)}%"
            lines.append(f"- **{t.get('title')}** — {t['status'].lower().replace('_', ' ')} ({pct})")
        lines.append("")

    lines.append("## Next")
    lines.append(f"- {_next_action(tasks, escalations)}")
    return "\n".join(lines)
