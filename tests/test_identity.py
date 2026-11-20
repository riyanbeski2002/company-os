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
        import worker
        from eventlog import make_event
        log = EventLog(self.root)
        log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                              task="TASK-1", data={"title": "t", "owner": "be-1", "gates": ["review"]}))
        self._run("event", "TASK-1", "IMPLEMENTATION_READY", "--evidence", "abc1234",
                  actor_env="be-1")
        self._run("event", "TASK-1", "TEST_RUN",
                  "--data", json.dumps({"cmd": "t", "exit_code": 0}),
                  "--evidence", "t.log", actor_env="be-1")
        # Launched after the implementation, as worker.launch() does it.
        secret, proof_data = worker._gate_secret("code-reviewer", ["TASK-1"])
        log.append(make_event(event="WORKER_STARTED", actor="code-reviewer-1", project="p",
                              task="TASK-1", data={"role": "code-reviewer", "tier": 2,
                                                   **proof_data}))
        with unittest.mock.patch.dict(os.environ, {"COMPANY_GATE_SECRET": secret}):
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


class TestForgedVerdictUnderARealReviewersName(unittest.TestCase):
    """ESC-002. The role binding above checks that the verdict's actor has a
    code-reviewer launch record on the task, but actor names are predictable
    (`code-reviewer-<n>`) and $COMPANY_ACTOR is just an env var: the
    implementer could sign a verdict as the reviewer that really was
    launched, and it counted toward DONE and merge. A verdict now has to
    present the secret the launcher put in that reviewer's env."""

    GATE_ROLES = TestGateActorRoleBinding.GATE_ROLES

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        for d in ("events", "tasks", "projects"):
            (self.root / d).mkdir(parents=True)
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, actor_env=None, token=None):
        env = dict(os.environ)
        env["COMPANY_PROJECT"] = "p"
        env.pop("COMPANY_ACTOR", None)
        env.pop("COMPANY_GATE_SECRET", None)
        if actor_env:
            env["COMPANY_ACTOR"] = actor_env
        if token:
            env["COMPANY_GATE_SECRET"] = token
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), *args],
            capture_output=True, text=True, env=env)

    def _start(self, actor, role, token, tasks=None):
        """What worker.launch()/launch_group() record via _gate_secret: the
        hash of each task's PASSED proof, never the secret."""
        from eventlog import gate_proof, make_event, proof_sha256
        members = tasks or ["TASK-1"]
        data = {"role": role, "tier": 2, "pass_event": "REVIEW_PASSED",
                "pass_proof_sha256": {
                    t: proof_sha256(gate_proof(token, t, "REVIEW_PASSED")) for t in members}}
        if tasks:
            data["tasks"] = tasks
        self.log.append(make_event(event="WORKER_STARTED", actor=actor, project="p",
                                   task=None if tasks else "TASK-1", data=data))

    def _created(self):
        from eventlog import make_event
        self.log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                                   task="TASK-1", data={"title": "t", "owner": "be-1",
                                                        "gates": ["review"]}))

    def _implemented(self, sha="abc1234"):
        self._run("event", "TASK-1", "IMPLEMENTATION_READY", "--evidence", sha,
                  actor_env="be-1")
        self._run("event", "TASK-1", "TEST_RUN",
                  "--data", json.dumps({"cmd": "t", "exit_code": 0}),
                  "--evidence", "t.log", actor_env="be-1")

    def _verdict(self, event, actor, token=None):
        return self._run("event", "TASK-1", event, "--evidence", "exit 0",
                         actor_env=actor, token=token)

    def _reasons(self):
        task = taskstate.fold(self.log.read())["TASK-1"]
        return taskstate.check_done(task, gate_roles=self.GATE_ROLES)

    def _refused(self):
        reasons = self._reasons()
        self.assertTrue(any("launch token" in r for r in reasons), reasons)

    def test_implementer_forging_the_launched_reviewers_name_is_refused(self):
        self._created()
        self._implemented()
        self._start("code-reviewer-1", "code-reviewer", "reviewers-secret")
        # The implementer guesses the reviewer's name; it never saw the token.
        self._verdict("REVIEW_PASSED", "code-reviewer-1")
        self._refused()

    def test_a_guessed_token_is_refused(self):
        self._created()
        self._implemented()
        self._start("code-reviewer-1", "code-reviewer", "reviewers-secret")
        self._verdict("REVIEW_PASSED", "code-reviewer-1", token="guess")
        self._refused()

    def test_the_real_reviewer_presenting_its_token_passes(self):
        self._created()
        self._implemented()
        self._start("code-reviewer-1", "code-reviewer", "reviewers-secret")
        r = self._verdict("REVIEW_PASSED", "code-reviewer-1", token="reviewers-secret")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._reasons(), [])
        # The log carries a proof the fold can check, never the raw secret
        # of a launch that has not voted yet.
        self.assertNotIn("reviewers-secret", json.dumps(self.log.read()[:-1]))

    def test_a_group_launch_token_counts_for_its_members(self):
        self._created()
        self._implemented()
        self._start("code-reviewer-group-g", "code-reviewer", "grp", tasks=["TASK-1"])
        self._verdict("REVIEW_PASSED", "code-reviewer-group-g", token="grp")
        self.assertEqual(self._reasons(), [])

    def test_another_actors_token_does_not_transfer(self):
        self._created()
        self._implemented()
        self._start("code-reviewer-1", "code-reviewer", "tok")
        self._verdict("REVIEW_PASSED", "code-reviewer-2", token="tok")
        self.assertTrue(self._reasons())

    def test_a_reviewer_started_before_the_latest_implementation_does_not_count(self):
        """Its token was minted for an older commit."""
        self._created()
        self._start("code-reviewer-1", "code-reviewer", "old")
        self._implemented()
        self._verdict("REVIEW_PASSED", "code-reviewer-1", token="old")
        self._refused()

    def test_a_new_implementation_after_the_pass_voids_it(self):
        self._created()
        self._implemented()
        self._start("code-reviewer-1", "code-reviewer", "tok")
        self._verdict("REVIEW_PASSED", "code-reviewer-1", token="tok")
        self._implemented(sha="def5678")
        self._refused()

    def _replay(self, event, actor, proof, task="TASK-1"):
        """A forger copying a proof it read from the log (no secret)."""
        return self._run("event", task, event, "--evidence", "exit 0",
                         "--data", json.dumps({"gate_proof": proof}), actor_env=actor)

    def _proof_of(self, event, task="TASK-1"):
        return next(e["data"]["gate_proof"] for e in self.log.read()
                    if e["event"] == event and e.get("task") == task)

    def test_a_failed_verdict_leaks_nothing_that_could_pass(self):
        self._created()
        self._implemented()
        self._start("code-reviewer-1", "code-reviewer", "tok")
        self._verdict("REVIEW_FAILED", "code-reviewer-1", token="tok")
        self.assertNotIn("gate_proof", json.dumps(self.log.read()))
        self._verdict("REVIEW_PASSED", "code-reviewer-1")  # forged over the failure
        self._refused()

    def test_a_group_members_proof_cannot_pass_a_sibling(self):
        from eventlog import make_event
        self._created()
        self.log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                                   task="TASK-2", data={"title": "t2", "owner": "be-2",
                                                        "gates": ["review"]}))
        self._implemented()
        self._start("code-reviewer-group-g", "code-reviewer", "grp", tasks=["TASK-1", "TASK-2"])
        self._verdict("REVIEW_PASSED", "code-reviewer-group-g", token="grp")
        self._replay("REVIEW_PASSED", "code-reviewer-group-g",
                     self._proof_of("REVIEW_PASSED"), task="TASK-2")
        task2 = taskstate.fold(self.log.read())["TASK-2"]
        reasons = taskstate.check_done(task2, gate_roles=self.GATE_ROLES)
        self.assertTrue(any("launch token" in r for r in reasons), reasons)

    def test_an_earlier_pass_cannot_be_replayed_over_a_later_fail(self):
        self._created()
        self._implemented()
        self._start("code-reviewer-1", "code-reviewer", "first")
        self._verdict("REVIEW_PASSED", "code-reviewer-1", token="first")
        self._start("code-reviewer-2", "code-reviewer", "second")
        self._verdict("REVIEW_FAILED", "code-reviewer-2", token="second")
        self._replay("REVIEW_PASSED", "code-reviewer-1", self._proof_of("REVIEW_PASSED"))
        self.assertTrue(self._reasons())

    def test_launcher_mints_a_fresh_secret_only_for_gate_roles(self):
        import worker
        s1, d1 = worker._gate_secret("code-reviewer", ["TASK-1"])
        s2, _ = worker._gate_secret("code-reviewer", ["TASK-1"])
        self.assertNotEqual(s1, s2)
        self.assertNotIn(s1, json.dumps(d1))
        self.assertEqual(worker._gate_secret("backend-engineer", ["TASK-1"]), (None, {}))

    def test_build_env_never_inherits_a_gate_secret(self):
        import worker
        with unittest.mock.patch.dict(os.environ, {"COMPANY_GATE_SECRET": "leak"}):
            env = worker.build_env(Path("/r"), self.root, {"id": "TASK-1"}, "be-1", Path("/w"))
        self.assertNotIn("COMPANY_GATE_SECRET", env)


if __name__ == "__main__":
    unittest.main()
