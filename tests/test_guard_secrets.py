"""PreToolUse hook: no worker reads a secret via Read/Grep (D5's ownership
guard only ever watched Write/Edit/NotebookEdit; this closes the read side).

The global settings on this machine had `"deny": []` — nothing stopped a
worker from reading `.env` straight into its transcript, even though
`.worktreeinclude` deliberately copies `.env` in so the app can *run*.
Running with it and reading its contents are different things.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

spec = importlib.util.spec_from_file_location(
    "guard_secrets", HERE.parent / "hooks" / "guard_secrets.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

from eventlog import EventLog  # noqa: E402


class TestSecretGlobs(unittest.TestCase):
    def _hit(self, rel):
        import pathrules
        return pathrules.matches_any(rel, guard.SECRET_GLOBS)

    def test_env_file_matches(self):
        self.assertIsNotNone(self._hit(".env"))
        self.assertIsNotNone(self._hit(".env.production"))

    def test_secrets_dir_matches(self):
        self.assertIsNotNone(self._hit("config/secrets/db.json"))

    def test_pem_and_ssh_key_match(self):
        self.assertIsNotNone(self._hit("certs/server.pem"))
        self.assertIsNotNone(self._hit(".ssh/id_rsa"))

    def test_ordinary_source_does_not_match(self):
        for rel in ("src/api/keys.py", "README.md", "config/settings.yaml",
                    "src/services/environment.py"):
            self.assertIsNone(self._hit(rel), rel)


class TestHookEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.root = self.repo / ".company"
        for d in ("events", "tasks"):
            (self.root / d).mkdir(parents=True)
        (self.root / "tasks" / "T-1.json").write_text(
            json.dumps({"id": "T-1", "owner": "be-1", "project": "p"}))
        (self.repo / ".env").write_text("SECRET=1")
        (self.repo / "README.md").write_text("# hi")

    def _run(self, tool_name, tool_input, env_extra=None):
        import os
        env = dict(os.environ)
        env.update({"COMPANY_TASK": "T-1", "COMPANY_ROOT": str(self.root),
                    "COMPANY_REPO": str(self.repo)})
        env.update(env_extra or {})
        import subprocess
        payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
        return subprocess.run(
            [sys.executable, str(HERE.parent / "hooks" / "guard_secrets.py")],
            input=payload, capture_output=True, text=True, env=env)

    def test_read_env_is_denied(self):
        result = self._run("Read", {"file_path": str(self.repo / ".env")})
        out = json.loads(result.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_read_ordinary_file_is_allowed(self):
        result = self._run("Read", {"file_path": str(self.repo / "README.md")})
        self.assertEqual(result.stdout.strip(), "")

    def test_denial_is_recorded_in_the_event_log(self):
        self._run("Read", {"file_path": str(self.repo / ".env")})
        events = EventLog(self.root).read()
        self.assertTrue(any(e["event"] == "SECRET_READ_BLOCKED" for e in events))

    def test_inert_outside_a_worker(self):
        """$COMPANY_TASK unset means an ordinary session is unaffected."""
        import os
        env = dict(os.environ)
        env.pop("COMPANY_TASK", None)
        import subprocess
        payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(self.repo / ".env")}})
        result = subprocess.run(
            [sys.executable, str(HERE.parent / "hooks" / "guard_secrets.py")],
            input=payload, capture_output=True, text=True, env=env)
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
