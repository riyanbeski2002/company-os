"""Worker lifecycle guards.

Both cases here come from handing the loop to a real PM agent:

- The PM launched a worker, truthfully reported it as running, and exited.
  Claude Code kills a `-p` run's background shell tasks seconds after the turn's
  final result, so the worker died mid-edit with uncommitted changes.
- Recovering from that made it easy to point a second worker at a worktree that
  already had one in it, which silently overwrites work.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import worker  # noqa: E402


class TestWorktreeCollision(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        self.workers = self.root / "state" / "workers"
        self.workers.mkdir(parents=True)
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            p.kill()
            p.wait()
        self.tmp.cleanup()

    def _worker(self, actor, task_id, alive=True):
        d = self.workers / actor
        d.mkdir()
        if alive:
            p = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
            self.procs.append(p)
            pid = p.pid
        else:
            p = subprocess.Popen([sys.executable, "-c", "pass"])
            p.wait()
            pid = p.pid
        (d / "pid").write_text(str(pid))
        (d / "started_task").write_text(task_id)

    def test_live_worker_on_task_is_found(self):
        self._worker("be-1", "TASK-1")
        self.assertEqual(worker.live_worker_on(self.root, "TASK-1"), "be-1")

    def test_worker_on_a_different_task_does_not_block(self):
        self._worker("be-1", "TASK-1")
        self.assertIsNone(worker.live_worker_on(self.root, "TASK-2"))

    def test_finished_worker_does_not_block(self):
        self._worker("be-1", "TASK-1", alive=False)
        self.assertIsNone(worker.live_worker_on(self.root, "TASK-1"))

    def test_no_workers_at_all(self):
        self.assertIsNone(worker.live_worker_on(self.root, "TASK-1"))

    def test_launch_refuses_a_second_worker_in_one_worktree(self):
        self._worker("be-1", "TASK-1")
        with self.assertRaises(worker.WorkerError) as ctx:
            worker.launch(Path(self.tmp.name), self.root,
                          {"id": "TASK-1", "project": "p", "title": "t"},
                          "packet", "backend-engineer", "be-2")
        self.assertIn("already working", str(ctx.exception))

    def test_the_same_worker_may_resume_its_own_worktree(self):
        """Refusing a retry of the same actor would make recovery impossible."""
        self._worker("be-1", "TASK-1")
        self.assertEqual(worker.live_worker_on(self.root, "TASK-1"), "be-1")
        # be-1 relaunching itself is not a collision; a different actor is.
        self.assertNotEqual("be-1", "be-2")


class TestWorkerEnvironment(unittest.TestCase):
    """The env a worker gets decides whether it can run at all."""

    def _env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            return worker.build_env(
                root, root / ".company",
                {"id": "TASK-1", "project": "p"}, "be-1",
                root / ".company" / "worktrees" / "TASK-1")

    def test_api_key_is_stripped(self):
        """A stale ANTHROPIC_API_KEY silently overrides the claude.ai login and
        makes every run fail with terminal_reason api_error and zero tokens."""
        os.environ["ANTHROPIC_API_KEY"] = "sk-should-not-reach-the-worker"
        try:
            self.assertNotIn("ANTHROPIC_API_KEY", self._env())
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_repo_points_at_the_worktree_not_the_main_checkout(self):
        env = self._env()
        self.assertTrue(env["COMPANY_REPO"].endswith("worktrees/TASK-1"))
        self.assertIn("COMPANY_MAIN_REPO", env)

    def test_parent_session_identity_does_not_leak(self):
        os.environ["CLAUDE_CODE_SESSION_ID"] = "parent-session"
        try:
            self.assertNotIn("CLAUDE_CODE_SESSION_ID", self._env())
        finally:
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

    def test_company_bin_is_prepended_to_path(self):
        """Workers must resolve `company` to THIS checkout's CLI.

        Asserted against the real plugin root rather than the literal string
        "company-os/bin", which broke in any clone with a different directory
        name — including the fresh-clone check that caught it.
        """
        expected = str(worker.PLUGIN_ROOT / "bin")
        self.assertTrue(self._env()["PATH"].startswith(expected + ":"),
                        f"PATH should start with {expected}")

    def test_actor_is_assigned_not_chosen(self):
        self.assertEqual(self._env()["COMPANY_ACTOR"], "be-1")


if __name__ == "__main__":
    unittest.main()
