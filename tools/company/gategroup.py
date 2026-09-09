"""Grouped gating (efficiency addendum v1, 2026-08-24): several tasks that
touch the same core get ONE gate launch instead of one per task — Riyan's
example: IAM design, IAM UI, and onboarding all reviewed together, not 3
separate review passes.

This does not change the Evidence Rule or its per-task bookkeeping. Every
task in the group still needs its OWN REVIEW_PASSED/QA_PASSED/
SECURITY_REVIEW_PASSED event, authored by someone other than its owner,
exactly as `taskstate.check_done()` already requires — nothing there changes.
What changes is orchestration: one launch reviews a combined diff and is
instructed to emit one verdict per task, and `cli.py`'s `cmd_gate_group`
verifies every task actually got one before treating the group as reviewed.

The combined diff is built the same way `integrate.py` already merges one
task branch into a shared worktree — just extended to N branches into a
throwaway review worktree instead of one branch into the permanent
`integration` branch. This worktree is scratch: rebuilt fresh on every call,
never treated as durable state the way a task's own worktree is.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class GroupMergeConflict(RuntimeError):
    def __init__(self, task_id: str, detail: str):
        super().__init__(f"merging {task_id} into the group review worktree conflicted: {detail}")
        self.task_id = task_id
        self.detail = detail


def _git(repo: Path, *args, cwd: Path | None = None):
    return subprocess.run(
        ["git", "-C", str(cwd or repo), *args], capture_output=True, text=True)


def group_worktree_path(company_root: Path, group_id: str,
                        role: str | None = None) -> Path:
    # Per-role, not per-group (2026-09-09): every gate role used to share one
    # `_gate-group-<id>` worktree+branch, so review/qa/security could only run
    # one at a time. Launching two concurrently left the second dead on
    # "cannot lock ref" AND the first half-created — a dir with no .git that
    # `cd` resolves to the MAIN repo, whose task merge then tries to overwrite
    # the real working tree. Measured live: three 5-minute gates took ~30
    # minutes as a forced sequence. Suffixing the role makes them independent.
    suffix = f"-{role}" if role else ""
    return Path(company_root) / "worktrees" / f"_gate-group-{group_id}{suffix}"


def build_group_review(repo: Path, company_root: Path, group_id: str,
                       tasks: list[dict], base: str,
                       role: str | None = None) -> Path:
    """Rebuild a throwaway worktree at `base` and merge every task's branch
    into it, in the given order. Raises GroupMergeConflict on the first
    branch that doesn't merge cleanly — a group that doesn't even merge
    together isn't reviewable as one unit, full stop, no partial review.

    Always rebuilt from scratch (never reused across calls): a group review
    that starts from a previous attempt's merge state risks reviewing stale
    or already-superseded code after a FAILED verdict sent a task back for
    rework. This worktree is scratch, not durable state.
    """
    wt = group_worktree_path(company_root, group_id, role)
    if wt.exists():
        _git(repo, "worktree", "remove", "--force", str(wt))
        shutil.rmtree(wt, ignore_errors=True)

    branch = f"_gate-group-{group_id}{f'-{role}' if role else ''}"
    _git(repo, "branch", "-D", branch)  # ignore failure if it doesn't exist

    wt.parent.mkdir(parents=True, exist_ok=True)
    r = _git(repo, "worktree", "add", str(wt), "-b", branch, base)
    if r.returncode != 0:
        raise RuntimeError(f"could not create the group review worktree: {r.stderr.strip()}")

    for task in tasks:
        branch_to_merge = task.get("branch")
        if not branch_to_merge:
            raise RuntimeError(f"task {task['id']} has no branch to merge into the group review")
        merge = _git(repo, "merge", "--no-ff", "--no-edit",
                     "-m", f"Group review {group_id}: merge {task['id']}",
                     branch_to_merge, cwd=wt)
        if merge.returncode != 0:
            _git(repo, "merge", "--abort", cwd=wt)
            raise GroupMergeConflict(task["id"], merge.stderr.strip()[:500])

    return wt


def verify_group_verdicts(events: list[dict], tasks: list[dict], actor: str,
                          role: str, worker_mod) -> list[str]:
    """Task ids in the group that did NOT get their own verdict event from
    `actor` for `role`'s gate. Empty means every task was actually reviewed.
    Reuses `worker.gave_no_verdict` unchanged — same rule, per task, whether
    it was reviewed alone or as part of a group.
    """
    missing = []
    for task in tasks:
        if worker_mod.gave_no_verdict(events, task["id"], actor, role):
            missing.append(task["id"])
    return missing
