"""The Capability Curator (V2): keeping every role's knowledge current.

Every agent in this system reasons from training data that goes stale the
moment it was cut — a security-reviewer that never hears about a new CVE
class is reviewing against last year's threat model. Riyan asked for this
generalized across every discipline, not just frontend, after noticing
frontend-engineer had no way to discover better resources at all.

The mechanism deliberately discovers and PROPOSES only. `company-pm` is the
only role with Write access to the registry; every other curator-eligible
role is read-only against it by construction (same independence guarantee as
review/security gates — a proposal that could self-approve is not a proposal).
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

sys.path.insert(0, str(ROOT / "tools" / "company"))


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    block = text.split("---", 2)[1]
    out = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


class TestCapabilityCuratorSkill(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "skills" / "capability-curator" / "SKILL.md"

    def test_skill_file_exists(self):
        self.assertTrue(self.path.exists())

    def test_frontmatter_has_name_and_trigger_description(self):
        fm = frontmatter(self.path)
        self.assertEqual(fm.get("name"), "capability-curator")
        self.assertIn("Triggers on", fm.get("description", ""))

    def test_defines_a_trust_hierarchy(self):
        text = self.path.read_text(encoding="utf-8")
        for tier in ("T0", "T1", "T2", "T3", "T4"):
            self.assertIn(tier, text)

    def test_discovers_and_proposes_never_installs(self):
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("never installs, adopts, or executes", text)
        self.assertIn("company escalate", text)

    def test_states_it_never_writes_the_registry_itself(self):
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("never the one who edits", text)

    def test_gates_research_queries_by_data_classification(self):
        """A WebSearch query is data leaving the repo, same as any other
        external call — CONFIDENTIAL/SECRET repos must not leak business
        specifics into it."""
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("data_classification", text)
        for tier in ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"):
            self.assertIn(tier, text)


class TestUxFlowSkill(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "skills" / "ux-flow" / "SKILL.md"

    def test_skill_file_exists(self):
        self.assertTrue(self.path.exists())

    def test_frontmatter_has_name_and_trigger_description(self):
        fm = frontmatter(self.path)
        self.assertEqual(fm.get("name"), "ux-flow")
        self.assertIn("Triggers on", fm.get("description", ""))

    def test_requires_the_non_happy_path_states(self):
        text = self.path.read_text(encoding="utf-8")
        for state in ("loading", "empty", "error", "unauthorized", "disabled"):
            self.assertIn(state, text, state)

    def test_says_when_to_skip_it(self):
        """Staffing this for every UI change would be the same tier-inflation
        defect the rest of the system explicitly guards against."""
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("When to skip this entirely", text)


class TestMotionVocabularySkill(unittest.TestCase):
    """Riyan explicitly requested and approved this one live, mid-turn — the
    capability-curator approval step is satisfied by that direct request,
    not a separate escalation. Content is an original write-up organized
    around 'when to reach for this,' not a verbatim copy of the source site."""

    def setUp(self):
        self.path = ROOT / "skills" / "motion-vocabulary" / "SKILL.md"

    def test_skill_file_exists(self):
        self.assertTrue(self.path.exists())

    def test_frontmatter_has_name_and_trigger_description(self):
        fm = frontmatter(self.path)
        self.assertEqual(fm.get("name"), "motion-vocabulary")
        self.assertIn("Triggers on", fm.get("description", ""))

    def test_covers_the_core_categories(self):
        text = self.path.read_text(encoding="utf-8")
        for category in ("Enter/exit", "Easing", "Spring", "Gestures",
                         "Performance vocabulary"):
            self.assertIn(category, text)

    def test_gives_a_concrete_default_not_just_a_glossary(self):
        """The point is defensible decisions, not a dictionary — ease-out as
        the default and the transform/opacity performance rule are the two
        most load-bearing facts in the whole skill."""
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("default for anything entering", text)
        self.assertIn("layout thrashing", text)

    def test_shipped_template_stays_empty(self):
        """config/capability-registry.yaml is the template `company init`
        copies into every newly onboarded repo — a company-os-specific
        approval does not belong there, or it would leak into every other
        project someone onboards. Caught this live: first attempt edited
        the template instead of company-os's own .company/ instance."""
        import yaml
        data = yaml.safe_load((ROOT / "config" / "capability-registry.yaml").read_text())
        self.assertEqual(data.get("entries"), [])

    def test_is_registered_and_approved_in_company_os_own_registry(self):
        import yaml
        reg_path = ROOT / ".company" / "config" / "capability-registry.yaml"
        if not reg_path.exists():
            self.skipTest("company-os not onboarded onto itself in this checkout")
        data = yaml.safe_load(reg_path.read_text())
        entry = next((e for e in data["entries"] if e["id"] == "motion-vocabulary"), None)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["approved_by"], "riyan")
        self.assertIn(entry["trust_tier"], ("T1", "T2", "T3"))

    def test_frontend_engineer_is_pointed_at_it(self):
        text = (ROOT / "agents" / "frontend-engineer.md").read_text(encoding="utf-8")
        self.assertIn("motion-vocabulary", text)


