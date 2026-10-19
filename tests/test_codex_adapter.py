"""tools/company/adapters/codex_adapter.py — translating Codex's streamed
JSONL into the single RESULT_SCHEMA-shaped object worker.py expects.

Runs the adapter as a real subprocess (so these also catch a syntax error or
an import failure that unit-importing the module might not), but fakes
`codex` itself with a tiny stand-in script on PATH so the tests are
deterministic and need no network, auth, or real Codex account.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADAPTER = HERE.parent / "tools" / "company" / "adapters" / "codex_adapter.py"


def _run_with_fake_codex(fake_codex_body: str, stdin_text: str = "do the task") -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        fake_codex = Path(tmp) / "codex"
        fake_codex.write_text("#!/usr/bin/env python3\n" + fake_codex_body, encoding="utf-8")
        fake_codex.chmod(0o755)

        env = dict(os.environ)
        env["PATH"] = f"{tmp}:{env.get('PATH', '')}"

        proc = subprocess.run(
            [sys.executable, str(ADAPTER), "--skip-git-repo-check"],
            input=stdin_text, env=env, capture_output=True, text=True,
        )
        return json.loads(proc.stdout), proc.returncode


class TestCodexAdapter(unittest.TestCase):
    def test_happy_path_extracts_session_usage_and_structured_reply(self):
        fake = textwrap.dedent('''
            import sys
            print(\'{"type":"thread.started","thread_id":"abc-123"}\')
            print(\'{"type":"item.completed","item":{"type":"agent_message","text":"{\\\\"summary\\\\": \\\\"done\\\\", \\\\"blocked\\\\": false}"}}\')
            print(\'{"type":"turn.completed","usage":{"input_tokens":120,"cached_input_tokens":100,"cache_write_input_tokens":5,"output_tokens":18}}\')
        ''')
        result, code = _run_with_fake_codex(fake)
        self.assertEqual(code, 0)
        self.assertEqual(result["session_id"], "abc-123")
        self.assertEqual(result["summary"], "done")
        self.assertFalse(result["blocked"])
        self.assertFalse(result["is_error"])
        self.assertIsNone(result["terminal_reason"])
        self.assertIsNone(result["total_cost_usd"])
        self.assertEqual(result["usage"], {
            "input_tokens": 20,            # 120 - 100 cached, not the raw 120
            "output_tokens": 18,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 5,
        })

    def test_turn_failed_is_an_error_with_terminal_reason(self):
        fake = textwrap.dedent('''
            print(\'{"type":"thread.started","thread_id":"x"}\')
            print(\'{"type":"turn.failed","error":{"message":"boom"}}\')
        ''')
        result, code = _run_with_fake_codex(fake)
        self.assertTrue(result["is_error"])
        self.assertEqual(result["terminal_reason"], "turn.failed")

    def test_nonzero_exit_is_an_error_even_without_a_turn_failed_event(self):
        fake = textwrap.dedent('''
            import sys
            print(\'{"type":"thread.started","thread_id":"x"}\')
            sys.exit(1)
        ''')
        result, code = _run_with_fake_codex(fake)
        self.assertEqual(code, 1)
        self.assertTrue(result["is_error"])

    def test_stray_non_json_lines_do_not_crash_the_adapter(self):
        fake = textwrap.dedent('''
            print("Reading prompt from stdin...")
            print(\'{"type":"thread.started","thread_id":"x"}\')
            print(\'{"type":"item.completed","item":{"type":"agent_message","text":"{\\\\"summary\\\\": \\\\"ok\\\\", \\\\"blocked\\\\": false}"}}\')
            print(\'{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\')
        ''')
        result, code = _run_with_fake_codex(fake)
        self.assertEqual(result["summary"], "ok")

    def test_unstructured_agent_text_yields_no_structured_fields_but_still_reports_usage(self):
        fake = textwrap.dedent('''
            print(\'{"type":"thread.started","thread_id":"x"}\')
            print(\'{"type":"item.completed","item":{"type":"agent_message","text":"just prose, no json"}}\')
            print(\'{"type":"turn.completed","usage":{"input_tokens":5,"output_tokens":2}}\')
        ''')
        result, code = _run_with_fake_codex(fake)
        self.assertNotIn("summary", result)
        self.assertEqual(result["usage"]["output_tokens"], 2)


if __name__ == "__main__":
    unittest.main()
