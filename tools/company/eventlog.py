"""Append-only event log — the authoritative state of Company OS (D1).

Workers never mutate task files. They append events. Task views are a fold
over this log (see taskstate.py). Stdlib only, so the worker-facing path
(`company event`) has no dependencies.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import time
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
}

# Gate name -> the event that satisfies it. Used by the Evidence Rule.
GATE_EVENT = {
    "review": "REVIEW_PASSED",
    "qa": "QA_PASSED",
    "security": "SECURITY_REVIEW_PASSED",
}


class EvidenceError(ValueError):
    """Raised when an event asserts a fact it cannot back up."""


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
