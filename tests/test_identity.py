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


if __name__ == "__main__":
    unittest.main()
