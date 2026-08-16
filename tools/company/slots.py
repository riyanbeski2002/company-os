"""Concurrency budget (D7).

The cap lives on disk, not in a supervisor's memory, so independently launched
`company run` calls respect it too. Exceeding the cap **queues** rather than
spawns — a budget you can silently exceed is not a budget.

Slots are pid files. A slot whose process is gone is reclaimed automatically,
so a `kill -9`'d worker cannot leak its slot forever.
"""

from __future__ import annotations

import os
import time
from pathlib import Path


class SlotTimeout(RuntimeError):
    pass


def _slot_dir(company_root: Path) -> Path:
    d = Path(company_root) / "state" / "slots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _alive(pid: int) -> bool:
    """True only for a process that is actually still working.

    `os.kill(pid, 0)` succeeds on a zombie — a process that has exited but whose
    parent has not reaped it. A zombie holds no resources and is doing no work,
    so counting it against the cap would deadlock the queue behind a corpse.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # exists, owned by another user
    return not _is_zombie(pid)


def _is_zombie(pid: int) -> bool:
    import subprocess
    try:
        r = subprocess.run(["ps", "-o", "state=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False         # can't tell: assume alive, fail safe
    return r.stdout.strip().startswith("Z")


def reap(company_root: Path) -> int:
    """Drop slots whose process is gone. Returns the live count."""
    live = 0
    for slot in _slot_dir(company_root).glob("*.pid"):
        try:
            pid = int(slot.read_text().strip())
        except (ValueError, OSError):
            slot.unlink(missing_ok=True)
            continue
        if _alive(pid):
            live += 1
        else:
            slot.unlink(missing_ok=True)
    return live


def acquire(company_root: Path, actor: str, cap: int, timeout: float = 1800.0,
            poll: float = 2.0) -> tuple[Path, float]:
    """Block until a slot is free, then claim it.

    Returns (slot_path, seconds_queued). Raises SlotTimeout if the wait exceeds
    `timeout` — a queue that waits forever is a hang, not a budget.
    """
    started = time.monotonic()
    slot = _slot_dir(company_root) / f"{actor}.pid"
    while True:
        if reap(company_root) < cap:
            slot.write_text(str(os.getpid()))
            return slot, round(time.monotonic() - started, 1)
        waited = time.monotonic() - started
        if waited >= timeout:
            raise SlotTimeout(
                f"waited {int(waited)}s for a worker slot (cap {cap}) and gave up"
            )
        time.sleep(poll)


def release(slot: Path) -> None:
    try:
        Path(slot).unlink(missing_ok=True)
    except OSError:
        pass


def live_count(company_root: Path) -> int:
    return reap(company_root)
