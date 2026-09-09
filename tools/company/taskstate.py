"""Task views derived by replaying the event log, plus the Evidence Rule (D6).

Nothing here mutates the log. `fold()` is a pure function of the event list,
which is what makes `company rebuild --verify` meaningful: if replay cannot
reproduce the task files byte-for-byte, the state model is broken.
"""

from __future__ import annotations

from pathlib import Path

from eventlog import GATE_EVENT, EventLog, canonical

LIFECYCLE = [
    "DRAFT", "PLANNED", "READY", "IN_PROGRESS", "IMPLEMENTATION_READY",
    "REVIEW", "QA", "SECURITY_REVIEW", "INTEGRATION", "DONE",
]
OFF_PATH = {"WAITING", "BLOCKED", "FAILED", "RETRYING", "ESCALATED", "ABANDONED"}

# Events that move a task along on their own. Everything else is recorded but
# does not advance state; `company task advance` is the only other mover.
IMPLIED_STATUS = {
    "TASK_ASSIGNED": "READY",
    "WORKER_STARTED": "IN_PROGRESS",
    "IMPLEMENTATION_READY": "IMPLEMENTATION_READY",
    "REVIEW_REQUESTED": "REVIEW",
    "DEPENDENCY_WAITING": "WAITING",
    "TASK_BLOCKED": "BLOCKED",
    "TASK_FAILED": "FAILED",
    "ESCALATION_RAISED": "ESCALATED",
    "MERGE_READY": "INTEGRATION",
    "TASK_COMPLETED": "DONE",
}

FAIL_GATE = {
    "REVIEW_FAILED": "review",
    "QA_FAILED": "qa",
    "SECURITY_REVIEW_FAILED": "security",
}

FIELDS_FROM_DATA = (
    "title", "tier", "owner", "department", "priority", "depends_on", "blocks",
    "owned_globs", "forbidden_globs", "branch", "worktree", "gates",
    "acceptance_criteria", "base",
    # gate_group (efficiency addendum v1, 2026-08-24): tasks sharing this
    # value get one combined gate launch (`company gate-group`) instead of
    # one each. Purely orchestration metadata — check_done()'s Evidence
    # Rule check is unchanged either way, each task still needs its own
    # verdict event.
    "gate_group",
)


