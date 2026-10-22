"""Pre-merge worktree-conflict check (2026-10-21, ECC donation) — see
integrate.py's module-level comment for why this is a merge-time check
rather than ECC's own live file-activity polling (company-os has no
daemon to poll with)."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import integrate  # noqa: E402
from eventlog import EventLog  # noqa: E402


class TestDetectConcurrentGlobConflicts(unittest.TestCase):
    def test_no_conflict_when_no_other_task_is_active(self):
        tasks = {
            "T-1": {"id": "T-1", "status": "REVIEW", "owned_globs": ["services/auth/**"]},
            "T-2": {"id": "T-2", "status": "DONE", "owned_globs": ["services/auth/**"]},
        }
        self.assertEqual(integrate.detect_concurrent_glob_conflicts(tasks, "T-1"), [])

    def test_flags_an_overlapping_active_task(self):
        tasks = {
            "T-1": {"id": "T-1", "status": "REVIEW", "owned_globs": ["services/auth/**"]},
            "T-2": {"id": "T-2", "status": "IN_PROGRESS", "owned_globs": ["services/**"]},
        }
        conflicts = integrate.detect_concurrent_glob_conflicts(tasks, "T-1")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["task"], "T-2")

    def test_does_not_flag_a_disjoint_active_task(self):
        tasks = {
            "T-1": {"id": "T-1", "status": "REVIEW", "owned_globs": ["services/auth/**"]},
            "T-2": {"id": "T-2", "status": "IN_PROGRESS", "owned_globs": ["frontend/**"]},
        }
        self.assertEqual(integrate.detect_concurrent_glob_conflicts(tasks, "T-1"), [])

    def test_unknown_task_id_returns_no_conflicts_not_a_crash(self):
        self.assertEqual(integrate.detect_concurrent_glob_conflicts({}, "T-nope"), [])

    def test_a_task_never_conflicts_with_itself(self):
        tasks = {"T-1": {"id": "T-1", "status": "IN_PROGRESS", "owned_globs": ["services/**"]}}
        self.assertEqual(integrate.detect_concurrent_glob_conflicts(tasks, "T-1"), [])

    def test_covers_every_concurrently_active_status(self):
        for status in ("IN_PROGRESS", "REVIEW", "QA", "SECURITY_REVIEW"):
            tasks = {
                "T-1": {"id": "T-1", "status": "REVIEW", "owned_globs": ["services/**"]},
                "T-2": {"id": "T-2", "status": status, "owned_globs": ["services/auth/**"]},
            }
            self.assertTrue(integrate.detect_concurrent_glob_conflicts(tasks, "T-1"), status)


class TestPathsOutsideOwnership(unittest.TestCase):
    TASK = {"owned_globs": ["api/approvals/**"], "forbidden_globs": ["api/approvals/secrets/**"]}

    def test_owned_paths_pass(self):
        self.assertEqual(integrate.paths_outside_ownership(
            ["api/approvals/handler.py", "api/approvals/tests/test_h.py"], self.TASK), [])

    def test_a_path_outside_the_globs_is_reported(self):
        out = integrate.paths_outside_ownership(
            ["api/approvals/handler.py", "other_team/file.py"], self.TASK)
        self.assertEqual([o["path"] for o in out], ["other_team/file.py"])
        self.assertIn("outside this task's owned globs", out[0]["reason"])

    def test_forbidden_wins_over_owned(self):
        out = integrate.paths_outside_ownership(["api/approvals/secrets/k.py"], self.TASK)
        self.assertEqual(len(out), 1)
        self.assertIn("forbidden", out[0]["reason"])

    def test_no_owned_globs_owns_nothing(self):
        self.assertEqual(len(integrate.paths_outside_ownership(["a.py"], {"owned_globs": []})), 1)


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True, text=True)


class TestIntegrateRefusesOutOfGlobDiff(unittest.TestCase):
    """The bypass this closes: a Bash write inside the worktree (never seen
    by guard_paths.py's Write/Edit hook) landing on the task branch."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.root = self.repo / ".company"
        (self.root / "events").mkdir(parents=True)
        _git(self.repo, "init", "-q", "-b", "main")
        (self.repo / ".gitignore").write_text(".company/\n")
        (self.repo / "api").mkdir()
        (self.repo / "api" / "app.py").write_text("orig\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "init")
        _git(self.repo, "checkout", "-qb", "task/1-x")

    def tearDown(self):
        self.tmp.cleanup()

    def _commit(self, rel, text="x\n"):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        _git(self.repo, "add", rel)
        _git(self.repo, "commit", "-qm", f"touch {rel}")

    def _integrate(self):
        _git(self.repo, "checkout", "-q", "main")
        task = {"id": "T-1", "project": "p", "branch": "task/1-x",
                "owned_globs": ["api/**"], "forbidden_globs": []}
        return integrate.integrate(self.repo, self.root, task, "true")

    def test_out_of_glob_file_blocks_the_merge(self):
        self._commit("api/app.py", "changed\n")
        self._commit("other_team/file.py")
        result = self._integrate()
        self.assertFalse(result["merged"])
        self.assertEqual(result["reason"], "diff outside owned globs")
        self.assertEqual([d["path"] for d in result["detail"]], ["other_team/file.py"])
        blocked = [e for e in EventLog(self.root).read() if e["event"] == "TASK_BLOCKED"]
        self.assertEqual(blocked[-1]["data"]["reason"], "diff outside owned globs")
        self.assertFalse([e for e in EventLog(self.root).read() if e["event"] == "MERGED"])

    def test_deleting_a_file_outside_the_globs_also_blocks(self):
        (self.repo / "README").write_text("r\n")
        _git(self.repo, "add", "README")
        _git(self.repo, "commit", "-qm", "readme")
        _git(self.repo, "checkout", "-q", "main")
        _git(self.repo, "merge", "-q", "--ff-only", "task/1-x")
        _git(self.repo, "checkout", "-q", "task/1-x")
        _git(self.repo, "rm", "-q", "README")
        _git(self.repo, "commit", "-qm", "rm readme")
        result = self._integrate()
        self.assertFalse(result["merged"])
        self.assertEqual([d["path"] for d in result["detail"]], ["README"])

    def test_in_glob_diff_merges(self):
        self._commit("api/app.py", "changed\n")
        result = self._integrate()
        self.assertTrue(result["merged"], result)


if __name__ == "__main__":
    unittest.main()
