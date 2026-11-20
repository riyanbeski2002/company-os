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


def poison_worktree_gitdir(repo: Path, wt: Path, branch: str, marker: Path) -> None:
    """ESC-014 / security review p2: the worker repoints its worktree's `.git`
    at a NON-bare gitdir it controls — core.worktree set, the real objects
    via alternates, the branch and index copied — so `git -C <worktree>`
    in the PM's process works normally while running core.fsmonitor (any
    index read) and diff.external (any diff) as the PM."""
    evil = Path(repo).parent / f"evil-{wt.name}"
    subprocess.run(["git", "init", "-q", "--bare", str(evil)], check=True, capture_output=True)
    common = subprocess.run(["git", "-C", str(repo), "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True,
                            check=True).stdout.strip()
    (evil / "objects" / "info" / "alternates").write_text(f"{common}/objects\n")
    for ref in ("main", branch):
        sha = subprocess.run(["git", "-C", str(repo), "rev-parse", ref], capture_output=True,
                             text=True, check=True).stdout.strip()
        (evil / "refs" / "heads" / ref).parent.mkdir(parents=True, exist_ok=True)
        (evil / "refs" / "heads" / ref).write_text(sha + "\n")
    (evil / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
    admin_index = Path(common) / "worktrees" / wt.name / "index"
    if admin_index.exists():
        (evil / "index").write_bytes(admin_index.read_bytes())
    for key, val in (("core.bare", "false"), ("core.worktree", str(wt)),
                     ("core.fsmonitor", f"touch {marker}; false"),
                     ("diff.external", f"touch {marker}")):
        subprocess.run(["git", "config", "-f", str(evil / "config"), key, val], check=True)
    (wt / ".git").write_text(f"gitdir: {evil}\n")


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

    def test_a_worker_poisoned_worktree_git_is_never_read(self):
        """ESC-014: the check runs in the PM's process, so it must not read
        the worktree's `.git`, which the worker can repoint at a gitdir it
        controls. Through `-C <worktree>` that gitdir both runs commands
        (fsmonitor on any index read) and answers the check: its `main` is
        an older commit, so a no-op SHA looks 1 commit ahead. Verified
        through the main checkout, the no-op is still refused."""
        self._create_task()
        older = _git("rev-parse", "main", cwd=self.repo)
        (self.repo / "f.txt").write_text("one\nmain moved\n")
        _git("commit", "-qam", "main moves on", cwd=self.repo)
        _git("merge", "-q", "--ff-only", "main", cwd=self.worktree)
        noop_sha = _git("rev-parse", "HEAD", cwd=self.worktree)  # == main: zero work

        marker = Path(self.tmp.name) / "pwned"
        poison_worktree_gitdir(self.repo, self.worktree, "task/1", marker)
        (Path(self.tmp.name) / "evil-wt-task-1" / "refs" / "heads" / "main").write_text(older + "\n")
        # The poisoned checkout is functional, hostile and lying via -C.
        lie = subprocess.run(["git", "-C", str(self.worktree), "rev-list", "--count",
                              f"main..{noop_sha}"], capture_output=True, text=True)
        self.assertEqual(lie.stdout.strip(), "1", "fixture: -C must see the lie")
        subprocess.run(["git", "-C", str(self.worktree), "status"], capture_output=True)
        self.assertTrue(marker.exists(), "fixture: the attack must work on `git -C`")
        marker.unlink()

        r = self._run("event", "TASK-1", "IMPLEMENTATION_READY",
                      "--evidence", noop_sha, actor_env="backend-engineer-1")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("0 commits ahead", r.stderr)
        self.assertFalse(marker.exists())

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
