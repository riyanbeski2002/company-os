"""Self-service skill authoring (donor review, 2026-10-19): a worker can
stage a new first-party skill draft (propose_skill.py) without it becoming
live, and only an explicit, separate promotion step (promote_skill.py) makes
it loadable and registers it — same "a proposal that could silently become
an adoption is not a proposal" discipline capability-curator already applies
to adopting external resources."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import promote_skill  # noqa: E402
import propose_skill  # noqa: E402

GOOD_DRAFT = """---
name: a-test-skill
description: A test skill with a real enough description to pass validation.
---

# A test skill

A body long enough to not look like a stub draft someone forgot to finish
writing before staging it.
"""


class TestProposeSkill(unittest.TestCase):
    def _draft(self, tmp: Path, text: str = GOOD_DRAFT, name: str = "SKILL.md") -> Path:
        p = tmp / name
        p.write_text(text)
        return p

    def test_a_good_draft_is_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            draft = self._draft(tmp)
            proposed = tmp / "proposed"
            dest, fm = propose_skill.stage("a-test-skill", draft, proposed_dir=proposed)
            self.assertTrue(dest.exists())
            self.assertEqual(fm["name"], "a-test-skill")

    def test_staging_never_touches_the_real_skills_or_registry(self):
        """stage() only writes under the proposed_dir it's given — it has no
        parameter that could reach skills/ or capability-registry.yaml."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            draft = self._draft(tmp)
            proposed = tmp / "proposed"
            propose_skill.stage("a-test-skill", draft, proposed_dir=proposed)
            self.assertFalse((ROOT / "skills" / "a-test-skill").exists())

    def test_rejects_a_file_not_named_skill_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            draft = self._draft(tmp, name="notes.md")
            with self.assertRaises(propose_skill.ProposalError):
                propose_skill.stage("x", draft, proposed_dir=tmp / "proposed")

    def test_rejects_missing_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            draft = self._draft(tmp, text="# just a heading, no frontmatter at all")
            with self.assertRaises(propose_skill.ProposalError):
                propose_skill.stage("x", draft, proposed_dir=tmp / "proposed")

    def test_rejects_frontmatter_missing_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            draft = self._draft(tmp, text="---\nname: x\n---\n\nbody text here, long enough.")
            with self.assertRaises(propose_skill.ProposalError):
                propose_skill.stage("x", draft, proposed_dir=tmp / "proposed")

    def test_rejects_a_stub_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            draft = self._draft(tmp, text="---\nname: x\ndescription: y\n---\n\ntiny.")
            with self.assertRaises(propose_skill.ProposalError):
                propose_skill.stage("x", draft, proposed_dir=tmp / "proposed")

    def test_refuses_to_overwrite_an_existing_staged_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            draft = self._draft(tmp)
            proposed = tmp / "proposed"
            propose_skill.stage("a-test-skill", draft, proposed_dir=proposed)
            with self.assertRaises(propose_skill.ProposalError):
                propose_skill.stage("a-test-skill", draft, proposed_dir=proposed)


