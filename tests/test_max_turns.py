"""Role-aware turn budgets (cost audit, 2026-09-14): a gate role is handed
the diff already, so it gets a lower default turn ceiling than an
implementer — see `cli.py`'s `_resolve_max_turns`.
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import cli  # noqa: E402


class TestResolveMaxTurns(unittest.TestCase):
    def test_gate_role_defaults_low(self):
        self.assertEqual(cli._resolve_max_turns(None, "code-reviewer"), cli.GATE_MAX_TURNS)
        self.assertEqual(cli._resolve_max_turns(None, "qa-engineer"), cli.GATE_MAX_TURNS)
        self.assertEqual(cli._resolve_max_turns(None, "security-reviewer"), cli.GATE_MAX_TURNS)

    def test_implementer_role_defaults_high(self):
        self.assertEqual(cli._resolve_max_turns(None, "backend-engineer"), cli.IMPLEMENTER_MAX_TURNS)
        self.assertEqual(cli._resolve_max_turns(None, "frontend-engineer"), cli.IMPLEMENTER_MAX_TURNS)

    def test_explicit_value_always_wins(self):
        self.assertEqual(cli._resolve_max_turns(5, "code-reviewer"), 5)
        self.assertEqual(cli._resolve_max_turns(99, "backend-engineer"), 99)
        self.assertEqual(cli._resolve_max_turns(0, "backend-engineer"), 0)


if __name__ == "__main__":
    unittest.main()
