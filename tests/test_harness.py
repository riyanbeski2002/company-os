"""BYO-model harness seam (tools/company/harness.py).

The default `claude` harness must keep producing exactly the command and env
the old hardcoded worker.py did — these tests pin that down so a future
config/harness.yaml edit can't silently change what a real launch does. The
rest exercises the generic templating/mapping machinery a second, non-Claude
harness would actually rely on.
"""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import harness  # noqa: E402
import worker  # noqa: E402

REPO = HERE.parent


class TestClaudeHarnessIsUnchanged(unittest.TestCase):
    def setUp(self):
        self.config = harness.load_config(REPO)  # no .company override here -> plugin default
        self.spec = harness.resolve(self.config, "backend-engineer")

    def test_default_harness_is_claude(self):
        self.assertEqual(self.spec["_name"], "claude")

    def test_command_matches_pre_harness_hardcoded_shape(self):
        cmd = harness.build_command(
            self.spec, role="backend-engineer", plugin_root=REPO,
            allowed_tools="Read,Grep,Glob,Edit,Write,Bash",
            schema=worker.RESULT_SCHEMA, model="sonnet", effort="high",
        )
        self.assertEqual(cmd, [
            "claude", "-p", "--agent", "backend-engineer", "--plugin-dir", str(REPO),
            "--strict-mcp-config", "--output-format", "json",
            "--json-schema", json.dumps(worker.RESULT_SCHEMA),
            "--permission-mode", "acceptEdits",
            "--allowedTools", "Read,Grep,Glob,Edit,Write,Bash",
            "--model", "sonnet", "--effort", "high",
        ])

    def test_schema_less_command_drops_the_flag_and_its_value(self):
        """The readonly-advisor launch never passed --json-schema at all."""
        cmd = harness.build_command(
            self.spec, role="cfo-advisor", plugin_root=REPO,
            allowed_tools="Read,Grep,Glob,Bash", schema=None,
        )
        self.assertNotIn("--json-schema", cmd)

    def test_skip_permissions_flag_is_opt_in(self):
        cmd = harness.build_command(
            self.spec, role="backend-engineer", plugin_root=REPO,
            allowed_tools="Read,Grep,Glob,Edit,Write,Bash", skip_permissions=True,
        )
        self.assertIn("--dangerously-skip-permissions", cmd)

    def test_native_agent_loading_is_true_for_claude(self):
        """worker.py must not double-inject agents/<role>.md for this harness."""
        self.assertTrue(self.spec.get("native_agent_loading"))

    def test_strip_env_matches_pre_harness_hardcoded_list(self):
        env = harness.apply_env(self.spec, {
            "ANTHROPIC_API_KEY": "x", "ANTHROPIC_AUTH_TOKEN": "y",
            "CLAUDE_CODE_SESSION_ID": "z", "CLAUDE_CODE_CHILD_SESSION": "w",
            "CLAUDE_CODE_ENTRYPOINT": "v", "KEEP_ME": "yes",
        })
        self.assertEqual(env, {"KEEP_ME": "yes"})


class TestCodexHarnessIsReal(unittest.TestCase):
    """The second real harness (2026-10-19) — invocation verified against
    paperclip's own codex-local adapter source and live-smoke-tested on this
    machine, not guessed. These tests pin the resulting command shape down;
    tests/test_codex_adapter.py covers the adapter script's own stdin/stdout
    translation."""

    def test_codex_harness_is_defined(self):
        config = harness.load_config(REPO)
        self.assertIn("codex", config["harnesses"])

    def test_not_native_agent_loading(self):
        spec = harness.load_config(REPO)["harnesses"]["codex"]
        self.assertFalse(spec.get("native_agent_loading"))

    def test_command_points_at_the_adapter_script_not_codex_directly(self):
        spec = harness.load_config(REPO)["harnesses"]["codex"]
        cmd = harness.build_command(spec, role="backend-engineer", plugin_root=REPO,
                                     allowed_tools="Read,Grep,Glob,Edit,Write,Bash")
        self.assertEqual(cmd[0], "python3")
        self.assertTrue(cmd[1].endswith("tools/company/adapters/codex_adapter.py"))
        self.assertIn("--skip-git-repo-check", cmd)

    def test_model_flag_is_deliberately_unset(self):
        """Shipping a guessed model_map would silently fail real launches —
        this account rejected a plausible-looking model id outright when
        live-tested. No model_flag means staffing.yaml's model policy is
        silently ignored for this harness rather than silently wrong."""
        spec = harness.load_config(REPO)["harnesses"]["codex"]
        cmd = harness.build_command(spec, role="backend-engineer", plugin_root=REPO,
                                     allowed_tools="Read", model="sonnet")
        self.assertNotIn("--model", cmd)

    def test_effort_is_translated_to_the_dash_c_form(self):
        spec = harness.load_config(REPO)["harnesses"]["codex"]
        cmd = harness.build_command(spec, role="backend-engineer", plugin_root=REPO,
                                     allowed_tools="Read", effort="high")
        self.assertIn("model_reasoning_effort=high", cmd)


