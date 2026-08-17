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

    def test_pm_preflights_before_accepting_work(self):
        """A PM that skips `company doctor` is indistinguishable from no PM.

        Launched with `claude --agent company-pm` in a repo that had never been
        onboarded, the PM found no `.company/`, said nothing about it, and worked
        like an ordinary session — no event log, no gates, no Evidence Rule,
        while the pane label said `company-pm`. Governance that silently isn't
        there is worse than none, because it is believed.
        """
        text = (AGENTS[0].parent / "company-pm.md").read_text(encoding="utf-8")
        self.assertIn("company doctor", text)
        self.assertIn("company onboard", text,
                      "the PM must know how to offer onboarding, not just refuse")

    def test_frontend_engineer_has_a_taste_standard(self):
        """Functional correctness alone ships generic AI-slop UI.

        `frontend-engineer` enforced states and file ownership but had no
        standard for what the screen should look like — nothing stopped it
        from shipping a gradient-bento default. Riyan noticed the gap reading
        the deep-research report's anti-slop rule list; this pins the fix.
        """
        text = (AGENTS[0].parent / "frontend-engineer.md").read_text(encoding="utf-8")
        self.assertIn("Never add motion, gradients", text)
        self.assertIn("fake KPI", text)

    def test_pm_knows_how_to_actually_launch_each_tier(self):
        """Watched live: the PM tried `company run` (Tier-2-only, requires a
        task already in the event log) to launch product-designer, which is
        Tier 1 and needs no task ID at all — then burned 6 minutes grepping
        its own source for the right invocation. The correct sequence for
        both tiers needed to be IN the prompt, not discoverable only by
        reading cli.py."""
        text = (AGENTS[0].parent / "company-pm.md").read_text(encoding="utf-8")
        self.assertIn("Tier 1 has no CLI step at all", text)
        self.assertIn("company plan --spec", text)
        self.assertIn("company staff --project", text)
        self.assertIn("company run TASK-101", text)

    def test_pm_unblocks_itself_before_asking_riyan(self):
        """Advising 'run these 4 commands yourself' for routine scaffolding/
        detect/baseline — all things the PM's own Bash/Write/Edit tools can
        do — was exactly the failure the escalation design exists to avoid,
        just in the opposite direction: handing Riyan a runbook instead of
        silently blocking. Both dump PM work onto the scarcest resource."""
        text = (AGENTS[0].parent / "company-pm.md").read_text(encoding="utf-8")
        self.assertIn("Do your own unblocking", text)
        self.assertIn("not Riyan's problem to", text)

    def test_pm_records_lessons_from_corrections(self):
        """Before this, a correction only became durable via a personal habit
        (hand-writing tasks/lessons.md) — invisible to Company OS itself and
        to any other project. This pins that the PM actually uses the
        durable, queryable mechanism instead."""
        text = (AGENTS[0].parent / "company-pm.md").read_text(encoding="utf-8")
        self.assertIn("company lesson", text)

    def test_product_designer_is_tier_1_and_writes_only_the_handoff(self):
        """No worktree, so no ownership hook — the write scope is a prompt
        discipline, not a mechanism. Say so plainly rather than imply a
        guarantee that doesn't exist at Tier 1."""
        text = (AGENTS[0].parent / "product-designer.md").read_text(encoding="utf-8")
        self.assertIn("no worktree", text.lower())
        self.assertIn("never touch implementation code", text)

    def test_frontend_builds_against_the_designer_handoff(self):
        text = (AGENTS[0].parent / "frontend-engineer.md").read_text(encoding="utf-8")
        self.assertIn("product-designer", text)

    def test_pm_knows_when_to_staff_a_designer(self):
        text = (AGENTS[0].parent / "company-pm.md").read_text(encoding="utf-8")
        self.assertIn("product-designer", text)
        self.assertIn("ux-flow", text)

    def test_worker_agents_carry_context_discipline(self):
        for name in ("backend-engineer", "frontend-engineer", "code-reviewer",
                     "qa-engineer", "security-reviewer", "product-designer"):
            text = (AGENTS[0].parent / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("Keep your own context small", text)



class TestResearchPresentOptionsBuild(unittest.TestCase):
    """Riyan's own words: 'the skill, the staff, the agent should be able to
    pick it up, understand, brainstorm, research and present me a top notch
    output' — for every discipline, not just frontend, which is just the
    easiest one to see fail ('i said i need a really good immersive UI...
    it built a crappy static AI sloppy hero page').

    A Haiku fleet audited every agent and skill against this pattern —
    RESEARCH -> PRESENT REAL OPTIONS WITH TRADEOFFS -> ASK FOR A CHOICE ->
    BUILD AGAINST IT — and every single one came back missing it. This pins
    that the gap is closed and stays closed."""

    MARKERS = {
        "company-pm": "Disambiguate a vague outcome before staffing it",
        "backend-engineer": "On architectural choices",
        "frontend-engineer": "Open-ended asks",
        "product-designer": "When the interaction pattern itself is a real choice",
        "security-reviewer": "Present remediation options",
        "qa-engineer": "genuinely ambiguous",
        "code-reviewer": "When you reject on approach",
        "cto-advisor": "Research before you recommend",
        "ciso-advisor": "How you recommend remediation",
        "cfo-advisor": "Waste vs. a real tradeoff",
        "coo-advisor": "more than one real fix",
    }

    def test_every_role_presents_options_before_building_or_deciding(self):
        for name, marker in self.MARKERS.items():
            text = (AGENTS[0].parent / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn(marker, text, f"{name}.md is missing its options-first section")


class TestInstallDiscoverability(unittest.TestCase):
    """Agents must resolve from any directory, not just this repo.

    `install.sh` originally wrote a `pluginDirectories` key into settings.json.
    No such setting exists — it silently did nothing, and `--agent company-pm`
    failed everywhere with "agent not found". User-scope `~/.claude/agents/`
    is the surface that actually loads in every project.
    """

    def test_installer_does_not_use_the_invented_setting(self):
        text = (Path(__file__).resolve().parent.parent / "install.sh").read_text()
        self.assertNotIn('setdefault("pluginDirectories"', text)
        self.assertIn("agents", text)

    def test_installer_links_agents_into_user_scope(self):
        text = (Path(__file__).resolve().parent.parent / "install.sh").read_text()
        self.assertIn("$CLAUDE_DIR/agents", text)

    def test_installer_links_skills_into_user_scope(self):
        """Skills have the exact same visibility problem agents had — a file
        inside this repo is invisible to Claude Code unless it is symlinked
        into a directory Claude actually scans. capability-curator would have
        silently never loaded without this."""
        text = (Path(__file__).resolve().parent.parent / "install.sh").read_text()
        self.assertIn("$CLAUDE_DIR/skills", text)

    def test_installer_registers_hooks_with_absolute_paths(self):
        text = (Path(__file__).resolve().parent.parent / "install.sh").read_text()
        for script in ("guard_paths.py", "protect_branches.py", "guard_secrets.py", "emit_exit.py"):
            self.assertIn(script, text)

if __name__ == "__main__":
    unittest.main()
