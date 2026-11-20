"""Commit 6cdd62d (2026-10-21, "4 ECC/paperclip orchestration-reliability
mechanisms...") rewrote cmd_integrate's gate check to be fail-closed on any
check_done() reason, but deleted the line that assigns `reasons` while
keeping the line that reads it — every `company integrate` call raised
`NameError: reasons`, unconditionally. No existing test caught this because
test_integrate.py only exercises the `integrate` module's helper functions,
never `cli.cmd_integrate` itself.

This runs cmd_integrate end to end (real EventLog, real taskstate.fold) and
would fail with the NameError if the assignment regressed again.
"""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import cli  # noqa: E402
from eventlog import EventLog, make_event  # noqa: E402


class Args:
    def __init__(self, **kw):
        self.root = None
        self.task = None
        self.test_command = "true"
        self.force = False
        self.actor = "pm"
        self.json = True
        self.__dict__.update(kw)


class TestCmdIntegrateDoesNotCrash(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.root = self.repo / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gates_not_satisfied_path_does_not_raise_nameerror(self):
        # TASK_CREATED + IMPLEMENTATION_READY gives evidence.diff, so the
        # task qualifies as an integrate target, but no TEST_RUN event means
        # check_done() returns a non-empty `reasons` list — the exact branch
        # that read `reasons` without it ever being assigned.
        self.log.append(make_event(event="TASK_CREATED", actor="pm", project="p", task="T-1"))
        self.log.append(make_event(
            event="IMPLEMENTATION_READY", actor="backend-engineer", project="p", task="T-1",
            evidence={"commit": "abc123"}))

        args = Args(root=str(self.root), task="T-1")
        with self.assertRaises(SystemExit) as ctx:
            cli.cmd_integrate(args)

        # A regression of the deleted assignment raises NameError instead,
        # which would surface as an uncaught exception, not SystemExit.
        self.assertIn(ctx.exception.code, (0, 3))


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t",
                           *args], check=True, capture_output=True, text=True).stdout.strip()


