"""Grouped gating (efficiency addendum v1, 2026-08-24): several tasks that
touch the same core get one gate launch instead of one each. Every test here
uses a real git repo — the merge behavior this depends on isn't something a
mock can stand in for.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import gategroup  # noqa: E402
import gitutil  # noqa: E402
import packet as packet_mod  # noqa: E402
import worker  # noqa: E402


def _git(repo, *args, cwd=None):
    r = subprocess.run(["git", "-C", str(cwd or repo), *args],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r


class GitRepoCase(unittest.TestCase):
    """A real git repo with `main` plus N task branches, each touching its
    own file — the non-conflicting case grouped gating exists for."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.company_root = Path(self.tmp.name) / ".company"
        _git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "base.txt").write_text("base\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-qm", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def _branch(self, name, filename, content):
        _git(self.repo, "checkout", "-qb", name, "main")
        (self.repo / filename).write_text(content)
        _git(self.repo, "add", "-A")
        _git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-qm", f"{name} work")
        _git(self.repo, "checkout", "-q", "main")

    def _task(self, tid, branch):
        return {"id": tid, "branch": branch, "project": "p"}


class TestBuildGroupReview(GitRepoCase):
    def test_merges_non_conflicting_branches_cleanly(self):
        self._branch("task/1", "design.py", "design\n")
        self._branch("task/2", "ui.py", "ui\n")
        tasks = [self._task("TASK-1", "task/1"), self._task("TASK-2", "task/2")]

        wt = gategroup.build_group_review(self.repo, self.company_root, "iam", tasks, "main")
        self.assertTrue((wt / "design.py").exists())
        self.assertTrue((wt / "ui.py").exists())

    def test_conflicting_branches_refuse_with_the_conflicting_task_named(self):
        self._branch("task/1", "same.py", "one\n")
        self._branch("task/2", "same.py", "two\n")
        tasks = [self._task("TASK-1", "task/1"), self._task("TASK-2", "task/2")]

        with self.assertRaises(gategroup.GroupMergeConflict) as ctx:
            gategroup.build_group_review(self.repo, self.company_root, "iam", tasks, "main")
        self.assertEqual(ctx.exception.task_id, "TASK-2")

    def test_rebuilding_a_group_review_starts_fresh_not_from_stale_state(self):
        """A group review worktree is scratch, never durable — rebuilding it
        after one task's branch changed must not carry over the old merge."""
        self._branch("task/1", "design.py", "v1\n")
        tasks = [self._task("TASK-1", "task/1")]
        wt = gategroup.build_group_review(self.repo, self.company_root, "iam", tasks, "main")
        self.assertEqual((wt / "design.py").read_text(), "v1\n")

        _git(self.repo, "checkout", "-q", "task/1")
        (self.repo / "design.py").write_text("v2\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t",
            "commit", "-qm", "task/1 v2")
        _git(self.repo, "checkout", "-q", "main")

        wt2 = gategroup.build_group_review(self.repo, self.company_root, "iam", tasks, "main")
        self.assertEqual((wt2 / "design.py").read_text(), "v2\n")

    def test_missing_branch_raises_clearly(self):
        with self.assertRaises(RuntimeError):
            gategroup.build_group_review(
                self.repo, self.company_root, "iam", [{"id": "TASK-1", "project": "p"}], "main")


class TestDiffPatchOrStat(GitRepoCase):
    def test_small_diff_embeds_the_real_patch(self):
        self._branch("task/1", "x.py", "def x(): pass\n")
        wt = gategroup.build_group_review(
            self.repo, self.company_root, "g", [self._task("TASK-1", "task/1")], "main")
        summary = gitutil.diff_patch_or_stat(wt, "main")
        self.assertIn("def x(): pass", summary)
        self.assertIn("HEAD ", summary)

    def test_large_diff_falls_back_to_stat(self):
        self._branch("task/1", "big.py", "x = 1\n" * 2000)
        wt = gategroup.build_group_review(
            self.repo, self.company_root, "g", [self._task("TASK-1", "task/1")], "main")
        summary = gitutil.diff_patch_or_stat(wt, "main", cap=200)
        self.assertNotIn("x = 1", summary)
        self.assertIn("too large to embed", summary)

    def test_no_commits_ahead_returns_none(self):
        wt = Path(self.tmp.name) / "plain"
        _git(self.repo, "worktree", "add", "--detach", str(wt), "main")
        self.assertIsNone(gitutil.diff_patch_or_stat(wt, "main"))

    def test_nonexistent_worktree_degrades_to_none_not_a_crash(self):
        self.assertIsNone(gitutil.diff_patch_or_stat(Path("/nonexistent/nowhere"), "main"))


class TestVerifyGroupVerdicts(unittest.TestCase):
    """Reuses worker.gave_no_verdict unchanged — same rule per task whether
    reviewed alone or as part of a group."""

    def test_all_tasks_verdicted_is_empty(self):
        events = [
            {"task": "TASK-1", "actor": "rev-1", "event": "REVIEW_PASSED"},
            {"task": "TASK-2", "actor": "rev-1", "event": "REVIEW_FAILED"},
        ]
        tasks = [{"id": "TASK-1"}, {"id": "TASK-2"}]
        missing = gategroup.verify_group_verdicts(events, tasks, "rev-1", "code-reviewer", worker)
        self.assertEqual(missing, [])

    def test_one_missing_task_is_named(self):
        events = [{"task": "TASK-1", "actor": "rev-1", "event": "REVIEW_PASSED"}]
        tasks = [{"id": "TASK-1"}, {"id": "TASK-2"}]
        missing = gategroup.verify_group_verdicts(events, tasks, "rev-1", "code-reviewer", worker)
        self.assertEqual(missing, ["TASK-2"])

    def test_a_sibling_being_reviewed_does_not_cover_another_task(self):
        """The core guarantee: reviewing TASK-1 does not silently satisfy
        TASK-2's own gate requirement just because they were in one launch."""
        events = [{"task": "TASK-1", "actor": "rev-1", "event": "REVIEW_PASSED"}]
        tasks = [{"id": "TASK-1"}, {"id": "TASK-2"}, {"id": "TASK-3"}]
        missing = gategroup.verify_group_verdicts(events, tasks, "rev-1", "code-reviewer", worker)
        self.assertEqual(missing, ["TASK-2", "TASK-3"])


class TestRenderGroup(unittest.TestCase):
    def test_lists_every_task_and_its_own_verdict_instruction(self):
        tasks = [
            {"id": "TASK-1", "title": "IAM design", "owned_globs": ["a.py"],
             "acceptance_criteria": ["designed"]},
            {"id": "TASK-2", "title": "IAM UI", "owned_globs": ["b.py"],
             "acceptance_criteria": ["wired"]},
        ]
        body = packet_mod.render_group(
            tasks, group_id="iam", why="ship IAM", diff_summary="HEAD abc\n+x",
            verify="pytest")
        for t in tasks:
            self.assertIn(t["id"], body)
            self.assertIn(f"company event {t['id']}", body)
        self.assertIn("independent judgment per task", body)

class TestPerRoleGroupWorktrees(GitRepoCase):
    """2026-09-09: the three gate roles used to share one `_gate-group-<id>`
    worktree AND branch, so they could only run one at a time — and launching
    two at once left the second dead on "cannot lock ref" and the first
    half-created (a directory with no .git, which `cd` resolves to the MAIN
    repo, whose task merge then targets the real working tree). Both the
    worktree/branch names and the worker claim are now per role.
    """

    def test_two_roles_get_independent_worktrees_for_the_same_group(self):
        self._branch("task/1", "design.py", "design\n")
        tasks = [self._task("TASK-1", "task/1")]

        rev = gategroup.build_group_review(
            self.repo, self.company_root, "iam", tasks, "main", role="code-reviewer")
        qa = gategroup.build_group_review(
            self.repo, self.company_root, "iam", tasks, "main", role="qa-engineer")

        # Distinct paths, and building the second did not destroy the first.
        self.assertNotEqual(rev, qa)
        self.assertTrue(rev.exists(), "building the qa worktree tore down the reviewer's")
        self.assertTrue(qa.exists())
        self.assertTrue((rev / "design.py").exists())
        self.assertTrue((qa / "design.py").exists())

        branches = _git(self.repo, "branch", "--list", "_gate-group-iam*").stdout
        self.assertIn("_gate-group-iam-code-reviewer", branches)
        self.assertIn("_gate-group-iam-qa-engineer", branches)

    def test_role_none_keeps_the_legacy_unsuffixed_name(self):
        legacy = gategroup.group_worktree_path(self.company_root, "iam")
        self.assertEqual(legacy.name, "_gate-group-iam")

    def test_group_claim_is_per_role_not_per_group(self):
        """Without this, the per-role worktrees still could not run at once:
        the second role was refused by a claim keyed on group_id alone."""
        self.assertTrue(worker.claim_task(
            self.company_root, "gate-group-iam-code-reviewer", "rev-1"))
        # A different role on the SAME group must still be able to claim.
        self.assertTrue(worker.claim_task(
            self.company_root, "gate-group-iam-qa-engineer", "qa-1"))
        # The same role twice must not.
        self.assertFalse(worker.claim_task(
            self.company_root, "gate-group-iam-code-reviewer", "rev-2"))


class TestPacketBudget(GitRepoCase):
    def test_over_budget_raises_same_as_a_solo_packet(self):
        tasks = [{"id": "TASK-1", "title": "t", "acceptance_criteria": ["a" * 9000]}]
        with self.assertRaises(packet_mod.PacketTooLarge):
            packet_mod.render_group(tasks, group_id="g", why="w", diff_summary=None,
                                    verify="pytest")


if __name__ == "__main__":
    unittest.main()