def fold(events: list[dict]) -> dict[str, dict]:
    """Replay events into task views. Pure — no I/O, no clock, no randomness."""
    tasks: dict[str, dict] = {}

    for ev in events:
        tid = ev.get("task")
        if not tid:
            # A GROUP gate launch (`company gate-group`) writes one
            # WORKER_STARTED for the whole group: no `task` field, the members
            # listed in data.tasks. Skipping it outright left every
            # group-gated task with no launch record, so check_done's
            # actor-role binding could never be satisfied and the task could
            # never reach DONE however genuinely it had been reviewed —
            # measured on finos 2026-09-09: 7 freshly gated tasks and ~52
            # historical ones, all uncloseable by construction.
            #
            # Same trust guarantee as the per-task case: this event is written
            # by worker.py before the worker's subprocess exists, so it is not
            # forgeable by the worker it describes.
            data = ev.get("data") or {}
            if ev.get("event") == "WORKER_STARTED" and data.get("role"):
                for member in data.get("tasks") or []:
                    if member in tasks:
                        tasks[member].setdefault(
                            "worker_roles", {})[ev.get("actor")] = data["role"]
            continue
        name = ev.get("event")
        data = ev.get("data") or {}

        if tid not in tasks:
            tasks[tid] = {
                "id": tid,
                "project": ev.get("project"),
                "status": "DRAFT",
                "evidence": {},
                "criteria_met": [],
                "created_at": ev["ts"],
                "updated_at": ev["ts"],
            }
        task = tasks[tid]
        task["updated_at"] = ev["ts"]

        if name == "TASK_CREATED":
            for field in FIELDS_FROM_DATA:
                if field in data:
                    task[field] = data[field]
            task["status"] = "PLANNED"

        elif name == "TASK_ASSIGNED":
            task["owner"] = data.get("owner", task.get("owner"))
            for field in ("branch", "worktree", "tier"):
                if field in data:
                    task[field] = data[field]

        elif name == "IMPLEMENTATION_READY":
            task["evidence"]["diff"] = (ev.get("evidence") or {}).get("commit")

        elif name == "TEST_RUN":
            # A green run always counts. A red run counts only when the repo was
            # already red and this change made it no worse — see baseline.py.
            # Judged at fold time by comparing against the baseline in force.
            task["last_test_run"] = {
                "exit_code": data.get("exit_code"),
                "failures": data.get("failures"),
                "actor": ev.get("actor"),
                "cmd": data.get("cmd"),
            }
            if data.get("exit_code") == 0:
                task["evidence"]["tests"] = f"exit {data['exit_code']}"
                task["evidence"]["tests_actor"] = ev.get("actor")
                task.pop("last_test_failure", None)
            else:
                task["evidence"].pop("tests", None)
                task["last_test_failure"] = (
                    f"exit {data.get('exit_code')}"
                    + (f", {data['failures']} failures" if data.get("failures") is not None else "")
                )

        elif name in GATE_EVENT.values():
            gate = next(g for g, e in GATE_EVENT.items() if e == name)
            task["evidence"][gate] = f"{name} by {ev.get('actor')}"
            task["evidence"][f"{gate}_actor"] = ev.get("actor")

        elif name in FAIL_GATE:
            gate = FAIL_GATE[name]
            task["evidence"].pop(gate, None)
            task["evidence"].pop(f"{gate}_actor", None)
            # A rejected gate is not the same as an unreviewed one. Recording
            # the rejection is what lets `status` say "failed" instead of
            # "pending", which are very different situations for an operator.
            task.setdefault("gates_failed", {})[gate] = {
                "actor": ev.get("actor"),
                "at": ev["ts"],
                "findings": data.get("findings") or data.get("reasons") or [],
            }

        if name in GATE_EVENT.values():
            task.get("gates_failed", {}).pop(
                next(g for g, e in GATE_EVENT.items() if e == name), None)

        elif name == "CONTRACT_PUBLISHED":
            task.setdefault("contracts", []).append(data.get("name", "unnamed"))

        elif name == "HANDOFF_WRITTEN":
            task.setdefault("handoffs", []).append(data.get("to", "unknown"))

        elif name == "WORKER_STARTED":
            # The trusted anchor for the actor-role binding check below: this
            # event is written by worker.py BEFORE the worker's own subprocess
            # exists, so a worker cannot forge an entry for itself the way it
            # can override $COMPANY_ACTOR on any of its own Bash commands.
            role = data.get("role")
            if role:
                task.setdefault("worker_roles", {})[ev.get("actor")] = role

        elif name == "MERGED":
            task["evidence"]["merged"] = (ev.get("evidence") or {}).get("commit")

        elif name == "STATUS_CHANGED":
            to = data.get("to")
            if to is not None:
                task["status"] = to
            else:
                # A malformed event must never crash replay — fold() runs
                # from scratch on every call, so one bad line anywhere in a
                # project's log would permanently wedge the CLI for that
                # project (and, since this file is shared, for every other
                # project on the machine too). Surface the anomaly on the
                # task view instead of silently swallowing it or crashing.
                task.setdefault("_malformed_events", []).append(
                    {"seq": ev.get("seq"), "event": name, "data": data})

        if data.get("criteria_met"):
            for c in data["criteria_met"]:
                if c not in task["criteria_met"]:
                    task["criteria_met"].append(c)

        implied = IMPLIED_STATUS.get(name)
        if implied and name != "STATUS_CHANGED":
            task["status"] = implied

    return tasks


def task_path(company_root: Path, tid: str) -> Path:
    return Path(company_root) / "tasks" / f"{tid}.json"


def write_views(company_root: Path, tasks: dict[str, dict]) -> list[Path]:
    out = []
    d = Path(company_root) / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    for tid, task in tasks.items():
        p = d / f"{tid}.json"
        p.write_text(canonical(task), encoding="utf-8")
        out.append(p)
    return out


