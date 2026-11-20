"""Shared git-diff helpers (efficiency addendum v1 + grouped gating).

One place for "hand a reviewer the actual patch, bounded, degrade gracefully"
— used by a single task's gate launch (cli.py) and a gate-group's combined
review (gategroup.py) alike, so the bound and the fallback behavior can't
drift between the two call sites.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Chars, not tokens (packet.py's own CHARS_PER_TOKEN=4) — deliberately well
# under the packet's 2000-token budget so embedding the patch can't itself
# trigger PacketTooLarge and block a gate launch. Past this, a gate gets the
# file list (git diff --stat) and reads the rest itself.
DIFF_PATCH_CHAR_CAP = 4000


# Inherited from a git hook (the pre-commit suite runs under one), these
# would redirect `git -C <repo>` at some other repository.
_GIT_SCRUB = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
              "GIT_PREFIX", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")


def git_trusted(repo: Path, *args, **kw) -> subprocess.CompletedProcess:
    """git in the PM's own process against the MAIN checkout only (ESC-014).
    Never `-C <worktree>`: a worker can rewrite its worktree's `.git` file to
    point at a gitdir whose config runs commands (core.fsmonitor, a diff or
    filter driver, core.pager) the moment git reads it, unsandboxed, here.
    Worktrees share the main repo's refs and objects, so any branch or SHA a
    worker produced is readable from the main checkout."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_SCRUB}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", "-C", str(repo), *args], env=env, **kw)


def git_worktree_trusted(repo: Path, wt: Path, *args, env: dict | None = None,
                         **kw) -> subprocess.CompletedProcess:
    """git on a linked worktree's index and files, in the PM's process
    (ESC-014). Some operations (status, a checkpoint commit) need the
    worktree itself, not just the branch. Both the gitdir and the common
    dir come from the MAIN checkout — `<common>/worktrees/<name>`, confirmed
    by its `gitdir` back-pointer — never from the worktree's `.git` file or
    the admin dir's `commondir` (GIT_COMMON_DIR overrides it). fsmonitor
    and hooks are off. Returns returncode 128 if no admin dir matches."""
    wt = Path(os.path.realpath(wt))
    common = git_trusted(repo, "rev-parse", "--path-format=absolute", "--git-common-dir",
                         capture_output=True, text=True)
    admin = Path(common.stdout.strip()) / "worktrees" / Path(wt).name
    try:
        back = (admin / "gitdir").read_text(encoding="utf-8").strip()
    except OSError:
        back = None
    if common.returncode != 0 or not back or \
            os.path.realpath(back) != str(wt / ".git"):
        return subprocess.CompletedProcess(args, 128, "", f"{wt} is not a worktree of {repo}")
    full_env = {k: v for k, v in os.environ.items() if k not in _GIT_SCRUB}
    full_env.update(GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                    GIT_COMMON_DIR=common.stdout.strip(), **(env or {}))
    return subprocess.run(
        ["git", f"--git-dir={admin}", f"--work-tree={wt}",
         "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=str(wt), env=full_env, **kw)


def diff_patch_or_stat(repo: Path, base: str, ref: str,
                       cap: int = DIFF_PATCH_CHAR_CAP) -> str | None:
    """The real `git diff` patch if it fits under `cap`, else `--stat` plus a
    pointer to run the diff directly. None if there's nothing to diff (no
    commits ahead of base) or on any git error — never raises, this is a cost
    optimization, not something a gate's correctness depends on.

    `repo` is the main checkout and `ref` the task's branch (never a
    worktree's HEAD): see git_trusted.
    """
    def git(*args):
        return git_trusted(repo, *args, capture_output=True, text=True, timeout=10)
    try:
        count = git("rev-list", "--count", f"{base}..{ref}")
        if count.returncode != 0 or int(count.stdout.strip() or 0) == 0:
            return None
        sha = git("rev-parse", "--verify", "--end-of-options", ref)
        header = f"{ref} {sha.stdout.strip()}"

        patch = git("diff", "--no-ext-diff", "--no-textconv", f"{base}..{ref}")
        if patch.returncode == 0 and 0 < len(patch.stdout) <= cap:
            return f"{header}\n{patch.stdout.rstrip()}"

        stat = git("diff", "--no-ext-diff", "--no-textconv", "--stat", f"{base}..{ref}")
        if stat.returncode != 0:
            return None
        return (f"{header}\n{stat.stdout.rstrip()}\n"
                f"(full patch too large to embed — run `git diff {base}..{ref}` "
                "in the worktree for the rest)")
    except Exception:
        return None


EVENT_LOG_REL = ".company/events/events.jsonl"


def event_log_git_state(repo: Path) -> dict:
    """Is the event log in git? Read-only: never edits .gitignore or the index.

    {"state": "tracked" | "ignored" | "untracked" | "unknown", "pattern": ...}
    `pattern` is check-ignore's `source:line:pattern` for "ignored", else None.
    Whether a repo tracks it is that repo's own .gitignore decision (company-os
    itself deliberately ignores its own); this only reports which it made.
    """
    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, timeout=10)
    try:
        if git("ls-files", "--error-unmatch", EVENT_LOG_REL).returncode == 0:
            return {"state": "tracked", "pattern": None}
        # The plain exit code decides; -v alone exits 0 on a matching
        # `!negation` too, which means NOT ignored.
        ignored = git("check-ignore", "-q", EVENT_LOG_REL).returncode
        if ignored == 1:
            return {"state": "untracked", "pattern": None}
        if ignored == 0:
            verbose = git("check-ignore", "-v", EVENT_LOG_REL).stdout
            return {"state": "ignored",
                    "pattern": verbose.split("\t", 1)[0].strip() or None}
    except Exception:
        pass
    return {"state": "unknown", "pattern": None}
