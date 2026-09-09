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


class TestRefusedCloseIsNotABlocker(unittest.TestCase):
    """A TASK_BLOCKED carrying attempted_transition is `company task advance`
    recording that the Evidence Rule refused a close — not a work blocker.
    finos 2026-09-09: MONEY-PAISE-M1 merged 20 Aug, a refused close on 25 Aug
    repainted it BLOCKED, and it was still reported as unstarted work weeks
    later."""

    def test_a_refused_close_does_not_overwrite_merged(self):
        events = [
            ev(1, "TASK_CREATED", data={"title": "t"}),
            ev(2, "MERGED"),
            ev(3, "TASK_BLOCKED", data={"attempted_transition": "DONE",
                                        "reasons": ["no test evidence"]}),
        ]
        self.assertEqual(taskstate.fold(events)["TASK-1"]["status"], "MERGED")

    def test_a_real_blocker_still_blocks(self):
        """Without attempted_transition it is a genuine blocker and must
        still set BLOCKED — the fix must not blunt the real signal."""
        events = [
            ev(1, "TASK_CREATED", data={"title": "t"}),
            ev(2, "TASK_BLOCKED", data={"stage": "gate_group_merge",
                                        "detail": "merge conflict"}),
        ]
        self.assertEqual(taskstate.fold(events)["TASK-1"]["status"], "BLOCKED")


class TestMergedStatus(unittest.TestCase):
    """2026-09-09: MERGED recorded evidence but moved no status, so a task
    could be live on main and still read BLOCKED forever. finos showed 175 of
    218 tasks shipped while the ledger claimed 134 DONE."""

    def test_merged_moves_a_task_off_in_progress(self):
        events = [
            ev(1, "TASK_CREATED", data={"title": "t"}),
            ev(2, "WORKER_STARTED", data={"role": "backend-engineer"}),
            ev(3, "MERGED"),
        ]
        self.assertEqual(taskstate.fold(events)["TASK-1"]["status"], "MERGED")

    def test_merged_does_not_downgrade_done(self):
        """DONE is the stronger claim — shipped AND evidenced. A merge
        recorded afterwards must not erase it."""
        events = [
            ev(1, "TASK_CREATED", data={"title": "t"}),
            ev(2, "TASK_COMPLETED"),
            ev(3, "MERGED"),
        ]
        self.assertEqual(taskstate.fold(events)["TASK-1"]["status"], "DONE")

    def test_merged_is_not_treated_as_done(self):
        """MERGED must stay distinct: back-dating DONE onto historical work
        would launder unverified changes into verified ones."""
        events = [ev(1, "TASK_CREATED", data={"title": "t"}), ev(2, "MERGED")]
        self.assertNotEqual(taskstate.fold(events)["TASK-1"]["status"], "DONE")


class TestGroupLaunchBinding(unittest.TestCase):
    """2026-09-09: a GROUP gate launch writes ONE WORKER_STARTED for the whole
    group — no `task` field, members in data.tasks. fold() opened with
    `if not tid: continue`, so that record was discarded and check_done's
    actor-role binding had nothing to verify: every group-gated task was
    uncloseable however genuinely it had been reviewed. 70 real tasks on finos
    were holding passing verdicts they could never spend.
    """

    def _group_started(self, seq, actor, role, members):
        return {"seq": seq, "ts": "2026-09-09T00:00:00Z",
                "event": "WORKER_STARTED", "actor": actor, "project": "p",
                "data": {"role": role, "tasks": members, "gate_group": "g"}}

    def test_group_launch_binds_the_role_to_every_member(self):
        events = [
            ev(1, "TASK_CREATED", task="TASK-1", data={"title": "a"}),
            ev(2, "TASK_CREATED", task="TASK-2", data={"title": "b"}),
            self._group_started(3, "rev-g", "code-reviewer", ["TASK-1", "TASK-2"]),
        ]
        tasks = taskstate.fold(events)
        for tid in ("TASK-1", "TASK-2"):
            self.assertEqual(tasks[tid]["worker_roles"]["rev-g"], "code-reviewer",
                             f"{tid} lost its group launch record")

    def test_only_tasks_the_launcher_named_are_bound(self):
        """The binding is evidence, not a blanket grant: a task absent from
        data.tasks must NOT inherit the role."""
        events = [
            ev(1, "TASK_CREATED", task="TASK-1", data={"title": "a"}),
            ev(2, "TASK_CREATED", task="TASK-2", data={"title": "b"}),
            self._group_started(3, "rev-g", "code-reviewer", ["TASK-1"]),
        ]
        tasks = taskstate.fold(events)
        self.assertEqual(tasks["TASK-1"]["worker_roles"]["rev-g"], "code-reviewer")
        self.assertNotIn("rev-g", tasks["TASK-2"].get("worker_roles", {}))

    def test_a_taskless_event_that_is_not_a_group_launch_is_still_skipped(self):
        events = [
            ev(1, "TASK_CREATED", task="TASK-1", data={"title": "a"}),
            {"seq": 2, "ts": "2026-09-09T00:00:00Z", "event": "ESCALATION_RAISED",
             "actor": "pm", "project": "p", "data": {"need": "x"}},
        ]
        tasks = taskstate.fold(events)
        self.assertNotIn("worker_roles", tasks["TASK-1"])


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
