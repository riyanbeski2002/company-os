"""Onboarding a fresh repo end to end (D8's per-repo scaffolding step).

Two real defects found by hand while onboarding `cld-kit`, a repo with no
project and no test suite yet:

1. The documented chain — `company init && company detect --write &&
   company baseline && company doctor` — appeared in four places (the global
   CLAUDE.md, company-pm.md, install.sh twice) and could not actually complete
   on a brand-new repo. `company baseline` required `--project`, but a project
   only exists once `company plan` has written one, which only happens once
   the PM is already working. First-run baseline was structurally impossible.
2. There was no single command a human (or the PM) could run to do the whole
   chain and stop cleanly at the first real failure.

Fixed by: `--project` becomes optional on `baseline` (tagged "unassigned" when
none exists — the measurement doesn't need a project, only the event does),
and a new `company onboard` verb runs the four steps in order.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE.parent / "tools" / "company" / "cli.py"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


class TestOnboardFreshRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@t.co")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "package.json").write_text(
            '{"scripts":{"test":"node -e \\"process.exit(0)\\""}}')
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def _run(self, *args):
        return subprocess.run([sys.executable, str(CLI), *args],
                              cwd=self.repo, capture_output=True, text=True)

    def test_baseline_no_longer_requires_a_project(self):
        """A brand-new repo has zero .company/projects/*.json — baseline must
        still be recordable, or the documented onboarding order is a lie."""
        self._run("init")
        self._run("detect", "--write")
        result = self._run("baseline")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["exit_code"], 0)
        self.assertTrue(out["green"])

    def test_onboard_completes_on_a_fresh_repo(self):
        result = self._run("onboard")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.repo / ".company" / "events" / "events.jsonl").exists())

    def test_onboard_doctor_reports_ok_after_a_real_run(self):
        self._run("onboard")
        doctor = self._run("doctor")
        out = json.loads(doctor.stdout)
        self.assertTrue(out["ok"], out)
        baseline_check = next(c for c in out["checks"] if c["check"] == "baseline recorded")
        self.assertTrue(baseline_check["ok"])

    def test_doctor_flags_a_local_branch_behind_its_upstream(self):
        """Caught live 2026-08-17 on ht-workspace: local main was one merged PR
        behind origin/main, and the PM reasoned from stale history — a merged
        feature read as an unbuilt stub until `git pull --ff-only` caught it
        up. Doctor must surface this (non-fatal — a warning, not a blocker) so
        the PM fetches before staffing, on any repo, not just this one."""
        remote = Path(self.tmp.name) / "remote.git"
        git(self.repo, "init", "-q", "--bare", str(remote))
        git(self.repo, "remote", "add", "origin", str(remote))
        git(self.repo, "push", "-q", "-u", "origin", "HEAD:main")

        # Advance the remote past local without updating local, simulating a
        # merge that happened elsewhere.
        clone = Path(self.tmp.name) / "clone"
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)],
                       check=True, capture_output=True)
        (clone / "new-file.txt").write_text("later commit\n")
        git(clone, "add", "-A")
        git(clone, "commit", "-q", "-m", "a commit local never saw")
        git(clone, "push", "-q", "origin", "HEAD:main")

        self._run("init")
        self._run("detect", "--write")
        self._run("baseline")
        result = self._run("doctor")
        out = json.loads(result.stdout)
        self.assertTrue(out["ok"], out)  # warning, not a blocker
        remote_check = next(c for c in out["checks"] if c["check"] == "up to date with remote")
        self.assertFalse(remote_check["ok"])
        self.assertIn("behind", remote_check["detail"])

    def test_doctor_skips_remote_check_with_no_upstream(self):
        self._run("init")
        self._run("detect", "--write")
        self._run("baseline")
        result = self._run("doctor")
        out = json.loads(result.stdout)
        remote_check = next(c for c in out["checks"] if c["check"] == "up to date with remote")
        self.assertTrue(remote_check["ok"])
        self.assertIn("no upstream", remote_check["detail"])

    def test_detect_defaults_data_classification_to_internal(self):
        """Governs what capability-curator may put in an external research
        query (see that skill) — needs a sane default on every repo, not just
        ones where someone remembered to set it."""
        import yaml
        self._run("init")
        result = self._run("detect", "--write")
        out = json.loads(result.stdout)
        cfg = yaml.safe_load(Path(out["written"]).read_text())
        self.assertEqual(cfg["data_classification"], "INTERNAL")

    def test_detect_preserves_an_explicitly_set_classification(self):
        self._run("init")
        self._run("detect", "--write")
        cfg_path = self.repo / ".company" / "config" / "project.yaml"
        import yaml
        data = yaml.safe_load(cfg_path.read_text())
        data["data_classification"] = "SECRET"
        cfg_path.write_text(yaml.safe_dump(data))

        result = self._run("detect", "--write")
        out = json.loads(result.stdout)
        data = yaml.safe_load(Path(out["written"]).read_text())
        self.assertEqual(data["data_classification"], "SECRET")

    def test_onboard_stops_at_the_first_real_failure(self):
        """A repo with no test script at all can init/detect fine but has
        nothing for baseline to run — onboard must stop there, not paper over
        it by inventing a verify command."""
        no_verify_repo = Path(self.tmp.name) / "no_verify"
        no_verify_repo.mkdir()
        git(no_verify_repo, "init", "-q")
        git(no_verify_repo, "config", "user.email", "t@t.co")
        git(no_verify_repo, "config", "user.name", "t")
        (no_verify_repo / "README.md").write_text("# nothing to test")
        git(no_verify_repo, "add", "-A")
        git(no_verify_repo, "commit", "-q", "-m", "init")

        result = subprocess.run([sys.executable, str(CLI), "onboard"],
                                cwd=no_verify_repo, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stopped_at", result.stdout)


if __name__ == "__main__":
    unittest.main()
