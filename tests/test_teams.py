"""Team bundles (teams/README.md, `company team show`) — read-only and
advisory by design. These tests cover the validation/render logic; the real
teams/web-app.yaml is checked for stale references by its own smoke test
below, not re-derived here."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "company"))

import teams  # noqa: E402


class TestLoadTeam(unittest.TestCase):
    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(teams.TeamError):
                teams.load_team("nope", teams_dir=Path(tmp))

    def test_a_real_file_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "x.yaml").write_text("name: x\nroles: [a]\n")
            team = teams.load_team("x", teams_dir=d)
            self.assertEqual(team["name"], "x")

    def test_missing_name_field_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "x.yaml").write_text("roles: [a]\n")
            with self.assertRaises(teams.TeamError):
                teams.load_team("x", teams_dir=d)


class TestValidate(unittest.TestCase):
    def _agents_dir(self, tmp: Path, names) -> Path:
        d = tmp / "agents"
        d.mkdir()
        for n in names:
            (d / f"{n}.md").write_text("---\nname: x\n---\nbody")
        return d

    def _registry(self, tmp: Path, ids) -> Path:
        p = tmp / "registry.yaml"
        body = "\n".join(f"  - id: {i}\n    type: skill" for i in ids)
        p.write_text("entries:\n" + body + "\n" if ids else "entries: []\n")
        return p

    def test_no_problems_when_everything_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            agents = self._agents_dir(tmp, ["backend-engineer"])
            registry = self._registry(tmp, ["a-skill"])
            team = {"roles": ["backend-engineer"],
                    "suggested_skills": [{"id": "a-skill"}]}
            problems = teams.validate(team, agents_dir=agents, registry_path=registry)
            self.assertEqual(problems, {"missing_roles": [], "missing_skills": []})

    def test_a_role_with_no_agent_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            agents = self._agents_dir(tmp, [])
            registry = self._registry(tmp, [])
            team = {"roles": ["ghost-role"]}
            problems = teams.validate(team, agents_dir=agents, registry_path=registry)
            self.assertEqual(problems["missing_roles"], ["ghost-role"])

    def test_a_skill_with_no_registry_entry_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            agents = self._agents_dir(tmp, [])
            registry = self._registry(tmp, [])
            team = {"suggested_skills": [{"id": "ghost-skill"}]}
            problems = teams.validate(team, agents_dir=agents, registry_path=registry)
            self.assertEqual(problems["missing_skills"], ["ghost-skill"])

    def test_missing_registry_file_treats_everything_as_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            agents = self._agents_dir(tmp, [])
            team = {"suggested_skills": [{"id": "x"}]}
            problems = teams.validate(team, agents_dir=agents,
                                       registry_path=tmp / "no-such-file.yaml")
            self.assertEqual(problems["missing_skills"], ["x"])


class TestRender(unittest.TestCase):
    def test_render_includes_a_stale_reference_section_only_when_something_is_wrong(self):
        team = {"name": "x", "roles": ["a"], "suggested_skills": [], "seed_tasks": []}
        clean = teams.render(team, {"missing_roles": [], "missing_skills": []})
        self.assertNotIn("Stale references", clean)

        dirty = teams.render(team, {"missing_roles": ["a"], "missing_skills": []})
        self.assertIn("Stale references", dirty)
        self.assertIn("no agents/a.md", dirty)


class TestRealWebAppBundle(unittest.TestCase):
    """The actual shipped example — must have zero stale references in a
    real checkout, not just in a synthetic fixture."""

    def test_web_app_bundle_has_no_stale_references(self):
        team = teams.load_team("web-app")
        problems = teams.validate(team)
        self.assertEqual(problems, {"missing_roles": [], "missing_skills": []},
                          "teams/web-app.yaml references something that no longer exists")


if __name__ == "__main__":
    unittest.main()
