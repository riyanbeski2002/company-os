#!/usr/bin/env python3
"""SessionEnd hook: guarantee a worker leaves a terminal record (§8).

A worker that dies mid-flight — killed, timed out, out of turns — must still
appear in the log as having exited. Otherwise stall detection cannot tell
"crashed" from "still thinking", and recovery has to guess.

Inert outside a Company OS worker.

COST AUDIT, 2026-09-14: this hook was firing on every session end, success or
not, with no check for whether the launcher (`worker.py`) already logged the
real WORKER_EXITED — and observed to fire twice per completion. A day's
ledger across two repos carried 99 WORKER_EXITED events for 33 actual worker
exits: every real one, tripled. It cost no tokens (this is a local file
write, not a model call) but it made `company status` and every worker-count
report — this session's own dashboard included — lie by 3x, and it's the
exact "WORKER_EXITED is 2.6x WORKER_STARTED" drift finos-ba/finos-de each
independently flagged the same day. Fixed by making the fallback idempotent
per session_id: only write it if nothing has recorded this session's exit
yet, whether that's the launcher's authoritative event or an earlier firing
of this same hook.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "company"))


def main() -> None:
    task_id = os.environ.get("COMPANY_TASK")
    root = os.environ.get("COMPANY_ROOT")
    if not task_id or not root:
        sys.exit(0)

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    try:
        from eventlog import EventLog, make_event
        company_root = Path(root)
        task = json.loads(
            (company_root / "tasks" / f"{task_id}.json").read_text(encoding="utf-8"))
        session_id = payload.get("session_id")

        # Idempotent per session_id: if the launcher already wrote the real
        # exit (or this hook already fired once for this same session), do
        # nothing. `session_id` is stable across both — it's how the
        # duplicate was detected in the first place.
        log = EventLog(company_root)
        already_recorded = session_id and any(
            e.get("event") == "WORKER_EXITED"
            and e.get("task") == task_id
            and (e.get("data") or {}).get("session_id") == session_id
            for e in log.read()
        )
        if not already_recorded:
            log.append(make_event(
                event="WORKER_EXITED",
                actor=os.environ.get("COMPANY_ACTOR", task.get("owner", "unknown")),
                project=task.get("project", "unknown"),
                task=task_id,
                data={"reason": payload.get("reason", "session_end"),
                      "session_id": session_id},
            ))
    except Exception:
        # A hook that crashes must not become the reason a session fails.
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
