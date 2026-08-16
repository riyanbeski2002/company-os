#!/usr/bin/env python3
"""SessionEnd hook: guarantee a worker leaves a terminal record (§8).

A worker that dies mid-flight — killed, timed out, out of turns — must still
appear in the log as having exited. Otherwise stall detection cannot tell
"crashed" from "still thinking", and recovery has to guess.

Inert outside a Company OS worker.
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
        EventLog(company_root).append(make_event(
            event="WORKER_EXITED",
            actor=os.environ.get("COMPANY_ACTOR", task.get("owner", "unknown")),
            project=task.get("project", "unknown"),
            task=task_id,
            data={"reason": payload.get("reason", "session_end"),
                  "session_id": payload.get("session_id")},
        ))
    except Exception:
        # A hook that crashes must not become the reason a session fails.
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
