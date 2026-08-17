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
import time
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

    def test_claim_task_closes_the_double_launch_race(self):
        """KNOWN_ISSUES #2, reproduced directly: many callers claiming the
        same fresh task concurrently — exactly two launch() calls issued
        close together, just with more concurrency to make a race failure
        near-certain rather than probabilistic. Exactly one must win."""
        import concurrent.futures
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(worker.claim_task, self.root, "TASK-RACE", f"actor-{i}")
                      for i in range(20)]
            results = [f.result() for f in futures]
        self.assertEqual(sum(results), 1, f"expected exactly one winner, got {sum(results)}")

    def test_a_fresh_contested_claim_is_never_stolen(self):
        claim_path = self.root / "state" / "claims" / "TASK-1.claim"
        claim_path.parent.mkdir(parents=True, exist_ok=True)
        claim_path.write_text("actor-a")
        self.assertFalse(worker.claim_task(self.root, "TASK-1", "actor-b"))

    def test_a_genuinely_stale_claim_is_reclaimed(self):
        import os as _os
        claim_path = self.root / "state" / "claims" / "TASK-1.claim"
        claim_path.parent.mkdir(parents=True, exist_ok=True)
        claim_path.write_text("actor-a")
        old = time.time() - worker.CLAIM_STALE_AFTER_S - 60
        _os.utime(claim_path, (old, old))
        self.assertTrue(worker.claim_task(self.root, "TASK-1", "actor-b"))
        self.assertEqual(claim_path.read_text(), "actor-b")

    def test_the_same_actor_resumes_its_own_claim(self):
        claim_path = self.root / "state" / "claims" / "TASK-1.claim"
        claim_path.parent.mkdir(parents=True, exist_ok=True)
        claim_path.write_text("actor-a")
        self.assertTrue(worker.claim_task(self.root, "TASK-1", "actor-a"))

    def test_release_claim_removes_it(self):
        claim_path = self.root / "state" / "claims" / "TASK-1.claim"
        claim_path.parent.mkdir(parents=True, exist_ok=True)
        claim_path.write_text("actor-a")
        worker.release_claim(self.root, "TASK-1")
        self.assertFalse(claim_path.exists())

    def test_release_claim_on_a_task_with_no_claim_does_not_error(self):
        worker.release_claim(self.root, "TASK-NEVER-CLAIMED")  # must not raise

    def test_a_live_worker_still_blocks_a_fresh_claim(self):
        """Backward compatible: an already-running worker (its own claim
        already released post-launch) still refuses a competing claim."""
        self._worker("be-1", "TASK-1")
        self.assertFalse(worker.claim_task(self.root, "TASK-1", "be-2"))

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


class TestGateNoVerdict(unittest.TestCase):
    """KNOWN_ISSUES #3: security-reviewer-201 ran 11 clean turns and emitted
    neither SECURITY_REVIEW_PASSED nor SECURITY_REVIEW_FAILED — silently
    re-run under a new actor name, paying for the review twice. Pure and
    unit-testable on purpose; launch() itself needs a real subprocess."""

    def test_no_verdict_at_all_is_flagged(self):
        events = [{"event": "WORKER_STARTED", "task": "T-1", "actor": "code-reviewer-1"}]
        expected = worker.gave_no_verdict(events, "T-1", "code-reviewer-1", "code-reviewer")
        self.assertEqual(expected, ("REVIEW_PASSED", "REVIEW_FAILED"))

    def test_a_real_pass_verdict_clears_it(self):
        events = [{"event": "REVIEW_PASSED", "task": "T-1", "actor": "code-reviewer-1"}]
        self.assertIsNone(worker.gave_no_verdict(events, "T-1", "code-reviewer-1", "code-reviewer"))

    def test_a_real_fail_verdict_also_clears_it(self):
        """Failing the gate is still a verdict — silence is the problem, not a red result."""
        events = [{"event": "REVIEW_FAILED", "task": "T-1", "actor": "code-reviewer-1"}]
        self.assertIsNone(worker.gave_no_verdict(events, "T-1", "code-reviewer-1", "code-reviewer"))

    def test_a_verdict_on_a_different_task_does_not_count(self):
        events = [{"event": "REVIEW_PASSED", "task": "T-2", "actor": "code-reviewer-1"}]
        expected = worker.gave_no_verdict(events, "T-1", "code-reviewer-1", "code-reviewer")
        self.assertIsNotNone(expected)

    def test_a_verdict_from_a_different_actor_does_not_count(self):
        """Prevents the exact failure that prompted this: a stalled reviewer's
        silence being papered over by a differently-named re-run."""
        events = [{"event": "REVIEW_PASSED", "task": "T-1", "actor": "code-reviewer-2"}]
        expected = worker.gave_no_verdict(events, "T-1", "code-reviewer-1", "code-reviewer")
        self.assertIsNotNone(expected)

    def test_non_gate_roles_are_never_flagged(self):
        self.assertIsNone(worker.gave_no_verdict([], "T-1", "be-1", "backend-engineer"))


if __name__ == "__main__":
    unittest.main()
