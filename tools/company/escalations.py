"""Escalations — the PM's channel to the CEO (§9).

The CEO is a *capability*, not just an approver. Some things the PM genuinely
cannot do: open tmux sessions, supply a credential, decide between two products
that are both defensible, authorise spend. Being blocked in silence is worse
than asking.

Escalations live in the event log like everything else (D1). The files under
`.company/escalations/` are a rendered view, rebuilt by replay — never the
source of truth.

What to escalate: irreversibility, genuine product ambiguity with materially
different outcomes, real risk, and anything only a human can physically do.
What NOT to escalate: routine implementation choices, test failures, retries,
ordinary merge conflicts. The CEO is an executive, not the process scheduler.
"""

from __future__ import annotations

from pathlib import Path

from eventlog import EventLog, canonical, make_event

# What the PM is asking for. `kind` drives how `status` presents it.
KINDS = {
    "human_action",   # something only a human can physically do (tmux, hardware, a login)
    "decision",       # two defensible options, materially different outcomes
    "approval",       # policy requires a human yes (deploy, spend, credentials)
    "information",    # the PM lacks context only the CEO has
    "risk",           # the PM believes proceeding is unsafe
}


def next_id(events: list[dict]) -> str:
    n = sum(1 for e in events if e.get("event") == "ESCALATION_RAISED")
    return f"ESC-{n + 1:03d}"


def raise_escalation(company_root: Path, *, project: str, actor: str, kind: str,
                     need: str, detail: str = "", blocking: bool = True,
                     task: str | None = None, options: list[str] | None = None,
                     commands: list[str] | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown escalation kind {kind!r}; expected one of {sorted(KINDS)}")
    if not need.strip():
        raise ValueError("an escalation needs a 'need' — say plainly what you want")

    log = EventLog(company_root)
    esc_id = next_id(log.read())
    data = {"id": esc_id, "kind": kind, "need": need, "blocking": blocking}
    if detail:
        data["detail"] = detail
    if options:
        data["options"] = options
    if commands:
        data["commands"] = commands

    log.append(make_event(event="ESCALATION_RAISED", actor=actor,
                          project=project, task=task, data=data))
    return data


def resolve(company_root: Path, esc_id: str, *, actor: str, project: str,
            resolution: str) -> dict:
    log = EventLog(company_root)
    open_now = fold(log.read())
    if esc_id not in open_now:
        raise KeyError(f"no open escalation {esc_id!r}")
    log.append(make_event(event="ESCALATION_RESOLVED", actor=actor, project=project,
                          task=open_now[esc_id].get("task"),
                          data={"id": esc_id, "resolution": resolution}))
    return {"id": esc_id, "resolution": resolution}


def fold(events: list[dict]) -> dict[str, dict]:
    """Open escalations, derived by replay. Resolved ones drop out."""
    open_escalations: dict[str, dict] = {}
    malformed: list[dict] = []
    for ev in events:
        name = ev.get("event")
        data = ev.get("data") or {}
        if name == "ESCALATION_RAISED":
            esc_id = data.get("id")
            if esc_id is None:
                # A malformed event must never crash replay — fold() runs
                # from scratch on every call, so one bad line anywhere in a
                # project's log would permanently wedge the CLI for that
                # project (and, since this file is shared, for every other
                # project on the machine too). Same defensive pattern as
                # taskstate.py's STATUS_CHANGED handler. The return shape
                # here is `id -> escalation dict` consumed directly by
                # render.status (each value must be a real escalation dict,
                # never a bare list) — so the anomaly is logged, not stored
                # in the map itself.
                malformed.append({"seq": ev.get("seq"), "event": name, "data": data})
                continue
            open_escalations[esc_id] = {
                **data,
                "raised_by": ev.get("actor"),
                "raised_at": ev["ts"],
                "task": ev.get("task"),
                "project": ev.get("project"),
            }
        elif name == "ESCALATION_RESOLVED":
            open_escalations.pop(data.get("id"), None)
    if malformed:
        import sys
        for m in malformed:
            print(f"warning: skipped malformed {m['event']} event (seq={m['seq']}, "
                  f"missing 'id') during escalations.fold() replay", file=sys.stderr)
    return open_escalations


def all_escalations(events: list[dict]) -> dict[str, dict]:
    """Every escalation, open or resolved, for the audit trail."""
    everything: dict[str, dict] = {}
    for ev in events:
        name = ev.get("event")
        data = ev.get("data") or {}
        if name == "ESCALATION_RAISED":
            esc_id = data.get("id")
            if esc_id is None:
                # Same malformed-event guard as fold() above — never let one
                # bad line anywhere in any project's log crash the shared CLI.
                continue
            everything[esc_id] = {
                **data, "raised_by": ev.get("actor"), "raised_at": ev["ts"],
                "task": ev.get("task"), "project": ev.get("project"),
                "status": "open",
            }
        elif name == "ESCALATION_RESOLVED" and data.get("id") in everything:
            everything[data["id"]].update(
                status="resolved", resolution=data.get("resolution"),
                resolved_by=ev.get("actor"), resolved_at=ev["ts"])
    return everything


def write_views(company_root: Path, events: list[dict]) -> list[Path]:
    """Render each escalation as a file a human can read without the CLI."""
    d = Path(company_root) / "escalations"
    d.mkdir(parents=True, exist_ok=True)
    written = []
    for esc_id, esc in all_escalations(events).items():
        path = d / f"{esc_id}.md"
        path.write_text(_render(esc), encoding="utf-8")
        written.append(path)
    return written


def _render(esc: dict) -> str:
    lines = [
        f"# {esc['id']} — {esc['need']}",
        "",
        f"- **Status**: {esc.get('status', 'open')}"
        + ("  ⛔ blocking" if esc.get("blocking") and esc.get("status") == "open" else ""),
        f"- **Kind**: {esc['kind']}",
        f"- **Raised by**: {esc.get('raised_by')} at {esc.get('raised_at')}",
    ]
    if esc.get("task"):
        lines.append(f"- **Task**: {esc['task']}")
    lines.append("")

    if esc.get("detail"):
        lines += ["## Context", "", esc["detail"], ""]

    if esc.get("options"):
        lines += ["## Options", ""]
        lines += [f"{i}. {o}" for i, o in enumerate(esc["options"], 1)]
        lines.append("")

    if esc.get("commands"):
        lines += ["## Run this", "", "```bash"]
        lines += list(esc["commands"])
        lines += ["```", ""]

    if esc.get("status") == "resolved":
        lines += ["## Resolution", "",
                  f"{esc.get('resolution')}",
                  "",
                  f"— {esc.get('resolved_by')} at {esc.get('resolved_at')}", ""]
    else:
        lines += ["## To resolve", "",
                  f"```bash\ncompany resolve {esc['id']} --resolution \"...\"\n```", ""]
    return "\n".join(lines)
