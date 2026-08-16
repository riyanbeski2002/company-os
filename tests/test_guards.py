"""Bash guardrails (§9, §12).

Both classes here exist because a real worker run tripped them:
- a reviewer's mutation-testing scratch dir (`rm -rf /tmp/rev101`) was wrongly
  blocked as a root delete;
- and the ownership hook, which only watches Write/Edit/NotebookEdit, could be
  bypassed entirely by a shell redirect.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

spec = importlib.util.spec_from_file_location(
    "protect_branches", HERE.parent / "hooks" / "protect_branches.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

WT = "/repo/.company/worktrees/TASK-1"
CROOT = "/repo/.company"


def blocked_by_rule(command: str) -> str | None:
    for pattern, label in guard.RULES:
        if pattern.search(command):
            return label
    return None


class TestDangerousCommands(unittest.TestCase):
    def test_blocks_force_push(self):
        self.assertIsNotNone(blocked_by_rule("git push --force origin task/1"))

    def test_blocks_protected_checkout(self):
        self.assertIsNotNone(blocked_by_rule("git checkout main"))

    def test_blocks_secret_commit(self):
        self.assertIsNotNone(blocked_by_rule("git add .env && git commit -m x"))

    def test_blocks_reading_secret_via_shell(self):
        """guard_secrets.py only covers the Read/Grep tools; `cat .env` is the
        same information exposure via Bash instead."""
        for cmd in ("cat .env", "head -20 secrets.yaml", "less config/secrets.json",
                    "tail -f .env.production"):
            self.assertIsNotNone(blocked_by_rule(cmd), cmd)

    def test_allows_ordinary_reads(self):
        for cmd in ("cat README.md", "head -5 CHANGELOG.md", "cat src/api/keys.py"):
            self.assertIsNone(blocked_by_rule(cmd), cmd)

    def test_blocks_worktree_removal(self):
        self.assertIsNotNone(blocked_by_rule("git worktree remove foo"))

    def test_allows_ordinary_work(self):
        for cmd in ("git add api/x.py && git commit -m 'work'",
                    "python3 -m unittest discover -q tests",
                    "git push origin task/101-expense-approval",
                    "git diff main..HEAD"):
            self.assertIsNone(blocked_by_rule(cmd), cmd)


class TestRmRule(unittest.TestCase):
    """Regression: `rm -rf /tmp/rev101` is ordinary scratch work, not a root wipe."""

    def test_blocks_root_ish_targets(self):
        for cmd in ("rm -rf /", "rm -rf ~", "rm -rf .", "rm -rf /tmp",
                    "rm -rf $HOME", "rm -fr /usr"):
            self.assertIsNotNone(blocked_by_rule(cmd), cmd)

    def test_allows_scoped_deletes(self):
        for cmd in ("rm -rf /tmp/rev101", "rm -rf ./build", "rm -rf node_modules",
                    "rm -rf $HOME/projects/scratch"):
            self.assertIsNone(blocked_by_rule(cmd), cmd)


class TestWorktreeEscape(unittest.TestCase):
    """The ownership hook does not see Bash. Without this, a redirect bypasses it."""

    def esc(self, cmd):
        return guard.find_escape(cmd, WT, CROOT)

    def test_blocks_redirect_into_main_checkout(self):
        self.assertEqual(self.esc("echo pwned > /repo/api/x.py"), "/repo/api/x.py")

    def test_blocks_append_outside(self):
        self.assertEqual(self.esc("echo x >> /etc/hosts"), "/etc/hosts")

    def test_blocks_cd_outside(self):
        self.assertEqual(self.esc("cd /repo && git log"), "/repo")

    def test_blocks_tee_outside(self):
        self.assertEqual(self.esc("cat a | tee /Users/x/notes.txt"), "/Users/x/notes.txt")

    def test_allows_tmp_scratch(self):
        self.assertIsNone(self.esc("mkdir -p /tmp/rev101 && cd /tmp/rev101"))

    def test_allows_dev_null(self):
        self.assertIsNone(self.esc("python3 -m unittest discover -q tests > /dev/null"))

    def test_allows_inside_worktree(self):
        self.assertIsNone(self.esc(f"echo x > {WT}/api/new.py"))

    def test_allows_company_root(self):
        self.assertIsNone(self.esc(f"echo x > {CROOT}/state/workers/w1/log.txt"))

    def test_allows_relative_paths(self):
        self.assertIsNone(self.esc("python3 -m unittest discover -q tests > out.txt 2>&1"))


if __name__ == "__main__":
    unittest.main()
