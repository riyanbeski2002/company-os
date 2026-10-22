"""Append-only event log — the authoritative state of Company OS (D1).

Workers never mutate task files. They append events. Task views are a fold
over this log (see taskstate.py). Stdlib only, so the worker-facing path
(`company event`) has no dependencies.
"""

from __future__ import annotations

import errno
import fcntl
import filecmp
import json
import os
import shutil
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# One serializer, used everywhere a JSON artifact is written to disk. Replay
# determinism (`company rebuild --verify`) depends on there being exactly one.
def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def compact(obj) -> str:
    """Single-line form used for event log lines."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- event vocabulary -------------------------------------------------------
# Extend as needed; never rename. Renaming breaks replay of historical logs.
# Extending isn't free either: state a one-line reason for a new event type
# in its commit message (what fact needs recording that an existing event
# can't carry), the same discipline paperclip's own telemetry pipeline
# requires for a new event name (doc/TELEMETRY_WORKFLOW.md) — this set is
# permanent once shipped, so it's worth the same one-line justification a
# new gate or risk trigger already gets.
EVENTS = {
    "TASK_CREATED", "TASK_ASSIGNED", "WORKER_STARTED", "WORKER_HEARTBEAT",
    "DEPENDENCY_WAITING", "CONTRACT_PUBLISHED", "IMPLEMENTATION_READY",
    "TEST_RUN", "REVIEW_REQUESTED", "REVIEW_PASSED", "REVIEW_FAILED",
    "SECURITY_REVIEW_REQUESTED", "SECURITY_REVIEW_PASSED", "SECURITY_REVIEW_FAILED",
    "QA_PASSED", "QA_FAILED",
    "HANDOFF_WRITTEN", "MERGE_READY", "MERGED", "TASK_BLOCKED", "TASK_FAILED",
    "WORKER_EXITED", "ESCALATION_RAISED", "ESCALATION_RESOLVED", "TASK_COMPLETED",
    "STATUS_CHANGED", "OWNERSHIP_BLOCKED", "BRANCH_GUARD_BLOCKED",
    "BASELINE_RECORDED", "ADVISORY_FINDING", "ADVISORY_RESOLVED",
    "SECRET_READ_BLOCKED", "LESSON_RECORDED", "GATE_NO_VERDICT",
    # A historical WORKER_EXITED can't be edited to add the tokens its
    # producer didn't record (KNOWN_ISSUES #1), so the reconstruction is its
    # own event, pointing back at the original by seq (backfill.py).
    "TOKENS_BACKFILLED",
    # Test-fixture LESSON_RECORDED events that leaked into the real log can't
    # be deleted from an append-only log, so a correction event names the seqs
    # to disregard; lessons.fold() then skips them (quarantine.py).
    "LESSONS_QUARANTINED",
    # ADR-006 goals (goals.py). No existing event records business intent
    # (`request` never reaches the log); a task's goal must be correctable
    # after TASK_CREATED; nothing records whether intent was *achieved*; and
    # an abandoned goal would otherwise sit "unassessed" forever.
    "GOAL_DEFINED", "GOAL_LINKED", "OUTCOME_ASSESSED", "GOAL_CLOSED",
    # Recurring work (routines.py). Nothing records that work should recur on
    # a schedule, or which scheduled occurrence already produced its tasks —
    # without the second, a retried `routine fire` would staff the same slot
    # twice. Retiring a routine is a re-definition with enabled: false.
    "ROUTINE_DEFINED", "ROUTINE_FIRED",
    # tools/capability.py stays standalone (no event log), so nothing recorded
    # that a catalog unit was ever actually loaded — `company capability load`
    # appends this (data: unit_id, type, optional task) after a load succeeds.
    "CAPABILITY_LOADED",
}

# Events asserting a fact must carry machine-checkable evidence (D6). An event
# without it is a claim, and the log records facts, not claims.
REQUIRES_EVIDENCE = {
    "IMPLEMENTATION_READY", "TEST_RUN", "REVIEW_PASSED", "SECURITY_REVIEW_PASSED",
    "QA_PASSED", "MERGED", "CONTRACT_PUBLISHED",
    # A baseline decides what "no worse" means for every later task, so it must
    # point at the commit and log it was measured from.
    # An officer's opinion without evidence is exactly the noise this system
    # exists to remove, so a finding must point at what it was derived from.
    # ADVISORY_RESOLVED is deliberately absent: closing a finding is a decision,
    # not a factual assertion.
    "BASELINE_RECORDED", "ADVISORY_FINDING",
    # A lesson without evidence of what actually happened is a vague feeling,
    # not a pattern — the exact thing this event exists to be more than.
    "LESSON_RECORDED",
    # Reconstructed tokens are only as good as the stdout.json they came from.
    "TOKENS_BACKFILLED",
    # A quarantine disregards recorded history, so it must point at the
    # investigation/commit that proved those entries were test-fixture leakage.
    "LESSONS_QUARANTINED",
    # Whether intent was achieved is the one goal fact that is a claim about
    # the world; defining, linking and closing are decisions.
    "OUTCOME_ASSESSED",
}

# ADR-006: one goal entity, three levels. Goal events are not project-scoped
# (an objective can span projects), so they carry this reserved project.
GOAL_EVENTS = {"GOAL_DEFINED", "GOAL_LINKED", "OUTCOME_ASSESSED", "GOAL_CLOSED"}
ORG_PROJECT = "_org"
GOAL_LEVELS = {"mission", "objective", "key_result"}
GOAL_PARENT_LEVEL = {"mission": None, "objective": "mission", "key_result": "objective"}
OUTCOME_VERDICTS = {"achieved", "not_achieved", "inconclusive"}
GOAL_DISPOSITIONS = {"abandoned", "superseded"}
MEASURE_DIRECTIONS = {"increase", "decrease"}

# Routines are org-level schedules, not tasks: same reserved project, same
# no-top-level-task rule as goal events. Their tasks are named in data.
ROUTINE_EVENTS = {"ROUTINE_DEFINED", "ROUTINE_FIRED"}

# What a LESSON_RECORDED's optional data.source_ref may cite: a commit SHA,
# the seq of a TEST_RUN or review event, or a task id. Optional on purpose —
# most real lessons are field observations with no single source event, and
# requiring one would just invite a fabricated citation.
SOURCE_REF_TYPES = ("commit", "test_run", "review", "task")

# Gate name -> the event that satisfies it. Used by the Evidence Rule.
GATE_EVENT = {
    "review": "REVIEW_PASSED",
    "qa": "QA_PASSED",
    "security": "SECURITY_REVIEW_PASSED",
}

# A gate's PASSED verdict, keyed to its own FAILED verdict for the same role
# (cost audit, 2026-09-14). Real incident, two independent sessions same day:
# a fix worker hit its usage limit and was relaunched WITHOUT committing —
# then the next review/security pass re-ran against the identical, still-
# broken commit and PASSED it, because nothing bound the verdict to the SHA
# it actually reviewed. See `_rejects_stale_gate_verdict` below.
GATE_FAIL_EVENT = {
    "REVIEW_PASSED": "REVIEW_FAILED",
    "QA_PASSED": "QA_FAILED",
    "SECURITY_REVIEW_PASSED": "SECURITY_REVIEW_FAILED",
}


class EvidenceError(ValueError):
    """Raised when an event asserts a fact it cannot back up."""


class TornTailError(ValueError):
    """Raised when the log's last line has no trailing newline — a previous
    write was interrupted mid-line, and appending would fuse onto it."""


def _evidence_commit(evidence) -> str | None:
    """The commit SHA an evidence value points at, or None. `cli.py`'s
    `_parse_evidence` normalizes a bare SHA on the command line into
    `{"commit": sha}` before it ever reaches here, so evidence is a dict in
    practice — this stays conservative and only reads that shape. Evidence
    that isn't commit-shaped (a log path, `{"log": ...}`) returns None and
    never trips the stale-verdict check below — the point is to catch
    "nothing changed," not to police evidence format."""
    if isinstance(evidence, dict):
        sha = evidence.get("commit")
    else:
        sha = evidence
    if not (isinstance(sha, str) and 7 <= len(sha) <= 40
            and all(c in "0123456789abcdef" for c in sha.lower())):
        return None
    return sha.lower()


def validate(event: dict) -> None:
    name = event.get("event")
    if name not in EVENTS:
        raise ValueError(f"unknown event type {name!r} (add it to EVENTS, never rename)")
    for field in ("ts", "event", "actor", "project"):
        if not event.get(field):
            raise ValueError(f"event missing required field {field!r}")

    if name in REQUIRES_EVIDENCE and not event.get("evidence"):
        raise EvidenceError(
            f"{name} asserts a fact and requires --evidence "
            f"(a file path, commit SHA, or exit code)"
        )
    if name == "TEST_RUN":
        if "exit_code" not in (event.get("data") or {}):
            raise EvidenceError("TEST_RUN requires data.exit_code — a real exit code")
    if name == "IMPLEMENTATION_READY":
        if not (event.get("evidence") or {}).get("commit"):
            raise EvidenceError("IMPLEMENTATION_READY requires evidence.commit (a SHA)")
    if name in GOAL_EVENTS:
        _validate_goal_event(event)
    if name in ROUTINE_EVENTS:
        _validate_routine_event(event)
    if name == "LESSON_RECORDED" and "source_ref" in (event.get("data") or {}):
        _validate_source_ref(event["data"]["source_ref"])


def _validate_source_ref(ref) -> None:
    """Shape only. Whether the cited seq/sha/task exists is deliberately not
    checked — an honest optional citation shouldn't be able to fail a lesson
    for reasons unrelated to the lesson itself."""
    if not isinstance(ref, dict) or ref.get("type") not in SOURCE_REF_TYPES:
        raise ValueError(f"source_ref type must be one of {', '.join(SOURCE_REF_TYPES)}")
    value = ref.get("ref")
    if isinstance(value, bool) or not isinstance(value, (str, int)) \
            or (isinstance(value, str) and not value.strip()):
        raise ValueError("source_ref requires a non-empty ref (a sha, a seq, or a task id)")


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate_goal_event(event: dict) -> None:
    """The shape rules ADR-006 §2 fixes at append time. Rules that need the
    rest of the log (does the parent exist, is it the right level, is there
    already an open mission) live in goals.check_against_history."""
    name = event["event"]
    data = event.get("data") or {}
    if event["project"] != ORG_PROJECT:
        raise ValueError(f"{name} is not project-scoped and must carry project {ORG_PROJECT!r}")
    if event.get("task"):
        # Members go in data.tasks; a top-level `task` would make
        # taskstate.fold() create a phantom DRAFT task for a misspelled id.
        raise ValueError(f"{name} must not carry a top-level 'task'")

    if name == "GOAL_DEFINED":
        level = data.get("level")
        if not str(data.get("id") or "").startswith("G-"):
            raise ValueError("GOAL_DEFINED requires data.id of the form G-NNN")
        if level not in GOAL_LEVELS:
            raise ValueError(f"GOAL_DEFINED level {level!r} is not one of {sorted(GOAL_LEVELS)}")
        if not str(data.get("title") or "").strip():
            raise ValueError("GOAL_DEFINED requires a non-empty data.title")
        if level == "mission" and data.get("parent"):
            raise ValueError("a mission has no parent")
        if level != "mission" and not data.get("parent"):
            raise ValueError(f"a {level} requires data.parent (a {GOAL_PARENT_LEVEL[level]})")
        measure = data.get("measure")
        if level == "key_result" and not isinstance(measure, dict):
            raise ValueError("a key_result requires data.measure — a key result "
                             "without a number is just a second objective")
        if measure is not None:
            if not isinstance(measure, dict) or not str(measure.get("metric") or "").strip() \
                    or measure.get("target") is None:
                raise ValueError("data.measure requires a 'metric' and a 'target'")
            if measure.get("direction") not in (None, *MEASURE_DIRECTIONS):
                raise ValueError(f"measure.direction must be one of {sorted(MEASURE_DIRECTIONS)}")
        budget = data.get("budget")
        if budget is not None and not (isinstance(budget, dict) and budget
                                       and all(_is_number(v) and v >= 0 for v in budget.values())):
            raise ValueError("data.budget must map a unit to a non-negative number")

    elif name == "GOAL_LINKED":
        if "goal" not in data or not (data["goal"] is None or isinstance(data["goal"], str)):
            raise ValueError("GOAL_LINKED requires data.goal (a goal id, or null to unlink)")
        tasks = data.get("tasks")
        if not (isinstance(tasks, list) and tasks and all(isinstance(t, str) and t for t in tasks)):
            raise ValueError("GOAL_LINKED requires a non-empty data.tasks list of task ids")

    elif name == "OUTCOME_ASSESSED":
        if not data.get("goal"):
            raise ValueError("OUTCOME_ASSESSED requires data.goal")
        if data.get("verdict") not in OUTCOME_VERDICTS:
            raise ValueError(f"OUTCOME_ASSESSED verdict {data.get('verdict')!r} is not "
                             f"one of {sorted(OUTCOME_VERDICTS)}")
        measured = data.get("measured")
        if measured is not None and not (isinstance(measured, dict) and "value" in measured):
            raise ValueError("data.measured, when given, requires a 'value'")
        evidence = event.get("evidence")
        if isinstance(evidence, dict) and set(evidence) == {"commit"}:
            # A commit proves a deliverable exists. This event records
            # something different, and accepting a merge SHA as proof of an
            # outcome would let "shipped" pass for "achieved" again.
            raise EvidenceError(
                "OUTCOME_ASSESSED refuses a bare commit as evidence — a commit proves "
                "something shipped, not that the outcome was achieved. Point at the "
                "measurement itself (a report, an export, a log).")

    elif name == "GOAL_CLOSED":
        if not data.get("goal"):
            raise ValueError("GOAL_CLOSED requires data.goal")
        if data.get("disposition") not in GOAL_DISPOSITIONS:
            raise ValueError(f"GOAL_CLOSED disposition {data.get('disposition')!r} is not "
                             f"one of {sorted(GOAL_DISPOSITIONS)}")
        if data["disposition"] == "superseded" and not data.get("superseded_by"):
            raise ValueError("a superseded goal requires data.superseded_by")
        if not str(data.get("reason") or "").strip():
            raise ValueError("GOAL_CLOSED requires a data.reason")


def _validate_routine_event(event: dict) -> None:
    """Shape rules a single routine event can answer. Whether the cron
    expression actually parses lives in routines.py, which owns the matcher;
    whether a slot already fired is checked in EventLog.append, under the lock."""
    name = event["event"]
    data = event.get("data") or {}
    if event["project"] != ORG_PROJECT:
        raise ValueError(f"{name} is not project-scoped and must carry project {ORG_PROJECT!r}")
    if event.get("task"):
        # Same reason as goal events: taskstate.fold() would create a
        # phantom DRAFT task for whatever id leaked in here.
        raise ValueError(f"{name} must not carry a top-level 'task'")

    if name == "ROUTINE_DEFINED":
        if not str(data.get("id") or "").startswith("R-"):
            raise ValueError("ROUTINE_DEFINED requires data.id of the form R-NNN")
        if not (isinstance(data.get("cron"), str) and len(data["cron"].split()) == 5):
            raise ValueError("ROUTINE_DEFINED requires data.cron, a 5-field cron expression")
        spec = data.get("spec")
        if not (isinstance(spec, dict) and spec.get("project")
                and isinstance(spec.get("tasks"), list) and spec["tasks"]
                and all(isinstance(t, dict) and t.get("id") for t in spec["tasks"])):
            raise ValueError("ROUTINE_DEFINED requires data.spec, a plan spec with a "
                             "'project' and a non-empty 'tasks' list of tasks with ids")
        if not isinstance(data.get("enabled"), bool):
            raise ValueError("ROUTINE_DEFINED requires data.enabled (true or false)")

    elif name == "ROUTINE_FIRED":
        if not data.get("routine") or not data.get("slot"):
            raise ValueError("ROUTINE_FIRED requires data.routine and data.slot")
        tasks = data.get("tasks")
        if not (isinstance(tasks, list) and tasks and all(isinstance(t, str) and t for t in tasks)):
            raise ValueError("ROUTINE_FIRED requires a non-empty data.tasks list of task ids")


class DuplicateFireError(ValueError):
    """Raised when a ROUTINE_FIRED names a (routine, slot) already in the log."""


def _rejects_duplicate_fire(event: dict, history: list[dict]) -> None:
    """Called with the append lock held, so two concurrent `routine fire`
    calls for one slot can't both read "not fired yet" and both append."""
    data = event.get("data") or {}
    key = (data.get("routine"), data.get("slot"))
    for prior in history:
        pd = prior.get("data") or {}
        if prior.get("event") == "ROUTINE_FIRED" and (pd.get("routine"), pd.get("slot")) == key:
            raise DuplicateFireError(f"{key[0]} already fired for slot {key[1]} "
                                     f"(seq {prior.get('seq')})")


