"""Agent definitions must not regress in the ways that cost the most.

The `tools:` check exists because `company-pm` shipped without one and paid
36,151 tokens of tool definitions on every turn, against 6,016 for a six-tool
agent — measured, same prompt. Over one 26-turn run that was ~659,000 tokens for
tools it never called, and nothing in the system noticed for weeks.

A finding that only lives in a report comes back. A finding that becomes a test
does not.
"""

import unittest
from pathlib import Path

AGENTS = sorted((Path(__file__).resolve().parent.parent / "agents").glob("*.md"))

READONLY = {"code-reviewer", "qa-engineer", "security-reviewer",
            "cto-advisor", "ciso-advisor", "cfo-advisor", "coo-advisor"}


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)[1]
    out = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


class TestAgentDefinitions(unittest.TestCase):
    def test_there_are_agents_to_check(self):
        self.assertGreater(len(AGENTS), 0)

    def test_every_agent_declares_a_tools_list(self):
        """The single most expensive omission available in this system."""
        missing = [p.stem for p in AGENTS if not frontmatter(p).get("tools")]
        self.assertEqual(
            missing, [],
            f"{missing} have no `tools:` list, so they carry every tool definition "
            f"in context on every turn (~36k vs ~6k measured).")

    def test_every_agent_has_name_and_description(self):
        for p in AGENTS:
            fm = frontmatter(p)
            self.assertTrue(fm.get("name"), f"{p.stem} has no name")
            self.assertTrue(fm.get("description"), f"{p.stem} has no description")

    def test_agent_name_matches_filename(self):
        for p in AGENTS:
            self.assertEqual(frontmatter(p).get("name"), p.stem)

    def test_reviewers_and_advisors_cannot_write(self):
        """Independence is structural, not a promise in a prompt."""
        for p in AGENTS:
            if p.stem not in READONLY:
                continue
            fm = frontmatter(p)
            tools = fm.get("tools", "")
            for writer in ("Write", "Edit", "NotebookEdit"):
                self.assertNotIn(writer, tools,
                                 f"{p.stem} is read-only but lists {writer}")
            self.assertIn("Write", fm.get("disallowedTools", ""),
                          f"{p.stem} should disallow Write explicitly")

    def test_implementers_can_write(self):
        for name in ("backend-engineer", "frontend-engineer"):
            tools = frontmatter(Path(AGENTS[0].parent / f"{name}.md")).get("tools", "")
            self.assertIn("Edit", tools)
            self.assertIn("Write", tools)

    def test_workers_have_a_turn_ceiling(self):
        """There is no --max-turns CLI flag; frontmatter is the only budget."""
        for p in AGENTS:
            if p.stem == "company-pm":
                continue   # the PM is interactive and bounded by the human
            self.assertTrue(frontmatter(p).get("maxTurns"),
                            f"{p.stem} has no maxTurns ceiling")

    def test_pm_can_delegate(self):
        """Tier 1 exists only if the PM can spawn subagents."""
        self.assertIn("Agent", frontmatter(
            Path(AGENTS[0].parent / "company-pm.md")).get("tools", ""))

    def test_worker_agents_carry_context_discipline(self):
        for name in ("backend-engineer", "frontend-engineer", "code-reviewer",
                     "qa-engineer", "security-reviewer"):
            text = (AGENTS[0].parent / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("Keep your own context small", text)


if __name__ == "__main__":
    unittest.main()
