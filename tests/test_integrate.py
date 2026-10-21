"""Pre-merge worktree-conflict check (2026-10-21, ECC donation) — see
integrate.py's module-level comment for why this is a merge-time check
rather than ECC's own live file-activity polling (company-os has no
daemon to poll with)."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import integrate  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
