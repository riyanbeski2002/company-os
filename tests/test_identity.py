"""Actor identity (D6).

The Evidence Rule turns on WHO authored a gate event. If a worker could choose
its own name, it could call itself "code-reviewer" and sign off on its own
change — which is exactly the thing the rule exists to prevent.

A real reviewer run signed its verdict as "qa/verifier" rather than its assigned
worker id, which is what prompted this.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

from eventlog import EventLog  # noqa: E402
import taskstate  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"


class TestAssignedIdentityWins(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        for d in ("events", "tasks", "projects"):
            (self.root / d).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, actor_env=None):
        env = dict(os.environ)
        env["COMPANY_PROJECT"] = "p"
        env.pop("COMPANY_ACTOR", None)
        if actor_env:
            env["COMPANY_ACTOR"] = actor_env
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), *args],
            capture_output=True, text=True, env=env)

    def test_worker_cannot_rename_itself(self):
        r = self._run("event", "TASK-1", "REVIEW_PASSED",
                      "--actor", "code-reviewer",     # the lie
                      "--evidence", "notes.md",
                      actor_env="backend-engineer-1")  # the truth
        self.assertEqual(r.returncode, 0, r.stderr)
        events = EventLog(self.root).read()
        self.assertEqual(events[0]["actor"], "backend-engineer-1")
        self.assertIn("ignoring --actor", r.stderr)

    def test_actor_flag_used_when_unassigned(self):
        r = self._run("event", "TASK-1", "REVIEW_PASSED",
                      "--actor", "code-reviewer-1", "--evidence", "notes.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(EventLog(self.root).read()[0]["actor"], "code-reviewer-1")

    def test_impersonation_cannot_satisfy_a_gate(self):
        """The end-to-end consequence: a worker signing off on itself is refused."""
        self._run("event", "TASK-1", "TASK_CREATED",
                  "--data", json.dumps({"title": "t", "owner": "backend-engineer-1",
                                        "gates": ["review"]}),
                  actor_env="company-pm")
        self._run("event", "TASK-1", "IMPLEMENTATION_READY", "--evidence", "abc1234",
                  actor_env="backend-engineer-1")
        self._run("event", "TASK-1", "TEST_RUN",
                  "--data", json.dumps({"cmd": "t", "exit_code": 0}),
                  "--evidence", "t.log", actor_env="backend-engineer-1")
        # The implementer tries to pass its own review under a reviewer's name.
        self._run("event", "TASK-1", "REVIEW_PASSED", "--actor", "code-reviewer-1",
                  "--evidence", "self.md", actor_env="backend-engineer-1")

        task = taskstate.fold(EventLog(self.root).read())["TASK-1"]
        reasons = taskstate.check_done(task)
        self.assertTrue(any("self-certified" in r for r in reasons), reasons)


class TestGateActorRoleBinding(unittest.TestCase):
    """CISO live-reproduced this: a worker sets $COMPANY_ACTOR to ANY string
    that isn't its own owner id and satisfies a gate with zero real review,
    because `actor != owner` was the entire check. Fixed by requiring the
    actor to have a WORKER_STARTED record on this task, written by the
    trusted launcher, whose role matches what the gate requires — and by
    blocking WORKER_STARTED itself from the worker-facing `company event`
    verb, since without that a worker could just forge its own launch record.
    """

    GATE_ROLES = {"review": "code-reviewer", "qa": "qa-engineer", "security": "security-reviewer"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        for d in ("events", "tasks", "projects"):
            (self.root / d).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, actor_env=None):
        env = dict(os.environ)
        env["COMPANY_PROJECT"] = "p"
        env.pop("COMPANY_ACTOR", None)
        if actor_env:
            env["COMPANY_ACTOR"] = actor_env
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), *args],
            capture_output=True, text=True, env=env)

    def test_the_live_reproduced_bypass_is_now_refused(self):
        """The exact CISO repro: an actor with no real launch record at all."""
        self._run("event", "TASK-1", "TASK_CREATED",
                  "--data", json.dumps({"title": "t", "owner": "backend-engineer-1",
                                        "gates": ["review"]}), actor_env="company-pm")
        self._run("event", "TASK-1", "REVIEW_PASSED", "--evidence", "exit 0",
                  actor_env="totally-not-a-reviewer")

        task = taskstate.fold(EventLog(self.root).read())["TASK-1"]
        reasons = taskstate.check_done(task, gate_roles=self.GATE_ROLES)
        self.assertTrue(any("no verified" in r and "code-reviewer" in r for r in reasons), reasons)

    def test_a_reviewer_launched_for_a_different_task_does_not_count(self):
        """Scoped per-task: a real code-reviewer id is not a blank check for
        every task it didn't actually review."""
        from eventlog import make_event
        log = EventLog(self.root)
        log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                              task="TASK-1", data={"title": "t", "owner": "be-1", "gates": ["review"]}))
        log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                              task="TASK-2", data={"title": "t2", "owner": "be-2", "gates": ["review"]}))
        # code-reviewer-1 was genuinely launched, but for TASK-2, not TASK-1.
        log.append(make_event(event="WORKER_STARTED", actor="code-reviewer-1", project="p",
                              task="TASK-2", data={"role": "code-reviewer", "tier": 2}))
        self._run("event", "TASK-1", "REVIEW_PASSED", "--evidence", "exit 0",
                  actor_env="code-reviewer-1")

        tasks = taskstate.fold(EventLog(self.root).read())
        reasons = taskstate.check_done(tasks["TASK-1"], gate_roles=self.GATE_ROLES)
        self.assertTrue(any("no verified" in r for r in reasons), reasons)

    def test_a_genuinely_launched_reviewer_satisfies_the_gate(self):
        from eventlog import make_event
        log = EventLog(self.root)
        log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                              task="TASK-1", data={"title": "t", "owner": "be-1", "gates": ["review"]}))
        log.append(make_event(event="WORKER_STARTED", actor="code-reviewer-1", project="p",
                              task="TASK-1", data={"role": "code-reviewer", "tier": 2}))
        self._run("event", "TASK-1", "IMPLEMENTATION_READY", "--evidence", "abc1234",
                  actor_env="be-1")
        self._run("event", "TASK-1", "TEST_RUN",
                  "--data", json.dumps({"cmd": "t", "exit_code": 0}),
                  "--evidence", "t.log", actor_env="be-1")
        self._run("event", "TASK-1", "REVIEW_PASSED", "--evidence", "exit 0",
                  actor_env="code-reviewer-1")

        tasks = taskstate.fold(EventLog(self.root).read())
        reasons = taskstate.check_done(tasks["TASK-1"], gate_roles=self.GATE_ROLES)
        self.assertEqual(reasons, [])

    def test_launched_as_the_wrong_role_does_not_satisfy_the_gate(self):
        """A real launch record exists, but as a backend-engineer, not a
        code-reviewer — the role must match, not just 'was launched at all'."""
        from eventlog import make_event
        log = EventLog(self.root)
        log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                              task="TASK-1", data={"title": "t", "owner": "be-1", "gates": ["review"]}))
        log.append(make_event(event="WORKER_STARTED", actor="be-2", project="p",
                              task="TASK-1", data={"role": "backend-engineer", "tier": 2}))
        self._run("event", "TASK-1", "REVIEW_PASSED", "--evidence", "exit 0", actor_env="be-2")

        tasks = taskstate.fold(EventLog(self.root).read())
        reasons = taskstate.check_done(tasks["TASK-1"], gate_roles=self.GATE_ROLES)
        self.assertTrue(any("was launched as 'backend-engineer'" in r for r in reasons), reasons)

    def test_without_gate_roles_the_old_self_cert_check_still_runs(self):
        """Backward compatible: callers that don't pass gate_roles still get
        the original actor != owner check, not a silent no-op."""
        task = {"id": "T-1", "owner": "be-1", "gates": ["review"],
               "evidence": {"diff": "abc", "tests": "exit 0", "review": "x",
                            "review_actor": "be-1"}}
        reasons = taskstate.check_done(task)
        self.assertTrue(any("self-certified" in r for r in reasons), reasons)

    def test_worker_started_cannot_be_forged_through_company_event(self):
        """The actual trust boundary: without this, a worker could forge its
        own launch record and defeat the role-binding check entirely."""
        result = self._run("event", "TASK-1", "WORKER_STARTED",
                           "--data", json.dumps({"role": "code-reviewer"}),
                           actor_env="backend-engineer-1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(EventLog(self.root).read(), [])

    def test_worker_exited_and_heartbeat_also_blocked(self):
        for event_type in ("WORKER_EXITED", "WORKER_HEARTBEAT"):
            result = self._run("event", "TASK-1", event_type, actor_env="backend-engineer-1")
            self.assertNotEqual(result.returncode, 0, event_type)


if __name__ == "__main__":
    unittest.main()
