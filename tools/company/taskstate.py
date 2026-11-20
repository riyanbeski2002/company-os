"""Task views derived by replaying the event log, plus the Evidence Rule (D6).

Nothing here mutates the log. `fold()` is a pure function of the event list,
which is what makes `company rebuild --verify` meaningful: if replay cannot
reproduce the task files byte-for-byte, the state model is broken.
"""

from __future__ import annotations

from pathlib import Path

import gatesig
from eventlog import GATE_EVENT, EventLog, canonical

LIFECYCLE = [
    "DRAFT", "PLANNED", "READY", "IN_PROGRESS", "IMPLEMENTATION_READY",
    "REVIEW", "QA", "SECURITY_REVIEW", "INTEGRATION", "DONE",
]
OFF_PATH = {"WAITING", "BLOCKED", "FAILED", "RETRYING", "ESCALATED", "ABANDONED",
            "MERGED"}

# Once a task reaches one of these, only an explicit STATUS_CHANGED — a
# deliberate decision — may move it elsewhere. Generalizes what used to be a
# single MERGED-vs-DONE carve-out below into the actual rule it was an
# instance of. Bug, live-reproduced on ht-workspace 2026-09-14: a task
# explicitly marked ABANDONED via STATUS_CHANGED had ESCALATION_RAISED fire
# right after it, and fold() flipped its displayed status back to
# ESCALATED — a closed task kept resurfacing as open work. The event that
# would have implied a status change still exists in the log (an escalation
# on already-abandoned work is real information, findable through
# `company status`'s own escalation list) — it just no longer overwrites
# what already happened, the same reasoning MERGED-vs-DONE already used.
TERMINAL_STATUSES = {"DONE", "ABANDONED", "MERGED"}

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
    # A merge is a FACT, not a judgment: the branch is on main, in production.
    # Previously MERGED recorded evidence but moved nothing, so a task could
    # ship and still read BLOCKED or IN_PROGRESS forever — measured on finos
    # 2026-09-09: 175 of 218 tasks were live on main while the ledger showed
    # 134 DONE, and six tasks reported BLOCKED had shipped weeks earlier.
    # MERGED is deliberately NOT "DONE": DONE additionally asserts the
    # Evidence Rule was satisfied, and back-dating that onto historical work
    # would launder unverified changes into verified ones. This says exactly
    # what is true and no more.
    "MERGED": "MERGED",
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
    # goal (ADR-006 §3): the goal this task serves, set at plan time. Only
    # copied when present — absence means ungoaled, so no historical task
    # view gains a key it never had.
    "goal",
)


