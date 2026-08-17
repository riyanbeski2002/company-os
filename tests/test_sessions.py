"""Session presence: who else is active on this checkout, and doing what.

Built after two top-level Claude Code sessions did company-pm-style work on
this same repo checkout at once, invisibly to each other — see
agents/company-pm.md, "Coordinating with other sessions."
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

import sessions  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"


class TestSessionsModule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"

    def tearDown(self):
        self.tmp.cleanup()

    def test_announce_requires_an_actor(self):
        with self.assertRaises(ValueError):
            sessions.announce(self.root, None, "doing something")

    def test_announce_requires_doing(self):
        with self.assertRaises(ValueError):
            sessions.announce(self.root, "sess-a", "   ")

    def test_list_is_empty_before_any_announce(self):
        self.assertEqual(sessions.list_active(self.root), [])

    def test_announce_then_list_round_trips(self):
        sessions.announce(self.root, "sess-a", "fixing the evidence rule",
                          ["tools/company/cli.py"])
        out = sessions.list_active(self.root)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["actor"], "sess-a")
        self.assertEqual(out[0]["doing"], "fixing the evidence rule")
        self.assertEqual(out[0]["globs"], ["tools/company/cli.py"])
        self.assertFalse(out[0]["stale"])

    def test_second_announce_from_same_actor_replaces_not_duplicates(self):
        sessions.announce(self.root, "sess-a", "first task")
        sessions.announce(self.root, "sess-a", "second task")
        out = sessions.list_active(self.root)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["doing"], "second task")

    def test_done_clears_the_entry(self):
        sessions.announce(self.root, "sess-a", "doing something")
        self.assertTrue(sessions.done(self.root, "sess-a"))
        self.assertEqual(sessions.list_active(self.root), [])

    def test_done_on_an_unknown_actor_is_safe(self):
        self.assertFalse(sessions.done(self.root, "nobody-here"))

    def test_stale_entries_are_flagged_not_hidden(self):
        sessions.announce(self.root, "sess-a", "doing something")
        p = self.root / "state" / "sessions" / "sess-a" / "doing.json"
        old = p.stat().st_mtime - (sessions.STALE_AFTER_S + 1)
        os.utime(p, (old, old))
        out = sessions.list_active(self.root)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["stale"])


class TestSessionCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        for d in ("events", "tasks", "projects", "state"):
            (self.root / d).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args, env_extra=None):
        env = dict(os.environ)
        env.pop("COMPANY_ACTOR", None)
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), *args],
            capture_output=True, text=True, env=env)

    def test_announce_falls_back_to_claude_code_session_id(self):
        r = self._run("session", "announce", "--doing", "reviewing a PR",
                      env_extra={"CLAUDE_CODE_SESSION_ID": "abc-123"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["actor"], "abc-123")

    def test_announce_without_any_actor_source_is_refused(self):
        r = self._run("session", "announce", "--doing", "reviewing a PR")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("actor identity", r.stderr)

    def test_list_reflects_two_announced_sessions(self):
        self._run("session", "announce", "--doing", "backend work",
                  "--actor", "sess-a")
        self._run("session", "announce", "--doing", "frontend work",
                  "--actor", "sess-b", "--globs", "src/ui/**,src/pages/**")
        r = self._run("session", "list")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["sessions"]
        actors = {s["actor"] for s in out}
        self.assertEqual(actors, {"sess-a", "sess-b"})
        by_actor = {s["actor"]: s for s in out}
        self.assertEqual(by_actor["sess-b"]["globs"], ["src/ui/**", "src/pages/**"])

    def test_done_removes_it_from_the_list(self):
        self._run("session", "announce", "--doing", "backend work", "--actor", "sess-a")
        r = self._run("session", "done", "--actor", "sess-a")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["cleared"], True)
        r = self._run("session", "list")
        self.assertEqual(json.loads(r.stdout)["sessions"], [])


if __name__ == "__main__":
    unittest.main()
