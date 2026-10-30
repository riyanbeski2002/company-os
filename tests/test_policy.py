"""hooks/policy.py — the harness-neutral guard policy (M2), and proof the
Claude shims still deliver it unchanged.

check_write (the ownership guard, D5) had no behavioral test of its own
before this: test_hook_guards.py covers secrets/commands and deliberately
skips ownership. It's pinned here because every harness shim now depends on
it — the Claude scripts and hooks/guard.py alike.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
HOOKS = HERE.parent / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import policy  # noqa: E402
from eventlog import EventLog  # noqa: E402


class OwnershipCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.wt = base / "wt"
        self.wt.mkdir()
        self.root = base / ".company"
        (self.root / "tasks").mkdir(parents=True)
        (self.root / "tasks" / "T-1.json").write_text(json.dumps({
            "id": "T-1", "project": "p", "owner": "be-1",
            "owned_globs": ["api/**"], "forbidden_globs": ["api/secret/**"]}))
        self.env = {"COMPANY_TASK": "T-1", "COMPANY_ROOT": str(self.root),
                    "COMPANY_REPO": str(self.wt), "COMPANY_ACTOR": "be-1"}

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, target, **env):
        with mock.patch.dict(os.environ, {**self.env, **env}, clear=False):
            return policy.check_write(target)

    def blocked(self):
        return [e for e in EventLog(self.root).read() if e["event"] == "OWNERSHIP_BLOCKED"]


class TestCheckWrite(OwnershipCase):
    def test_owned_path_is_allowed(self):
        self.assertIsNone(self.check(str(self.wt / "api" / "routes.py")))

    def test_unowned_path_is_denied_and_recorded(self):
        reason = self.check(str(self.wt / "web" / "app.tsx"))
        self.assertIn("ownership guard", reason)
        self.assertEqual(len(self.blocked()), 1)

    def test_forbidden_inside_owned_is_denied(self):
        self.assertIsNotNone(self.check(str(self.wt / "api" / "secret" / "k.py")))

    def test_outside_the_repository_is_denied(self):
        self.assertIn("outside the repository", self.check("/etc/hosts"))

    def test_unreadable_task_view_fails_closed(self):
        (self.root / "tasks" / "T-1.json").write_text("{not json")
        self.assertIn("Denying rather than guessing", self.check(str(self.wt / "api" / "x.py")))

    def test_missing_company_root_fails_closed(self):
        self.assertIn("not readable", self.check(str(self.wt / "api" / "x.py"),
                                                 COMPANY_ROOT="/nonexistent/.company"))

    def test_inert_outside_a_worker(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(policy.check_write("/anything"))


class TestClaudeShimsDeliverThePolicy(OwnershipCase):
    """The Claude scripts are now translators; prove the translation."""

    def run_hook(self, script, payload):
        env = {**os.environ, **self.env}
        r = subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(payload),
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def test_write_outside_ownership_gets_claudes_deny_shape(self):
        out = self.run_hook("guard_paths.py", {
            "tool_name": "Write", "tool_input": {"file_path": str(self.wt / "web" / "x.ts")}})
        decision = out["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("ownership guard", decision["permissionDecisionReason"])

    def test_owned_write_prints_nothing(self):
        self.assertIsNone(self.run_hook("guard_paths.py", {
            "tool_name": "Edit", "tool_input": {"file_path": str(self.wt / "api" / "x.py")}}))

    def test_a_non_write_tool_is_ignored(self):
        self.assertIsNone(self.run_hook("guard_paths.py", {
            "tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}))

    def test_force_push_is_denied_through_the_bash_shim(self):
        out = self.run_hook("protect_branches.py", {
            "tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}})
        self.assertIn("force-push", out["hookSpecificOutput"]["permissionDecisionReason"])


class TestNoLaunchWithoutGuards(unittest.TestCase):
    """H3 (migration §4.6): a harness that can't show how the guards reach
    its workers doesn't get workers. Before this, `roles: {x: codex}` would
    have launched a code-writing worker with no ownership, secret, or branch
    guard at all — doc/BYO-MODEL.md's own correction says so."""

    def setUp(self):
        import harness
        self.harness = harness
        self.repo = HERE.parent

    def mode(self, **spec):
        return self.harness.guard_mode({"_name": "x", "command": ["x"], **spec})

    def test_claude_plugin_is_inferred_from_the_mechanism_itself(self):
        # Older .company/config copies have no `guards:` field; --plugin-dir
        # {plugin_root} is literally what loads hooks/hooks.json.
        self.assertEqual(self.mode(command=["claude", "-p", "--plugin-dir", "{plugin_root}"]),
                         "claude-plugin")

    def test_a_harness_that_says_nothing_has_no_guards(self):
        self.assertIsNone(self.mode())

    def test_unknown_guard_mode_is_refused_at_resolve(self):
        cfg = {"default": "x", "harnesses": {"x": {"command": ["x"], "guards": "hope"}}}
        with self.assertRaises(self.harness.HarnessError):
            self.harness.resolve(cfg, "r")

    def test_shipped_harnesses(self):
        for root in (self.repo, self.repo / ".company"):
            hs = self.harness.load_config(root)["harnesses"]
            self.assertEqual(self.harness.guard_mode({**hs["claude"], "_name": "claude"}),
                             "claude-plugin")

    def test_launch_refuses_an_unguarded_harness_before_touching_anything(self):
        import worker
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".company"
            (root / "config").mkdir(parents=True)
            (root / "config" / "harness.yaml").write_text(
                "default: bare\nroles: {}\nharnesses:\n  bare:\n"
                "    self_sandboxed: true\n    command: [\"true\"]\n")
            with self.assertRaises(worker.WorkerError) as ctx:
                worker.launch_readonly(Path(tmp), root, "p", "packet", "cto-advisor", "cto-advisor")
            self.assertIn("guards", str(ctx.exception))
            self.assertFalse((root / "events" / "events.jsonl").exists()
                             and "WORKER_STARTED" in (root / "events" / "events.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