def _rejects_stale_gate_verdict(event: dict, history: list[dict]) -> None:
    """A PASSED verdict citing the exact same commit SHA as that role's own
    most recent FAILED verdict on this task is refused — that combination
    means the gate reviewed nothing new, whether because a relaunch died
    before committing or a fix was never actually made. `history` is this
    task's prior events only; the caller filters."""
    name = event.get("event")
    fail_event = GATE_FAIL_EVENT.get(name)
    if not fail_event:
        return
    sha = _evidence_commit(event.get("evidence"))
    if not sha:
        return
    for prior in reversed(history):
        if prior.get("event") not in (name, fail_event):
            continue
        # Most recent verdict from this same gate family is the one that
        # matters — an earlier one two rounds back is stale information.
        if prior.get("event") == fail_event and _evidence_commit(prior.get("evidence")) == sha:
            raise EvidenceError(
                f"{name} cites evidence {sha!r}, the exact commit its own "
                f"{fail_event} already reviewed and rejected — nothing has "
                f"changed since that verdict, so this one can't be trusted. "
                f"Relaunch the implementer, confirm a NEW commit exists, "
                f"then gate that."
            )
        break


class EventLog:
    def __init__(self, company_root: Path):
        self.root = Path(company_root)
        self.path = self.root / "events" / "events.jsonl"
        self.lockpath = self.root / "events" / ".lock"

    # --- writing ------------------------------------------------------------
    def append(self, event: dict) -> dict:
        """Append one event under an exclusive lock.

        The lock does double duty: it serializes writes across concurrent
        worker processes, and it makes `seq` assignment atomic. Without it two
        workers finishing at once would race for the same sequence number.
        """
        validate(event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lockpath.touch(exist_ok=True)

        with open(self.lockpath, "r+") as lock:
            _flock_with_timeout(lock)
            try:
                if self._torn_tail():
                    # Refuse rather than guess: only the operator can know
                    # what the partial line was meant to say, and writing
                    # now would turn one bad line into two fused ones.
                    raise TornTailError(
                        f"{self.path} ends mid-line — a previous write was "
                        f"interrupted, so this event would be fused onto that "
                        f"partial line. Nothing was written. Run `company doctor` "
                        f"to diagnose, inspect the tail of the file by hand, and "
                        f"repair it or restore from `company backup` before "
                        f"continuing.")
                if event.get("task") and event.get("event") in GATE_FAIL_EVENT:
                    task_history = [e for e in self.read() if e.get("task") == event["task"]]
                    _rejects_stale_gate_verdict(event, task_history)
                if event.get("event") == "ROUTINE_FIRED":
                    _rejects_duplicate_fire(event, self.read())
                event = dict(event)
                event["seq"] = self._next_seq()
                line = compact(event)
                if "\n" in line:
                    raise ValueError("event serialized to more than one line")
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        return event

    def _next_seq(self) -> int:
        # Called with the lock held.
        if not self.path.exists():
            return 1
        count = 0
        with open(self.path, "rb") as fh:
            for _ in fh:
                count += 1
        return count + 1

    def _torn_tail(self) -> bool:
        # Called with the lock held. Every complete append ends in "\n", so
        # any other last byte means a write died partway through its line.
        try:
            with open(self.path, "rb") as fh:
                if fh.seek(0, os.SEEK_END) == 0:
                    return False
                fh.seek(-1, os.SEEK_END)
                return fh.read(1) != b"\n"
        except FileNotFoundError:
            return False

    @contextmanager
    def _locked(self):
        """The same lock append() holds, for readers that need a view no
        writer is halfway through (integrity checks, backups)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lockpath.touch(exist_ok=True)
        with open(self.lockpath, "r+") as lock:
            _flock_with_timeout(lock)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def integrity(self) -> dict:
        """check_integrity() on the live log, under the append lock — without
        it, an append in flight reads as a torn tail."""
        with self._locked():
            return check_integrity(self.path)

    def snapshot(self, dest: Path, unless_same_as: Path | None = None) -> bool:
        """Copy the log to `dest` atomically, under the append lock, so the
        copy can never contain half an event. fsync'd before the rename and
        the directory after it, so a crash leaves either no copy or a whole
        one. Returns False, writing nothing, if `unless_same_as` is already
        byte-identical to the log (repeat backups don't pile up duplicates)."""
        dest = Path(dest)
        tmp = dest.with_name(f".{dest.name}.tmp-{os.getpid()}")
        with self._locked():
            if unless_same_as and filecmp.cmp(unless_same_as, self.path, shallow=False):
                return False
            try:
                with open(self.path, "rb") as src, open(tmp, "wb") as out:
                    shutil.copyfileobj(src, out)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp, dest)
            finally:
                tmp.unlink(missing_ok=True)
        dirfd = os.open(dest.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        return True

    # --- reading ------------------------------------------------------------
    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        events = []
        with open(self.path, encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    events.append(json.loads(raw))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{self.path}:{lineno} is not valid JSON — the event log is "
                        f"corrupt and must be repaired by hand: {exc}"
                    ) from exc
        return events


_MAX_LISTED_PROBLEMS = 20


def check_integrity(path: Path) -> dict:
    """Every line valid JSON, `seq` running 1, 2, 3... with no gap or repeat,
    and a trailing newline. Reports what it finds, never raises on bad
    content — read() already refuses a corrupt log; this says exactly where.

    After an unparseable line the seq check resyncs on the next good one, so
    one bad line is one problem, not a cascade of gaps after it."""
    problems, events, lines = [], 0, 0
    prev, last = 0, b"\n"
    with open(path, "rb") as fh:
        for lineno, raw in enumerate(fh, 1):
            lines, last = lineno, raw
            if not raw.strip():
                problems.append(f"line {lineno} is blank")
                prev = None
                continue
            try:
                ev = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                problems.append(f"line {lineno} is not valid JSON: {exc}")
                prev = None
                continue
            seq = ev.get("seq") if isinstance(ev, dict) else None
            if not isinstance(seq, int) or isinstance(seq, bool):
                problems.append(f"line {lineno} has no integer seq")
                prev = None
                continue
            events += 1
            if prev is not None and seq != prev + 1:
                kind = "a gap" if seq > prev + 1 else "a repeated or out-of-order seq"
                problems.append(f"line {lineno}: seq {seq} follows {prev} — {kind}")
            prev = seq
    if not last.endswith(b"\n"):
        problems.append(f"line {lines} has no trailing newline — a write was "
                        f"interrupted mid-line (torn tail), and append() will "
                        f"refuse until it is repaired by hand")
    return {"lines": lines, "events": events, "problem_count": len(problems),
            "problems": problems[:_MAX_LISTED_PROBLEMS]}


def _flock_with_timeout(handle, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"could not acquire the event log lock within {timeout}s"
                ) from exc
            time.sleep(0.01)


def make_event(*, event: str, actor: str, project: str, task: str | None = None,
               data: dict | None = None, evidence: dict | None = None) -> dict:
    ev = {
        "ts": utcnow(),
        "event": event,
        "actor": actor,
        "project": project,
    }
    if task:
        ev["task"] = task
    if data:
        ev["data"] = data
    if evidence:
        ev["evidence"] = evidence
    return ev
