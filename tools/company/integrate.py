"""Integration and merge (§6).

Never merge on a worker's assertion. A task branch is rebased onto the
integration branch in a dedicated worktree, the full suite runs there, and the
merge happens only if that run is green. The suite result recorded is the one
observed here, not the one the worker reported.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from eventlog import EventLog, make_event
import pathrules

INTEGRATION_BRANCH = "integration"

# Pre-merge worktree-conflict check (2026-10-21, ECC donation). ECC's own
# session daemon polls per-session file-activity live and pauses one side
# the moment two concurrent sessions touch the same path; company-os has no
# daemon, so the adapted version is a check at the one moment that already
# exists for it -- just before a task's branch is actually merged -- rather
# than something continuously watching while workers run. A git merge
# conflict (handled separately above, by the real `git merge` attempt) only
# tells you AFTER the fact that two branches touched the same lines; this
# tells a human BEFORE attempting the merge that another task still running
# right now owns an overlapping subtree, so they can judge whether to wait.
_CONCURRENT_STATUSES = {"IN_PROGRESS", "REVIEW", "QA", "SECURITY_REVIEW"}


def detect_concurrent_glob_conflicts(tasks: dict, target_id: str) -> list[dict]:
    """Other currently-active tasks whose owned_globs overlap `target_id`'s.

    `tasks` is a fold()-shaped dict of task_id -> task view. Pure function,
    no I/O -- the caller already has the task list from taskstate.fold().
    """
    target = tasks.get(target_id)
    if not target:
        return []
    conflicts = []
    seen_pairs = set()
    for other_id, other in tasks.items():
        if other_id == target_id or other.get("status") not in _CONCURRENT_STATUSES:
            continue
        for ours in target.get("owned_globs") or ():
            for theirs in other.get("owned_globs") or ():
                if pathrules.globs_overlap(ours, theirs):
                    key = (other_id, ours, theirs)
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        conflicts.append({"task": other_id, "status": other.get("status"),
                                          "ours": ours, "theirs": theirs})
    return conflicts


def _git(repo: Path, *args, cwd: Path | None = None):
    return subprocess.run(
        ["git", "-C", str(cwd or repo), *args], capture_output=True, text=True)


def ensure_integration_worktree(repo: Path, company_root: Path, base: str = "main"):
    wt = Path(company_root) / "worktrees" / "_integration"
    if wt.exists():
        return wt

    exists = _git(repo, "rev-parse", "--verify", INTEGRATION_BRANCH).returncode == 0
    args = ["worktree", "add", str(wt)]
    args += [INTEGRATION_BRANCH] if exists else ["-b", INTEGRATION_BRANCH, base]
    r = _git(repo, *args)
    if r.returncode != 0:
        raise RuntimeError(f"could not create the integration worktree: {r.stderr.strip()}")
    return wt


def integrate(repo: Path, company_root: Path, task: dict, test_command: str,
              actor: str = "integration", baseline: dict | None = None) -> dict:
    """Rebase one task branch into integration and merge it if the suite is green."""
    log = EventLog(company_root)
    branch = task.get("branch")
    if not branch:
        raise RuntimeError(f"task {task['id']} has no branch to integrate")

    wt = ensure_integration_worktree(repo, company_root)
    result = {"task": task["id"], "branch": branch, "worktree": str(wt)}

    merge = _git(repo, "merge", "--no-ff", "--no-edit",
                 "-m", f"Integrate {task['id']}: {task.get('title', '')}",
                 branch, cwd=wt)
    if merge.returncode != 0:
        _git(repo, "merge", "--abort", cwd=wt)
        log.append(make_event(
            event="TASK_BLOCKED", actor=actor, project=task["project"], task=task["id"],
            data={"stage": "integration", "reason": "merge conflict",
                  "detail": merge.stderr.strip()[:500]}))
        return {**result, "merged": False, "reason": "merge conflict",
                "detail": merge.stderr.strip()[:500]}

    # The suite that decides is the one that runs here, after the merge. Uses
    # baseline.measure() rather than a bare subprocess.run(..., shell=True,
    # timeout=...) call — that pattern only kills the shell process on
    # timeout, not any children it spawned, which is the exact runaway-
    # process incident CTO reproduced against `company baseline`. Same bug
    # class, same fix: process-group tracking and kill.
    import baseline as baseline_mod
    measured = baseline_mod.measure(wt, test_command)
    log_path = Path(company_root) / "state" / "workers" / actor
    log_path.mkdir(parents=True, exist_ok=True)
    out_file = log_path / f"integration-{task['id']}.log"
    out_file.write_text(measured["output_tail"], encoding="utf-8")

    failures = measured["failures"]
    log.append(make_event(
        event="TEST_RUN", actor=actor, project=task["project"], task=task["id"],
        data={"cmd": test_command, "exit_code": measured["exit_code"], "failures": failures,
              "stage": "integration"},
        evidence={"log": str(out_file)}))

    # On a repo that was already red, "green" means "added no failures". The
    # comparison is against the recorded baseline, never against a worker's claim.
    acceptable, why = baseline_mod.compare(
        baseline, {"exit_code": measured["exit_code"], "failures": failures})

    if not acceptable:
        # Undo the merge: integration must never carry a regression.
        _git(repo, "reset", "--hard", "HEAD~1", cwd=wt)
        log.append(make_event(
            event="TASK_BLOCKED", actor=actor, project=task["project"], task=task["id"],
            data={"stage": "integration", "reason": why, "merge_reverted": True}))
        return {**result, "merged": False, "reason": why, "test_log": str(out_file)}

    sha = _git(repo, "rev-parse", "HEAD", cwd=wt).stdout.strip()
    log.append(make_event(
        event="MERGED", actor=actor, project=task["project"], task=task["id"],
        data={"into": INTEGRATION_BRANCH, "test_exit_code": measured["exit_code"],
              "failures": failures, "accepted_because": why},
        evidence={"commit": sha}))

    return {**result, "merged": True, "commit": sha,
            "test_exit_code": measured["exit_code"], "accepted_because": why,
            "test_log": str(out_file)}
