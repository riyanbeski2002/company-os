"""Ownership matching (D5). Getting `**` wrong silently widens every rule."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import pathrules  # noqa: E402


class TestGlob(unittest.TestCase):
    def test_double_star_crosses_separators(self):
        self.assertTrue(pathrules.matches("services/auth/deep/nested/x.py", "services/auth/**"))

    def test_single_star_does_not_cross_separators(self):
        self.assertFalse(pathrules.matches("services/auth/x.py", "services/*"))
        self.assertTrue(pathrules.matches("services/auth", "services/*"))

    def test_owns_the_directory_itself(self):
        self.assertTrue(pathrules.matches("services/auth", "services/auth/**"))

    def test_leading_double_star(self):
        self.assertTrue(pathrules.matches("a/b/migrations/001.sql", "**/migrations/**"))
        self.assertTrue(pathrules.matches("migrations/001.sql", "**/migrations/**"))

    def test_no_accidental_prefix_match(self):
        self.assertFalse(pathrules.matches("services/authority/x.py", "services/auth/**"))


class TestCheck(unittest.TestCase):
    OWNED = ["api/approvals/**", "tests/**"]
    FORBIDDEN = ["web/**", "services/auth/**"]

    def test_owned_allowed(self):
        ok, _ = pathrules.check("api/approvals/rbac.py", self.OWNED, self.FORBIDDEN)
        self.assertTrue(ok)

    def test_forbidden_denied(self):
        ok, reason = pathrules.check("web/app.js", self.OWNED, self.FORBIDDEN)
        self.assertFalse(ok)
        self.assertIn("forbidden", reason)

    def test_unowned_denied(self):
        ok, _ = pathrules.check("infra/main.tf", self.OWNED, self.FORBIDDEN)
        self.assertFalse(ok)

    def test_forbidden_beats_owned(self):
        ok, reason = pathrules.check(
            "services/auth/x.py", ["services/**"], ["services/auth/**"])
        self.assertFalse(ok)
        self.assertIn("forbidden", reason)

    def test_no_owned_globs_denies_everything(self):
        ok, _ = pathrules.check("anything.py", [], [])
        self.assertFalse(ok)


class TestRepoRelative(unittest.TestCase):
    """Regression: a worker lives INSIDE its worktree.

    Resolving its paths against the main checkout produced
    `.company/worktrees/TASK-101/api/approvals/expenses.py`, which matches no
    owned glob, so the guard blocked the worker from its own files. Paths must
    resolve against the worktree.
    """

    def test_paths_resolve_against_the_worktree_not_the_main_checkout(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "repo"
            wt = main / ".company" / "worktrees" / "TASK-101"
            (wt / "api" / "approvals").mkdir(parents=True)
            target = wt / "api" / "approvals" / "expenses.py"
            target.write_text("x")

            wrong = pathrules.relative_to_repo(str(target), str(main))
            self.assertEqual(wrong, ".company/worktrees/TASK-101/api/approvals/expenses.py")
            self.assertFalse(pathrules.check(wrong, ["api/approvals/**"], [])[0])

            right = pathrules.relative_to_repo(str(target), str(wt))
            self.assertEqual(right, "api/approvals/expenses.py")
            self.assertTrue(pathrules.check(right, ["api/approvals/**"], [])[0])

    def test_escaping_the_repo_returns_none(self):
        self.assertIsNone(pathrules.relative_to_repo("/etc/passwd", "/tmp/repo"))


if __name__ == "__main__":
    unittest.main()
