"""Content-derived trust validation + drift detection (donor review,
2026-10-19): a registry entry's trust_tier is a human judgment made once at
ingest time; detect_content_shape/source_commit are computed fresh every
build so a tier that stops matching what's actually there, or a fork that
moved since it was last reviewed, is visible rather than silently indexed."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_capability_index as bci  # noqa: E402


class TestDetectContentShape(unittest.TestCase):
    def test_markdown_only_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "SKILL.md").write_text("# a skill\njust prose")
            (d / "README.md").write_text("more prose")
            self.assertEqual(bci.detect_content_shape(d), "markdown_only")

    def test_a_shell_script_is_scripts_executables(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "SKILL.md").write_text("# a skill")
            (d / "setup.sh").write_text("#!/bin/sh\necho hi")
            self.assertEqual(bci.detect_content_shape(d), "scripts_executables")

    def test_an_executable_bit_with_no_recognized_suffix_still_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            exe = d / "run-me"
            exe.write_text("#!/bin/sh\necho hi")
            exe.chmod(0o755)
            self.assertEqual(bci.detect_content_shape(d), "scripts_executables")

    def test_git_internals_are_not_scanned(self):
        """A bare .git/hooks/*.sample is executable-suffixed noise, not
        content the unit itself ships."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "SKILL.md").write_text("# a skill")
            git_hooks = d / ".git" / "hooks"
            git_hooks.mkdir(parents=True)
            (git_hooks / "pre-commit.sample").write_text("#!/bin/sh")
            self.assertEqual(bci.detect_content_shape(d), "markdown_only")

    def test_missing_directory_is_unknown_not_a_crash(self):
        self.assertEqual(bci.detect_content_shape(Path("/no/such/dir")), "unknown")


class TestSourceCommit(unittest.TestCase):
    def test_a_real_git_repo_returns_its_head_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=d, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
            (d / "f.txt").write_text("x")
            subprocess.run(["git", "add", "f.txt"], cwd=d, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=d, check=True)
            sha = bci.source_commit(d)
            self.assertIsNotNone(sha)
            self.assertEqual(len(sha), 40)

    def test_non_git_directory_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(bci.source_commit(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
