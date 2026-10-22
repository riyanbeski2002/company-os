"""Is events.jsonl in git? Reported by init and doctor, never enforced.

Whether an onboarded repo's event log reached its remote used to be an
accident of that repo's own pre-existing .gitignore: a blanket `.company/`
ignore meant zero backup anywhere, with nothing to say so. The default going
forward is to track it — but only by telling the operator. company-os's own
.gitignore ignores its own log on purpose, so nothing here may ever rewrite or
negate an existing rule: every case asserts .gitignore is byte-identical
across `company init` and `company doctor`.

`.company/worktrees/` and `.company/state/` are pre-seeded because init has
always ensured those two lines; seeding them isolates this change's effect.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE.parent / "tools" / "company" / "cli.py"
LOG = ".company/events/events.jsonl"
INIT_LINES = ".company/worktrees/\n.company/state/\n"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


class EventLogGitCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t.co")
        git(self.repo, "config", "user.name", "t")
        # An empty global excludes file, so the operator's own can't leak in.
        git(self.repo, "config", "core.excludesFile", str(Path(self.tmp.name) / "none"))
        (self.repo / "package.json").write_text(
            '{"scripts":{"test":"node -e \\"process.exit(0)\\""}}')

    def _commit_with_gitignore(self, extra=""):
        (self.repo / ".gitignore").write_text(INIT_LINES + extra)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        return (self.repo / ".gitignore").read_bytes()

    def _run(self, *args):
        # --root, not cwd alone: an inherited COMPANY_ROOT beats cwd in
        # company_root() — see test_onboard.
        return subprocess.run([sys.executable, str(CLI), "--root",
                               str(self.repo / ".company"), *args],
                              cwd=self.repo, capture_output=True, text=True)

    def _init(self):
        result = self._run("init")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout), result.stderr

    def _doctor_detail(self):
        result = self._run("doctor")
        out = json.loads(result.stdout)
        check = next(c for c in out["checks"] if c["check"] == "event log tracked in git")
        self.assertTrue(check["ok"], check)  # informational, never a failure
        self.assertNotIn("event log tracked in git", " ".join(out["blocking"]))
        return check["detail"]


class TestInit(EventLogGitCase):
    def test_fresh_repo_is_not_ignored_and_gets_the_add_reminder(self):
        before = self._commit_with_gitignore()
        out, note = self._init()
        self.assertEqual(out["event_log_git"], {"state": "untracked", "pattern": None})
        self.assertIn("is not ignored", note)
        self.assertIn(f"git add {LOG}", note)
        self.assertIn("never commits on your behalf", note)
        self.assertEqual((self.repo / ".gitignore").read_bytes(), before)

    def test_broad_company_ignore_is_named_in_an_actionable_note(self):
        before = self._commit_with_gitignore(".company/\n")
        out, note = self._init()
        self.assertEqual(out["event_log_git"],
                         {"state": "ignored", "pattern": ".gitignore:3:.company/"})
        self.assertIn("matched by: .gitignore:3:.company/", note)
        self.assertIn(f"!{LOG}", note)
        self.assertIn("parent directory", note)
        self.assertIn("Nothing was changed", note)
        self.assertEqual((self.repo / ".gitignore").read_bytes(), before)

    def test_explicit_file_ignore_like_company_os_own_is_left_alone(self):
        """company-os's own .gitignore lists the log by exact path, on purpose."""
        before = self._commit_with_gitignore(f"{LOG}\n")
        out, note = self._init()
        self.assertEqual(out["event_log_git"]["state"], "ignored")
        self.assertIn(f".gitignore:3:{LOG}", note)
        self.assertEqual((self.repo / ".gitignore").read_bytes(), before)
        # Idempotent re-run: still advisory, still no edit.
        self._init()
        self.assertEqual((self.repo / ".gitignore").read_bytes(), before)

    def test_a_working_negation_is_reported_as_not_ignored(self):
        """`check-ignore -v` exits 0 on a matching `!` rule too; that must not
        be misread as ignored."""
        before = self._commit_with_gitignore(
            f".company/*\n!.company/events/\n.company/events/*\n!{LOG}\n")
        out, _ = self._init()
        self.assertEqual(out["event_log_git"]["state"], "untracked")
        self.assertEqual((self.repo / ".gitignore").read_bytes(), before)

    def test_no_gitignore_gains_no_event_log_line(self):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        self._init()
        lines = [l for l in (self.repo / ".gitignore").read_text().splitlines() if l]
        self.assertEqual(lines, INIT_LINES.split())

    def test_init_does_not_commit_or_stage_anything(self):
        self._commit_with_gitignore()
        head = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout
        self._init()
        self.assertEqual(subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"],
                                        capture_output=True, text=True).stdout, head)
        staged = subprocess.run(["git", "-C", str(self.repo), "diff", "--cached", "--name-only"],
                                capture_output=True, text=True).stdout
        self.assertEqual(staged, "")


class TestDoctor(EventLogGitCase):
    def test_reports_tracked(self):
        before = self._commit_with_gitignore()
        self._init()
        git(self.repo, "add", LOG)
        git(self.repo, "commit", "-q", "-m", "track the event log")
        self.assertTrue(self._doctor_detail().startswith("tracked"))
        self.assertEqual((self.repo / ".gitignore").read_bytes(), before)

    def test_tracked_wins_over_a_later_ignore_rule(self):
        """git keeps tracking a file an ignore rule matches after it was added."""
        self._commit_with_gitignore()
        self._init()
        git(self.repo, "add", LOG)
        git(self.repo, "commit", "-q", "-m", "track the event log")
        (self.repo / ".gitignore").write_text(INIT_LINES + ".company/\n")
        before = (self.repo / ".gitignore").read_bytes()
        self.assertTrue(self._doctor_detail().startswith("tracked"))
        self.assertEqual((self.repo / ".gitignore").read_bytes(), before)

    def test_reports_ignored_with_the_pattern(self):
        before = self._commit_with_gitignore(".company/\n")
        self._init()
        detail = self._doctor_detail()
        self.assertTrue(detail.startswith("not tracked (ignored"), detail)
        self.assertIn(".gitignore:3:.company/", detail)
        self.assertEqual((self.repo / ".gitignore").read_bytes(), before)

    def test_reports_never_added(self):
        before = self._commit_with_gitignore()
        self._init()
        detail = self._doctor_detail()
        self.assertTrue(detail.startswith("not tracked (never added"), detail)
        self.assertEqual((self.repo / ".gitignore").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
