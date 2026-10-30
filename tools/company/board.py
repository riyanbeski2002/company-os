"""The coordination board — live, typed, peer-visible notes for concurrently
running subagents sharing one subject (a task or an exploratory goal) with
real duplicate-work risk.

This is NOT for the standard single-worker Tier-2 pipeline: a task's owned
file globs already prevent two workers from colliding on the same code, and
gategroup.py already merges/reviews the result. It is for fan-out work where
nothing structural prevents duplication — parallel debugging, parallel
research subagents, parallel gap-finding — the exact gap KNOWN_GAPS.md #7
names: company-os had no live channel for concurrently running subagents to
tell each other "I already tried that, it's false" or "I'm taking this
angle, pick another."

Mined from microsoft/Agensh's board-service (shared_lessons.py, verifier.py)
— not adopted, not referenced, not run: its actual mechanisms (typed terse
notes, a deterministic evidence gate on completion claims, a self-expiring
claim instead of a lock, FAIL invalidating a now-stale claim) are real and
reusable, but the implementation here is native to company-os's own
architecture: one event (BOARD_NOTE) in the existing append-only log, folded
on read, like every other derived view in this system (taskstate.py's own
pattern) — no separate service, no database, no dependency.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from eventlog import EventLog, make_event


def _ts_epoch(ts: str) -> float:
    """eventlog.utcnow()'s exact format — every event's `ts` is this shape."""
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()

# FACT / OBSERVED: durable findings, deduped by content.
# FAIL: the highest-value note — it stops a peer spending budget on a
# hypothesis already falsified. Invalidates the same actor's own most recent
# open CLAIM or DONE_SUMMARY on this subject (not a peer's — a FAIL is a
# correction of what ITS author claimed, never a verdict on someone else's).
# CLAIM: "I'm working this angle" — self-expiring (ttl_seconds), not a lock;
# a crashed or abandoned subagent can't block peers forever.
# DONE_SUMMARY: a completion claim, gated by _has_solid_evidence() below —
# "should work"/"looks right" is refused the same way a bare assertion is
# refused everywhere else in this log (eventlog.EvidenceError's philosophy,
# applied one level before a claim would even reach a gate).
# DIRECTIVE: company-pm redirecting every peer on this subject at once — a
# scope or phase change ("stop exploring new angles, converge on what's
# found"). Nothing enforces who may write one; same trust-by-convention model
# the rest of this log already uses.
BOARD_NOTE_TYPES = ("FACT", "OBSERVED", "FAIL", "CLAIM", "DONE_SUMMARY", "DIRECTIVE")

CONTENT_CAP = 100
DONE_SUMMARY_CAP = 300
DEFAULT_CLAIM_TTL_SECONDS = 3600.0

_WEAK_EVIDENCE_PHRASES = (
    "pending", "not verified", "unverified", "should work", "should pass",
    "looks right", "looks correct", "seems to work", "to be verified",
    "will verify", "tbd", "n/a", "probably",
)
_SOLID_EVIDENCE_RE = re.compile(
    r"\b(pass(?:ed|es)?|verified|confirmed|no longer|now returns|now produces|"
    r"reproduced|fixed and checked)\b",
    re.IGNORECASE,
)


def _has_solid_evidence(content: str) -> bool:
    """Deterministic text check, same spirit as Agensh's verifier.py: does
    NOT execute anything or check the claim is actually true — it only
    rejects the placeholder language that marks a claim nobody has checked.
    A DONE_SUMMARY that clears this can still be wrong; that's what a FAIL
    from the same actor, or a real gate, is for."""
    low = content.strip().lower()
    if not low:
        return False
    if any(p in low for p in _WEAK_EVIDENCE_PHRASES):
        return False
    return bool(_SOLID_EVIDENCE_RE.search(content))


class BoardError(ValueError):
    pass


def validate_note(data: dict) -> None:
    """Shape rules for a BOARD_NOTE's `data`, called from eventlog.validate()
    so a malformed note can never be appended, same discipline as every
    other typed event in this log."""
    subject = data.get("subject")
    if not (isinstance(subject, str) and subject.strip()):
        raise BoardError("BOARD_NOTE requires a non-empty data.subject "
                          "(the task or goal id this note is scoped to)")
    kind = data.get("type")
    if kind not in BOARD_NOTE_TYPES:
        raise BoardError(f"BOARD_NOTE type {kind!r} is not one of {BOARD_NOTE_TYPES}")
    content = data.get("content")
    if not (isinstance(content, str) and content.strip()):
        raise BoardError(f"{kind} requires non-empty data.content")
    cap = DONE_SUMMARY_CAP if kind == "DONE_SUMMARY" else CONTENT_CAP
    if len(content) > cap:
        raise BoardError(f"{kind} content is {len(content)} chars, over the "
                          f"{cap}-char cap — say less, or publish a FACT with "
                          f"the short version and keep detail out of band")
    if kind == "DONE_SUMMARY" and not _has_solid_evidence(content):
        raise BoardError(
            "DONE_SUMMARY requires real evidence in the content, not a "
            "placeholder like 'should work' or 'pending' — say what you "
            "actually ran and what it showed (e.g. 'tests passed', "
            "'confirmed against main'), or publish a CLAIM instead if it "
            "isn't actually done yet"
        )
    ttl = data.get("ttl_seconds")
    if ttl is not None and not (isinstance(ttl, (int, float)) and not isinstance(ttl, bool) and ttl >= 0):
        raise BoardError("ttl_seconds, when given, must be a non-negative number")


def note(company_root, *, subject: str, type: str, content: str, actor: str,
         project: str, task: str | None = None, ttl_seconds: float | None = None) -> dict:
    data = {"subject": subject, "type": type, "content": content}
    if type == "CLAIM" and ttl_seconds is not None:
        data["ttl_seconds"] = ttl_seconds
    written = EventLog(company_root).append(make_event(
        event="BOARD_NOTE", actor=actor, project=project, task=task, data=data))
    return written


def _norm(content: str) -> str:
    return " ".join(content.split()).lower()


def read_board(events: list[dict], subject: str, now: float | None = None) -> dict:
    """Fold every BOARD_NOTE for `subject` into the live view a peer would
    actually want: durable facts (deduped), open claims (TTL-expired ones
    dropped), the latest directive, and done-summaries with their status —
    `invalidated_by_fail` the moment the same actor's own later FAIL lands,
    exactly as a stale PASSED verdict is already refused elsewhere in this
    log (eventlog._rejects_stale_gate_verdict's sibling, one layer earlier)."""
    now = time.time() if now is None else now
    notes = []
    for ev in events:
        if ev.get("event") != "BOARD_NOTE":
            continue
        data = ev.get("data") or {}
        if data.get("subject") != subject:
            continue
        notes.append({**data, "ts": ev.get("ts"), "seq": ev.get("seq"), "actor": ev.get("actor")})

    fails_by_actor: list[dict] = [n for n in notes if n.get("type") == "FAIL"]

    def _invalidated(entry: dict) -> bool:
        return any(
            f["actor"] == entry["actor"] and f["seq"] > entry["seq"]
            for f in fails_by_actor
        )

    facts, observed, fails, claims, done, directives = [], [], [], [], [], []
    dedupe: dict[tuple, dict] = {}
    for n in notes:
        kind = n["type"]
        if kind in ("FACT", "OBSERVED"):
            key = (kind, _norm(n["content"]))
            if key in dedupe:
                dedupe[key]["count"] += 1
                dedupe[key]["last_ts"] = n["ts"]
                continue
            entry = {"content": n["content"], "actor": n["actor"], "ts": n["ts"],
                     "last_ts": n["ts"], "count": 1}
            dedupe[key] = entry
            (facts if kind == "FACT" else observed).append(entry)
        elif kind == "FAIL":
            fails.append({"content": n["content"], "actor": n["actor"], "ts": n["ts"]})
        elif kind == "CLAIM":
            ttl = n.get("ttl_seconds", DEFAULT_CLAIM_TTL_SECONDS)
            expired = now > _ts_epoch(n["ts"]) + ttl
            claims.append({"content": n["content"], "actor": n["actor"], "seq": n["seq"],
                          "ts": n["ts"], "ttl_seconds": ttl, "expired": expired,
                          "invalidated_by_fail": _invalidated(n)})
        elif kind == "DONE_SUMMARY":
            done.append({"content": n["content"], "actor": n["actor"], "seq": n["seq"],
                        "ts": n["ts"], "invalidated_by_fail": _invalidated(n)})
        elif kind == "DIRECTIVE":
            directives.append({"content": n["content"], "actor": n["actor"], "ts": n["ts"]})

    # Open: not invalidated by the claimant's own later FAIL, and not past
    # its TTL — a crashed or abandoned subagent's claim stops blocking peers
    # on its own, without anyone having to notice and clear it by hand.
    open_claims = [c for c in claims if not c["invalidated_by_fail"] and not c["expired"]]
    directives.sort(key=lambda d: d["ts"])

    return {
        "subject": subject,
        "facts": facts,
        "observed": observed,
        "fails": fails,
        "open_claims": open_claims,
        "done_summaries": done,
        "latest_directive": directives[-1] if directives else None,
    }


def published_since(events: list[dict], subject: str, actor: str, since_seq: int) -> bool:
    """Did `actor` publish anything on `subject` after `since_seq`? The
    forced-write-nudge equivalent (Agensh's dispatcher.ts: a turn that ends
    with no new gist gets one nudge before the next turn starts) — used by
    company-pm after collecting a worker's result to catch the silent-worker
    failure mode: real work happened, but nothing peers (or the PM) can use
    was ever published."""
    return any(
        ev.get("event") == "BOARD_NOTE"
        and (ev.get("data") or {}).get("subject") == subject
        and ev.get("actor") == actor
        and ev.get("seq", 0) > since_seq
        for ev in events
    )
