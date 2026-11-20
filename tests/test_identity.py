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
import unittest.mock
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
        r = self._run("event", "TASK-1", "REVIEW_FAILED",
                      "--actor", "code-reviewer",     # the lie
                      "--evidence", "notes.md",
                      actor_env="backend-engineer-1")  # the truth
        self.assertEqual(r.returncode, 0, r.stderr)
        events = EventLog(self.root).read()
        self.assertEqual(events[0]["actor"], "backend-engineer-1")
        self.assertIn("ignoring --actor", r.stderr)

    def test_actor_flag_used_when_unassigned(self):
        r = self._run("event", "TASK-1", "REVIEW_FAILED",
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
        r = self._run("event", "TASK-1", "REVIEW_PASSED", "--actor", "code-reviewer-1",
                      "--evidence", "self.md", actor_env="backend-engineer-1")
        self.assertEqual(r.returncode, 2, r.stderr)

        task = taskstate.fold(EventLog(self.root).read())["TASK-1"]
        reasons = taskstate.check_done(task)
        self.assertTrue(any("gate 'review' not satisfied" in r for r in reasons), reasons)


class TestLauncherSignedVerdicts(unittest.TestCase):
    """ESC-002. A gate verdict counts only when the launcher wrote it, from
    the gate worker's structured output, signed with the key under
    .company/secrets/ (which no worker sandbox can read), for a launch it
    signed of the right role on this task after the latest implementation.
    History: a self-chosen actor name (CISO repro), then a guessed reviewer
    name, then a per-launch env secret that the implementer bypassed by
    appending its own WORKER_STARTED to the sandbox-writable log, and that
    leaked to every child of the gate (security review, forge.py)."""

    GATE_ROLES = {"review": "code-reviewer", "qa": "qa-engineer", "security": "security-reviewer"}

    def setUp(self):
        import gatesig
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        for d in ("events", "tasks", "projects"):
            (self.root / d).mkdir(parents=True)
        self.log = EventLog(self.root)
        self.key = gatesig.load_key(self.root, create=True)
        self._created("TASK-1")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, actor_env=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("COMPANY_")}
        env["COMPANY_PROJECT"] = "p"
        if actor_env:
            env["COMPANY_ACTOR"] = actor_env
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), *args],
            capture_output=True, text=True, env=env)

    def _created(self, tid):
        from eventlog import make_event
        self.log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                                   task=tid, data={"title": "t", "owner": "be-1",
                                                   "gates": ["review"]}))

    def _implemented(self, tid="TASK-1", sha="abc1234"):
        from eventlog import make_event
        self.log.append(make_event(event="IMPLEMENTATION_READY", actor="be-1", project="p",
                                   task=tid, evidence={"commit": sha}))
        self.log.append(make_event(event="TEST_RUN", actor="be-1", project="p", task=tid,
                                   data={"cmd": "t", "exit_code": 0}, evidence={"log": "t"}))

    def _launch(self, actor, role="code-reviewer", tasks=("TASK-1",), verdict="pass",
                sha="a" * 40):
        """What worker.launch()/launch_group() do around the gate run."""
        import gatesig
        import worker
        from eventlog import make_event
        tasks = list(tasks)
        group = len(tasks) > 1
        ws = self.log.append(make_event(
            event="WORKER_STARTED", actor=actor, project="p",
            task=None if group else tasks[0],
            data={"role": role, **({"tasks": tasks} if group else {})}),
            finalize=gatesig.sign_started(self.key, tasks, {t: sha for t in tasks}))
        out = ({"task_verdicts": [{"task": t, "verdict": verdict} for t in tasks]}
               if group else {"verdict": verdict})
        if verdict is None:
            out = {}
        worker.record_verdicts(self.log, self.key, role, actor, "p", ws["seq"],
                               [{"id": t} for t in tasks], {"structured_output": out},
                               0, self.root / "out.json", {t: sha for t in tasks})
        return ws

    def _reasons(self, tid="TASK-1", key="default"):
        task = taskstate.fold(self.log.read())[tid]
        return taskstate.check_done(task, gate_roles=self.GATE_ROLES,
                                    gate_key=self.key if key == "default" else key)

    def _raw(self, ev):
        """An implementer's raw append to events.jsonl (its sandbox allows it)."""
        with open(self.log.path, "a") as fh:
            fh.write(json.dumps(ev) + "\n")

    def _last(self, name):
        return [e for e in self.log.read() if e["event"] == name][-1]

    # --- the real path ------------------------------------------------------

    def test_a_launched_reviewer_passing_in_structured_output_satisfies_the_gate(self):
        self._implemented()
        self._launch("code-reviewer-1")
        self.assertEqual(self._reasons(), [])
        self.assertEqual(oct(os.stat(self.root / "secrets" / "gate.key").st_mode & 0o777),
                         "0o600")

    def test_a_group_launch_counts_for_each_member(self):
        self._created("TASK-2")
        self._implemented("TASK-1")
        self._implemented("TASK-2", sha="def5678")
        self._launch("code-reviewer-group-g", tasks=("TASK-1", "TASK-2"))
        self.assertEqual(self._reasons("TASK-1"), [])
        self.assertEqual(self._reasons("TASK-2"), [])

    def test_without_the_key_nothing_verifies(self):
        self._implemented()
        self._launch("code-reviewer-1")
        self.assertTrue(self._reasons(key=None))
        self.assertTrue(self._reasons(key=b"wrong"))

    def test_launched_as_the_wrong_role_does_not_satisfy_the_gate(self):
        self._implemented()
        self._launch("qa-1", role="qa-engineer")  # a QA pass is not a review
        self.assertTrue(self._reasons())

    def test_no_structured_verdict_is_no_verdict(self):
        self._implemented()
        self._launch("code-reviewer-1", verdict=None)
        self.assertTrue(self._reasons())
        self.assertEqual(self._last("GATE_NO_VERDICT")["actor"], "code-reviewer-1")

    # --- forgeries ----------------------------------------------------------

    def test_company_event_refuses_a_pass(self):
        self._implemented()
        for actor in ("be-1", "code-reviewer-1", "totally-not-a-reviewer"):
            r = self._run("event", "TASK-1", "REVIEW_PASSED", "--evidence", "exit 0",
                          actor_env=actor)
            self.assertEqual(r.returncode, 2, r.stderr)
        self.assertTrue(self._reasons())
        # A FAILED is still accepted from anyone: failing is the safe direction.
        r = self._run("event", "TASK-1", "REVIEW_FAILED", actor_env="be-1")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_worker_started_cannot_be_forged_through_company_event(self):
        r = self._run("event", "TASK-1", "WORKER_STARTED",
                      "--data", json.dumps({"role": "code-reviewer"}), actor_env="be-1")
        self.assertNotEqual(r.returncode, 0)

    def test_forge_py_raw_launch_and_pass_with_an_attacker_key(self):
        """The security review's forge.py: the implementer appends its own
        WORKER_STARTED and a pass MAC'd under a key it chose."""
        import gatesig
        self._implemented()
        mine = b"attacker-chosen"
        seq = len(self.log.read()) + 1
        self._raw({"ts": "t", "event": "WORKER_STARTED", "actor": "code-reviewer-1",
                   "project": "p", "task": "TASK-1", "seq": seq,
                   "data": {"role": "code-reviewer", "tier": 2, "launch_mac":
                            gatesig.started_mac(mine, "code-reviewer-1", "code-reviewer",
                                                seq, ["TASK-1"], {"TASK-1": "a" * 40}),
                            "commits": {"TASK-1": "a" * 40}}})
        self._raw({"ts": "t", "event": "REVIEW_PASSED", "actor": "code-reviewer-1",
                   "project": "p", "task": "TASK-1", "seq": seq + 1,
                   "evidence": {"log": "x"},
                   "data": {"role": "code-reviewer", "ws_seq": seq, "verdict": "pass",
                            "commit": "a" * 40,
                            "verdict_mac": gatesig.verdict_mac(
                                mine, "TASK-1", "REVIEW_PASSED", "code-reviewer-1",
                                "code-reviewer", seq, "pass", "a" * 40)}})
        reasons = self._reasons()
        self.assertTrue(any("launcher signature" in r for r in reasons), reasons)

    def test_a_pass_with_an_empty_actor_never_counts(self):
        self._implemented()
        self._launch("code-reviewer-1")
        events = self.log.read()
        assert events[-1]["event"] == "REVIEW_PASSED"
        self.assertEqual(self._reasons(), [])  # control: the genuine event counts
        # The same signed event with its actor blanked, in place of the original.
        events[-1] = dict(events[-1], actor="")
        task = taskstate.fold(events)["TASK-1"]
        self.assertTrue(taskstate.check_done(task, gate_roles=self.GATE_ROLES,
                                             gate_key=self.key))

    def test_a_members_signed_pass_cannot_pass_a_sibling(self):
        self._created("TASK-2")
        self._implemented("TASK-1")
        self._implemented("TASK-2", sha="def5678")
        self._launch("code-reviewer-group-g", tasks=("TASK-1", "TASK-2"), verdict="fail")
        # (a PASS on the very SHA its gate just failed is refused, so: a fix)
        self._launch("code-reviewer-1", tasks=("TASK-1",), sha="b" * 40)
        self._raw(dict(self._last("REVIEW_PASSED"), task="TASK-2"))
        self.assertEqual(self._reasons("TASK-1"), [])
        self.assertTrue(self._reasons("TASK-2"))

    def test_a_signed_pass_replayed_after_a_new_implementation_does_not_count(self):
        self._implemented()
        ws = self._launch("code-reviewer-1")
        old_pass = self._last("REVIEW_PASSED")
        self._implemented(sha="def5678")
        self.assertTrue(self._reasons())
        # Re-append the signed launch and pass after the new implementation.
        self._raw(ws)
        self._raw(old_pass)
        self.assertTrue(self._reasons())

    def test_a_signed_pass_replayed_over_a_later_fail_does_not_count(self):
        self._implemented()
        ws = self._launch("code-reviewer-1")
        old_pass = self._last("REVIEW_PASSED")
        self._launch("code-reviewer-2", verdict="fail")
        self._raw(ws)
        self._raw(old_pass)
        self.assertTrue(self._reasons())

    def test_a_reviewer_launched_before_the_latest_implementation_does_not_count(self):
        self._implemented()
        self._launch("code-reviewer-1")
        self._implemented(sha="def5678")
        self.assertTrue(any("not satisfied" in r for r in self._reasons()))

    def test_pre_esc002_unsigned_passes_no_longer_count(self):
        from eventlog import make_event
        self._implemented()
        self.log.append(make_event(event="WORKER_STARTED", actor="code-reviewer-1",
                                   project="p", task="TASK-1",
                                   data={"role": "code-reviewer", "tier": 2}))
        self.log.append(make_event(event="REVIEW_PASSED", actor="code-reviewer-1",
                                   project="p", task="TASK-1", evidence={"log": "n"}))
        self.assertTrue(self._reasons())

    def test_no_gate_secret_reaches_any_worker(self):
        import worker
        with unittest.mock.patch.dict(os.environ, {"COMPANY_GATE_SECRET": "leak"}):
            env = worker.build_env(Path("/r"), self.root, {"id": "TASK-1"}, "qa-1", Path("/w"))
        self.assertFalse([k for k, v in env.items() if self.key.hex() in v])
        tools = (HERE.parent / "tools" / "company")
        self.assertFalse([f.name for f in tools.glob("*.py")
                          if "COMPANY_GATE_SECRET" in f.read_text()])


if __name__ == "__main__":
    unittest.main()
