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


if __name__ == "__main__":
    unittest.main()