class TestPromoteSkill(unittest.TestCase):
    def _staged(self, tmp: Path, slug: str = "a-test-skill") -> tuple[Path, Path]:
        proposed = tmp / "proposed"
        draft_dir = proposed / slug
        draft_dir.mkdir(parents=True)
        (draft_dir / "SKILL.md").write_text(GOOD_DRAFT)
        return proposed, draft_dir

    def _registry(self, tmp: Path, entries=None) -> Path:
        reg = tmp / "registry.yaml"
        if entries is None:
            entries = [{"id": "pre-existing", "type": "skill"}]
        # Hand-built, matching the REAL capability-registry.yaml's actual
        # indentation (`  - id: ...`, 2 spaces before the dash, each
        # following field indented 4) — yaml.dump's own default list style
        # indents dashes at the SAME column as the key, not +2, so
        # generating this fixture with yaml.dump would silently test
        # against a shape the real file doesn't use.
        lines = []
        for e in entries:
            items = list(e.items())
            first_k, first_v = items[0]
            lines.append(f"  - {first_k}: {first_v}")
            for k, v in items[1:]:
                lines.append(f"    {k}: {v}")
        body = "\n".join(lines)
        reg.write_text(
            "# a hand-written comment that must survive promotion untouched\n"
            + ("entries: []\n" if not body else "entries:\n" + body + "\n")
        )
        return reg

    def test_an_empty_registry_is_refused_not_corrupted(self):
        """Not a real scenario (the live registry always has entries), but
        the function must fail cleanly rather than write invalid YAML if it
        ever is."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proposed, _ = self._staged(tmp)
            skills = tmp / "skills"
            skills.mkdir()
            registry = self._registry(tmp, entries=[])
            before = registry.read_text()
            with self.assertRaises(promote_skill.PromotionError):
                promote_skill.promote("a-test-skill", "riyan", "T0", "2026-10-19",
                                       proposed_dir=proposed, skills_dir=skills, registry_path=registry)
            self.assertEqual(registry.read_text(), before, "must not write on a failed append")

    def test_promotion_moves_the_draft_and_registers_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proposed, _ = self._staged(tmp)
            skills = tmp / "skills"
            skills.mkdir()
            registry = self._registry(tmp)

            dest = promote_skill.promote(
                "a-test-skill", "riyan", "T0", "2026-10-19",
                proposed_dir=proposed, skills_dir=skills, registry_path=registry)

            self.assertTrue(dest.exists())
            self.assertFalse((proposed / "a-test-skill").exists())  # draft consumed

            import yaml
            data = yaml.safe_load(registry.read_text())
            entry = next(e for e in data["entries"] if e["id"] == "a-test-skill")
            self.assertEqual(entry["approved_by"], "riyan")
            self.assertEqual(entry["trust_tier"], "T0")
            self.assertEqual(entry["source"], "authored in this repo")

    def test_existing_registry_comments_and_entries_survive_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proposed, _ = self._staged(tmp)
            skills = tmp / "skills"
            skills.mkdir()
            registry = self._registry(tmp, entries=[{"id": "existing-one", "type": "skill"}])
            before = registry.read_text()

            promote_skill.promote("a-test-skill", "riyan", "T0", "2026-10-19",
                                   proposed_dir=proposed, skills_dir=skills, registry_path=registry)

            after = registry.read_text()
            self.assertTrue(after.startswith(before),
                             "promotion must APPEND, never rewrite existing text")
            self.assertIn("a hand-written comment", after)

    def test_refuses_a_slug_that_already_has_a_registry_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proposed, _ = self._staged(tmp)
            skills = tmp / "skills"
            skills.mkdir()
            registry = self._registry(tmp, entries=[{"id": "a-test-skill", "type": "skill"}])
            with self.assertRaises(promote_skill.PromotionError):
                promote_skill.promote("a-test-skill", "riyan", "T0", "2026-10-19",
                                       proposed_dir=proposed, skills_dir=skills, registry_path=registry)

    def test_refuses_a_slug_that_already_exists_under_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proposed, _ = self._staged(tmp)
            skills = tmp / "skills"
            (skills / "a-test-skill").mkdir(parents=True)
            registry = self._registry(tmp)
            with self.assertRaises(promote_skill.PromotionError):
                promote_skill.promote("a-test-skill", "riyan", "T0", "2026-10-19",
                                       proposed_dir=proposed, skills_dir=skills, registry_path=registry)

    def test_refuses_a_slug_with_no_staged_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            proposed = tmp / "proposed"
            proposed.mkdir()
            skills = tmp / "skills"
            skills.mkdir()
            registry = self._registry(tmp)
            with self.assertRaises(promote_skill.PromotionError):
                promote_skill.promote("never-staged", "riyan", "T0", "2026-10-19",
                                       proposed_dir=proposed, skills_dir=skills, registry_path=registry)


if __name__ == "__main__":
    unittest.main()
