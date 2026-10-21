"""Cross-session guard enforcement (2026-10-21, ECC donation).

guard_secrets.py and protect_branches.py used to be inert whenever
$COMPANY_TASK was unset -- i.e. in every session except a spawned Tier-2
worker, which is exactly the "residual gap" company-os's own README admitted
(a PM or advisor session reading a secret or force-pushing was never
checked at all). These tests exercise the two guards with no task-scoped
env vars set, against a real temp git repo, to prove the fix holds without
a worker ever being spawned.

guard_paths.py (ownership) is deliberately NOT tested here for universal
behaviour -- it stays worker-only by design, since "ownership" (owned_globs)
has no meaning for a PM's own session.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))
sys.path.insert(0, str(HERE.parent / "hooks"))

import pathrules  # noqa: E402


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _run_hook(module_name: str, payload: dict, env_overrides: dict, cwd: Path) -> tuple[int, dict | None]:
    """Run a hook's main() with a fresh stdin/env, outside pytest's own
    process env leakage, and parse its JSON stdout (if any)."""
    old_env = dict(os.environ)
    old_cwd = Path.cwd()
    try:
        for key in ("COMPANY_TASK", "COMPANY_ROOT", "COMPANY_REPO", "COMPANY_MAIN_REPO", "COMPANY_ACTOR"):
            os.environ.pop(key, None)
        os.environ.update(env_overrides)
        os.chdir(cwd)

        # Re-import fresh each call -- these are script modules with global
        # state read at import time in a couple of spots (sys.path only, but
        # be safe) and module-level caches would otherwise leak between tests.
        sys.modules.pop(module_name, None)
        hook = __import__(module_name)

        buf = io.StringIO()
        sys.stdin = io.StringIO(json.dumps(payload))
        try:
            with redirect_stdout(buf):
                hook.main()
            code = 0
        except SystemExit as exc:
            code = exc.code or 0
        out = buf.getvalue().strip()
        return code, (json.loads(out) if out else None)
    finally:
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)
        sys.stdin = sys.__stdin__


class TestResolveRepoContext(unittest.TestCase):
    def test_finds_the_repo_root_from_a_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "sub" / "dir").mkdir(parents=True)
            found = pathrules.resolve_repo_context(root / "sub" / "dir")
            self.assertEqual(found.resolve(), root.resolve())

    def test_returns_none_outside_any_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            # tmp itself is not a git repo and (on a sane CI box) neither is /tmp
            found = pathrules.resolve_repo_context(Path(tmp))
            self.assertIsNone(found)


class TestSecretsGuardFiresWithoutAWorker(unittest.TestCase):
    def test_reading_an_env_file_is_blocked_with_no_company_task_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / ".env").write_text("SECRET=1")
            code, out = _run_hook("guard_secrets", {
                "tool_name": "Read", "tool_input": {"file_path": str(root / ".env")},
            }, {}, root)
            self.assertEqual(code, 0)  # hooks always exit 0; the decision is in stdout
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_reading_an_ordinary_file_is_allowed_with_no_company_task_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("hello")
            code, out = _run_hook("guard_secrets", {
                "tool_name": "Read", "tool_input": {"file_path": str(root / "README.md")},
            }, {}, root)
            self.assertEqual(code, 0)
            self.assertIsNone(out)

    def test_outside_any_repo_allows_rather_than_failing_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)  # deliberately not a git repo
            (root / ".env").write_text("SECRET=1")
            code, out = _run_hook("guard_secrets", {
                "tool_name": "Read", "tool_input": {"file_path": str(root / ".env")},
            }, {}, root)
            self.assertEqual(code, 0)
            self.assertIsNone(out)


class TestBranchGuardFiresWithoutAWorker(unittest.TestCase):
    def test_force_push_is_blocked_with_no_company_task_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            code, out = _run_hook("protect_branches", {
                "tool_name": "Bash", "tool_input": {"command": "git push --force origin main"},
            }, {}, root)
            self.assertEqual(code, 0)
            self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_an_ordinary_command_is_allowed_with_no_company_task_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            code, out = _run_hook("protect_branches", {
                "tool_name": "Bash", "tool_input": {"command": "git status"},
            }, {}, root)
            self.assertEqual(code, 0)
            self.assertIsNone(out)

    def test_worktree_escape_check_is_skipped_without_a_task_id(self):
        """find_escape only makes sense for a spawned worker's worktree --
        a PM session writing to an absolute path outside any worktree concept
        must not be flagged as 'escaping' something that doesn't exist for it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            code, out = _run_hook("protect_branches", {
                "tool_name": "Bash", "tool_input": {"command": f"echo hi > {root}/notes.txt"},
            }, {}, root)
            self.assertEqual(code, 0)
            self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
