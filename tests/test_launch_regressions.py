"""KNOWN_ISSUES #2 and #3, proven through a real `worker.launch()`.

test_worker_lifecycle.py covers the pieces — claim_task's O_EXCL race,
live_worker_on, the pure gave_no_verdict check — but every one of them is a
unit below launch(), whose own docstring-noted gap was "launch() itself needs
a real subprocess." Both incidents happened at launch() level, so this runs
it end to end with a stand-in harness: a tiny Python script wired in through
the repo-level config/harness.yaml override, the same seam a real BYO harness
uses. No `claude` binary, no network.
"""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

from eventlog import EventLog  # noqa: E402
import costs  # noqa: E402
import render  # noqa: E402
import worker  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"

# A clean `claude -p` result: end_turn, no error — the exact shape
# security-reviewer-201's stdout.json had when it emitted no verdict.
CLEAN_RESULT = {"type": "result", "subtype": "success", "is_error": False,
                "stop_reason": "end_turn", "terminal_reason": None, "num_turns": 11,
                "session_id": "sess", "total_cost_usd": 0.1,
                "usage": {"input_tokens": 1, "output_tokens": 6582,
                          "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0}}


class FakeHarnessCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = base
        self.root = base / ".company"
        (self.root / "events").mkdir(parents=True)
        (self.root / "config").mkdir()
        self.wt = base / "wt"
        self.wt.mkdir()  # pre-existing worktree: ensure_worktree reuses it, no git needed
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _harness(self, *, sleep=0.0, verdict=None):
        """Point every role at a script that reads the packet, optionally
        sleeps (to hold the task while a competitor tries to launch), optionally
        emits a verdict through the real worker-facing CLI, then prints a clean
        result."""
        script = Path(self.tmp.name) / "fake_harness.py"
        script.write_text(
            "import json, os, subprocess, sys, time\n"
            "sys.stdin.read()\n"
            f"time.sleep({sleep})\n"
            f"verdict = {verdict!r}\n"
            "if verdict:\n"
            f"    subprocess.run([sys.executable, {str(CLI)!r}, 'event',\n"
            "                    os.environ['COMPANY_TASK'], verdict,\n"
            "                    '--evidence', 'review-notes.md', '--no-rebuild'], check=True)\n"
            f"result = {CLEAN_RESULT!r}\n"
            "result['session_id'] = os.environ['COMPANY_ACTOR'] + '-sess'\n"
            "print(json.dumps(result))\n")
        (self.root / "config" / "harness.yaml").write_text(
            "default: fake\nroles: {}\nharnesses:\n  fake:\n"
            "    native_agent_loading: true\n"
            f"    command: [{json.dumps(sys.executable)}, {json.dumps(str(script))}]\n")

    def _task(self, tid="T-1"):
        return {"id": tid, "project": "p", "title": "t", "worktree": str(self.wt)}

    def _events(self, name, **match):
        return [e for e in self.log.read() if e["event"] == name
                and all(e.get(k) == v for k, v in match.items())]


class TestExclusiveLease(FakeHarnessCase):
    """KNOWN_ISSUES #2: TASK-202 built four times concurrently because each
    launch checked for a live worker before any had written its marker."""

    def test_concurrent_launches_on_one_task_start_exactly_one_worker(self):
        self._harness(sleep=1.5)
        n = 6
        barrier = threading.Barrier(n)
        outcomes = {}

        def attempt(i):
            actor = f"fe-202-{i}"
            barrier.wait()
            try:
                worker.launch(self.repo, self.root, self._task("TASK-202"), "packet",
                              "frontend-engineer", actor, timeout=30)
                outcomes[actor] = "ran"
            except worker.WorkerError as exc:
                outcomes[actor] = str(exc)

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ran = [a for a, o in outcomes.items() if o == "ran"]
        self.assertEqual(len(ran), 1, outcomes)
        for actor, outcome in outcomes.items():
            if actor not in ran:
                self.assertIn("already working", outcome)
        # The refused launches never got as far as recording a start, so the
        # log can't show a run that never happened — or bill for one.
        self.assertEqual([e["actor"] for e in self._events("WORKER_STARTED")], ran)
        self.assertEqual([e["actor"] for e in self._events("WORKER_EXITED")], ran)

    def test_a_launch_while_the_first_worker_is_running_is_refused(self):
        """The claim is released once pid/started_task are on disk; this is
        the window after that, where live_worker_on alone must hold the lease."""
        self._harness(sleep=2.0)
        first = threading.Thread(target=worker.launch, args=(
            self.repo, self.root, self._task(), "packet", "backend-engineer", "be-1"),
            kwargs={"timeout": 30})
        first.start()
        try:
            marker = self.root / "state" / "workers" / "be-1" / "started_task"
            for _ in range(200):
                if marker.exists() and not (self.root / "state" / "claims" / "T-1.claim").exists():
                    break
                threading.Event().wait(0.01)
            self.assertTrue(marker.exists(), "first worker never started")
            with self.assertRaises(worker.WorkerError) as ctx:
                worker.launch(self.repo, self.root, self._task(), "packet",
                              "backend-engineer", "be-2", timeout=30)
            self.assertIn("be-1 is already working", str(ctx.exception))
        finally:
            first.join()
        self.assertEqual([e["actor"] for e in self._events("WORKER_STARTED")], ["be-1"])

    def test_the_task_is_launchable_again_once_its_worker_exits(self):
        """Exclusive while live, not forever — otherwise a fix run could never follow."""
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "backend-engineer", "be-1")
        worker.launch(self.repo, self.root, self._task(), "packet", "backend-engineer", "be-2")
        self.assertEqual([e["actor"] for e in self._events("WORKER_STARTED")], ["be-1", "be-2"])
        self.assertFalse((self.root / "state" / "claims" / "T-1.claim").exists())


class TestGateNoVerdictThroughLaunch(FakeHarnessCase):
    """KNOWN_ISSUES #3: security-reviewer-201 ran 11 clean turns, emitted no
    verdict, and was silently re-run as security-reviewer-201b."""

    def test_a_clean_exit_with_no_verdict_records_gate_no_verdict(self):
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet",
                      "security-reviewer", "security-reviewer-201")
        [exited] = self._events("WORKER_EXITED")
        self.assertEqual(exited["data"]["exit_code"], 0)
        self.assertFalse(exited["data"]["is_error"])
        [ev] = self._events("GATE_NO_VERDICT")
        self.assertEqual(ev["actor"], "security-reviewer-201")
        self.assertEqual(ev["task"], "T-1")
        self.assertEqual(ev["data"]["role"], "security-reviewer")
        self.assertEqual(ev["data"]["expected_one_of"],
                         ["SECURITY_REVIEW_PASSED", "SECURITY_REVIEW_FAILED"])
        self.assertGreater(ev["seq"], exited["seq"])

    def test_a_gate_that_does_emit_its_verdict_is_not_flagged(self):
        self._harness(verdict="SECURITY_REVIEW_PASSED")
        worker.launch(self.repo, self.root, self._task(), "packet",
                      "security-reviewer", "security-reviewer-201")
        self.assertEqual(len(self._events("SECURITY_REVIEW_PASSED", actor="security-reviewer-201")), 1)
        self.assertEqual(self._events("GATE_NO_VERDICT"), [])

    def test_a_failed_verdict_is_still_a_verdict(self):
        self._harness(verdict="SECURITY_REVIEW_FAILED")
        worker.launch(self.repo, self.root, self._task(), "packet",
                      "security-reviewer", "security-reviewer-201")
        self.assertEqual(self._events("GATE_NO_VERDICT"), [])

    def test_an_implementer_exiting_without_a_verdict_is_not_flagged(self):
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "backend-engineer", "be-1")
        self.assertEqual(self._events("GATE_NO_VERDICT"), [])

    def test_a_rerun_under_a_new_actor_does_not_erase_the_first_runs_silence(self):
        """The exact incident: 201 says nothing, 201b passes. 201b's verdict
        must not retroactively cover 201, and the double spend must stay
        visible in the log, in `company status`'s stalled-gate surfacing
        while the task is open, and in `company costs`."""
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet",
                      "security-reviewer", "security-reviewer-201")
        self._harness(verdict="SECURITY_REVIEW_PASSED")
        worker.launch(self.repo, self.root, self._task(), "packet",
                      "security-reviewer", "security-reviewer-201b")

        events = self.log.read()
        self.assertEqual([e["actor"] for e in self._events("GATE_NO_VERDICT")],
                         ["security-reviewer-201"], "only the silent run is flagged")
        self.assertIsNotNone(worker.gave_no_verdict(events, "T-1", "security-reviewer-201",
                                                    "security-reviewer"))
        self.assertIsNone(worker.gave_no_verdict(events, "T-1", "security-reviewer-201b",
                                                 "security-reviewer"))

        flagged = render.gates_with_no_verdict(events, [{"id": "T-1", "status": "IN_REVIEW"}])
        self.assertIn("security-reviewer-201", flagged["T-1"])

        by_actor = costs.aggregate(events)["by_actor"]
        self.assertEqual(set(by_actor), {"security-reviewer-201", "security-reviewer-201b"},
                         "both paid-for runs show in costs")


if __name__ == "__main__":
    unittest.main()
