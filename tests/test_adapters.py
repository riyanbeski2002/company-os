"""adapters/ — one normalized result per run, whichever harness produced it
(docs/HARNESS-AGNOSTIC-MIGRATION.md §4.1, milestone M1).

worker.py used to read Claude Code's own result JSON keys directly
(`total_cost_usd`, `is_error`, ...), so every other harness had to
impersonate that shape through a wrapper script. Each harness now names its
output format in harness.yaml and an adapter parses it; worker.py only ever
sees the normalized fields. Fixtures are the recorded shapes of real output
(Claude's `-p --output-format json`, codex's `exec --json` JSONL, as
live-tested 2026-10-19), not invented ones.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools" / "company"))

import adapters  # noqa: E402
import harness  # noqa: E402
import worker  # noqa: E402
from eventlog import EventLog  # noqa: E402

NORMALIZED_KEYS = {"session_id", "is_error", "terminal_reason", "structured_output",
                   "text", "cost_usd", "num_turns", "usage"}
USAGE_KEYS = {"input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens"}

CLAUDE_RESULT = {"type": "result", "subtype": "success", "is_error": False,
                 "stop_reason": "end_turn", "terminal_reason": None, "num_turns": 11,
                 "session_id": "sess-1", "total_cost_usd": 0.42,
                 "structured_output": {"summary": "done", "blocked": False},
                 "usage": {"input_tokens": 1, "output_tokens": 6582,
                           "cache_read_input_tokens": 100, "cache_creation_input_tokens": 7}}


def _jsonl(*events):
    return "".join(json.dumps(e) + "\n" for e in events)


CODEX_OK = _jsonl(
    {"type": "thread.started", "thread_id": "abc-123"},
    {"type": "item.completed", "item": {"type": "agent_message",
                                        "text": '{"summary": "done", "blocked": false}'}},
    {"type": "turn.completed", "usage": {"input_tokens": 120, "cached_input_tokens": 100,
                                         "cache_write_input_tokens": 5, "output_tokens": 18}},
)


class TestClaudeJson(unittest.TestCase):
    def parse(self, raw, code=0):
        return adapters.parse({"_name": "claude"}, raw, code)

    def test_maps_every_field(self):
        r = self.parse(json.dumps(CLAUDE_RESULT))
        self.assertEqual(set(r), NORMALIZED_KEYS)
        self.assertEqual(r["session_id"], "sess-1")
        self.assertIs(r["is_error"], False)
        self.assertEqual(r["cost_usd"], 0.42)
        self.assertEqual(r["num_turns"], 11)
        self.assertEqual(r["structured_output"], {"summary": "done", "blocked": False})
        self.assertEqual(r["usage"], CLAUDE_RESULT["usage"])
        self.assertEqual(self.parse(json.dumps({**CLAUDE_RESULT, "result": "LGTM"}))["text"],
                         "LGTM")

    def test_banner_text_before_the_json_is_tolerated(self):
        r = self.parse("some banner\n" + json.dumps(CLAUDE_RESULT))
        self.assertEqual(r["session_id"], "sess-1")

    def test_empty_output_is_all_unknown_not_an_invented_value(self):
        # A killed or crashed run prints nothing. Unknown stays None — the
        # same thing worker.py recorded before the adapter layer existed.
        r = self.parse("", 143)
        self.assertEqual(set(r), NORMALIZED_KEYS)
        self.assertIsNone(r["session_id"])
        self.assertIsNone(r["is_error"])
        self.assertIsNone(r["cost_usd"])
        self.assertEqual(r["usage"], dict.fromkeys(USAGE_KEYS, 0))


class TestCodexJsonl(unittest.TestCase):
    SPEC = {"_name": "codex", "output": "codex-jsonl"}

    def parse(self, raw, code=0):
        return adapters.parse(self.SPEC, raw, code)

    def test_happy_path(self):
        r = self.parse(CODEX_OK)
        self.assertEqual(set(r), NORMALIZED_KEYS)
        self.assertEqual(r["text"], '{"summary": "done", "blocked": false}')
        self.assertEqual(r["session_id"], "abc-123")
        self.assertIs(r["is_error"], False)
        self.assertIsNone(r["terminal_reason"])
        self.assertIsNone(r["cost_usd"], "codex reports tokens only, never a cost")
        self.assertIsNone(r["num_turns"])
        self.assertEqual(r["structured_output"], {"summary": "done", "blocked": False})
        self.assertEqual(r["usage"], {
            "input_tokens": 20,  # 120 minus the 100 cached: disjoint, like Claude's
            "output_tokens": 18,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 5,
        })

    def test_turn_failed_is_an_error_with_its_reason(self):
        r = self.parse(_jsonl({"type": "thread.started", "thread_id": "x"},
                              {"type": "turn.failed", "error": {"message": "boom"}}))
        self.assertIs(r["is_error"], True)
        self.assertEqual(r["terminal_reason"], "turn.failed")

    def test_nonzero_exit_is_an_error_without_a_failure_event(self):
        r = self.parse(_jsonl({"type": "thread.started", "thread_id": "x"}), 1)
        self.assertIs(r["is_error"], True)

    def test_stray_lines_and_prose_replies(self):
        r = self.parse("Reading prompt from stdin...\n" + _jsonl(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "just prose"}},
            {"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 2}}))
        self.assertIsNone(r["structured_output"])
        self.assertEqual(r["usage"]["output_tokens"], 2)


# Verbatim stdout of three live agy 1.4.12 runs (2026-10-31).
AGY_OK = ('{"conversation_id":"ca6cc266-069c-41bd-ad62-2101eee46ec3","status":"SUCCESS",'
          '"response":"OK\\n","duration_seconds":5.6986609999999995,"num_turns":1,'
          '"usage":{"input_tokens":8717,"output_tokens":64,"thinking_tokens":63,'
          '"cache_read_tokens":0,"total_tokens":8781}}\n')
AGY_SCHEMA = ('{"conversation_id":"74785e45-e4f8-408a-be30-2618c9743e35","status":"SUCCESS",'
              '"response":"status ok\\n{\\"status\\":\\"ok\\"}\\n","duration_seconds":6.898416,'
              '"num_turns":2,"structured_output":{"status":"ok"},"json_schema":{"type":"object",'
              '"required":["status"],"properties":{"status":{"type":"string"}}},'
              '"usage":{"input_tokens":17738,"output_tokens":172,"thinking_tokens":156,'
              '"cache_read_tokens":0,"total_tokens":17910}}\n')
AGY_DENIED = ('{"conversation_id":"5e07bef0-2288-4aaa-a66a-3dbcc64d3519","status":"SUCCESS",'
              '"response":"","duration_seconds":4.891635,"num_turns":1,'
              '"usage":{"input_tokens":8708,"output_tokens":188,"thinking_tokens":151,'
              '"cache_read_tokens":0,"total_tokens":8896},'
              '"denied_actions":[{"action":"command","display_name":"RunCommand"}]}\n')


class TestAgyJson(unittest.TestCase):
    SPEC = {"_name": "agy", "output": "agy-json"}

    def parse(self, raw, code=0):
        return adapters.parse(self.SPEC, raw, code)

    def test_happy_path(self):
        r = self.parse(AGY_OK)
        self.assertEqual(set(r), NORMALIZED_KEYS)
        self.assertEqual(r["text"], "OK\n")
        self.assertEqual(r["session_id"], "ca6cc266-069c-41bd-ad62-2101eee46ec3")
        self.assertIs(r["is_error"], False)
        self.assertIsNone(r["terminal_reason"])
        self.assertIsNone(r["cost_usd"], "agy reports tokens only, never a cost")
        self.assertEqual(r["num_turns"], 1)
        self.assertIsNone(r["structured_output"])
        self.assertEqual(r["usage"], {"input_tokens": 8717, "output_tokens": 64,
                                      "cache_read_input_tokens": 0,
                                      "cache_creation_input_tokens": 0})

    def test_schema_run_carries_structured_output(self):
        self.assertEqual(self.parse(AGY_SCHEMA)["structured_output"], {"status": "ok"})

    def test_auto_denied_tool_is_an_error_despite_status_success(self):
        r = self.parse(AGY_DENIED)
        self.assertIs(r["is_error"], True)
        self.assertEqual(r["terminal_reason"], "permission_denied")

    def test_usage_error_with_no_output_is_an_error(self):
        # e.g. a bare `--print` followed by another flag: exit 2, empty stdout.
        r = self.parse("", 2)
        self.assertIs(r["is_error"], True)
        self.assertIsNone(r["session_id"])

    def test_killed_run_with_no_output_is_unknown(self):
        self.assertIsNone(self.parse("", None)["is_error"])


class TestHarnessOutputContract(unittest.TestCase):
    def _config(self, **spec):
        return {"default": "x", "harnesses": {"x": {"command": ["x"], **spec}}}

    def test_output_defaults_to_claude_json(self):
        # Every harness.yaml written before `output:` existed is a Claude one.
        spec = harness.resolve(self._config(), "any-role")
        self.assertEqual(adapters.output_format(spec), "claude-json")

    def test_unknown_output_format_is_refused_before_any_launch(self):
        with self.assertRaises(harness.HarnessError):
            harness.resolve(self._config(output="tea-leaves"), "any-role")

    def test_both_shipped_config_copies_name_their_formats(self):
        for root in (REPO, REPO / ".company"):
            harnesses = harness.load_config(root)["harnesses"]
            self.assertEqual(adapters.output_format(harnesses["claude"]), "claude-json")
            self.assertEqual(harnesses["codex"]["output"], "codex-jsonl")

    def test_trailing_args_land_after_every_appended_flag(self):
        spec = {"_name": "x", "command": ["cli", "run"], "trailing_args": ["-"],
                "effort_flag": "--effort", "self_sandboxed": True}
        cmd = harness.build_command(spec, role="r", plugin_root=REPO, allowed_tools="Read",
                                    effort="high", settings={"sandbox": {}})
        self.assertEqual(cmd, ["cli", "run", "--effort", "high", "-"])


class TestCodexRunsDirectly(unittest.TestCase):
    """The wrapper script used to exec `codex exec --json <its argv> -`. M1
    ran that same argv directly (only the parsing moved); M2 adds exactly two
    things on top — the guard hook (`-c hooks.PreToolUse=...`) and the trust
    bypass without which codex silently skips it. Nothing else differs from
    the live-tested 2026-10-19 invocation."""

    def test_argv_is_the_wrapper_argv_plus_only_the_guard_hook(self):
        spec = harness.load_config(REPO)["harnesses"]["codex"]
        cmd = harness.build_command({**spec, "_name": "codex"}, role="backend-engineer",
                                    plugin_root=REPO, allowed_tools="Read", effort="low",
                                    settings={"sandbox": {}})
        hook = ('hooks.PreToolUse=[{matcher=".*", hooks=[{type="command", '
                f"command=\"python3 '{REPO}/hooks/guard.py' codex\", timeout=30}}]}}]")
        self.assertEqual(cmd, [
            "codex", "exec", "--json", "--skip-git-repo-check",
            "--dangerously-bypass-hook-trust",
            "-c", 'sandbox_mode="workspace-write"',
            "-c", "sandbox_workspace_write.network_access=false",
            "-c", hook,
            "-c", "model_reasoning_effort=low",
            "-",
        ])


class TestLaunchUsesTheAdapter(unittest.TestCase):
    """A codex-jsonl harness through a real (readonly) launch: the event log
    gets the session and tokens without any wrapper translating them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / ".company"
        (self.root / "config").mkdir(parents=True)
        script = base / "fake_codex.py"
        script.write_text("import sys\nsys.stdin.read()\n"
                          f"sys.stdout.write({CODEX_OK!r})\n")
        (self.root / "config" / "harness.yaml").write_text(
            "default: fake\nroles: {}\nharnesses:\n  fake:\n"
            "    native_agent_loading: true\n    self_sandboxed: true\n"
            # a stand-in process: no hooks of its own; the guards it would
            # need are not what these tests exercise
            "    guards: external\n"
            "    output: codex-jsonl\n"
            f"    command: [{json.dumps(sys.executable)}, {json.dumps(str(script))}]\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_worker_exited_carries_the_normalized_result(self):
        out = worker.launch_readonly(self.root.parent, self.root, "p", "packet",
                                     "cto-advisor", "cto-advisor")
        exited = [e for e in EventLog(self.root).read() if e["event"] == "WORKER_EXITED"]
        self.assertEqual(len(exited), 1)
        data = exited[0]["data"]
        self.assertEqual(data["session_id"], "abc-123")
        self.assertIsNone(data["cost_usd_estimate"])
        self.assertEqual(data["tokens"], {"output": 18, "input": 20,
                                          "cache_read": 100, "cache_creation": 5})
        normalized = json.loads((Path(out["stdout"]).parent / "result.json").read_text())
        self.assertEqual(normalized["structured_output"], {"summary": "done", "blocked": False})


if __name__ == "__main__":
    unittest.main()
