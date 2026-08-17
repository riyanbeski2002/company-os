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


def project_progress(tasks: list[dict]) -> str:
    values = [progress(t) for t in tasks]
    known = [v for v in values if v is not None]
    if not known:
        return "unknown"
    return f"{round(100 * sum(known) / len(known))}%"


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


def gates_with_no_verdict(events: list[dict]) -> dict[str, str]:
    """Tasks whose gate worker exited without a PASSED/FAILED verdict.

    KNOWN_ISSUES #3: this looked identical to success — a gate worker ending
    cleanly with no verdict got silently re-run under a new actor name and
    paid for twice. GATE_NO_VERDICT events (worker.py) are the fix; this is
    what surfaces them rather than leaving them buried in the raw log.
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
