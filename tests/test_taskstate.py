"""fold() must never crash on a malformed event (D1: replay is total).

Live bug, 17 Aug: a STATUS_CHANGED event in a project's log was missing
`data.to`. `fold()` did `task["status"] = data["to"]` with no fallback, and
since fold() replays the *entire* log from scratch on every call, that one
bad line permanently crashed `company` for that project — and since
taskstate.py is shared source used by every project on the machine, it was
one bad line away from crashing the CLI everywhere, not just there.
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import taskstate  # noqa: E402


def ev(seq, event, task="TASK-1", data=None, actor="pm", project="p"):
    return {"seq": seq, "ts": "2026-08-17T00:00:00Z", "event": event,
            "actor": actor, "project": project, "task": task, "data": data or {}}


class TestGateGroupField(unittest.TestCase):
    def test_gate_group_survives_the_fold(self):
        """Efficiency addendum v1, 2026-08-24: `company gate-group` finds a
        group's tasks by reading this field back off the folded task view —
        it has to actually round-trip through TASK_CREATED, not just be
        accepted and dropped."""
        events = [ev(1, "TASK_CREATED", data={"title": "t", "gate_group": "iam"})]
        task = taskstate.fold(events)["TASK-1"]
        self.assertEqual(task["gate_group"], "iam")

    def test_a_task_with_no_gate_group_has_none(self):
        events = [ev(1, "TASK_CREATED", data={"title": "t"})]
        task = taskstate.fold(events)["TASK-1"]
        self.assertNotIn("gate_group", task)


class TestMalformedStatusChanged(unittest.TestCase):
    def test_a_well_formed_status_changed_still_applies_normally(self):
        events = [
            ev(1, "TASK_CREATED", data={"title": "t"}),
            ev(2, "STATUS_CHANGED", data={"to": "BLOCKED"}),
        ]
        task = taskstate.fold(events)["TASK-1"]
        self.assertEqual(task["status"], "BLOCKED")
        self.assertNotIn("_malformed_events", task)

    def test_a_status_changed_with_no_to_does_not_crash_replay(self):
        events = [
            ev(1, "TASK_CREATED", data={"title": "t"}),
            ev(2, "STATUS_CHANGED", data={}),  # the actual malformed shape seen live
        ]
        tasks = taskstate.fold(events)  # must not raise KeyError
        self.assertIn("TASK-1", tasks)

    def test_the_malformed_event_is_surfaced_not_silently_dropped(self):
        events = [
            ev(1, "TASK_CREATED", data={"title": "t"}),
            ev(2, "STATUS_CHANGED", data={}),
        ]
        task = taskstate.fold(events)["TASK-1"]
        self.assertEqual(len(task["_malformed_events"]), 1)
        self.assertEqual(task["_malformed_events"][0]["seq"], 2)
        self.assertEqual(task["_malformed_events"][0]["event"], "STATUS_CHANGED")

    def test_status_is_left_untouched_by_the_malformed_event(self):
        events = [
            ev(1, "TASK_CREATED", data={"title": "t"}),  # -> PLANNED
            ev(2, "WORKER_STARTED", data={"role": "backend-engineer"}),  # -> IN_PROGRESS
            ev(3, "STATUS_CHANGED", data={}),  # malformed — must not move status
        ]
        task = taskstate.fold(events)["TASK-1"]
        self.assertEqual(task["status"], "IN_PROGRESS")

    def test_a_later_well_formed_status_changed_still_works_after_a_malformed_one(self):
        events = [
            ev(1, "TASK_CREATED", data={"title": "t"}),
            ev(2, "STATUS_CHANGED", data={}),           # malformed, historical
            ev(3, "STATUS_CHANGED", data={"to": "REVIEW"}),  # a later, real one
        ]
        task = taskstate.fold(events)["TASK-1"]
        self.assertEqual(task["status"], "REVIEW")
        self.assertEqual(len(task["_malformed_events"]), 1)


if __name__ == "__main__":
    unittest.main()
