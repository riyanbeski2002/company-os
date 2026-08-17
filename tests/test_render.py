"""Operator view honesty (§12).

Both bugs here shipped briefly and were caught reading real output:
- workers that exited cleanly were reported STALLED, because a finished worker
  leaves the same dead pid file as a crashed one;
- a gate that was reviewed and REJECTED rendered identically to one never
  reviewed, which are opposite situations for whoever is reading.
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import render  # noqa: E402
import taskstate  # noqa: E402
from eventlog import EventLog, make_event  # noqa: E402


class TestCleanExitIsNotAStall(unittest.TestCase):
    def test_worker_with_terminal_event_is_not_stalled(self):
        events = [
            {"event": "WORKER_STARTED", "actor": "w1"},
            {"event": "WORKER_EXITED", "actor": "w1"},
        ]
        self.assertIn("w1", render.workers_that_ended_cleanly(events))

    def test_worker_without_terminal_event_is_a_candidate(self):
        events = [{"event": "WORKER_STARTED", "actor": "w1"}]
        self.assertNotIn("w1", render.workers_that_ended_cleanly(events))

    def test_restarted_worker_is_a_candidate_again(self):
        events = [
            {"event": "WORKER_STARTED", "actor": "w1"},
            {"event": "WORKER_EXITED", "actor": "w1"},
            {"event": "WORKER_STARTED", "actor": "w1"},   # retry, still running
        ]
        self.assertNotIn("w1", render.workers_that_ended_cleanly(events))

    def test_dead_pid_with_clean_exit_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wdir = root / "state" / "workers" / "w1"
            wdir.mkdir(parents=True)
            (wdir / "pid").write_text("999999")          # long dead
            tasks = [{"id": "T-1", "status": "IN_PROGRESS", "owner": "w1"}]

            crashed = render.detect_stalls(root, tasks, [
                {"event": "WORKER_STARTED", "actor": "w1"}])
            self.assertIn("T-1", crashed)

            finished = render.detect_stalls(root, tasks, [
                {"event": "WORKER_STARTED", "actor": "w1"},
                {"event": "WORKER_EXITED", "actor": "w1"}])
            self.assertEqual(finished, {})


class TestFailedGateIsDistinct(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)
        self.log.append(make_event(
            event="TASK_CREATED", actor="pm", project="p", task="T-1",
            data={"title": "t", "owner": "b1", "gates": ["security"]}))

    def tearDown(self):
        self.tmp.cleanup()

    def _task(self):
        return taskstate.fold(self.log.read())["T-1"]

    def test_rejection_is_recorded_with_findings(self):
        self.log.append(make_event(
            event="SECURITY_REVIEW_FAILED", actor="sec-1", project="p", task="T-1",
            data={"findings": [{"issue": "self-approval"}, {"issue": "no audit"}]}))
        failed = self._task()["gates_failed"]
        self.assertEqual(failed["security"]["actor"], "sec-1")
        self.assertEqual(len(failed["security"]["findings"]), 2)

    def test_unreviewed_gate_has_no_failure_record(self):
        self.assertEqual(self._task().get("gates_failed", {}), {})

    def test_later_pass_clears_the_failure(self):
        self.log.append(make_event(
            event="SECURITY_REVIEW_FAILED", actor="sec-1", project="p", task="T-1",
            data={"findings": [{"issue": "x"}]}))
        self.log.append(make_event(
            event="SECURITY_REVIEW_PASSED", actor="sec-1", project="p", task="T-1",
            evidence={"log": "findings.md"}))
        task = self._task()
        self.assertEqual(task.get("gates_failed", {}), {})
        self.assertIn("security", task["evidence"])

    def test_next_action_points_at_the_findings(self):
        self.log.append(make_event(
            event="SECURITY_REVIEW_FAILED", actor="sec-1", project="p", task="T-1",
            data={"findings": [{"issue": "x"}, {"issue": "y"}]}))
        text = render.status("p", [self._task()], [])
        self.assertIn("FAILED by sec-1", text)
        self.assertIn("fix 2 security findings", text)

    def test_failed_gate_still_blocks_done(self):
        self.log.append(make_event(
            event="SECURITY_REVIEW_FAILED", actor="sec-1", project="p", task="T-1",
            data={"findings": [{"issue": "x"}]}))
        reasons = taskstate.check_done(self._task())
        self.assertTrue(any("security" in r for r in reasons))


class TestProgressIsEvidenceBased(unittest.TestCase):
    def test_unknown_when_no_criteria(self):
        self.assertIsNone(render.progress({"id": "T", "status": "IN_PROGRESS"}))
        self.assertEqual(render.project_progress([{"id": "T", "status": "IN_PROGRESS"}]),
                         "unknown")

    def test_partial_credit_only_for_verified_criteria(self):
        task = {"id": "T", "status": "IN_PROGRESS",
                "acceptance_criteria": ["a", "b", "c", "d"], "criteria_met": ["a"]}
        self.assertEqual(render.progress(task), 0.25)

    def test_no_credit_before_verification(self):
        task = {"id": "T", "status": "IN_PROGRESS",
                "acceptance_criteria": ["a", "b"], "criteria_met": []}
        self.assertEqual(render.progress(task), 0.0)


class TestGatesWithNoVerdict(unittest.TestCase):
    def test_surfaces_a_gate_no_verdict_event(self):
        events = [{"event": "GATE_NO_VERDICT", "task": "T-1", "actor": "code-reviewer-1",
                  "data": {"role": "code-reviewer",
                          "expected_one_of": ["REVIEW_PASSED", "REVIEW_FAILED"]}}]
        out = render.gates_with_no_verdict(events)
        self.assertIn("T-1", out)
        self.assertIn("code-reviewer-1", out["T-1"])
        self.assertIn("REVIEW_PASSED", out["T-1"])

    def test_no_events_no_findings(self):
        self.assertEqual(render.gates_with_no_verdict([]), {})


if __name__ == "__main__":
    unittest.main()
