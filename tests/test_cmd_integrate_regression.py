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


if __name__ == "__main__":
    unittest.main()
