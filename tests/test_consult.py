"""`company consult` (M5): a PM on any harness gets a Tier-1 judgment through
a `company` verb instead of Claude's `Agent` tool. Run end to end through
the real CLI with a stand-in harness, as test_launch_regressions does."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import harness  # noqa: E402
from test_launch_regressions import CLI, CLEAN_RESULT, FakeHarnessCase  # noqa: E402


class TestConsult(FakeHarnessCase):
    def setUp(self):
        super().setUp()
        # Replies with the packet it was given, so the test can see what the
        # role was asked; `is_error` is steerable through the packet.
        script = Path(self.tmp.name) / "echo_packet.py"
        script.write_text(
            "import json, sys\n"
            "packet = sys.stdin.read()\n"
            f"result = {CLEAN_RESULT!r}\n"
            "result['result'] = 'VERDICT: ' + packet\n"
            "result['is_error'] = 'FAIL-ME' in packet\n"
            "print(json.dumps(result))\n")
        (self.root / "config" / "harness.yaml").write_text(
            "default: fake\nroles: {}\nharnesses:\n  fake:\n"
            "    native_agent_loading: true\n    self_sandboxed: true\n"
            "    guards: external\n"
            f"    command: [{json.dumps(sys.executable)}, {json.dumps(str(script))}]\n")

    def consult(self, *args, stdin="", env=None):
        e = {k: v for k, v in os.environ.items()
             if k not in ("COMPANY_ACTOR", "COMPANY_TASK", "COMPANY_PROJECT")}
        e.update(env or {})
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), "consult", *args,
             "--project", "p"],
            input=stdin, capture_output=True, text=True, env=e, timeout=60)

    def test_returns_the_roles_reply_and_records_the_launch(self):
        r = self.consult("code-reviewer", "--packet", "-", stdin="is T-1 sound?")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"])
        self.assertIn("VERDICT: Repository: ", out["text"])
        self.assertIn("is T-1 sound?", out["text"])
        self.assertTrue(out["actor"].startswith("code-reviewer-consult-"))
        started = self._events("WORKER_STARTED")
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0]["data"]["role"], "code-reviewer")
        self.assertEqual(started[0]["data"]["harness"], "fake")
        self.assertEqual(started[0]["data"]["provider"], "native")
        self.assertTrue(started[0]["data"]["readonly"])
        self.assertEqual(len(self._events("WORKER_EXITED")), 1)

    def test_a_failed_reply_is_not_ok(self):
        r = self.consult("qa-engineer", "--packet", "FAIL-ME")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(json.loads(r.stdout)["ok"])

    def test_implementers_are_refused_before_any_launch(self):
        for role in ("backend-engineer", "frontend-engineer", "company-pm"):
            with self.subTest(role):
                r = self.consult(role, "--packet", "build it")
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("company run", r.stderr)
        self.assertEqual(self._events("WORKER_STARTED"), [])

    def test_unknown_role_and_empty_question_are_refused(self):
        self.assertEqual(self.consult("no-such-role", "--packet", "x").returncode, 1)
        self.assertEqual(self.consult("code-reviewer", "--packet", "-", stdin="  ").returncode, 1)
        self.assertEqual(self._events("WORKER_STARTED"), [])

    def test_a_worker_cannot_consult(self):
        r = self.consult("code-reviewer", "--packet", "x", env={"COMPANY_ACTOR": "be-1"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("worker", r.stderr)
        self.assertEqual(self._events("WORKER_STARTED"), [])


class TestPmBriefForOtherHarnesses(unittest.TestCase):
    """A PM on codex gets agents/company-pm.md through the same loader
    non-Claude workers use: no frontmatter, and Tier 1 via `company`."""

    def test_brief_is_the_body_with_consult_and_no_frontmatter(self):
        brief = harness.load_persona(HERE.parent, "company-pm")
        self.assertFalse(brief.startswith("---"))
        self.assertNotIn("permissionMode:", brief)
        self.assertIn("Tier 1 is one verb, `company consult`", brief)
        self.assertIn("company run TASK-101", brief)


if __name__ == "__main__":
    unittest.main()
