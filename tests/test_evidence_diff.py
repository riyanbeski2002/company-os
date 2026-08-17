"""Evidence Rule: a commit SHA is not evidence of work unless it is actually
ahead of the task's base ref (D6).

Live-reproduced on the finos repo, 17 Aug: a Tier-2 worker launched via
`company run <task> --role backend-engineer --detach` reported
IMPLEMENTATION_READY with evidence {"tests": "exit 0", "diff": <sha>} where
<sha> was the worktree's own merge-base with main. `git log main..HEAD` was
empty and the tree was clean — the worker did zero work but self-reported
completion, and a green test run looked like proof because nothing had
changed to break. See cli.py:_reject_noop_diff.
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


def _git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {args} failed: {r.stderr}"
    return r.stdout.strip()


class TestNoopDiffRejected(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        _git("init", "-q", "-b", "main", cwd=self.repo)
        _git("config", "user.email", "t@t.com", cwd=self.repo)
        _git("config", "user.name", "t", cwd=self.repo)
        (self.repo / "f.txt").write_text("one\n")
        _git("add", ".", cwd=self.repo)
        _git("commit", "-q", "-m", "init", cwd=self.repo)

        self.root = self.repo / ".company"
        for d in ("events", "tasks", "projects"):
            (self.root / d).mkdir(parents=True)

        self.worktree = Path(self.tmp.name) / "wt-task-1"
        _git("worktree", "add", str(self.worktree), "-b", "task/1", "main", cwd=self.repo)

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

    def _create_task(self, tid="TASK-1"):
        r = self._run("event", tid, "TASK_CREATED",
                      "--data", json.dumps({
                          "title": "t", "tier": 2, "base": "main",
                          "worktree": str(self.worktree),
                      }),
                      actor_env="company-pm")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_sha_with_zero_commits_ahead_of_base_is_rejected(self):
        self._create_task()
        base_sha = _git("rev-parse", "main", cwd=self.repo)  # nothing committed in the worktree

        r = self._run("event", "TASK-1", "IMPLEMENTATION_READY",
                      "--evidence", base_sha, actor_env="backend-engineer-1")

        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("0 commits ahead", r.stderr)
        events = [e for e in EventLog(self.root).read() if e["event"] == "IMPLEMENTATION_READY"]
        self.assertEqual(events, [])  # never written to the log

    def test_a_real_commit_ahead_of_base_is_accepted(self):
        self._create_task()
        (self.worktree / "f.txt").write_text("one\ntwo\n")
        _git("add", ".", cwd=self.worktree)
        _git("commit", "-q", "-m", "actual work", cwd=self.worktree)
        real_sha = _git("rev-parse", "HEAD", cwd=self.worktree)

        r = self._run("event", "TASK-1", "IMPLEMENTATION_READY",
                      "--evidence", real_sha, actor_env="backend-engineer-1")

        self.assertEqual(r.returncode, 0, r.stderr)
        task = taskstate.fold(EventLog(self.root).read())["TASK-1"]
        self.assertEqual(task["evidence"]["diff"], real_sha)

    def test_unresolvable_sha_is_also_rejected(self):
        """A garbage SHA must not slip through just because it isn't 0-ahead —
        `git rev-list` failing outright is exactly as untrustworthy."""
        self._create_task()
        r = self._run("event", "TASK-1", "IMPLEMENTATION_READY",
                      "--evidence", "deadbeef", actor_env="backend-engineer-1")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("could not be verified", r.stderr)

    def test_task_without_a_real_worktree_is_unaffected(self):
        """No checkout to verify against (e.g. a Tier-1 task, or a unit-test
        fixture) — the check has nothing to compare and gets out of the way,
        same as before this fix."""
        r = self._run("event", "TASK-2", "TASK_CREATED",
                      "--data", json.dumps({"title": "t", "tier": 1}),
                      actor_env="company-pm")
        self.assertEqual(r.returncode, 0, r.stderr)

        r = self._run("event", "TASK-2", "IMPLEMENTATION_READY",
                      "--evidence", "abc1234", actor_env="backend-engineer-1")
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
