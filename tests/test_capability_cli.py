"""tools/capability.py's COMMANDS wiring. `search` was defined
(cmd_search) but never added to COMMANDS — a real, previously-identified
bug that made `tools/capability.py search ...` fail with "usage: ... <list|
show|load|unload>" even though the function existed and worked. Fixed as a
drive-by during the 2026-10-19 donor review while this module was already
being read for the team-bundle-manifest work; this pins the fix down."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import capability  # noqa: E402


class TestCommandsWiring(unittest.TestCase):
    def test_search_is_wired_into_commands(self):
        self.assertIn("search", capability.COMMANDS)
        self.assertIs(capability.COMMANDS["search"], capability.cmd_search)

    def test_every_defined_cmd_function_is_reachable(self):
        """Catches the inverse mistake too: a cmd_* function nobody wired in."""
        defined = {name[len("cmd_"):] for name in dir(capability) if name.startswith("cmd_")}
        self.assertEqual(defined, set(capability.COMMANDS.keys()))

    def test_search_runs_against_the_real_index_without_crashing(self):
        if not capability.INDEX.exists():
            self.skipTest("config/capability-index.yaml not present in this checkout")
        with self.assertRaises(SystemExit):
            capability.cmd_search([])  # no keyword -> usage exit, not a crash


class TestCompanyCapabilityLoad(unittest.TestCase):
    """`company capability load` wraps the standalone script and records
    CAPABILITY_LOADED; the script itself stays free of any event-log coupling."""

    def setUp(self):
        import tempfile
        from unittest import mock
        import yaml
        sys.path.insert(0, str(ROOT / "tools" / "company"))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        (self.base / "external" / "demo" / "skill").mkdir(parents=True)
        (self.base / "skills").mkdir()
        index = self.base / "capability-index.yaml"
        index.write_text(yaml.safe_dump({"units": [
            {"unit_id": "demo:skill", "type": "skill", "name": "skill",
             "description": "d", "path": "external/demo/skill", "pairs_with": []},
            {"unit_id": "demo:ref", "type": "reference", "name": "ref",
             "description": "d", "path": "external/demo/README.md", "pairs_with": []},
        ]}))
        for name, value in (("INDEX", index), ("REPO_ROOT", self.base),
                            ("SKILLS_DIR", self.base / "skills")):
            patcher = mock.patch.object(capability, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.root = self.base / ".company"
        (self.root / "events").mkdir(parents=True)

    def company(self, *argv):
        import contextlib
        import io
        import json
        import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as ctx:
            cli.main(["--root", str(self.root), *argv])
        return ctx.exception.code, json.loads(out.getvalue()) if out.getvalue() else None

    def events(self):
        from eventlog import EventLog
        return [e for e in EventLog(self.root).read() if e["event"] == "CAPABILITY_LOADED"]

    def test_load_links_the_skill_and_records_the_event(self):
        code, out = self.company("capability", "load", "demo:skill",
                                 "--task", "T-9", "--project", "p", "--actor", "company-pm")
        self.assertEqual(code, 0)
        self.assertTrue((self.base / "skills" / "demo__skill").is_symlink())
        self.assertIn("loaded: skills/demo__skill", out["output"])
        ev, = self.events()
        self.assertEqual(ev["data"], {"unit_id": "demo:skill", "type": "skill", "task": "T-9"})
        self.assertEqual((ev["project"], ev["actor"]), ("p", "company-pm"))
        self.assertEqual(out["seq"], ev["seq"])

    def test_unknown_unit_records_nothing(self):
        code, out = self.company("capability", "load", "demo:nope", "--project", "p")
        self.assertEqual(code, 1)
        self.assertEqual(self.events(), [])

    def test_standalone_script_load_still_works_and_writes_no_event(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            capability.cmd_load(["demo:skill"])
        self.assertTrue((self.base / "skills" / "demo__skill").is_symlink())
        self.assertIn("loaded: skills/demo__skill", out.getvalue())
        self.assertEqual(self.events(), [])

    def test_event_type_is_registered_and_needs_no_evidence(self):
        from eventlog import EVENTS, REQUIRES_EVIDENCE, make_event, validate
        self.assertIn("CAPABILITY_LOADED", EVENTS)
        self.assertNotIn("CAPABILITY_LOADED", REQUIRES_EVIDENCE)
        validate(make_event(event="CAPABILITY_LOADED", actor="company-pm",
                            project="p", data={"unit_id": "demo:skill"}))


if __name__ == "__main__":
    unittest.main()
