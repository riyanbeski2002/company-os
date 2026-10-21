"""Token backfill for runs logged before WORKER_EXITED carried `tokens`
(`company backfill-tokens`) — KNOWN_ISSUES #1's outstanding half.

worker.py now writes `_usage(result)` into every WORKER_EXITED, so new runs
are covered. Older ones carry only cost/elapsed/exit_code/session_id, but the
harness result they were derived from is usually still on disk at
state/workers/<actor>/stdout.json — the exact dict `_usage()` reads, so
reconstruction reuses `_read_result`/`_usage` rather than re-deriving them.

The log is append-only, so a historical WORKER_EXITED is never rewritten.
Each reconstruction is a new TOKENS_BACKFILLED event pointing back at the
original by `seq` (unique per line, assigned under the append lock), with the
original's actor and session_id alongside so costs.py can refuse a backfill
that doesn't actually describe the run it claims to.

Two things make a stdout.json NOT trustworthy for a given event, and both are
reported rather than guessed around:
- it belongs to a different run: state/workers/<actor>/ is reused when the
  same actor is relaunched, so only a session_id match proves the file is
  this run's and not a later one's;
- it has no usable `usage` block: `_usage()` zero-fills a missing one, which
  is right for a live run's report and wrong here — a fabricated zero is
  indistinguishable from a real one in `company costs`.
"""

from __future__ import annotations

from pathlib import Path

from eventlog import EventLog, make_event
import worker

BACKFILL_ACTOR = "company-backfill"
_USAGE_KEYS = ("output_tokens", "input_tokens", "cache_read_input_tokens",
               "cache_creation_input_tokens")


def backfilled_seqs(events: list[dict]) -> set:
    return {(ev.get("data") or {}).get("backfills_seq")
            for ev in events if ev.get("event") == "TOKENS_BACKFILLED"}


def plan(events: list[dict], company_root: Path, project: str | None = None) -> dict:
    """What a backfill would append, and what it can't. Pure apart from
    reading stdout.json files — appends nothing, so `--dry-run` is just this."""
    workers = Path(company_root) / "state" / "workers"
    done = backfilled_seqs(events)
    exited = [ev for ev in events if ev.get("event") == "WORKER_EXITED"
              and (not project or ev.get("project") == project)]

    # Two tokenless exits with the same actor and session_id can't both be
    # the run one stdout.json describes — backfilling both would count it twice.
    seen: dict[tuple, int] = {}
    for ev in exited:
        if "tokens" not in (ev.get("data") or {}):
            key = (ev.get("actor"), (ev.get("data") or {}).get("session_id"))
            seen[key] = seen.get(key, 0) + 1

    out = {"to_append": [], "already_backfilled": [], "has_tokens": 0,
           "unreconstructable": []}
    for ev in exited:
        data = ev.get("data") or {}
        if "tokens" in data:
            out["has_tokens"] += 1
            continue
        seq = ev.get("seq")
        if seq in done:
            out["already_backfilled"].append(seq)
            continue

        actor, session_id = ev.get("actor"), data.get("session_id")
        ref = {"seq": seq, "actor": actor, "task": ev.get("task"),
               "session_id": session_id}
        path = workers / str(actor) / "stdout.json"

        reason = None
        if seq is None:
            reason = "event has no seq to reference"
        elif not actor or Path(actor).name != actor:
            reason = f"actor {actor!r} is not a plain worker-directory name"
        elif not session_id:
            reason = "event has no session_id, so no stdout.json can be proven to be this run's"
        elif seen[(actor, session_id)] > 1:
            reason = f"{seen[(actor, session_id)]} tokenless WORKER_EXITED events share this session_id"
        elif not path.is_file():
            reason = f"no {path}"
        else:
            result = worker._read_result(path)
            usage = result.get("usage")
            if not result:
                reason = f"{path} is missing or not parseable JSON"
            elif result.get("session_id") != session_id:
                reason = (f"{path} is session {result.get('session_id')!r}, a different run "
                          f"of the same actor — it was overwritten by a later launch")
            elif not isinstance(usage, dict) or not any(
                    isinstance(usage.get(k), int) for k in _USAGE_KEYS):
                reason = f"{path} has no usable usage block"
            else:
                out["to_append"].append({**ref, "project": ev.get("project"),
                                         "stdout": str(path), "tokens": worker._usage(result)})
                continue
        out["unreconstructable"].append({**ref, "reason": reason})
    return out


def run(company_root: Path, project: str | None = None, dry_run: bool = False) -> dict:
    """Append one TOKENS_BACKFILLED per reconstructable run. Idempotent: a
    run that already has a backfill event is skipped, never re-appended."""
    log = EventLog(company_root)
    result = plan(log.read(), company_root, project)
    appended = []
    if not dry_run:
        for item in result["to_append"]:
            data = {"backfills_seq": item["seq"], "actor": item["actor"],
                    "session_id": item["session_id"], "tokens": item["tokens"]}
            if item["task"]:
                # In data, not on the event: a `task` field would make
                # taskstate.fold bump that task's updated_at to today.
                data["task"] = item["task"]
            written = log.append(make_event(
                event="TOKENS_BACKFILLED", actor=BACKFILL_ACTOR, project=item["project"],
                data=data, evidence={"log": item["stdout"]}))
            appended.append({"seq": written["seq"], "backfills_seq": item["seq"],
                             "actor": item["actor"], "tokens": item["tokens"]})
    return {
        "dry_run": dry_run,
        "appended": appended,
        "would_append": result["to_append"] if dry_run else [],
        "already_backfilled": result["already_backfilled"],
        "already_had_tokens": result["has_tokens"],
        "unreconstructable": result["unreconstructable"],
    }
