"""hooks/guard.py — company-os's guards for harnesses other than Claude Code (M2).

Payload and deny shapes are taken from each CLI's own installed contract, as
read 2026-10-30 (no live run yet — see `guards_verified` in harness.py):
  codex 0.163.0  embedded schema `pre-tool-use.command.input`: tool_name /
                 tool_input / cwd; deny = Claude's hookSpecificOutput shape.
  agy 1.4.11     ~/.gemini/antigravity/.../docs/hooks.md: toolCall.name /
                 toolCall.args; deny = {"decision": "deny", "reason": ...}.
Which tool names actually reach each hook was NOT confirmable offline, so the
shim fails closed: an unrecognized tool, or a write whose target it can't
find, is denied with the name in the reason — the first live run then names
the real tools instead of silently allowing them.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUARD = HERE.parent / "hooks" / "guard.py"
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import harness  # noqa: E402

WRITER_TOOLS = "Read,Grep,Glob,Edit,Write,Bash"
READER_TOOLS = "Read,Grep,Glob,Bash"


class ShimCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.wt = base / "wt"
        (self.wt / "api").mkdir(parents=True)
        self.root = base / ".company"
        (self.root / "tasks").mkdir(parents=True)
        (self.root / "tasks" / "T-1.json").write_text(json.dumps({
            "id": "T-1", "project": "p", "owner": "be-1", "owned_globs": ["api/**"]}))
        self.env = {**os.environ, "COMPANY_TASK": "T-1", "COMPANY_ROOT": str(self.root),
                    "COMPANY_REPO": str(self.wt), "COMPANY_ACTOR": "be-1",
                    "COMPANY_ALLOWED_TOOLS": WRITER_TOOLS}

    def tearDown(self):
        self.tmp.cleanup()

    def run_guard(self, harness_id, payload, raw=None, **env):
        r = subprocess.run([sys.executable, str(GUARD), harness_id],
                           input=raw if raw is not None else json.dumps(payload),
                           capture_output=True, text=True, env={**self.env, **env})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None


class TestCodex(ShimCase):
    def codex(self, tool_name, tool_input, **env):
        return self.run_guard("codex", {
            "session_id": "s", "turn_id": "t", "transcript_path": None, "cwd": str(self.wt),
            "hook_event_name": "PreToolUse", "model": "m", "permission_mode": "default",
            "tool_name": tool_name, "tool_input": tool_input, "tool_use_id": "u"}, **env)

    def reason(self, out):
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        return out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_force_push_through_shell_is_denied(self):
        out = self.codex("exec_command", {"command": ["git", "push", "--force", "origin", "x"]})
        self.assertIn("force-push", self.reason(out))

    def test_ordinary_shell_is_allowed(self):
        self.assertIsNone(self.codex("shell_command", {"command": "pytest -q"}))

    def test_patch_inside_owned_globs_is_allowed(self):
        patch = "*** Begin Patch\n*** Add File: api/new.py\n+x = 1\n*** End Patch\n"
        self.assertIsNone(self.codex("apply_patch", {"input": patch}))

    def test_patch_touching_an_unowned_file_is_denied(self):
        patch = ("*** Begin Patch\n*** Update File: api/ok.py\n@@\n-a\n+b\n"
                 "*** Update File: web/app.ts\n@@\n-a\n+b\n*** End Patch\n")
        self.assertIn("ownership guard", self.reason(self.codex("apply_patch", {"input": patch})))

    def test_patch_moving_a_file_out_of_ownership_is_denied(self):
        patch = ("*** Begin Patch\n*** Update File: api/ok.py\n*** Move to: web/ok.py\n"
                 "*** End Patch\n")
        self.assertIsNotNone(self.codex("apply_patch", {"input": patch}))

    def test_patch_with_no_recognizable_target_is_denied(self):
        self.assertIn("could not determine", self.reason(
            self.codex("apply_patch", {"input": "something else entirely"})))

    def test_unknown_tool_is_denied_and_named(self):
        self.assertIn("mystery_tool", self.reason(self.codex("mystery_tool", {})))

    def test_read_only_role_cannot_patch(self):
        patch = "*** Begin Patch\n*** Add File: api/new.py\n+x\n*** End Patch\n"
        out = self.codex("apply_patch", {"input": patch}, COMPANY_ALLOWED_TOOLS=READER_TOOLS)
        self.assertIn("read-only", self.reason(out))

    def test_malformed_payload_is_denied_not_allowed(self):
        out = self.run_guard("codex", None, raw="{not json")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")


class TestAgy(ShimCase):
    def agy(self, name, args, **env):
        return self.run_guard("agy", {
            "toolCall": {"name": name, "args": args}, "stepIdx": 1, "conversationId": "c",
            "workspacePaths": [str(self.wt)], "modelName": "auto"}, **env)

    def test_force_push_is_denied_in_agys_shape(self):
        out = self.agy("run_command", {"CommandLine": "git push -f origin main"})
        self.assertEqual(out["decision"], "deny")
        self.assertIn("force-push", out["reason"])

    def test_write_outside_ownership_is_denied(self):
        out = self.agy("write_to_file", {"TargetFile": str(self.wt / "web" / "x.ts"),
                                         "CodeContent": "x"})
        self.assertEqual(out["decision"], "deny")

    def test_owned_write_prints_nothing(self):
        self.assertIsNone(self.agy("replace_file_content",
                                   {"TargetFile": str(self.wt / "api" / "x.py")}))

    def test_reading_an_env_file_is_denied(self):
        out = self.agy("view_file", {"AbsolutePath": str(self.wt / ".env")})
        self.assertIn("secrets guard", out["reason"])

    def test_unknown_tool_is_denied(self):
        self.assertEqual(self.agy("teleport", {})["decision"], "deny")


class TestShimNeedsLiveVerification(unittest.TestCase):
    """A skipped hook is indistinguishable from an allowing one — codex skips
    untrusted hooks silently. So `guards: shim` only counts once a live smoke
    test has proven the hook fires, recorded as `guards_verified`."""

    def test_unverified_shim_is_refused(self):
        with self.assertRaises(harness.HarnessError) as ctx:
            harness.require_guards({"_name": "codex", "guards": "shim", "command": ["codex"]})
        self.assertIn("verified", str(ctx.exception))

    def test_verified_shim_is_accepted(self):
        self.assertEqual(harness.require_guards(
            {"_name": "codex", "guards": "shim", "guards_verified": "2026-11-01 codex 0.163.0",
             "command": ["codex"]}), "shim")

    def test_shipped_codex_carries_the_shim_but_is_not_yet_verified(self):
        spec = {**harness.load_config(HERE.parent)["harnesses"]["codex"], "_name": "codex"}
        self.assertEqual(spec["guards"], "shim")
        self.assertFalse(spec.get("guards_verified"))
        cmd = harness.build_command(spec, role="backend-engineer", plugin_root=HERE.parent,
                                    allowed_tools=WRITER_TOOLS)
        self.assertIn("--dangerously-bypass-hook-trust", cmd)
        hook_cfg = [t for t in cmd if t.startswith("hooks.PreToolUse=")]
        self.assertEqual(len(hook_cfg), 1)
        self.assertIn(f"{HERE.parent}/hooks/guard.py", hook_cfg[0])
        self.assertIn("codex", hook_cfg[0])


if __name__ == "__main__":
    unittest.main()
