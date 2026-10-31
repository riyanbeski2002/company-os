"""harnesses.py / `company harnesses` — which agent CLIs exist on this
machine, at which version, what each was verified to support, and whether a
role could launch on it right now (migration §4.1 manifest, M3; directive V2
§6: "Values must be confirmed against the installed version... run a
compatibility check when a harness is registered or upgraded").

Detection only ever runs `<cli> --version` — never a model call.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "tools" / "company"))

import harness  # noqa: E402
import harnesses  # noqa: E402

CLI = REPO / "tools" / "company" / "cli.py"


def _fake_cli(directory: Path, name: str, version_line: str) -> Path:
    p = directory / name
    p.write_text(f"#!/bin/sh\necho '{version_line}'\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


class DetectCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(os.path.realpath(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()


class TestDetect(DetectCase):
    def test_finds_a_cli_on_path_and_parses_its_version(self):
        _fake_cli(self.dir, "fakecli", "fakecli v1.2.3 (build 9)")
        with mock.patch.dict(os.environ, {"PATH": str(self.dir)}):
            d = harnesses.detect({"_name": "f", "binary": "fakecli"})
        self.assertEqual(d["path"], str(self.dir / "fakecli"))
        self.assertEqual(d["version"], "1.2.3")

    def test_falls_back_to_declared_install_paths_off_path(self):
        # agy installs to ~/.gemini/bin, which isn't on PATH by default.
        _fake_cli(self.dir, "agy", "1.4.11")
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            d = harnesses.detect({"_name": "agy", "binary": "agy",
                                  "binary_paths": [str(self.dir / "agy")]})
        self.assertEqual(d["path"], str(self.dir / "agy"))
        self.assertEqual(d["version"], "1.4.11")

    def test_absent_cli_is_reported_not_guessed(self):
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            d = harnesses.detect({"_name": "x", "binary": "no-such-cli"})
        self.assertIsNone(d["path"])
        self.assertIsNone(d["version"])

    def test_build_command_uses_the_detected_path_for_an_off_path_binary(self):
        _fake_cli(self.dir, "agy", "1.4.11")
        spec = {"_name": "agy", "binary": "agy", "binary_paths": [str(self.dir / "agy")],
                "command": ["agy", "-p"], "self_sandboxed": True}
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            cmd = harness.build_command(spec, role="r", plugin_root=REPO, allowed_tools="Read")
        self.assertEqual(cmd, [str(self.dir / "agy"), "-p"])


class TestReport(DetectCase):
    def _config(self, **spec):
        return {"default": "h", "roles": {}, "harnesses": {"h": {
            "binary": "fakecli", "command": ["fakecli"], "guards": "external",
            "verified_with": "1.2.3", **spec}}}

    def _row(self, config):
        _fake_cli(self.dir, "fakecli", "fakecli 1.2.3")
        with mock.patch.dict(os.environ, {"PATH": str(self.dir)}):
            return harnesses.report(config)["harnesses"]["h"]

    def test_a_healthy_harness_is_launchable_with_no_drift(self):
        row = self._row(self._config())
        self.assertTrue(row["launchable"], row)
        self.assertFalse(row["drift"])

    def test_version_drift_is_flagged(self):
        row = self._row(self._config(verified_with="1.2.0"))
        self.assertTrue(row["drift"])

    def test_unverified_shim_is_not_launchable_and_says_why(self):
        row = self._row(self._config(guards="shim"))
        self.assertFalse(row["launchable"])
        self.assertTrue(any("verified" in r for r in row["reasons"]))

    def test_catalogued_harness_is_not_launchable_and_says_why(self):
        row = self._row(self._config(command=None))
        self.assertFalse(row["launchable"])
        self.assertTrue(any("catalogued" in r for r in row["reasons"]))

    def test_not_installed_is_not_launchable(self):
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            row = harnesses.report(self._config())["harnesses"]["h"]
        self.assertFalse(row["launchable"])
        self.assertIn("not installed", " ".join(row["reasons"]))

    def test_invalid_capability_state_is_refused(self):
        with self.assertRaises(harness.HarnessError):
            harnesses.validate_capabilities("h", {"headless": "PROBABLY"})


# A stand-in CLI that behaves like codex would: every action goes through
# hooks/guard.py codex first and happens only if the guard allows it.
FAKE_GUARDED_CLI = r'''
import json, os, subprocess, sys
sys.stdin.read()
GUARD = os.environ["SMOKE_GUARD"]
def allowed(tool, tin):
    p = {"tool_name": tool, "tool_input": tin, "cwd": os.getcwd()}
    r = subprocess.run([sys.executable, GUARD, "codex"], input=json.dumps(p),
                       capture_output=True, text=True)
    return not r.stdout.strip()
patch = "*** Begin Patch\n*** Add File: {}\n+x\n*** End Patch"
if allowed("apply_patch", {"command": patch.format("forbidden.txt")}):
    open("forbidden.txt", "w").write("x")
for cmd in ("git push --force origin main", "cat .env"):
    if allowed("Bash", {"command": cmd}):
        print(subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout)
if allowed("apply_patch", {"command": patch.format("src/allowed.txt")}):
    open("src/allowed.txt", "w").write("ok")
print("done")
'''


class TestSmoke(DetectCase):
    def _config(self, script_body):
        script = self.dir / "fakecli.py"
        script.write_text(script_body)
        return {"harnesses": {"fake": {
            "binary": "python3", "command": [sys.executable, str(script)],
            "guards": "shim", "self_sandboxed": True, "native_agent_loading": True}}}

    def test_a_guarded_cli_passes_and_says_what_to_record(self):
        env = {"SMOKE_GUARD": str(REPO / "hooks" / "guard.py")}
        with mock.patch.dict(os.environ, env):
            out = harnesses.smoke(self._config(FAKE_GUARDED_CLI), "fake", timeout=60)
        self.assertTrue(out["pass"], out)
        self.assertTrue(out["force_push_blocked"])
        self.assertIn("guards_verified", out["record"])

    def test_an_unguarded_cli_fails_and_records_nothing(self):
        # Same CLI, but its hook never runs: everything it attempts happens.
        body = FAKE_GUARDED_CLI.replace("return not r.stdout.strip()", "return True")
        env = {"SMOKE_GUARD": str(REPO / "hooks" / "guard.py")}
        with mock.patch.dict(os.environ, env):
            out = harnesses.smoke(self._config(body), "fake", timeout=60)
        self.assertFalse(out["pass"])
        self.assertFalse(out["checks"]["forbidden_file_absent"])
        self.assertFalse(out["checks"]["secret_not_in_output"])
        self.assertIsNone(out["record"])

    def test_external_guards_have_nothing_to_smoke_test(self):
        cfg = self._config("print('x')")
        cfg["harnesses"]["fake"]["guards"] = "external"
        with self.assertRaises(harness.HarnessError):
            harnesses.smoke(cfg, "fake")


class TestShippedCatalogue(unittest.TestCase):
    def test_the_four_v1_harnesses_are_catalogued_with_valid_states(self):
        for root in (REPO, REPO / ".company"):
            hs = harness.load_config(root)["harnesses"]
            for name in ("claude", "codex", "agy", "opencode"):
                self.assertIn(name, hs, (root, name))
                harnesses.validate_capabilities(name, hs[name].get("capabilities") or {})
                self.assertTrue(hs[name].get("capabilities"), name)
                self.assertTrue(hs[name].get("verified_with"), name)

    def test_agy_and_opencode_are_catalogued_only_until_a_live_run(self):
        hs = harness.load_config(REPO)["harnesses"]
        for name in ("agy", "opencode"):
            with self.assertRaises(harness.HarnessError) as ctx:
                harness.resolve({"default": name, "harnesses": hs}, None)
            self.assertIn("catalogued", str(ctx.exception))

    def test_opencode_records_its_missing_blocking_hook(self):
        caps = harness.load_config(REPO)["harnesses"]["opencode"]["capabilities"]
        self.assertNotEqual(caps["blocking_pre_tool_hook"], "SUPPORTED")


class TestCli(unittest.TestCase):
    def _run(self, *args, env=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".company"
            (root / "config").mkdir(parents=True)
            (root / "config" / "harness.yaml").write_text(
                "default: h\nroles: {}\nharnesses:\n  h:\n    binary: no-such-cli\n"
                "    command: [no-such-cli]\n    guards: external\n    verified_with: '1.0'\n"
                "    capabilities: {headless: SUPPORTED}\n")
            r = subprocess.run([sys.executable, str(CLI), "--root", str(root), "harnesses", *args],
                               capture_output=True, text=True)
            return r.returncode, json.loads(r.stdout[r.stdout.find("{"):])

    def test_lists_without_failing(self):
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertFalse(out["harnesses"]["h"]["launchable"])

    def test_check_fails_when_the_default_harness_cannot_launch(self):
        code, out = self._run("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("h", out["problems"][0])


if __name__ == "__main__":
    unittest.main()
