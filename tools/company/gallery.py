"""tmux viewing gallery (§13) — a window, not a database.

The PM cannot open terminal windows. The CEO can. So the PM computes how many
panes the current run needs and asks, rather than sitting blocked or silently
doing without.

Nothing here is on the machine communication path. Every pane is a `tail -f`.
Kill the tmux server mid-run and the loop is unaffected — the event log does not
care whether anyone is watching.

This file still never sends keys into a pane, by design — nothing here is on
the machine communication path. Pane control for messaging a peer does exist
now, but lives in `sessions.py` (`company session ping`), not here, and it is
explicitly a fallback: prefer `SendMessage` (reaches an interactive
tmux-hosted session the same as a spawned subagent — see agents/company-pm.md,
"Coordinating with other sessions") and reach for `session ping` only when
that tool isn't bound yet or its hook is erroring. `session ping` bakes in a
real race a PM hit hand-rolling this on finos, 17 Aug: one
`tmux send-keys -t <pane> "text" Enter` call frequently leaves the text
sitting unsent — the Enter arrives before the paste registers. Two separate
calls, with a pause between, don't race.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SESSION = "company"


def panes_needed(tasks: list[dict], stalls: dict | None = None) -> list[dict]:
    """One pane per Tier-2 task that has work worth watching, plus a status pane."""
    panes = [{
        "name": "status",
        "purpose": "company status, refreshed every 5s",
        "command": "while true; do clear; company status; sleep 5; done",
    }]
    for task in sorted(tasks, key=lambda t: t["id"]):
        if task.get("tier") != 2:
            continue
        if task.get("status") in ("DONE", "MERGED", "ABANDONED"):
            continue
        owner = task.get("owner")
        if not owner:
            continue
        panes.append({
            "name": task["id"],
            "purpose": f"{task['id']} — {task.get('title', '')} ({owner})",
            "command": f"tail -f .company/state/workers/{owner}/stderr.log",
        })
    return panes


def plan(company_root: Path, tasks: list[dict]) -> dict:
    panes = panes_needed(tasks)
    repo = Path(company_root).parent
    return {
        "sessions": 1,
        "session_name": SESSION,
        "panes": len(panes),
        "layout": panes,
        "tmux_installed": shutil.which("tmux") is not None,
        "run": f"cd {repo} && company gallery --open",
        "note": ("The gallery is display only. Killing the tmux server does not "
                 "affect any worker or any state."),
    }


def script(company_root: Path, tasks: list[dict]) -> str:
    """Emit a shell script that builds the layout. Idempotent by session name."""
    panes = panes_needed(tasks)
    repo = Path(company_root).parent
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"cd {repo}",
        f'tmux kill-session -t {SESSION} 2>/dev/null || true',
        f'tmux new-session -d -s {SESSION} -n gallery {_q(panes[0]["command"])}',
    ]
    for pane in panes[1:]:
        lines.append(f'tmux split-window -t {SESSION} {_q(pane["command"])}')
        lines.append(f'tmux select-layout -t {SESSION} tiled')
    lines.append(f'tmux attach-session -t {SESSION}')
    return "\n".join(lines) + "\n"


def _q(command: str) -> str:
    return "'" + command.replace("'", "'\\''") + "'"
