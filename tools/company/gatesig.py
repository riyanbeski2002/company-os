"""Launcher-signed gate verdicts (ESC-002).

A gate verdict used to be a worker's own `company event ... REVIEW_PASSED`.
Anything a worker can run — or anything its children run, like the
implementer-authored tests QA executes — could therefore write one, and any
secret handed to the worker was handed to those children too. So the worker
holds nothing: it reports its verdict in its structured output, and after it
exits the launcher (worker.launch / launch_group, in the PM's process)
appends the verdict event itself, HMAC'd with a key under
`.company/secrets/`, which the worker sandbox cannot read
(worker.sandbox_settings denyRead, hooks/policy.py SECRET_GLOBS).

WORKER_STARTED is signed over (actor, role, its own seq, the tasks it
covers); each verdict over (task, gate event, actor, role, that
WORKER_STARTED's seq, verdict). taskstate.fold places a verdict against the
launch it names; check_done verifies both MACs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

VERDICTS = ("pass", "fail")


def key_path(company_root: Path) -> Path:
    return Path(company_root) / "secrets" / "gate.key"


def load_key(company_root: Path, create: bool = False) -> bytes | None:
    """The signing key, or None if it doesn't exist or can't be read (a
    sandboxed worker: nothing it folds will ever verify, which is the point).
    `create` makes it, 0600, on first use — only the launcher does that."""
    path = key_path(company_root)
    try:
        return bytes.fromhex(path.read_text(encoding="ascii").strip())
    except FileNotFoundError:
        if not create:
            return None
    except (OSError, ValueError):
        return None
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return load_key(company_root)  # a concurrent launcher won the race
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(secrets.token_hex(32))
    return load_key(company_root)


def _mac(key: bytes, *fields) -> str:
    msg = json.dumps(list(fields), separators=(",", ":"), sort_keys=True)
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()


def started_mac(key: bytes, actor: str, role: str, seq: int, tasks: list[str]) -> str:
    return _mac(key, "WORKER_STARTED", actor, role, seq, sorted(tasks))


def verdict_mac(key: bytes, task: str, event: str, actor: str, role: str,
                ws_seq: int, verdict: str) -> str:
    return _mac(key, "VERDICT", task, event, actor, role, ws_seq, verdict)


def sign_started(key: bytes, tasks: list[str]):
    """EventLog.append finalizer: the MAC covers the seq the log assigns."""
    def finalize(ev: dict) -> None:
        data = ev.setdefault("data", {})
        data["launch_mac"] = started_mac(key, ev["actor"], data["role"], ev["seq"], tasks)
    return finalize


def verify(key: bytes | None, task_id: str, event: str, actor: str | None,
           sig: dict | None) -> bool:
    """`sig` is what taskstate.fold recorded for a PASSED verdict."""
    if not key or not actor or not isinstance(sig, dict):
        return False
    try:
        want_ws = started_mac(key, actor, sig["role"], sig["ws_seq"], sig["ws_tasks"])
        want_v = verdict_mac(key, task_id, event, actor, sig["role"], sig["ws_seq"],
                             sig["verdict"])
        return (sig["verdict"] == "pass"
                and hmac.compare_digest(want_ws, str(sig["launch_mac"]))
                and hmac.compare_digest(want_v, str(sig["verdict_mac"])))
    except (KeyError, TypeError):
        return False


def structured_verdicts(output, task_ids: list[str]) -> dict[str, dict]:
    """task id -> {"verdict", "findings", "criteria_met"} from a gate's
    structured output.

    A solo launch may answer with the top-level `verdict`; a group must use
    `task_verdicts`, one entry per task. Anything else is no verdict
    (GATE_NO_VERDICT). Two entries for one task that disagree are a fail."""
    if not isinstance(output, dict):
        return {}
    out: dict[str, dict] = {}

    def put(tid, entry):
        verdict = entry.get("verdict")
        if tid not in task_ids or verdict not in VERDICTS:
            return
        lists = {k: entry.get(k) if isinstance(entry.get(k), list) else []
                 for k in ("findings", "criteria_met")}
        prev = out.get(tid)
        if prev:
            if prev["verdict"] != verdict:
                verdict = "fail"
            lists = {k: prev[k] + v for k, v in lists.items()}
        out[tid] = {"verdict": verdict, **lists}

    for entry in output.get("task_verdicts") or []:
        if isinstance(entry, dict):
            put(entry.get("task"), entry)
    if len(task_ids) == 1 and "verdict" in output:
        put(task_ids[0], output)
    return out