class TestRoleResolution(unittest.TestCase):
    def test_unconfigured_role_falls_back_to_default(self):
        config = {"default": "claude", "harnesses": {"claude": {"command": ["claude"]}}}
        spec = harness.resolve(config, "some-role-with-no-override")
        self.assertEqual(spec["_name"], "claude")

    def test_role_override_wins_over_default(self):
        config = {
            "default": "claude",
            "roles": {"backend-engineer": "other"},
            "harnesses": {"claude": {"command": ["claude"]}, "other": {"command": ["other"]}},
        }
        self.assertEqual(harness.resolve(config, "backend-engineer")["_name"], "other")
        self.assertEqual(harness.resolve(config, "frontend-engineer")["_name"], "claude")

    def test_missing_default_harness_definition_raises(self):
        config = {"default": "nonexistent"}
        with self.assertRaises(harness.HarnessError):
            harness.resolve(config, "backend-engineer")

    def test_no_default_configured_raises(self):
        with self.assertRaises(harness.HarnessError):
            harness.resolve({}, "backend-engineer")


class TestGenericHarnessTemplating(unittest.TestCase):
    """What a second, non-Claude harness actually relies on."""

    def setUp(self):
        self.spec = {
            "_name": "other-cli",
            "native_agent_loading": False,
            "command": ["other-cli", "--role", "{role}", "--workdir", "{plugin_root}"],
            "model_flag": "--model",
            "effort_flag": "--effort",
            "model_map": {"sonnet": "gpt-5.1", "opus": "gpt-5.1-high"},
            "effort_map": {"medium": "standard"},
            "strip_env": ["SOME_VENDOR_TOKEN"],
            "extra_env": {"OTHER_CLI_MODE": "headless"},
        }

    def test_placeholders_are_filled(self):
        cmd = harness.build_command(self.spec, role="backend-engineer",
                                     plugin_root=Path("/repo"), allowed_tools="Read")
        self.assertEqual(cmd, ["other-cli", "--role", "backend-engineer", "--workdir", "/repo"])

    def test_unknown_placeholder_raises_rather_than_launching_malformed(self):
        bad = {**self.spec, "command": ["other-cli", "{nonsense}"]}
        with self.assertRaises(harness.HarnessError):
            harness.build_command(bad, role="x", plugin_root=Path("/repo"), allowed_tools="Read")

    def test_model_and_effort_are_mapped_not_passed_through_raw(self):
        cmd = harness.build_command(self.spec, role="backend-engineer", plugin_root=Path("/r"),
                                     allowed_tools="Read", model="sonnet", effort="medium")
        self.assertIn("gpt-5.1", cmd)
        self.assertIn("standard", cmd)
        self.assertNotIn("sonnet", cmd)
        self.assertNotIn("medium", cmd)

    def test_unmapped_model_passes_through_unchanged(self):
        self.assertEqual(harness.translate_model(self.spec, "haiku"), "haiku")

    def test_extra_env_is_applied_alongside_stripping(self):
        env = harness.apply_env(self.spec, {"SOME_VENDOR_TOKEN": "leak", "KEEP": "1"})
        self.assertEqual(env, {"KEEP": "1", "OTHER_CLI_MODE": "headless"})


class TestPersonaInjectionContract(unittest.TestCase):
    """Only a harness without --agent-equivalent loading needs this."""

    def test_claude_role_persona_loads_and_strips_frontmatter(self):
        body = harness.load_persona(REPO, "backend-engineer")
        self.assertNotIn("---\nname:", body)
        self.assertIn("senior backend engineer", body.lower())

    def test_missing_role_file_raises_clearly(self):
        with self.assertRaises(harness.HarnessError):
            harness.load_persona(REPO, "no-such-role-exists")


if __name__ == "__main__":
    unittest.main()
