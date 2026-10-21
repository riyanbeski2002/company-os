"""Quarantine of test-fixture lessons that leaked into the real log
(`company quarantine-lessons`).

tests/test_lessons.py and tests/test_onboard.py recorded LESSON_RECORDED
events under project "p" straight into the real, authoritative
.company/events/events.jsonl whenever the suite ran inside a worker session:
worker.py exports COMPANY_ROOT pointing at the real repo into every worker's
env, so an EventLog built from the environment wrote through to it. Commit
a3e20be root-caused and stopped that leak going forward, but the entries it
already produced still sit in the log.

The log is append-only, so a contaminated LESSON_RECORDED is never deleted or
rewritten — exactly backfill.py's discipline for a historical line that can't
be edited. Instead a single LESSONS_QUARANTINED event names the seqs to
disregard, carrying evidence (the commit that proved the leak) the same way
TOKENS_BACKFILLED points back at the stdout.json it was reconstructed from.
lessons.fold() then skips the listed seqs, so cross-project lesson listing and
repeat-detection no longer count the fixture noise. History stays intact and
auditable; nothing is removed.

Refuse-rather-than-guess, like backfill.py: the seqs are re-derived from the
log on every run, not hardcoded, and an `expect` count that doesn't match what
the log actually holds aborts rather than quarantining a different set than
intended.
"""

from __future__ import annotations

from pathlib import Path

from eventlog import EventLog, make_event

QUARANTINE_ACTOR = "company-quarantine"

# The project the test fixtures wrote under. Real lessons are recorded under a
# repo's own project name (e.g. "company-os"); "p" is the placeholder
# test_lessons.py/test_onboard.py pass, so it is a reliable, stable marker of
# fixture leakage and not of any genuine lesson.
LEAKED_PROJECT = "p"

DEFAULT_REASON = (
    "test-fixture LESSON_RECORDED events leaked into the real log by "
    "tests/test_lessons.py and tests/test_onboard.py running inside a worker "
    "session (COMPANY_ROOT pointed at the real repo). Leak stopped by a3e20be; "
    "these pre-fix entries are disregarded, not deleted."
)


def quarantined_seqs(events: list[dict]) -> set:
    """Every seq disregarded by any LESSONS_QUARANTINED event so far."""
    out: set = set()
    for ev in events:
        if ev.get("event") == "LESSONS_QUARANTINED":
            out.update((ev.get("data") or {}).get("seqs") or [])
    return out


def contaminated_seqs(events: list[dict], project: str = LEAKED_PROJECT) -> list:
    """The seqs of every leaked LESSON_RECORDED, oldest first. A LESSON_RECORDED
    under the fixture project is the leak; nothing else is touched."""
    return sorted(ev.get("seq") for ev in events
                  if ev.get("event") == "LESSON_RECORDED"
                  and ev.get("project") == project
                  and ev.get("seq") is not None)


def plan(events: list[dict], project: str = LEAKED_PROJECT) -> dict:
    """What a quarantine would disregard, and what is already disregarded.
    Pure — appends nothing, so `--dry-run` is just this."""
    done = quarantined_seqs(events)
    contaminated = contaminated_seqs(events, project)
    return {
        "contaminated": contaminated,
        "to_quarantine": [s for s in contaminated if s not in done],
        "already_quarantined": [s for s in contaminated if s in done],
    }


def run(company_root: Path, project: str = LEAKED_PROJECT,
        reason: str = DEFAULT_REASON, evidence_commit: str | None = None,
        expect: int | None = None, dry_run: bool = False) -> dict:
    """Append one LESSONS_QUARANTINED covering every not-yet-quarantined leaked
    seq. Idempotent: a second run finds nothing left to quarantine and appends
    nothing. Refuses rather than guesses if `expect` disagrees with the log."""
    log = EventLog(company_root)
    result = plan(log.read(), project)

    if expect is not None and len(result["contaminated"]) != expect:
        raise ValueError(
            f"expected {expect} contaminated LESSON_RECORDED events under "
            f"project {project!r}, but the log holds {len(result['contaminated'])} "
            f"— refusing to quarantine a different set than intended. "
            f"Re-derive the count and pass --expect that, or omit it."
        )

    appended = None
    if not dry_run and result["to_quarantine"]:
        data = {"seqs": result["to_quarantine"],
                "count": len(result["to_quarantine"]),
                "project": project, "reason": reason}
        evidence = ({"commit": evidence_commit} if evidence_commit
                    else {"log": "a3e20be: test-isolation leak root-caused and fixed"})
        appended = log.append(make_event(
            event="LESSONS_QUARANTINED", actor=QUARANTINE_ACTOR,
            project=project, data=data, evidence=evidence))

    return {
        "dry_run": dry_run,
        "appended": appended,
        "would_quarantine": result["to_quarantine"] if dry_run else [],
        "already_quarantined": result["already_quarantined"],
        "contaminated_total": len(result["contaminated"]),
    }