class TestSkillsResearchAndPresentOptions(unittest.TestCase):
    """Same audit as test_agents.py's TestResearchPresentOptionsBuild, applied
    to skills — capability-curator's research had governance without depth,
    ux-flow produced one flow as if there were one right answer, and
    motion-vocabulary was a glossary with no bridge to presentable options."""

    MARKERS = {
        "capability-curator": "How to research well, not just procedurally",
        "ux-flow": "Start with creative direction",
        "motion-vocabulary": "Motion profiles — from vocabulary to presentable options",
    }

    def test_every_skill_presents_options_before_building(self):
        for name, marker in self.MARKERS.items():
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn(marker, text, f"{name}/SKILL.md is missing its options-first section")


class TestCapabilityRegistryConfig(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "config" / "capability-registry.yaml"

    def test_shipped_default_exists(self):
        self.assertTrue(self.path.exists())

    def test_starts_empty(self):
        import yaml
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("entries"), [])

    def test_gets_installed_by_company_init(self):
        """Same mechanism as risk-triggers.yaml / budgets.yaml — no new code
        path, just a new file in config/ that cmd_init's glob already picks
        up. This pins that assumption rather than trusting it silently."""
        import subprocess
        import sys as _sys
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "t@t.co"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
            (repo / "README.md").write_text("x")
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
            subprocess.run([_sys.executable, str(ROOT / "tools" / "company" / "cli.py"), "init"],
                          cwd=repo, check=True, capture_output=True)
            self.assertTrue((repo / ".company" / "config" / "capability-registry.yaml").exists())


class TestCuratorAccessIsScoped(unittest.TestCase):
    """Judgment/knowledge roles need Skill+WebSearch to discover anything;
    narrowly-scoped Tier-2 implementers deliberately do not — they stay
    inside their task packet and escalate instead of freelancing web
    research mid-task, same reasoning as their existing 'no reason to touch
    backend code' scoping."""

    CURATOR_ELIGIBLE = ("company-pm", "cfo-advisor", "ciso-advisor", "cto-advisor",
                        "coo-advisor", "code-reviewer", "qa-engineer", "security-reviewer")
    NOT_ELIGIBLE = ("backend-engineer", "frontend-engineer")

    def test_curator_eligible_roles_have_skill_and_websearch(self):
        for name in self.CURATOR_ELIGIBLE:
            fm = frontmatter(ROOT / "agents" / f"{name}.md")
            tools = fm.get("tools", "")
            self.assertIn("Skill", tools, name)
            self.assertIn("WebSearch", tools, name)

    def test_implementers_stay_narrowly_scoped(self):
        for name in self.NOT_ELIGIBLE:
            fm = frontmatter(ROOT / "agents" / f"{name}.md")
            self.assertNotIn("WebSearch", fm.get("tools", ""), name)

    def test_curator_eligible_roles_reference_the_skill_in_their_prompt(self):
        for name in self.CURATOR_ELIGIBLE:
            text = (ROOT / "agents" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("capability-curator", text, name)


if __name__ == "__main__":
    unittest.main()
