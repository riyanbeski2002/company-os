"""worktrees.py — disposable task worktrees, cleaned up safely (directive V2
§13-19, docs/HARNESS-AGNOSTIC-MIGRATION.md §4.3 invariants W1-W8).

Every test uses a real git repo: what `git worktree remove` refuses, what
`prune` touches, and what a checkpoint ref actually retains are git's
behavior, not something a mock can stand in for.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import worker  # noqa: E402
import worktrees  # noqa: E402
from eventlog import EventLog, make_event  # noqa: E402

ID = ["-c", "user.email=t@t", "-c", "user.name=t"]


def _git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check:
        assert r.returncode == 0, r.stderr
    return r


def _no_holders():
    return set()


class WorktreeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self.tmp.name))
        self.repo = base / "repo"
        self.repo.mkdir()
        self.root = self.repo / ".company"
        _git(self.repo, "init", "-q", "-b", "main")
        (self.repo / ".gitignore").write_text(".company/\nnode_modules/\n")
        (self.repo / "base.txt").write_text("base\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, *ID, "commit", "-qm", "init")
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    # --- helpers -----------------------------------------------------------
    def _task(self, tid, status=None, project="p"):
        self.log.append(make_event(event="TASK_CREATED", actor="pm", project=project,
                                   task=tid, data={"title": tid}))
        if status:
            self._status(tid, status)
        return {"id": tid, "project": project, "title": tid}

    def _status(self, tid, status):
        self.log.append(make_event(event="STATUS_CHANGED", actor="pm", project="p",
                                   task=tid, data={"to": status}))

    def _staffed(self, tid, status=None):
        task = self._task(tid)
        wt, branch = worker.ensure_worktree(self.repo, self.root, task)
        if status:
            self._status(tid, status)
        return wt, branch

    def _commit_in(self, wt, name="work.py", content="x = 1\n"):
        (wt / name).write_text(content)
        _git(wt, "add", "-A")
        _git(wt, *ID, "commit", "-qm", f"work in {wt.name}")
        return _git(wt, "rev-parse", "HEAD").stdout.strip()

    def _cleanup(self, **kw):
        kw.setdefault("holders", _no_holders)
        return worktrees.cleanup(self.repo, self.root, **kw)

    def _registered(self):
        return [w["path"] for w in worktrees.list_worktrees(self.repo)]

    def _events(self, name):
        return [e for e in self.log.read() if e["event"] == name]


class TestEnsureWorktreeRecordsOwnership(WorktreeCase):
    def test_creation_appends_worktree_created(self):
        wt, branch = self._staffed("TASK-1")
        created = self._events("WORKTREE_CREATED")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["data"]["path"], str(wt))
        self.assertEqual(created[0]["data"]["branch"], branch)
        self.assertEqual(created[0]["data"]["task"], "TASK-1")

    def test_reattaches_an_existing_branch_after_cleanup(self):
        wt, branch = self._staffed("TASK-1")
        sha = self._commit_in(wt)
        self._status("TASK-1", "MERGED")
        self._cleanup()
        self.assertFalse(wt.exists())

        task = {"id": "TASK-1", "project": "p", "title": "TASK-1"}
        wt2, branch2 = worker.ensure_worktree(self.repo, self.root, task)
        self.assertEqual(branch2, branch)
        self.assertEqual(_git(wt2, "rev-parse", "HEAD").stdout.strip(), sha)

    def test_refuses_a_preexisting_directory_that_is_not_a_worktree(self):
        # The catastrophic case gategroup.py's history describes: a dir with
        # no .git, which `cd` resolves to the MAIN repo.
        task = self._task("TASK-1")
        (self.root / "worktrees" / "TASK-1").mkdir(parents=True)
        with self.assertRaises(worker.WorkerError):
            worker.ensure_worktree(self.repo, self.root, task)


class TestCompletedWorktreesAreRemoved(WorktreeCase):
    def test_merged_task_worktree_is_removed_and_branch_kept(self):
        wt, branch = self._staffed("TASK-1")
        sha = self._commit_in(wt)
        self._status("TASK-1", "MERGED")

        report = self._cleanup()

        self.assertFalse(wt.exists())
        self.assertNotIn(str(wt), self._registered())
        self.assertEqual(_git(self.repo, "rev-parse", branch).stdout.strip(), sha,
                         "the branch (the commit reference) must survive cleanup")
        self.assertEqual([r["path"] for r in report["removed"]], [str(wt)])
        removed = self._events("WORKTREE_REMOVED")
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["evidence"]["commit"], sha)

    def test_ignored_dependency_dirs_go_with_it_without_force(self):
        wt, _ = self._staffed("TASK-1")
        (wt / "node_modules" / "pkg").mkdir(parents=True)
        (wt / "node_modules" / "pkg" / "index.js").write_text("x" * 5000)
        self._status("TASK-1", "DONE")
        report = self._cleanup()
        self.assertFalse(wt.exists())
        self.assertGreaterEqual(report["bytes_reclaimed"], 5000)

    def test_abandoned_task_with_unmerged_commits_keeps_them_on_its_branch(self):
        wt, branch = self._staffed("TASK-1")
        sha = self._commit_in(wt)
        self._status("TASK-1", "ABANDONED")
        self._cleanup()
        self.assertFalse(wt.exists())
        self.assertEqual(_git(self.repo, "rev-parse", branch).stdout.strip(), sha)

    def test_provisioned_skill_symlinks_do_not_count_as_dirty(self):
        target = self.repo / "ext-skill"
        target.mkdir()
        (self.repo / "skills").mkdir()
        (self.repo / "skills" / "s1").symlink_to(target)
        wt, _ = self._staffed("TASK-1")
        self.assertTrue((wt / "skills" / "s1").is_symlink())
        self._status("TASK-1", "DONE")
        report = self._cleanup()
        self.assertFalse(wt.exists())
        self.assertEqual(report["removed"][0].get("checkpoint"), None)


class TestActiveAndUnsafeWorktreesAreProtected(WorktreeCase):
    def test_in_progress_task_is_kept(self):
        wt, _ = self._staffed("TASK-1", status="IN_PROGRESS")
        report = self._cleanup()
        self.assertTrue(wt.exists())
        self.assertEqual(report["removed"], [])
        self.assertEqual([k["path"] for k in report["kept"]], [str(wt)])

    def test_failed_task_is_kept_for_retry(self):
        wt, _ = self._staffed("TASK-1", status="FAILED")
        self._cleanup()
        self.assertTrue(wt.exists())

    def test_live_claim_blocks_removal(self):
        wt, _ = self._staffed("TASK-1", status="DONE")
        self.assertTrue(worker.claim_task(self.root, "TASK-1", "w1"))
        report = self._cleanup()
        self.assertTrue(wt.exists())
        self.assertEqual([b["path"] for b in report["blocked"]], [str(wt)])

    def test_a_process_with_its_cwd_inside_blocks_removal(self):
        wt, _ = self._staffed("TASK-1", status="DONE")
        report = self._cleanup(holders=lambda: {str(wt / "src")})
        self.assertTrue(wt.exists())
        self.assertIn("cwd", " ".join(report["blocked"][0]["reasons"]))

    def test_human_worktree_under_the_managed_root_is_never_touched(self):
        human = self.root / "worktrees" / "my-experiment"
        human.parent.mkdir(parents=True, exist_ok=True)
        _git(self.repo, "worktree", "add", "-q", str(human), "-b", "mine", "main")
        report = self._cleanup()
        self.assertTrue(human.exists())
        self.assertEqual(report["removed"], [])

    def test_worktree_outside_the_managed_root_is_never_touched_even_if_recorded(self):
        outside = self.repo.parent / "elsewhere"
        _git(self.repo, "worktree", "add", "-q", str(outside), "-b", "x", "main")
        self._task("TASK-9", status="DONE")
        # A forged/mistaken ownership record must not extend cleanup's reach.
        self.log.append(make_event(event="WORKTREE_CREATED", actor="company", project="p",
                                   data={"path": str(outside), "branch": "x",
                                         "task": "TASK-9", "base": "main"}))
        self._cleanup()
        self.assertTrue(outside.exists())

    def test_main_worktree_is_never_touched(self):
        self._cleanup()
        self.assertTrue((self.repo / "base.txt").exists())
        self.assertIn(str(self.repo), self._registered())

    def test_unregistered_directory_is_reported_not_deleted(self):
        stray = self.root / "worktrees" / "TASK-404"
        stray.mkdir(parents=True)
        (stray / "notes.txt").write_text("someone's work\n")
        report = self._cleanup()
        self.assertTrue((stray / "notes.txt").exists())
        self.assertIn(str(stray), [b["path"] for b in report["blocked"]])


class TestCrashRecovery(WorktreeCase):
    def test_dirty_terminal_worktree_is_checkpointed_before_removal(self):
        wt, branch = self._staffed("TASK-1")
        head = self._commit_in(wt)
        (wt / "work.py").write_text("x = 2  # uncommitted\n")
        (wt / "new_untracked.py").write_text("y = 1\n")
        self._status("TASK-1", "ABANDONED")

        report = self._cleanup()

        self.assertFalse(wt.exists())
        ref = report["removed"][0]["checkpoint"]
        self.assertTrue(ref.startswith("refs/company/checkpoints/"))
        self.assertEqual(_git(self.repo, "show", f"{ref}:work.py").stdout,
                         "x = 2  # uncommitted\n")
        self.assertEqual(_git(self.repo, "show", f"{ref}:new_untracked.py").stdout, "y = 1\n")
        self.assertEqual(_git(self.repo, "rev-parse", f"{ref}^").stdout.strip(), head)
        # The task branch itself is untouched — the checkpoint is beside it.
        self.assertEqual(_git(self.repo, "rev-parse", branch).stdout.strip(), head)
        self.assertEqual(self._events("WORKTREE_REMOVED")[0]["data"]["checkpoint"], ref)

    def test_dry_run_changes_nothing(self):
        wt, _ = self._staffed("TASK-1", status="MERGED")
        (wt / "dirty.txt").write_text("d\n")
        report = self._cleanup(dry_run=True)
        self.assertTrue(wt.exists())
        self.assertTrue((wt / "dirty.txt").exists())
        self.assertEqual(self._events("WORKTREE_REMOVED"), [])
        self.assertEqual([r["path"] for r in report["removed"]], [str(wt)])
        self.assertTrue(report["dry_run"])
        refs = _git(self.repo, "for-each-ref", "refs/company/").stdout
        self.assertEqual(refs, "")


class TestReconciliation(WorktreeCase):
    def test_orphaned_registration_is_pruned(self):
        wt, _ = self._staffed("TASK-1", status="IN_PROGRESS")
        import shutil
        shutil.rmtree(wt)  # simulating a crash/external delete, not cleanup itself
        report = self._cleanup()
        self.assertTrue(report["pruned"])
        self.assertNotIn(str(wt), self._registered())

    def test_prune_is_skipped_when_a_missing_worktree_is_not_ours(self):
        outside = self.repo.parent / "usb-drive-wt"
        _git(self.repo, "worktree", "add", "-q", str(outside), "-b", "usb", "main")
        import shutil
        shutil.rmtree(outside)
        report = self._cleanup()
        self.assertFalse(report["pruned"])
        porcelain = _git(self.repo, "worktree", "list", "--porcelain").stdout
        self.assertIn(str(outside), porcelain)

    def test_repeated_cleanup_is_idempotent(self):
        self._staffed("TASK-1", status="MERGED")
        wt2, _ = self._staffed("TASK-2", status="DONE")
        self.assertTrue(worker.claim_task(self.root, "TASK-2", "w2"))
        self._cleanup()
        second = self._cleanup()
        self.assertEqual(second["removed"], [])
        self.assertEqual(len(self._events("WORKTREE_REMOVED")), 1)
        # A still-blocked worktree is reported every run but logged once.
        self.assertEqual(len(second["blocked"]), 1)
        self.assertEqual(len(self._events("WORKTREE_CLEANUP_BLOCKED")), 1)

    def test_task_filter_limits_the_sweep(self):
        wt1, _ = self._staffed("TASK-1", status="MERGED")
        wt2, _ = self._staffed("TASK-2", status="MERGED")
        self._cleanup(task="TASK-1")
        self.assertFalse(wt1.exists())
        self.assertTrue(wt2.exists())

    def test_legacy_task_worktree_without_a_created_event_is_still_owned(self):
        # Worktrees staffed before WORKTREE_CREATED existed: owned when the
        # directory is named for a known task and sits on that task's branch.
        self._task("TASK-1")
        self.log.append(make_event(event="TASK_ASSIGNED", actor="pm", project="p",
                                   task="TASK-1", data={"owner": "w", "branch": "task/1-legacy"}))
        wt = self.root / "worktrees" / "TASK-1"
        wt.parent.mkdir(parents=True, exist_ok=True)
        _git(self.repo, "worktree", "add", "-q", str(wt), "-b", "task/1-legacy", "main")
        self._status("TASK-1", "MERGED")
        self._cleanup()
        self.assertFalse(wt.exists())


class TestScratchWorktrees(WorktreeCase):
    def test_gate_group_scratch_is_removed_and_its_branch_kept(self):
        import gategroup
        wt1, b1 = self._staffed("TASK-1")
        self._commit_in(wt1)
        task = {"id": "TASK-1", "branch": b1, "project": "p"}
        scratch = gategroup.build_group_review(self.repo, self.root, "g", [task], "main",
                                               role="code-reviewer")
        report = worktrees.cleanup_path(self.repo, self.root, scratch,
                                        trigger="gate_verdict", holders=_no_holders)
        self.assertFalse(scratch.exists())
        self.assertEqual(len(report["removed"]), 1)
        _git(self.repo, "rev-parse", "--verify", "_gate-group-g-code-reviewer")

    def test_rebuilding_a_dirty_scratch_never_loses_its_content(self):
        import gategroup
        wt1, b1 = self._staffed("TASK-1")
        self._commit_in(wt1)
        task = {"id": "TASK-1", "branch": b1, "project": "p"}
        scratch = gategroup.build_group_review(self.repo, self.root, "g", [task], "main")
        (scratch / "reviewer-notes.md").write_text("finding\n")

        gategroup.build_group_review(self.repo, self.root, "g", [task], "main")

        refs = _git(self.repo, "for-each-ref", "--format=%(refname)",
                    "refs/company/checkpoints/").stdout.split()
        self.assertEqual(len(refs), 1)
        self.assertEqual(_git(self.repo, "show", f"{refs[0]}:reviewer-notes.md").stdout,
                         "finding\n")

    def test_integration_worktree_is_permanent(self):
        import integrate
        wt = integrate.ensure_integration_worktree(self.repo, self.root)
        report = self._cleanup()
        self.assertTrue(wt.exists())
        self.assertEqual(report["removed"], [])


class TestCli(WorktreeCase):
    """The lifecycle trigger and the reconciliation verb, end to end."""

    CLI = HERE.parent / "tools" / "company" / "cli.py"

    def _run(self, *args):
        import json
        r = subprocess.run([sys.executable, str(self.CLI), "--root", str(self.root), *args],
                           capture_output=True, text=True)
        return r.returncode, json.loads(r.stdout[r.stdout.find("{"):])

    def test_advancing_to_abandoned_removes_the_worktree(self):
        wt, _ = self._staffed("TASK-1")
        code, out = self._run("task", "advance", "TASK-1", "--to", "ABANDONED")
        self.assertEqual(code, 0, out)
        self.assertFalse(wt.exists())
        self.assertEqual([r["path"] for r in out["worktree_cleanup"]["removed"]], [str(wt)])

    def test_advancing_to_a_non_terminal_state_leaves_it(self):
        wt, _ = self._staffed("TASK-1")
        code, out = self._run("task", "advance", "TASK-1", "--to", "IN_PROGRESS")
        self.assertEqual(code, 0, out)
        self.assertTrue(wt.exists())
        self.assertNotIn("worktree_cleanup", out)

    def test_cleanup_dry_run_then_real(self):
        wt, _ = self._staffed("TASK-1", status="MERGED")
        code, out = self._run("cleanup", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertTrue(out["dry_run"])
        self.assertTrue(wt.exists())
        code, out = self._run("cleanup")
        self.assertEqual(code, 0, out)
        self.assertFalse(wt.exists())
        self.assertEqual(len(out["removed"]), 1)


if __name__ == "__main__":
    unittest.main()