def fold(events: list[dict], gate_key: bytes | None = None) -> dict[str, dict]:
    """Replay events into task views. Pure — no I/O, no clock, no randomness.

    With `gate_key` (the PM's process: `load`), state events the PM did not
    sign are dropped first (gatesig.trusted_events); every caller that
    decides DONE, a merge or a cleanup must pass it."""
    events = gatesig.trusted_events(events, gate_key)
    tasks: dict[str, dict] = {}
    created: set[str] = set()
    # ESC-002. Signed gate launches by seq, and per (task, gate) the seq a
    # PASSED's launch must exceed. `high` is the highest seq seen so far: an
    # IMPLEMENTATION_READY or FAILED voids every launch at or below it, so
    # an earlier launch's signed PASS re-appended later (the log is
    # writable from a worker's sandbox) never counts. A forged seq can only
    # raise `high`, i.e. refuse more.
    launches: dict[int, dict] = {}
    floors: dict[tuple[str, str], int] = {}
    high = 0

    for ev in events:
        seq = ev.get("seq")
        if isinstance(seq, int) and not isinstance(seq, bool):
            high = max(high, seq)
        tid = ev.get("task")
        if ev.get("event") == "WORKER_STARTED":
            _record_launch(launches, ev, tid)
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
            # GOAL_LINKED (ADR-006 §3) has the same members-in-data shape, so
            # a misspelled id can never create a phantom DRAFT task; goals.py
            # reports unknown ids as `unknown_tasks`. It deliberately leaves
            # `updated_at` alone: relinking is classification, not work, and
            # bumping it would reset detect_stale_tasks/detect_resting_tasks.
            elif ev.get("event") == "GOAL_LINKED" and "goal" in data:
                for member in data.get("tasks") or []:
                    if member in tasks:
                        tasks[member]["goal"] = data["goal"]
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
            if tid not in created or ev.get("_pm_signed"):
                for field in FIELDS_FROM_DATA:
                    if field in data:
                        task[field] = data[field]
                if tid not in created:
                    task["status"] = "PLANNED"
                created.add(tid)
                if ev.get("_pm_signed"):
                    task["created_signed"] = True
                else:
                    task.pop("created_signed", None)
            else:
                # A repeated, unsigned TASK_CREATED (ESC-002 c: a worker
                # re-declaring its own task with `gates: []`) changes
                # nothing — except that gates may only ever grow.
                task["gates"] = list(dict.fromkeys(
                    [*(task.get("gates") or []), *(data.get("gates") or [])]))

        elif name == "TASK_SNAPSHOT":
            # A task's whole state as of the switch to signing (gatesig.migrate).
            for field in FIELDS_FROM_DATA:
                if field in data:
                    task[field] = data[field]
            if data.get("status"):
                task["status"] = data["status"]
            if data.get("merged"):
                task["evidence"]["merged"] = data["merged"]
            created.add(tid)
            if ev.get("_pm_signed"):
                task["created_signed"] = True

        elif name == "TASK_ASSIGNED":
            task["owner"] = data.get("owner", task.get("owner"))
            for field in ("branch", "worktree", "tier"):
                if field in data:
                    task[field] = data[field]

        elif name == "IMPLEMENTATION_READY":
            task["evidence"]["diff"] = (ev.get("evidence") or {}).get("commit")
            # A new implementation voids every gate launch and pass before
            # it: those judged an older commit (ESC-002).
            for gate in GATE_EVENT:
                floors[(tid, gate)] = high
                _drop_pass(task, gate)

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
            # ESC-002: only a PASSED the launcher wrote for a launch it
            # signed counts, and only placed against that launch: the actor
            # string is whatever $COMPANY_ACTOR said, and the log itself is
            # writable from a worker's sandbox. Anything else — a worker's
            # own `company event`, a pre-ESC-002 pass, a raw append — is
            # ignored. check_done() then verifies both MACs with the key.
            gate = next(g for g, e in GATE_EVENT.items() if e == name)
            sig = _pass_signature(launches, floors, tid, gate, ev)
            if sig:
                task["evidence"][gate] = f"{name} by {ev.get('actor')}"
                task["evidence"][f"{gate}_actor"] = ev.get("actor")
                task["evidence"][f"{gate}_sig"] = sig
                task.get("gates_failed", {}).pop(gate, None)

        elif name in FAIL_GATE:
            gate = FAIL_GATE[name]
            # From anyone, signed or not: failing is the safe direction. It
            # also voids every launch so far for this gate, so an earlier
            # signed PASS can't be replayed over it.
            floors[(tid, gate)] = high
            _drop_pass(task, gate)
            # A rejected gate is not the same as an unreviewed one. Recording
            # the rejection is what lets `status` say "failed" instead of
            # "pending", which are very different situations for an operator.
            task.setdefault("gates_failed", {})[gate] = {
                "actor": ev.get("actor"),
                "at": ev["ts"],
                "findings": data.get("findings") or data.get("reasons") or [],
            }

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
        # A TASK_BLOCKED carrying `attempted_transition` is not a work
        # blocker: it is `company task advance` recording that the Evidence
        # Rule REFUSED a close. Treating it as BLOCKED made the ledger claim
        # a task was stuck when it had already merged — finos 2026-09-09:
        # MONEY-PAISE-M1 merged 20 Aug, a refused close on 25 Aug repainted it
        # BLOCKED, and it was still being reported as unstarted work today.
        # The refusal stays in the log; it just no longer overwrites reality.
        if name == "TASK_BLOCKED" and data.get("attempted_transition"):
            implied = None
        if implied and name != "STATUS_CHANGED":
            # A terminal status (DONE/ABANDONED/MERGED) is never silently
            # overwritten by an implied-status event — only STATUS_CHANGED
            # can move a task out of one. This is what protects MERGED from
            # downgrading DONE (a merge recorded after DONE would otherwise
            # erase the stronger, evidenced claim) and ABANDONED from being
            # reopened by a later ESCALATION_RAISED, the same rule either way.
            if task.get("status") in TERMINAL_STATUSES:
                pass
            else:
                task["status"] = implied

    return tasks


def _record_launch(launches: dict, ev: dict, tid: str | None) -> None:
    """A WORKER_STARTED carrying the launcher's MAC (gatesig.sign_started).
    Recorded by its seq, which the MAC covers; check_done verifies it."""
    data = ev.get("data") or {}
    seq, mac = ev.get("seq"), data.get("launch_mac")
    if not (isinstance(seq, int) and isinstance(mac, str) and data.get("role")
            and ev.get("actor")):
        return
    members = [tid] if tid else list(data.get("tasks") or [])
    commits = data.get("commits")
    if not isinstance(commits, dict):
        return
    launches.setdefault(seq, {"actor": ev["actor"], "role": data["role"],
                              "tasks": members, "commits": commits, "mac": mac})


