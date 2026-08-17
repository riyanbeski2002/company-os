"""Session presence — who is doing what, right now, in this checkout.

Not an event. What a top-level session is currently doing changes every few
minutes and is worthless once the session ends — event-sourcing it would
bloat the one append-only log this system's replay correctness depends on
for no lasting benefit. It lives in `.company/state/sessions/`, the same
ephemeral-state pattern worker.py already uses for `state/workers/*/pid` to
answer "is anyone already working here" without asking anyone to self-report
honestly.

Built after two Claude Code sessions ran company-pm-style work against this
same repo checkout at once with zero visibility into each other — one fixed
a bug in cli.py, the other fixed a bug in cli.py, purely by luck they didn't
collide. `company session list` is what lets the second session see the
first *before* staffing overlapping work, instead of discovering the overlap
in `git diff` after the fact. See agents/company-pm.md, "Coordinating with
other sessions."
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from eventlog import canonical, utcnow

STALE_AFTER_S = 1800  # 30 minutes with no update. Long enough that a normal
# PM turn — which can run many minutes between announces — never falsely
# reads as gone; short enough that a listing from an hour ago doesn't get
# trusted as still true. Stale entries are flagged, not hidden: a session
# that died without calling `done` is exactly the case a peer needs to see.


def _dir(company_root: Path) -> Path:
    return Path(company_root) / "state" / "sessions"


def announce(company_root: Path, actor: str | None, doing: str,
            globs: list[str] | None = None) -> dict:
    """Record, or update, what `actor` is doing right now."""
    if not actor:
        raise ValueError(
            "a session needs an actor identity to announce itself — pass "
            "--actor explicitly, or run where $CLAUDE_CODE_SESSION_ID is set"
        )
    if not doing or not doing.strip():
        raise ValueError(
            "--doing is required — a session with no stated purpose is "
            "invisible to the peer session it's about to collide with"
        )
    d = _dir(company_root) / actor
    d.mkdir(parents=True, exist_ok=True)
    record = {"actor": actor, "doing": doing.strip(), "globs": globs or [],
              "updated_at": utcnow()}
    (d / "doing.json").write_text(canonical(record), encoding="utf-8")
    return record


def done(company_root: Path, actor: str | None) -> bool:
    """Clear `actor`'s entry. Returns False if it had none — always safe to
    call, e.g. as a session's last act before it ends."""
    if not actor:
        return False
    d = _dir(company_root) / actor
    p = d / "doing.json"
    if not p.exists():
        return False
    p.unlink()
    try:
        d.rmdir()
    except OSError:
        pass  # not empty for some other reason — not this function's job to force
    return True


def list_active(company_root: Path) -> list[dict]:
    """Every announced session, most-recently-updated first. Staleness is
    flagged on the record rather than filtered out — a stale entry usually
    means a session ended without calling `done`, and that is signal a peer
    should see, not noise to hide."""
    out = []
    d = _dir(company_root)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*/doing.json")):
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        age = time.time() - p.stat().st_mtime
        record["age_s"] = round(age)
        record["stale"] = age > STALE_AFTER_S
        out.append(record)
    out.sort(key=lambda r: r["age_s"])
    return out


def ping_via_tmux(target: str, message: str, actor: str | None) -> str:
    """Push a tagged message directly into a peer's tmux pane. **Fallback
    only** — use `SendMessage` first; this exists for the gap while a
    session hasn't picked up that tool yet (grants only apply to a session
    started after the file changed, see agents/company-pm.md) or while the
    `SendMessage` hook is erroring machine-wide, which happened live on
    finos, 17 Aug.

    Bakes in the fix for a real race hit doing this by hand that day: one
    `tmux send-keys -t <target> "text" Enter` call frequently leaves the
    text sitting unsent in the pane's input box — the Enter arrives before
    the paste registers. Two separate calls, with a pause between them,
    don't race. Also tags the message with the sender, the same job
    `SendMessage` does natively, so the receiving pane can tell it's an
    inbound peer message and not its own reasoning or the human typing.
    """
    import shutil
    import subprocess
    import time as _time

    if not shutil.which("tmux"):
        raise RuntimeError(
            "tmux not found — this fallback only works when the peer is a "
            "tmux pane; if it isn't, there is no fallback and the message "
            "cannot be delivered this way"
        )
    tagged = f"[from {actor or 'unknown'}] {message}"
    r = subprocess.run(["tmux", "send-keys", "-t", target, tagged],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"tmux send-keys failed: {r.stderr.strip()}")
    _time.sleep(0.4)  # the race: without this, Enter below can arrive before
    # the line above finishes registering in the pane's input box.
    r = subprocess.run(["tmux", "send-keys", "-t", target, "Enter"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"tmux send-keys (Enter) failed: {r.stderr.strip()}")
    return tagged
