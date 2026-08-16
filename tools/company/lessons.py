"""The retrospective loop (V2): corrections become durable, not personal.

Before this, a correction from Riyan only became durable via a personal habit
— hand-writing it to `tasks/lessons.md` in whatever repo happened to be open.
Nothing in Company OS itself captured it, so the same mistake could recur on
a different project with no way to know it had already been made and fixed
once. This is the mechanism the report called Task Observer feeding a
Capability Curator, sized down to what V1/V2 actually needs: append-only,
per-repo, queryable, and it feeds the SAME registry-approval flow as
`capability-curator` rather than a second parallel one.

A lesson is a PATTERN worth not repeating, not a one-off mistake. "I fixed a
typo" is not a lesson; "the deploy script silently swallows the exit code, so
three runs looked green when they'd failed" is.
"""

from __future__ import annotations

from pathlib import Path

from eventlog import EventLog, make_event


def record(company_root: Path, *, project: str, pattern: str, evidence: str,
          fix: str, actor: str | None = None) -> dict:
    if not pattern.strip():
        raise ValueError("a lesson requires a pattern — what kept happening, not just what happened once")
    if not fix.strip():
        raise ValueError("a lesson requires the fix that was actually applied — "
                         "an observation with no fix is a complaint, not a lesson")
    if not evidence.strip():
        raise ValueError(
            "a lesson requires evidence of what actually happened. A vague "
            "feeling that something went wrong is not a pattern worth recording."
        )

    data = {"pattern": pattern, "fix": fix}
    EventLog(company_root).append(make_event(
        event="LESSON_RECORDED", actor=actor or "company-pm",
        project=project, data=data, evidence={"log": evidence}))
    return data


def fold(events: list[dict], project: str | None = None) -> list[dict]:
    """Every recorded lesson, oldest first — this list only ever grows.

    Unlike an escalation or an advisory finding, a lesson is never 'resolved'
    — the fix already happened by the time it's recorded. What matters is
    that the next task, on this repo or another, can be told to check it.
    """
    out = []
    for ev in events:
        if ev.get("event") != "LESSON_RECORDED":
            continue
        if project and ev.get("project") != project:
            continue
        data = ev.get("data") or {}
        out.append({
            "id": f"LESSON-{ev.get('seq')}",
            "ts": ev.get("ts"),
            "actor": ev.get("actor"),
            "pattern": data.get("pattern"),
            "fix": data.get("fix"),
            "evidence": (ev.get("evidence") or {}).get("log"),
        })
    return out
