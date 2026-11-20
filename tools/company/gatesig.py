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
covers, and each task's branch SHA as the launcher read it); each verdict
over (task, gate event, actor, role, that WORKER_STARTED's seq, verdict,
that SHA). taskstate.fold places a verdict against the launch it names;
check_done verifies both MACs and that every gate judged the same SHA, and
integrate merges exactly that SHA — never the branch tip, which anything
the gate ran (a conftest) could have committed to.
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

    Its existence IS the signing mode: once it exists, only signed PM_EVENTS
    count (trusted_events). `create` makes it on first use — only the PM's
    own process (the launcher, or any `company` command outside a worker) —
    after carrying the log over (migrate). Raises OSError if it can't."""
    path = key_path(company_root)
    try:
        key = bytes.fromhex(path.read_text(encoding="ascii").strip())
        try:
            ignore_secrets_dir(path.parent)  # repos keyed before the ignore existed
        except OSError:
            pass
        return key
    except FileNotFoundError:
        if not create:
            return None
    except (OSError, ValueError):
        return None
    return _create(company_root)


def ignore_secrets_dir(secrets_dir: Path) -> None:
    """A `.gitignore` of `*` inside the secrets dir: git never sees the key,
    whatever the repo's own ignore rules (some repos track .company/)."""
    gi = secrets_dir / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")


