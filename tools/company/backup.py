"""Event-log backups (`company backup`).

events.jsonl is the only authoritative state Company OS has — every task
view, gate verdict and cost figure is a fold over it — and before this there
was no copy of it anywhere. A backup is one file copy taken under the same
lock append() holds (EventLog.snapshot), so it always ends on a whole event.

Copies go OUTSIDE the repo, to ~/.company-backups/<repo-name>-<hash>/: a
backup inside the working tree dies with the checkout it is meant to survive.
Several repos are onboarded on one machine, often with the same directory
name in different places, so the folder is keyed by the repo's name (for a
human to find it) plus a short hash of its resolved path (so two `app/`s
never share one).

Restoring is deliberately not a command: copy the chosen backup over
.company/events/events.jsonl by hand, then `company rebuild --verify`. Which
backup to trust after an incident is the operator's call, not a guess this
module should make.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from eventlog import EventLog, check_integrity


def default_dir(company_root: Path) -> Path:
    repo = Path(company_root).resolve().parent
    tag = hashlib.sha256(str(repo).encode()).hexdigest()[:8]
    return Path.home() / ".company-backups" / f"{repo.name}-{tag}"


def latest(dest: Path) -> Path | None:
    # Timestamped names sort chronologically; in-flight temp files start
    # with "." and never match.
    found = sorted(Path(dest).glob("events-*.jsonl")) if Path(dest).is_dir() else []
    return found[-1] if found else None


def run(company_root: Path, dest: Path | None = None) -> dict:
    """Snapshot the live log into `dest` (default: default_dir). Safe to run
    any time and as often as you like: a log unchanged since the newest
    backup writes nothing new."""
    log = EventLog(company_root)
    if not log.path.is_file():
        raise FileNotFoundError(f"no event log at {log.path} — nothing to back up")
    dest = Path(dest) if dest else default_dir(company_root)
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)

    prior = latest(dest)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = dest / f"events-{stamp}.jsonl"
    written = log.snapshot(target, unless_same_as=prior)
    kept = target if written else prior

    # Integrity of what was actually saved: a backup of an already-damaged
    # log still preserves every good line, but whoever restores from it
    # needs to know it isn't clean.
    report = check_integrity(kept)
    return {
        "backup": str(kept),
        "written": written,
        "dest": str(dest),
        "bytes": kept.stat().st_size,
        "events": report["events"],
        "intact": report["problem_count"] == 0,
        "problems": report["problems"],
    }
