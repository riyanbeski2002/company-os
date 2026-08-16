"""tmux viewing gallery (§13) — a window, not a database.

The PM cannot open terminal windows. The CEO can. So the PM computes how many
panes the current run needs and asks, rather than sitting blocked or silently
doing without.

Nothing here is on the machine communication path. Every pane is a `tail -f`.
Kill the tmux server mid-run and the loop is unaffected — the event log does not
care whether anyone is watching.
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
