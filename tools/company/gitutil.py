"""Shared git-diff helpers (efficiency addendum v1 + grouped gating).

One place for "hand a reviewer the actual patch, bounded, degrade gracefully"
— used by a single task's gate launch (cli.py) and a gate-group's combined
review (gategroup.py) alike, so the bound and the fallback behavior can't
drift between the two call sites.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Chars, not tokens (packet.py's own CHARS_PER_TOKEN=4) — deliberately well
# under the packet's 2000-token budget so embedding the patch can't itself
# trigger PacketTooLarge and block a gate launch. Past this, a gate gets the
# file list (git diff --stat) and reads the rest itself.
DIFF_PATCH_CHAR_CAP = 4000


def diff_patch_or_stat(worktree: Path, base: str, ref: str = "HEAD",
                       cap: int = DIFF_PATCH_CHAR_CAP) -> str | None:
    """The real `git diff` patch if it fits under `cap`, else `--stat` plus a
    pointer to run the diff directly. None if there's nothing to diff (no
    commits ahead of base) or on any git error — never raises, this is a cost
    optimization, not something a gate's correctness depends on.
    """
    try:
        count = subprocess.run(
            ["git", "-C", str(worktree), "rev-list", "--count", f"{base}..{ref}"],
            capture_output=True, text=True, timeout=10)
        if count.returncode != 0 or int(count.stdout.strip() or 0) == 0:
            return None
        sha = subprocess.run(["git", "-C", str(worktree), "rev-parse", ref],
                             capture_output=True, text=True, timeout=10)
        header = f"{ref} {sha.stdout.strip()}"

        patch = subprocess.run(["git", "-C", str(worktree), "diff", f"{base}..{ref}"],
                               capture_output=True, text=True, timeout=10)
        if patch.returncode == 0 and 0 < len(patch.stdout) <= cap:
            return f"{header}\n{patch.stdout.rstrip()}"

        stat = subprocess.run(["git", "-C", str(worktree), "diff", "--stat", f"{base}..{ref}"],
                              capture_output=True, text=True, timeout=10)
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
