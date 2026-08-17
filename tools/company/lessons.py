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
          fix: str, actor: str | None = None, skill: str | None = None) -> dict:
    """`skill` is what closes the loop this event log used to leave open: a
    lesson that names the skill/agent it's about is queryable by
    `fold(..., skill=...)`, so 2+ lessons touching the same skill become a
    concrete signal that skill needs a real patch — not a hope that someone
    remembers to go read the log."""
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
    if skill:
        data["skill"] = skill
    EventLog(company_root).append(make_event(
        event="LESSON_RECORDED", actor=actor or "company-pm",
        project=project, data=data, evidence={"log": evidence}))
    return data


def fold(events: list[dict], project: str | None = None,
        skill: str | None = None) -> list[dict]:
    """Every recorded lesson, oldest first — this list only ever grows.

    Unlike an escalation or an advisory finding, a lesson is never 'resolved'
    — the fix already happened by the time it's recorded. What matters is
    that the next task, on this repo or another, can be told to check it.

    `skill` filters to lessons tagged with that skill/agent name — this is
    the query that turns repeated lessons into a concrete signal a skill
    needs patching, instead of accumulating unread.
    """
    out = []
    for ev in events:
        if ev.get("event") != "LESSON_RECORDED":
            continue
        if project and ev.get("project") != project:
            continue
        data = ev.get("data") or {}
        if skill and data.get("skill") != skill:
            continue
        out.append({
            "id": f"LESSON-{ev.get('seq')}",
            "ts": ev.get("ts"),
            "actor": ev.get("actor"),
            "pattern": data.get("pattern"),
            "fix": data.get("fix"),
            "skill": data.get("skill"),
            "evidence": (ev.get("evidence") or {}).get("log"),
        })
    return out


def skills_with_repeated_lessons(events: list[dict], threshold: int = 2) -> dict[str, int]:
    """Skills/agents with `threshold`+ lessons tagged against them — the
    actual trigger for "this skill needs a real patch," not a hope someone
    remembers to go read the log. A single lesson might be a one-off; a
    repeated one is the golden-path-worth-harvesting signal."""
    counts: dict[str, int] = {}
    for lesson in fold(events):
        skill = lesson.get("skill")
        if skill:
            counts[skill] = counts.get(skill, 0) + 1
    return {s: n for s, n in counts.items() if n >= threshold}