def rebuild(company_root: Path, verify: bool = False) -> tuple[int, list[str]]:
    """Replay the log into task views. With verify=True, compare instead of write.

    Returns (task_count, mismatches). A non-empty mismatch list means the task
    files on disk cannot be reproduced from the event log, which invalidates
    the entire state model.
    """
    tasks = fold(EventLog(company_root).read())
    if not verify:
        write_views(company_root, tasks)
        return len(tasks), []

    mismatches = []
    for tid, task in tasks.items():
        p = task_path(company_root, tid)
        expected = canonical(task)
        if not p.exists():
            mismatches.append(f"{p}: missing — replay produces it, disk does not have it")
        elif p.read_text(encoding="utf-8") != expected:
            mismatches.append(f"{p}: differs from replay")

    known = {f"{tid}.json" for tid in tasks}
    tdir = Path(company_root) / "tasks"
    if tdir.exists():
        for stray in sorted(tdir.glob("*.json")):
            if stray.name not in known:
                mismatches.append(f"{stray}: on disk but no events produce it")
    return len(tasks), mismatches


# --- The Evidence Rule ------------------------------------------------------

class EvidenceRuleViolation(Exception):
    pass


def check_done(task: dict, baseline: dict | None = None,
               gate_roles: dict[str, str] | None = None) -> list[str]:
    """Return the reasons this task may NOT enter DONE. Empty list == allowed.

    Checked against the event-derived view alone. No agent's assertion counts.

    `baseline` is the repo's pre-existing verify result. Without one, a green
    run is required. With a red baseline, a run that adds no failures is
    accepted — otherwise a half-built repo could never close a task, and the
    only escapes would be fixing unrelated code or lying.

    `gate_roles` is quality-gates.yaml's gate -> actor_role mapping. Without
    it, only `actor != owner` is checked (the pre-existing, forgeable check —
    a worker can set $COMPANY_ACTOR to any string that isn't its own owner id
    and self-certify). WITH it, the actor is additionally required to have a
    WORKER_STARTED record on this task, written by the trusted launcher, whose
    role matches what the gate requires. A live-reproduced bypass: any
    Tier-2 worker could run `COMPANY_ACTOR=anything company event <task>
    REVIEW_PASSED --evidence "exit 0"` and satisfy the review gate with zero
    real review, because nothing checked that "anything" was ever launched as
    a code-reviewer on this task. Callers should always pass gate_roles;
    the None default exists only so this function has no required config
    dependency of its own.
    """
    reasons = []
    ev = task.get("evidence") or {}
    owner = task.get("owner")

    if not ev.get("diff"):
        reasons.append(
            "no diff evidence: no IMPLEMENTATION_READY event carrying a commit SHA"
        )

    if not ev.get("tests"):
        last = task.get("last_test_run")
        if last is None:
            reasons.append("no test evidence: no TEST_RUN event at all")
        else:
            import baseline as baseline_mod
            ok, why = baseline_mod.compare(baseline, last)
            if ok:
                task.setdefault("evidence", {})["tests"] = (
                    f"exit {last['exit_code']} (no regression vs baseline)")
                task["evidence"]["tests_actor"] = last.get("actor")
            else:
                reasons.append(why)

    for gate in task.get("gates") or []:
        event_name = GATE_EVENT.get(gate)
        if not event_name:
            reasons.append(f"unknown gate {gate!r} — not in the quality-gate table")
            continue
        if not ev.get(gate):
            reasons.append(f"gate {gate!r} not satisfied: no {event_name} event")
            continue
        actor = ev.get(f"{gate}_actor")
        if actor and owner and actor == owner:
            reasons.append(
                f"gate {gate!r} was self-certified: {event_name} was authored by "
                f"{actor!r}, who is also the task owner. A gated change requires a "
                f"review from a different worker."
            )
            continue

        required_role = (gate_roles or {}).get(gate)
        if actor and required_role:
            actual_role = (task.get("worker_roles") or {}).get(actor)
            if actual_role != required_role:
                reasons.append(
                    f"gate {gate!r} actor {actor!r} has no verified {required_role!r} "
                    f"launch record for this task"
                    + (f" (was launched as {actual_role!r})" if actual_role else "")
                    + f". {event_name} was accepted from an actor the trusted launcher "
                    f"never started as {required_role!r} on this task — a self-reported "
                    f"actor string is not evidence of who actually reviewed it."
                )
    return reasons
