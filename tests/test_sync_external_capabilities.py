"""tools/sync_external_capabilities.py's pin-aware sync_one (tasks/
lessons.md, 2026-10-19): a `pinned_commit` entry must be checked out exactly,
never `git pull`-ed past, while an unpinned entry keeps today's original
branch-tracking behavior unchanged."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import sync_external_capabilities as sec  # noqa: E402


def _run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def _bare_remote_with_two_commits(tmp: Path) -> tuple[Path, str, str]:
    """A bare 'origin' repo with commit A then commit B on its default
    branch — returns (remote_path, sha_a, sha_b)."""
    work = tmp / "work"
    work.mkdir()
    _run(["git", "init", "-q"], work)
    _run(["git", "config", "user.email", "t@example.com"], work)
    _run(["git", "config", "user.name", "t"], work)
    (work / "f.txt").write_text("v1")
    _run(["git", "add", "f.txt"], work)
    _run(["git", "commit", "-q", "-m", "A"], work)
    sha_a = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work,
                            capture_output=True, text=True).stdout.strip()

    (work / "f.txt").write_text("v2 -- an upstream change nobody reviewed yet")
    _run(["git", "add", "f.txt"], work)
    _run(["git", "commit", "-q", "-m", "B"], work)
    sha_b = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work,
                            capture_output=True, text=True).stdout.strip()
    return work, sha_a, sha_b


class TestSyncOnePinning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.remote, self.sha_a, self.sha_b = _bare_remote_with_two_commits(self.tmp_path)

    def _cloned_at(self, sha: str) -> Path:
        """A real clone, left ON its tracking branch but reset back to
        `sha` — same as a clone from a while ago, not a detached-HEAD
        checkout (which `git pull` can't act on at all)."""
        dest = self.tmp_path / "external" / "x"
        dest.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "-q", str(self.remote), str(dest)], self.tmp_path)
        _run(["git", "reset", "-q", "--hard", sha], dest)
        return dest

    def test_pinned_entry_stays_on_its_pin_even_when_the_remote_moved_on(self):
        dest = self._cloned_at(self.sha_a)
        sec.EXTERNAL_DIR = self.tmp_path / "external"  # sync_one resolves EXTERNAL_DIR / id_
        entry = {"id": "x", "source": str(self.remote), "pinned_commit": self.sha_a}

        ok = sec.sync_one(entry, check_only=False)

        self.assertTrue(ok)
        head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                               capture_output=True, text=True).stdout.strip()
        self.assertEqual(head, self.sha_a, "a pin must never be pulled past")

    def test_unpinned_entry_still_tracks_the_branch_head(self):
        """Backward compatible: today's original behavior for an entry with
        no pinned_commit yet."""
        dest = self._cloned_at(self.sha_a)
        sec.EXTERNAL_DIR = self.tmp_path / "external"
        entry = {"id": "x", "source": str(self.remote)}

        ok = sec.sync_one(entry, check_only=False)

        self.assertTrue(ok)
        head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                               capture_output=True, text=True).stdout.strip()
        self.assertEqual(head, self.sha_b, "unpinned entries still pull to the branch tip")


if __name__ == "__main__":
    unittest.main()