def _create(company_root: Path) -> bytes:
    from eventlog import EventLog
    path = key_path(company_root)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    ignore_secrets_dir(path.parent)
    log = EventLog(company_root)
    with log._locked():  # one creator; no event lands between snapshot and key
        if path.exists():
            return load_key(company_root)
        key = secrets.token_bytes(32)
        # Write the key file BEFORE migrating: a process that can't create
        # it (a worker's sandbox) must fail here, before any signed snapshot
        # is appended — otherwise it leaves a signed log with no key, which
        # the PM then refuses forever (security review, sr/denied.py).
        tmp = path.with_name(f".{path.name}.{os.getpid()}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="ascii") as fh:
                fh.write(key.hex())
                fh.flush()
                os.fsync(fh.fileno())
            migrate(log, key)
            os.link(tmp, path)  # never replaces a key
        finally:
            os.unlink(tmp)
    return load_key(company_root)


def migrate(log, key: bytes) -> int:
    """Carry an unsigned log over to signing, under the caller's lock: fold
    it the old, unkeyed way and append, PM-signed, a TASK_SNAPSHOT of every
    task (definition, status, merged), the latest baseline per project, and
    a resolution for every already-resolved escalation. After this the keyed
    fold reads only signed PM events and these snapshots. Run only while
    creating the key, so once; a crash before the key is in place leaves
    snapshots signed with a key nobody has, and the refusal below.
    Returns how many events it appended.

    Refuses (ValueError) a log that already carries signatures: the key it
    was signed with is gone, and carrying that log over unkeyed would bless
    whatever a worker appended since. Restore .company/secrets/gate.key."""
    import escalations
    import taskstate
    from eventlog import make_event
    events = log.read()
    if any((ev.get("data") or {}).get(k) for ev in events for k in ("pm_mac", "launch_mac")):
        raise ValueError(
            f"{log.path} is already signed but {key_path(log.root)} is missing — "
            f"refusing to re-sign it unverified. Restore the key from backup.")
    out = []
    for tid, t in sorted(taskstate.fold(events).items()):
        data = {f: t[f] for f in taskstate.FIELDS_FROM_DATA if f in t}
        data["status"] = t.get("status")
        if (t.get("evidence") or {}).get("merged"):
            data["merged"] = t["evidence"]["merged"]
        out.append(make_event(event="TASK_SNAPSHOT", actor="company-pm",
                              project=t.get("project") or "unknown", task=tid, data=data))
    baselines = {}
    for ev in events:
        if ev.get("event") == "BASELINE_RECORDED":
            baselines[ev.get("project")] = ev
    for ev in baselines.values():
        data = {k: v for k, v in (ev.get("data") or {}).items() if k != "pm_mac"}
        out.append(make_event(event="BASELINE_RECORDED", actor="company-pm",
                              project=ev.get("project") or "unknown",
                              data={**data, "snapshot_of_seq": ev.get("seq")},
                              evidence=ev.get("evidence") or {"log": "migrated"}))
    still_open = escalations.fold(events)
    resolved = {}
    for ev in events:
        esc = (ev.get("data") or {}).get("id")
        if ev.get("event") == "ESCALATION_RESOLVED" and esc and esc not in still_open:
            resolved[esc] = ev
    for esc, ev in resolved.items():
        out.append(make_event(event="ESCALATION_RESOLVED", actor="company-pm",
                              project=ev.get("project") or "unknown", task=ev.get("task"),
                              data={"id": esc, "resolution": (ev.get("data") or {}).get(
                                  "resolution"), "snapshot_of_seq": ev.get("seq")}))
    for ev in out:
        log.append_held(ev, sign_pm(key))
    return len(out)


def _mac(key: bytes, *fields) -> str:
    msg = json.dumps(list(fields), separators=(",", ":"), sort_keys=True)
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()


def started_mac(key: bytes, actor: str, role: str, seq: int, tasks: list[str],
                commits: dict[str, str]) -> str:
    return _mac(key, "WORKER_STARTED", actor, role, seq, sorted(tasks), commits)


def verdict_mac(key: bytes, task: str, event: str, actor: str, role: str,
                ws_seq: int, verdict: str, commit: str) -> str:
    return _mac(key, "VERDICT", task, event, actor, role, ws_seq, verdict, commit)


def sign_started(key: bytes, tasks: list[str], commits: dict[str, str]):
    """EventLog.append finalizer: the MAC covers the seq the log assigns.
    `commits` (task -> reviewed SHA) is also written into the event."""
    def finalize(ev: dict) -> None:
        data = ev.setdefault("data", {})
        data["commits"] = dict(commits)
        data["launch_mac"] = started_mac(key, ev["actor"], data["role"], ev["seq"], tasks,
                                         commits)
    return finalize


def verify(key: bytes | None, task_id: str, event: str, actor: str | None,
           sig: dict | None) -> bool:
    """`sig` is what taskstate.fold recorded for a PASSED verdict."""
    if not key or not actor or not isinstance(sig, dict):
        return False
    try:
        want_ws = started_mac(key, actor, sig["role"], sig["ws_seq"], sig["ws_tasks"],
                              sig["ws_commits"])
        want_v = verdict_mac(key, task_id, event, actor, sig["role"], sig["ws_seq"],
                             sig["verdict"], sig["commit"])
        return (sig["verdict"] == "pass" and isinstance(sig["commit"], str)
                and sig["ws_commits"].get(task_id) == sig["commit"]
                and hmac.compare_digest(want_ws, str(sig["launch_mac"]))
                and hmac.compare_digest(want_v, str(sig["verdict_mac"])))
    except (KeyError, TypeError, AttributeError):
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


# --- PM-signed state events (ESC-002 c) --------------------------------------
# Everything taskstate.fold derives that check_done or integrate rely on,
# besides the gate verdicts above: a task's gates, owner, tier, branch,
# worktree, base and owned/forbidden globs (TASK_CREATED, TASK_ASSIGNED), its
# terminal status (STATUS_CHANGED, TASK_COMPLETED, MERGED), and the baseline
# a red test run is judged against (BASELINE_RECORDED). The events log is
# writable from a worker's sandbox, so these count only when the PM's own
# process signed them (it can read the key; a worker cannot).
PM_EVENTS = frozenset({"TASK_SNAPSHOT", "TASK_CREATED", "TASK_ASSIGNED", "STATUS_CHANGED", "TASK_COMPLETED",
                       "MERGED", "BASELINE_RECORDED",
                       # a worker "resolving" an escalation would read as Riyan's answer
                       "ESCALATION_RESOLVED"})


def pm_mac(key: bytes, ev: dict) -> str:
    data = {k: v for k, v in (ev.get("data") or {}).items() if k != "pm_mac"}
    return _mac(key, "PM", ev.get("event"), ev.get("task"), ev.get("project"),
                ev.get("actor"), ev.get("seq"), data, ev.get("evidence"))


def sign_pm(key: bytes):
    """EventLog.append finalizer for a PM_EVENTS event (covers its seq)."""
    def finalize(ev: dict) -> None:
        ev.setdefault("data", {})["pm_mac"] = pm_mac(key, ev)
    return finalize


def pm_signer(company_root: Path):
    """The finalizer the PM's own process appends PM_EVENTS with, creating
    the key on first use; None where the key can't be had (a worker's
    sandbox), whose unsigned event the fold then ignores."""
    try:
        key = load_key(company_root, create=True)
    except OSError:
        key = None
    return sign_pm(key) if key else None


def _pm_signed(key: bytes, ev: dict) -> bool:
    mac = (ev.get("data") or {}).get("pm_mac")
    return isinstance(mac, str) and isinstance(ev.get("seq"), int) and \
        hmac.compare_digest(pm_mac(key, ev), mac)


def trusted_events(events: list[dict], key: bytes | None) -> list[dict]:
    """The log with every PM_EVENTS event the PM did not sign removed. A
    signed one is kept once, in seq order — a replayed copy (seq at or below
    one already kept) is dropped — and marked `_pm_signed` for the fold. No
    legacy window: whatever came before the key was carried over, signed,
    by migrate(). Without a key (none yet, or a worker's own process, which
    can't read it) the list is returned unchanged."""
    if not key:
        return events
    out, high = [], 0
    for ev in events:
        if ev.get("event") not in PM_EVENTS:
            out.append(ev)
        elif _pm_signed(key, ev) and ev["seq"] > high:
            high = ev["seq"]
            out.append({**ev, "_pm_signed": True})
    return out
