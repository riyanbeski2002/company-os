"""Bring-your-own-key providers (M4, migration doc §4.5): only key NAMES are
stored, the key reaches only the worker's env and never the evidence trail,
and a provider the project's classification forbids is refused, not
silently swapped for another."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))
sys.path.insert(0, str(HERE))

import providers  # noqa: E402
import worker  # noqa: E402
from test_launch_regressions import FakeHarnessCase  # noqa: E402

KEY = "sk-or-v1-PLANTED0123456789abcdefKEY"


def cfg(**provs):
    return {"default": "native", "roles": {}, "providers": provs}


BYO = {"auth": "env", "key_ref": "TEST_BYO_KEY", "trust": "third_party",
       "max_classification": "INTERNAL", "base_url": "https://example.test/api"}


class TestValidation(unittest.TestCase):
    def test_shipped_config_routes_every_role_to_native(self):
        c = providers.load_config(HERE.parent / ".company")
        self.assertEqual(providers.resolve(c, "backend-engineer")["_name"], "native")
        self.assertEqual(providers.resolve(c, "cto-advisor")["_name"], "native")

    def test_a_pasted_key_is_rejected_without_echoing_it(self):
        for field in ("key_ref", "base_url"):
            with self.subTest(field=field):
                with self.assertRaises(providers.ProviderError) as ctx:
                    providers.validate(cfg(byo={**BYO, field: KEY}))
                self.assertIn("credential", str(ctx.exception))
                self.assertNotIn(KEY, str(ctx.exception))

    def test_a_key_in_a_comment_is_rejected_too(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config").mkdir()
            (Path(d) / "config" / "providers.yaml").write_text(
                f"default: native\n# my key: {KEY}\nproviders: {{}}\n")
            with self.assertRaises(providers.ProviderError):
                providers.load_config(Path(d))

    def test_names_paths_and_urls_are_not_mistaken_for_keys(self):
        providers.validate(cfg(byo={**BYO, "key_ref": "OPENROUTER_API_KEY_FOR_A_LONG_TEAM_NAME",
                                    "base_url": "https://openrouter.ai/api/v1/chat/completions"}))
        # prose in a comment: "task-orchestration" contains "sk-orchestration"
        for text in ("see task-orchestration-notes", "docs/HARNESS-AGNOSTIC-MIGRATION.md",
                     "risk_assessment_for_vendors"):
            self.assertFalse(providers._looks_like_key(text), text)

    def test_bad_entries_are_rejected(self):
        bad = {
            "key_ref not an env name": {**BYO, "key_ref": "openrouter key"},
            "env auth without key_ref": {k: v for k, v in BYO.items() if k != "key_ref"},
            "key_ref without env auth": {**BYO, "auth": "none"},
            "no ceiling": {k: v for k, v in BYO.items() if k != "max_classification"},
            "unknown trust": {**BYO, "trust": "trusted"},
            "native auth on a provider": {**BYO, "auth": "native"},
            "non-http base_url": {**BYO, "base_url": "file:///etc"},
        }
        for why, spec in bad.items():
            with self.subTest(why), self.assertRaises(providers.ProviderError):
                providers.validate(cfg(byo=spec))

    def test_routing_to_an_undefined_provider_is_rejected(self):
        with self.assertRaises(providers.ProviderError):
            providers.validate({"default": "native", "roles": {"qa-engineer": "nope"},
                                "providers": {}})

    def test_native_cannot_be_redefined(self):
        with self.assertRaises(providers.ProviderError):
            providers.validate(cfg(native=BYO))


class TestClassificationGate(unittest.TestCase):
    def spec(self, ceiling):
        return {**BYO, "max_classification": ceiling, "_name": "byo"}

    def test_at_or_below_the_ceiling_is_allowed(self):
        providers.check_classification(self.spec("INTERNAL"), "INTERNAL")
        providers.check_classification(self.spec("INTERNAL"), "PUBLIC")

    def test_above_the_ceiling_is_refused(self):
        with self.assertRaises(providers.ProviderIneligible):
            providers.check_classification(self.spec("INTERNAL"), "CONFIDENTIAL")

    def test_native_has_no_ceiling(self):
        providers.check_classification({"_name": "native"}, "SECRET")

    def test_an_unknown_project_level_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config").mkdir()
            (Path(d) / "config" / "project.yaml").write_text("data_classification: TOPSECRET\n")
            with self.assertRaises(providers.ProviderError):
                providers.project_classification(Path(d))


class TestWorkerEnv(unittest.TestCase):
    CARRY = {"_name": "h", "provider_env": {"key": "H_TOKEN", "base_url": "H_BASE"}}

    def test_native_injects_nothing(self):
        self.assertEqual(providers.worker_env({"_name": "native"}, {}), ({}, []))

    def test_key_moves_to_the_harness_variable_only(self):
        add, remove = providers.worker_env({**BYO, "_name": "byo"}, self.CARRY,
                                           {"TEST_BYO_KEY": KEY})
        self.assertEqual(add, {"H_TOKEN": KEY, "H_BASE": "https://example.test/api"})
        self.assertEqual(remove, ["TEST_BYO_KEY"])

    def test_unset_key_refuses(self):
        with self.assertRaises(providers.ProviderError) as ctx:
            providers.worker_env({**BYO, "_name": "byo"}, self.CARRY, {})
        self.assertIn("TEST_BYO_KEY", str(ctx.exception))

    def test_harness_without_provider_env_refuses(self):
        with self.assertRaises(providers.ProviderError):
            providers.worker_env({**BYO, "_name": "byo"}, {"_name": "codex"},
                                 {"TEST_BYO_KEY": KEY})

    def test_redact(self):
        out = providers.redact(f"auth failed for {KEY}!", {"TEST_BYO_KEY": KEY})
        self.assertEqual(out, "auth failed for [REDACTED:TEST_BYO_KEY]!")

    def test_report_says_only_whether_a_key_is_set(self):
        r = providers.report(cfg(byo=BYO), {"TEST_BYO_KEY": KEY})
        self.assertTrue(r["providers"]["byo"]["key_set"])
        self.assertNotIn(KEY, json.dumps(r))


class TestLaunchWithProvider(FakeHarnessCase):
    """End to end through worker.launch, with a stand-in CLI that echoes the
    key it was given to stdout and stderr, as a CLI's auth error might."""

    def setUp(self):
        super().setUp()
        script = Path(self.tmp.name) / "echo_key.py"
        script.write_text(
            "import json, os, sys\n"
            "sys.stdin.read()\n"
            "key = os.environ.get('H_TOKEN', '')\n"
            "print(f'401 Unauthorized for key {key}', file=sys.stderr)\n"
            "print(json.dumps({'type': 'result', 'is_error': False, 'num_turns': 1,\n"
            "                  'session_id': 's', 'result': 'saw ' + key,\n"
            "                  'leaked_ref_var': os.environ.get('TEST_BYO_KEY'),\n"
            "                  'base': os.environ.get('H_BASE'),\n"
            "                  'usage': {'input_tokens': 1, 'output_tokens': 1}}))\n")
        (self.root / "config" / "harness.yaml").write_text(
            "default: fake\nroles: {}\nharnesses:\n  fake:\n"
            "    native_agent_loading: true\n    self_sandboxed: true\n"
            "    guards: external\n"
            f"    command: [{json.dumps(sys.executable)}, {json.dumps(str(script))}]\n"
            "    provider_env: {key: H_TOKEN, base_url: H_BASE}\n")
        (self.root / "config" / "providers.yaml").write_text(
            "default: native\nroles: {backend-engineer: byo}\nproviders:\n"
            "  byo: {auth: env, key_ref: TEST_BYO_KEY, trust: third_party,\n"
            "        max_classification: INTERNAL, base_url: 'https://example.test/api'}\n")
        self.env = mock.patch.dict(os.environ, {"TEST_BYO_KEY": KEY})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _launch(self, actor="be-1"):
        return worker.launch(self.repo, self.root, self._task(), "packet",
                             "backend-engineer", actor, timeout=30)

    def test_planted_key_never_reaches_the_evidence_trail(self):
        res = self._launch()
        state = self.root / "state" / "workers" / "be-1"
        stdout = (state / "stdout.json").read_text()
        # The worker did receive it (its echo was scrubbed, not empty)...
        self.assertIn("saw [REDACTED:TEST_BYO_KEY]", stdout)
        self.assertIn("[REDACTED:TEST_BYO_KEY]", (state / "stderr.log").read_text())
        # ...only under the harness's variable, alongside the base URL.
        out = json.loads(stdout)
        self.assertIsNone(out["leaked_ref_var"])
        self.assertEqual(out["base"], "https://example.test/api")
        # And nowhere a reader of the evidence could find it.
        for f in (state / "stdout.json", state / "stderr.log", state / "result.json",
                  self.root / "events" / "events.jsonl"):
            self.assertNotIn(KEY, f.read_text(), f)
        self.assertNotIn(KEY, json.dumps(res))
        started = self._events("WORKER_STARTED")[0]
        self.assertEqual(started["data"]["provider"], "byo")

    def test_unset_key_refuses_before_anything_starts(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_BYO_KEY")
            with self.assertRaises(worker.WorkerError) as ctx:
                self._launch()
        self.assertIn("TEST_BYO_KEY", str(ctx.exception))
        self.assertEqual(self._events("WORKER_STARTED"), [])
        self.assertFalse((self.root / "state" / "claims" / "T-1.claim").exists())

    def test_ineligible_provider_is_escalated_and_not_launched(self):
        (self.root / "config" / "project.yaml").write_text("data_classification: CONFIDENTIAL\n")
        with self.assertRaises(worker.WorkerError) as ctx:
            self._launch()
        self.assertIn("CONFIDENTIAL", str(ctx.exception))
        self.assertEqual(self._events("WORKER_STARTED"), [])
        esc = self._events("ESCALATION_RAISED")
        self.assertEqual(len(esc), 1)
        self.assertEqual(esc[0]["task"], "T-1")
        self.assertEqual(esc[0]["data"]["kind"], "decision")
        self.assertFalse((self.root / "state" / "claims" / "T-1.claim").exists())

    def test_a_role_left_on_native_gets_no_provider_vars(self):
        res = worker.launch(self.repo, self.root, self._task(), "packet",
                            "frontend-engineer", "fe-1", timeout=30)
        out = json.loads(Path(res["stdout"]).read_text())
        self.assertEqual(out["result"], "saw ")
        self.assertIsNone(out["base"])
        # Native inherits the parent env unchanged, as before M4.
        self.assertEqual(out["leaked_ref_var"], KEY)
        self.assertEqual(self._events("WORKER_STARTED")[0]["data"]["provider"], "native")

    def test_advisor_launch_is_gated_too(self):
        (self.root / "config" / "providers.yaml").write_text(
            "default: byo\nroles: {}\nproviders:\n"
            "  byo: {auth: env, key_ref: TEST_BYO_KEY, trust: third_party,\n"
            "        max_classification: PUBLIC}\n")
        with self.assertRaises(worker.WorkerError):
            worker.launch_readonly(self.repo, self.root, "p", "packet",
                                   "cto-advisor", "cto-1", timeout=30)
        self.assertEqual(self._events("WORKER_STARTED"), [])
        self.assertEqual(len(self._events("ESCALATION_RAISED")), 1)


if __name__ == "__main__":
    unittest.main()