class TestIntegrateMergesTheReviewedCommit(unittest.TestCase):
    """ESC-002 (b), security re-review: integrate merged the branch TIP while
    the gates had judged some earlier commit, so anything a gate ran — a
    conftest during QA — could `git commit` to the branch and have that
    merged unreviewed. Gates now sign the SHA the launcher read; integrate
    merges exactly it and refuses a branch that has moved."""

    def setUp(self):
        import gatesig
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.root = self.repo / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)
        self.key = gatesig.load_key(self.root, create=True)
        _git(self.repo, "init", "-q", "-b", "main")
        (self.repo / ".gitignore").write_text(".company/\n")
        (self.repo / "api").mkdir()
        (self.repo / "api" / "app.py").write_text("orig\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "init")
        _git(self.repo, "branch", "task/1-x")
        self.reviewed = self._commit("api/app.py", "reviewed\n")
        self.log.append(make_event(event="TASK_CREATED", actor="pm", project="p", task="T-1",
                                   data={"title": "x", "owner": "be-1", "branch": "task/1-x",
                                         "owned_globs": ["api/**"], "gates": ["review", "qa"]}))
        self.log.append(make_event(event="IMPLEMENTATION_READY", actor="be-1", project="p",
                                   task="T-1", evidence={"commit": self.reviewed}))
        self.log.append(make_event(event="TEST_RUN", actor="be-1", project="p", task="T-1",
                                   data={"exit_code": 0}, evidence={"log": "t"}))

    def tearDown(self):
        self.tmp.cleanup()

    def _commit(self, rel, text):
        wt = self.repo / "wt"
        if not wt.exists():
            _git(self.repo, "worktree", "add", "-q", str(wt), "task/1-x")
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text)
        _git(wt, "add", "-A")
        _git(wt, "commit", "-qm", f"touch {rel}")
        return _git(wt, "rev-parse", "HEAD")

    def _gate(self, actor, role):
        """What worker.launch does around a gate that passes: the SHA is the
        branch tip read through the main checkout at launch."""
        import gatesig
        import worker
        commits = {"T-1": worker.branch_sha(self.repo, "task/1-x")}
        ws = self.log.append(make_event(event="WORKER_STARTED", actor=actor, project="p",
                                        task="T-1", data={"role": role}),
                             finalize=gatesig.sign_started(self.key, ["T-1"], commits))
        worker.record_verdicts(self.log, self.key, role, actor, "p", ws["seq"], [{"id": "T-1"}],
                               {"structured_output": {"verdict": "pass"}}, 0,
                               self.root / "out.json", commits)

    def _integrate(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            cli.cmd_integrate(Args(root=str(self.root), task="T-1"))
        [result] = json.loads(out.getvalue())["results"]
        return result

    def _merged(self):
        return [e for e in self.log.read() if e["event"] == "MERGED"]

    def test_a_genuine_same_sha_flow_merges_that_sha(self):
        self._gate("code-reviewer-1", "code-reviewer")
        self._gate("qa-1", "qa-engineer")
        result = self._integrate()
        self.assertTrue(result["merged"], result)
        self.assertEqual(result["commit_reviewed"], self.reviewed)
        _git(self.repo, "merge-base", "--is-ancestor", self.reviewed, "integration")

    def test_a_commit_after_the_pass_is_refused_at_integrate(self):
        self._gate("code-reviewer-1", "code-reviewer")
        self._gate("qa-1", "qa-engineer")
        # QA's run of the implementer's tests (a conftest) commits to the branch.
        sneaked = self._commit("api/app.py", "unreviewed\n")
        result = self._integrate()
        self.assertFalse(result["merged"], result)
        self.assertEqual(result["reason"], "branch moved after review")
        self.assertFalse(self._merged())
        r = subprocess.run(["git", "-C", str(self.repo), "merge-base", "--is-ancestor",
                            sneaked, "integration"], capture_output=True)
        self.assertNotEqual(r.returncode, 0, "the unreviewed commit must not be merged")

    def test_gates_that_passed_different_shas_are_refused(self):
        import taskstate
        self._gate("code-reviewer-1", "code-reviewer")
        self._commit("api/app.py", "changed after review\n")
        self._gate("qa-1", "qa-engineer")  # QA judged the newer commit
        task = taskstate.fold(self.log.read())["T-1"]
        reasons = taskstate.check_done(task, gate_key=self.key)
        self.assertTrue(any("different commits" in r for r in reasons), reasons)
        self.assertIsNone(taskstate.reviewed_commit(task, self.key))
        result = self._integrate()
        self.assertFalse(result["merged"], result)
        self.assertFalse(self._merged())


class TestWorkersCannotRewriteTheirTask(unittest.TestCase):
    """ESC-002 (c), final review (sr/ungate.py): an implementer re-declared
    its own task with `company event TASK-1 TASK_CREATED --data
    '{"gates":[]}'`; the fold took the new gates, check_done returned [] and
    integrate merged the tip. Every event the fold derives gating, ownership,
    status or the baseline from now counts only when the PM signed it."""

    CLI = HERE.parent / "tools" / "company" / "cli.py"

    def setUp(self):
        import gatesig
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.root = self.repo / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)
        _git(self.repo, "init", "-q", "-b", "main")
        (self.repo / ".gitignore").write_text(".company/\n")
        (self.repo / "api").mkdir()
        (self.repo / "api" / "app.py").write_text("orig\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "init")
        _git(self.repo, "checkout", "-qb", "task/1-x")
        (self.repo / "api" / "app.py").write_text("work\n")
        _git(self.repo, "commit", "-qam", "work")
        self.tip = _git(self.repo, "rev-parse", "HEAD")
        _git(self.repo, "checkout", "-q", "main")
        self.sign = gatesig.pm_signer(self.root)  # what `company staff` uses
        self.key = gatesig.load_key(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _pm(self, event, tid="TASK-1", **data):
        self.log.append(make_event(event=event, actor="company-pm", project="p", task=tid,
                                   data=data), finalize=self.sign)

    def _define(self, tid="TASK-1", gates=("review",)):
        self._pm("TASK_CREATED", tid, title="x", owner="be-1", branch="task/1-x",
                 owned_globs=["api/**"], gates=list(gates))
        self.log.append(make_event(event="IMPLEMENTATION_READY", actor="be-1", project="p",
                                   task=tid, evidence={"commit": self.tip}))
        self.log.append(make_event(event="TEST_RUN", actor="be-1", project="p", task=tid,
                                   data={"exit_code": 0}, evidence={"log": "t"}))

    def _worker(self, *args):
        env = {k: v for k, v in __import__("os").environ.items() if not k.startswith("COMPANY_")}
        env.update(COMPANY_PROJECT="p", COMPANY_ACTOR="be-1")
        return subprocess.run([sys.executable, str(self.CLI), "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env)

    def _raw(self, event, tid="TASK-1", **data):
        with open(self.log.path, "a") as fh:
            fh.write(json.dumps({"ts": "t", "event": event, "actor": "be-1", "project": "p",
                                 "task": tid, "seq": len(self.log.read()) + 1,
                                 "data": data}) + "\n")

    def _task(self, tid="TASK-1"):
        import taskstate
        return taskstate.load(self.root).get(tid)

    def _integrate(self, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            cli.cmd_integrate(Args(root=str(self.root), task="TASK-1", **kw))
        return json.loads(out.getvalue())["results"][0]

    def test_ungate_py_fails_closed(self):
        import taskstate
        self._define()
        r = self._worker("event", "TASK-1", "TASK_CREATED", "--data",
                         json.dumps({"title": "t", "owner": "be-1", "gates": []}))
        self._raw("TASK_CREATED", title="t", owner="be-1", gates=[], owned_globs=["**"])
        task = self._task()
        self.assertEqual(task["gates"], ["review"], r.stderr)
        self.assertEqual(task["owned_globs"], ["api/**"])
        self.assertTrue(taskstate.check_done(task, gate_key=self.key))
        self.assertFalse(self._integrate()["merged"])
        self.assertFalse([e for e in self.log.read() if e["event"] == "MERGED"])

    def test_a_duplicate_task_created_is_ignored_even_without_the_key(self):
        import taskstate
        self._define()
        self._raw("TASK_CREATED", title="t", owner="someone-else", gates=["qa"],
                  owned_globs=["**"], branch="evil")
        for task in (self._task(), taskstate.fold(self.log.read())["TASK-1"]):
            self.assertEqual(task["owner"], "be-1")
            self.assertEqual(task["branch"], "task/1-x")
            self.assertEqual(task["owned_globs"], ["api/**"])
        # ...except that gates only ever grow.
        self.assertEqual(self._task()["gates"], ["review"])  # unsigned: dropped entirely
        self.assertEqual(taskstate.fold(self.log.read())["TASK-1"]["gates"], ["review", "qa"])

    def test_a_signed_pm_redefinition_still_applies(self):
        self._define()
        self._pm("TASK_CREATED", title="x", owner="be-1", branch="task/1-x",
                 owned_globs=["api/**"], gates=["review", "qa"])
        self.assertEqual(self._task()["gates"], ["review", "qa"])

    def test_unsigned_status_merged_assignment_and_baseline_are_ignored(self):
        import baseline
        self._define()
        self._raw("STATUS_CHANGED", to="DONE")
        self._raw("TASK_COMPLETED")
        self._raw("MERGED")
        self._raw("TASK_ASSIGNED", owner="code-reviewer-1", branch="other")
        with open(self.log.path, "a") as fh:  # a red baseline excusing failures
            fh.write(json.dumps({"ts": "t", "event": "BASELINE_RECORDED", "actor": "be-1",
                                 "project": "p", "seq": len(self.log.read()) + 1,
                                 "data": {"exit_code": 1, "failures": 999,
                                          "green": False}}) + "\n")
        task = self._task()
        self.assertEqual(task["status"], "IMPLEMENTATION_READY")
        self.assertNotIn("merged", task["evidence"])
        self.assertEqual((task["owner"], task["branch"]), ("be-1", "task/1-x"))
        self.assertIsNone(cli._baseline(self.root, "p"))

    def test_a_replayed_signed_event_is_ignored(self):
        self._define()
        first = [e for e in self.log.read() if e["event"] == "TASK_CREATED"][0]
        self._pm("TASK_ASSIGNED", owner="be-2", branch="task/1-x")
        assigned = [e for e in self.log.read() if e["event"] == "TASK_ASSIGNED"][0]
        self._pm("TASK_ASSIGNED", owner="be-3", branch="task/1-x")
        with open(self.log.path, "a") as fh:
            fh.write(json.dumps(assigned) + "\n")
            fh.write(json.dumps(dict(first, data={**first["data"], "gates": []})) + "\n")
        task = self._task()
        self.assertEqual(task["owner"], "be-3")
        self.assertEqual(task["gates"], ["review"])

    def test_a_new_unsigned_task_cannot_merge_with_or_without_force(self):
        self._define("TASK-0")  # signing has begun in this log
        self._raw("TASK_CREATED", title="mine", owner="be-1", branch="task/1-x",
                  owned_globs=["**"], gates=[])
        self._raw("IMPLEMENTATION_READY")
        task = self._task()  # the definition was dropped: no title, globs or signature
        self.assertFalse({"title", "owned_globs", "created_signed"} & set(task))
        # And where it IS visible (no key: an old log), it still can't merge.
        import gatesig
        gatesig.key_path(self.root).unlink()
        for force in (False, True):
            result = self._integrate(force=force)
            self.assertFalse(result["merged"], result)
        self.assertFalse([e for e in self.log.read() if e["event"] == "MERGED"])

    def test_a_signed_ungated_task_merges(self):
        """The control: the PM's own ungated task still integrates."""
        self._define(gates=())
        result = self._integrate()
        self.assertTrue(result["merged"], result)
        [merged] = [e for e in self.log.read() if e["event"] == "MERGED"]
        self.assertIn("pm_mac", merged["data"])
        self.assertEqual(self._task()["status"], "MERGED")

    def test_integrate_and_force_are_refused_inside_a_worker(self):
        self._define(gates=())
        for extra in ([], ["--force"]):
            r = self._worker("integrate", "--task", "TASK-1", "--test-command", "true", *extra)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("inside a launched worker", r.stderr)
        self.assertFalse([e for e in self.log.read() if e["event"] == "MERGED"])


if __name__ == "__main__":
    unittest.main()