def _pass_signature(launches: dict, floors: dict, tid: str, gate: str,
                    ev: dict) -> dict | None:
    """What check_done needs to verify a PASSED, if it names a signed launch
    of this actor on this task started after the gate's floor; else None."""
    data = ev.get("data") or {}
    ws_seq, mac, actor = data.get("ws_seq"), data.get("verdict_mac"), ev.get("actor")
    launch = launches.get(ws_seq) if isinstance(ws_seq, int) else None
    if not (actor and isinstance(mac, str) and launch and launch["actor"] == actor
            and tid in launch["tasks"] and launch["role"] == data.get("role")
            and ws_seq > floors.get((tid, gate), 0)
            and data.get("commit") and launch["commits"].get(tid) == data.get("commit")):
        return None
    return {"role": launch["role"], "ws_seq": ws_seq, "ws_tasks": launch["tasks"],
            "ws_commits": launch["commits"], "commit": data["commit"],
            "launch_mac": launch["mac"], "verdict": data.get("verdict"),
            "verdict_mac": mac}


def _drop_pass(task: dict, gate: str) -> None:
    for key in (gate, f"{gate}_actor", f"{gate}_sig"):
        task["evidence"].pop(key, None)


def gate_verified(task: dict, gate: str, gate_key: bytes | None) -> bool:
    """True only for a launcher-signed PASSED (both MACs check out)."""
    ev = task.get("evidence") or {}
    return gatesig.verify(gate_key, task.get("id"), GATE_EVENT.get(gate, ""),
                          ev.get(f"{gate}_actor"), ev.get(f"{gate}_sig"))


def reviewed_commits(task: dict, gate_key: bytes | None) -> set[str]:
    """The SHAs this task's verified gate passes judged (launcher-read)."""
    ev = task.get("evidence") or {}
    return {ev[f"{g}_sig"]["commit"] for g in task.get("gates") or []
            if gate_verified(task, g, gate_key)}


def reviewed_commit(task: dict, gate_key: bytes | None) -> str | None:
    """The one SHA every gate passed — what integrate merges — or None if
    the gates aren't all passed on the same commit."""
    shas = reviewed_commits(task, gate_key)
    gates = task.get("gates") or []
    if len(shas) != 1 or not all(gate_verified(task, g, gate_key) for g in gates):
        return None
    return next(iter(shas))


def load(company_root: Path, events: list[dict] | None = None) -> dict[str, dict]:
    """fold() with the PM's key, when this process can read it."""
    if events is None:
        events = EventLog(company_root).read()
    return fold(events, gatesig.load_key(company_root))


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
    import goals
    events = EventLog(company_root).read()
    tasks = fold(events, gatesig.load_key(company_root))
    # Goal views are a second projection over the same log, taking this
    # fold's links as input, and get the same byte-identical-replay rules.
    goal_views = goals.fold(events, tasks)
    if not verify:
        write_views(company_root, tasks)
        goals.write_views(company_root, goal_views)
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
    mismatches += goals.verify_views(company_root, goal_views)
    return len(tasks), mismatches


# --- The Evidence Rule ------------------------------------------------------

class EvidenceRuleViolation(Exception):
    pass


def check_done(task: dict, baseline: dict | None = None,
               gate_roles: dict[str, str] | None = None,
               gate_key: bytes | None = None) -> list[str]:
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

    `gate_key` (gatesig.load_key) verifies that each PASSED was written by
    the launcher for a launch it signed (ESC-002). Without it no gate is
    satisfied: an unverifiable pass is not evidence.
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
            reasons.append(f"gate {gate!r} not satisfied: no {event_name} event "
                           f"signed by the launcher for a launch after the latest "
                           f"IMPLEMENTATION_READY")
            continue
        actor = ev.get(f"{gate}_actor")
        if actor and owner and actor == owner:
            reasons.append(
                f"gate {gate!r} was self-certified: {event_name} was authored by "
                f"{actor!r}, who is also the task owner. A gated change requires a "
                f"review from a different worker."
            )
            continue

        if not gate_verified(task, gate, gate_key):
            reasons.append(
                f"gate {gate!r}: {event_name} by {actor!r} carries no valid launcher "
                f"signature for a gate launched after the latest IMPLEMENTATION_READY "
                f"— only a verdict the launcher recorded from the gate worker's "
                f"structured output counts (ESC-002). Relaunch the gate."
            )
            continue
        required_role = (gate_roles or {}).get(gate)
        signed_role = (ev.get(f"{gate}_sig") or {}).get("role")
        if required_role and signed_role != required_role:
            reasons.append(
                f"gate {gate!r} actor {actor!r} has no verified {required_role!r} "
                f"launch record for this task (was launched as {signed_role!r}). "
                f"{event_name} came from a launch the trusted launcher did not start "
                f"as {required_role!r}."
            )
    shas = reviewed_commits(task, gate_key)
    if len(shas) > 1:
        reasons.append(
            f"gate passes are on different commits ({', '.join(sorted(shas))}): each gate "
            f"must judge the same branch SHA, which is what integrate merges. "
            f"Relaunch the gates on the current commit."
        )
    return reasons
