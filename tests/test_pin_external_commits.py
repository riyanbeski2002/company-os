"""tools/pin_external_commits.py — closing the moving-branch gap
(tasks/lessons.md, 2026-10-19): pin a cloned capability-registry entry to its
current commit, as text insertion that can never touch the file's
hand-written comments or any other entry's fields."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import pin_external_commits as pec  # noqa: E402

REGISTRY_TEXT = """# a hand-written comment that must survive untouched
entries:
  - id: has-local-path
    type: tool
    purpose: "x"
    trust_tier: T2
    source: "https://example.com/x"
    local_path: "external/has-local-path"
    license: MIT
    approved_by: riyan
    approved_at: "2026-01-01"
    checked_at: "2026-01-01"
  - id: no-local-path
    type: skill
    purpose: "native, nothing to pin"
    trust_tier: T0
    source: "authored in this repo"
    license: original
    approved_by: riyan
    approved_at: "2026-01-01"
"""


def _git_repo_with_commit(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "f.txt").write_text("x")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, check=True)
    return repo


class TestCurrentSha(unittest.TestCase):
    def test_a_real_repo_returns_its_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _git_repo_with_commit(Path(tmp))
            sha = pec.current_sha(repo)
            self.assertIsNotNone(sha)
            self.assertEqual(len(sha), 40)

    def test_non_git_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(pec.current_sha(Path(tmp)))


class TestEntrySpans(unittest.TestCase):
    def test_finds_both_entries_by_id(self):
        spans = pec._entry_spans(REGISTRY_TEXT)
        ids = [s[0] for s in spans]
        self.assertEqual(ids, ["has-local-path", "no-local-path"])

    def test_spans_cover_only_their_own_entry(self):
        spans = pec._entry_spans(REGISTRY_TEXT)
        first_block = REGISTRY_TEXT[spans[0][1]:spans[0][2]]
        self.assertIn("has-local-path", first_block)
        self.assertNotIn("no-local-path", first_block)


class TestPlanAndApply(unittest.TestCase):
    def test_plan_only_includes_entries_with_local_path_and_a_real_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            external = tmp / "external"
            external.mkdir()
            repo = _git_repo_with_commit(external)
            (external / "has-local-path").symlink_to(repo)  # same effect as a real clone there

            shas = pec.plan(REGISTRY_TEXT, {"has-local-path"}, external_dir=external)
            self.assertEqual(set(shas), {"has-local-path"})

    def test_plan_skips_an_already_pinned_entry(self):
        pinned_text = REGISTRY_TEXT.replace(
            'local_path: "external/has-local-path"',
            'local_path: "external/has-local-path"\n    pinned_commit: "deadbeef"',
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            external = tmp / "external"
            external.mkdir()
            repo = _git_repo_with_commit(external)
            (external / "has-local-path").symlink_to(repo)

            shas = pec.plan(pinned_text, {"has-local-path"}, external_dir=external)
            self.assertEqual(shas, {})

    def test_apply_inserts_pinned_commit_right_after_local_path(self):
        new_text = pec.apply(REGISTRY_TEXT, {"has-local-path": "abc123"})
        self.assertIn('pinned_commit: "abc123"', new_text)
        # The unrelated entry and the leading comment must survive untouched.
        self.assertIn("# a hand-written comment that must survive untouched", new_text)
        self.assertIn("no-local-path", new_text)

    def test_apply_result_still_parses_as_valid_yaml_with_the_same_entry_count(self):
        import yaml
        new_text = pec.apply(REGISTRY_TEXT, {"has-local-path": "abc123"})
        data = yaml.safe_load(new_text)
        self.assertEqual(len(data["entries"]), 2)
        pinned = next(e for e in data["entries"] if e["id"] == "has-local-path")
        self.assertEqual(pinned["pinned_commit"], "abc123")

    def test_apply_never_touches_an_entry_with_no_sha_for_it(self):
        new_text = pec.apply(REGISTRY_TEXT, {})
        self.assertEqual(new_text, REGISTRY_TEXT)


if __name__ == "__main__":
    unittest.main()
