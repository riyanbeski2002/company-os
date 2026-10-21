"""Goals above projects, and outcomes distinct from "done" (ADR-006).

One entity, `goal`, at three levels: mission -> objective -> key_result.
Tasks link to an objective or a key result, at creation (`goal` on the task)
or later (`GOAL_LINKED`). The link is resolved in exactly one place,
`taskstate.fold()`; this module takes that fold's output as input and never
re-reads link events for membership. One log, one link derivation, two views.

Each goal view keeps two axes that are never collapsed into one status:
`delivery` (what the linked tasks shipped) and `outcome` (whether the intent
was achieved, per an evidenced OUTCOME_ASSESSED). No task event ever moves
`outcome` — "shipped and it didn't work" is a first-class state, not one
that looks like success.

Files under `.company/goals/` are a rendered view, rebuilt by replay
(`company rebuild`), never the source of truth.
"""

from __future__ import annotations

import re
from pathlib import Path

import costs
import taskstate
from eventlog import (GOAL_PARENT_LEVEL, ORG_PROJECT, EventLog, _is_number,
                      canonical, make_event, validate)

DELIVERED = {"DONE", "MERGED"}
# A task that has left these has had work start on it.
NOT_STARTED = {"DRAFT", "PLANNED", "READY"}
ACTIVITY_FIELDS = ("runs", "output_tokens", "cache_read_tokens", "seconds", "usd_equivalent")


def next_id(events: list[dict]) -> str:
    """G-NNN, one past the highest id ever defined. Revisions reuse their id,
    so this counts ids, not GOAL_DEFINED events."""
    nums = [int(m.group(1)) for e in events if e.get("event") == "GOAL_DEFINED"
            for m in [re.fullmatch(r"G-(\d+)", str((e.get("data") or {}).get("id")))] if m]
    return f"G-{max(nums, default=0) + 1:03d}"


def definitions(events: list[dict]) -> dict[str, dict]:
    """goal id -> its latest definition plus `closed`, for append-time checks."""
    out: dict[str, dict] = {}
    for ev in events:
        data = ev.get("data") or {}
        if ev.get("event") == "GOAL_DEFINED" and data.get("id"):
            out[data["id"]] = {**data, "closed": out.get(data["id"], {}).get("closed", False)}
        elif ev.get("event") == "GOAL_CLOSED" and data.get("goal") in out:
            out[data["goal"]]["closed"] = True
    return out


def check_against_history(event: dict, events: list[dict], tasks: dict[str, dict]) -> None:
    """The ADR-006 rules that need the rest of the log; eventlog.validate()
    owns the ones a single event can answer. Raises ValueError."""
    name = event["event"]
    data = event.get("data") or {}
    defs = definitions(events)

    def open_goal(gid: str, what: str) -> dict:
        goal = defs.get(gid)
        if not goal:
            raise ValueError(f"{what}: no goal {gid!r} is defined")
        if goal["closed"]:
            raise ValueError(f"{what}: goal {gid!r} is closed")
        return goal

    if name == "GOAL_DEFINED":
        gid, level = data["id"], data["level"]
        prior = defs.get(gid)
        if prior:
            if prior["closed"]:
                raise ValueError(f"goal {gid!r} is closed and can't be revised")
            if prior["level"] != level:
                raise ValueError(f"goal {gid!r} is a {prior['level']}; a revision "
                                 f"can't change its level")
            if not str(data.get("reason") or "").strip():
                raise ValueError(f"goal {gid!r} is already defined — revising it "
                                 f"requires a reason")
        if level == "mission":
            other = [g for g, d in defs.items()
                     if d["level"] == "mission" and not d["closed"] and g != gid]
            if other:
                raise ValueError(f"{other[0]} is already the open mission — at most "
                                 f"one per log; close it first")
        else:
            parent = open_goal(data["parent"], f"parent of {gid}")
            if parent["level"] != GOAL_PARENT_LEVEL[level]:
                raise ValueError(f"a {level}'s parent must be a {GOAL_PARENT_LEVEL[level]}, "
                                 f"and {data['parent']} is a {parent['level']}")

    elif name == "GOAL_LINKED":
        if data["goal"] is not None:
            goal = open_goal(data["goal"], "link")
            if goal["level"] == "mission":
                raise ValueError("tasks link to an objective or key_result, never the "
                                 "mission — everything serves the mission")
        terminal = [t for t in data["tasks"]
                    if (tasks.get(t) or {}).get("status") in taskstate.TERMINAL_STATUSES]
        if terminal and not str(data.get("reason") or "").strip():
            raise ValueError(f"{', '.join(terminal)} already terminal — retro-linking "
                             f"requires a reason")

    elif name == "OUTCOME_ASSESSED":
        goal = open_goal(data["goal"], "assess")
        if goal["level"] == "key_result" and data["verdict"] != "inconclusive" \
                and "value" not in (data.get("measured") or {}):
            raise ValueError("a key_result verdict requires measured.value — "
                             "the number is the point")

    elif name == "GOAL_CLOSED":
        open_goal(data["goal"], "close")
        if data.get("superseded_by"):
            open_goal(data["superseded_by"], "superseded_by")


def append(company_root: Path, *, event: str, actor: str, data: dict,
           evidence: dict | None = None) -> dict:
    """Validate against the log, then append one goal event. The only writer
    of the four goal events (`company event` refuses them)."""
    log = EventLog(company_root)
    events = log.read()
    ev = make_event(event=event, actor=actor, project=ORG_PROJECT, data=data,
                    evidence=evidence)
    validate(ev)
    check_against_history(ev, events, taskstate.fold(events))
    return log.append(ev)


# --- the projection ---------------------------------------------------------

def meets_target(measure: dict | None, measured: dict | None) -> bool | None:
    """Computed, never asserted: None unless both sides are numbers and the
    measure names a direction."""
    measure, measured = measure or {}, measured or {}
    target, value, direction = measure.get("target"), measured.get("value"), measure.get("direction")
    if not (_is_number(target) and _is_number(value) and direction):
        return None
    return value >= target if direction == "increase" else value <= target


def _delivery(linked: list[dict]) -> dict:
    counts = {"total": len(linked), "done": 0, "merged": 0, "abandoned": 0, "open": 0}
    for t in linked:
        status = t.get("status")
        key = {"DONE": "done", "MERGED": "merged", "ABANDONED": "abandoned"}.get(status, "open")
        counts[key] += 1
    live = counts["total"] - counts["abandoned"]
    if live and counts["open"] == 0:
        state = "delivered"
    elif any(t.get("status") not in NOT_STARTED | {"ABANDONED"} for t in linked):
        state = "in_progress"
    else:
        state = "none"
    return {"state": state, **counts}


def _delivered_seq(events: list[dict], tasks: dict[str, dict]) -> dict[str, int]:
    """task id -> seq of the last event that delivered it, for tasks that are
    delivered now. Used only for staleness, which is judged by seq, not clock."""
    out = {}
    for i, ev in enumerate(events, 1):
        tid = ev.get("task")
        name = ev.get("event")
        if not tid or (tasks.get(tid) or {}).get("status") not in DELIVERED:
            continue
        if name in ("MERGED", "TASK_COMPLETED") or (
                name == "STATUS_CHANGED" and (ev.get("data") or {}).get("to") in DELIVERED):
            out[tid] = ev.get("seq", i)
    return out


def fold(events: list[dict], tasks: dict[str, dict]) -> dict[str, dict]:
    """Goal views, derived by replay. Pure — `tasks` is taskstate.fold(events),
    the single source of task -> goal membership."""
    goals: dict[str, dict] = {}
    raw_assessments: dict[str, list[dict]] = {}
    named_in_links: dict[str, str | None] = {}

    for i, ev in enumerate(events, 1):
        name = ev.get("event")
        data = ev.get("data") or {}
        if name == "GOAL_DEFINED" and data.get("id"):
            # A revision is a complete definition (the CLI fills in what it
            # doesn't change), so last wins outright; only identity, history
            # and closure carry over.
            prior = goals.get(data["id"]) or {}
            goal = {k: v for k, v in data.items() if k != "reason"}
            goal["defined_by"] = prior.get("defined_by", ev.get("actor"))
            goal["defined_at"] = prior.get("defined_at", ev.get("ts"))
            goal["revisions"] = prior.get("revisions", []) + (
                [{"by": ev.get("actor"), "at": ev.get("ts"), "reason": data.get("reason")}]
                if prior else [])
            goal["status"] = prior.get("status", "open")
            if "closed" in prior:
                goal["closed"] = prior["closed"]
            goals[data["id"]] = goal
        elif name == "OUTCOME_ASSESSED" and data.get("goal"):
            raw_assessments.setdefault(data["goal"], []).append(
                {"seq": ev.get("seq", i), "by": ev.get("actor"), "at": ev.get("ts"),
                 "verdict": data.get("verdict"), "measured": data.get("measured"),
                 "method": data.get("method"), "evidence": ev.get("evidence")})
        elif name == "GOAL_CLOSED" and data.get("goal") in goals:
            goals[data["goal"]]["status"] = "closed"
            goals[data["goal"]]["closed"] = {
                k: v for k, v in {"disposition": data.get("disposition"),
                                  "superseded_by": data.get("superseded_by"),
                                  "reason": data.get("reason"), "by": ev.get("actor"),
                                  "at": ev.get("ts")}.items() if v is not None}
        elif name == "GOAL_LINKED":
            # Read only to name ids taskstate.fold() could not link because
            # no such task exists — membership itself comes from `tasks`.
            for member in data.get("tasks") or []:
                named_in_links[member] = data.get("goal")

    if not goals:
        return {}

    by_task = costs.aggregate(events)["by_task"]
    delivered_at = _delivered_seq(events, tasks)

    for gid, goal in goals.items():
        linked = sorted((t for t in tasks.values() if t.get("goal") == gid),
                        key=lambda t: t["id"])
        owners = {t.get("owner") for t in linked if t.get("owner")}
        goal["tasks"] = [t["id"] for t in linked]
        goal["projects"] = sorted({t.get("project") for t in linked if t.get("project")})
        goal["unknown_tasks"] = sorted(t for t, g in named_in_links.items()
                                       if g == gid and t not in tasks)
        goal["delivery"] = _delivery(linked)

        activity = {k: 0 for k in ACTIVITY_FIELDS}
        split = False
        for t in goal["tasks"]:
            entry = by_task.get(t) or {}
            for k in ACTIVITY_FIELDS:
                activity[k] += entry.get(k, 0)
            split = split or entry.get("split_across_tasks", 1) > 1
        activity["seconds"] = round(activity["seconds"], 1)
        activity["usd_equivalent"] = round(activity["usd_equivalent"], 4)
        # A gate-group run's cost is an even split (costs.py) — say so.
        activity["includes_split_estimate"] = split
        goal["activity"] = activity

        assessments = []
        for a in raw_assessments.get(gid, []):
            a = dict(a)
            # Same principle as check_done() refusing a self-certified gate.
            a["self_assessed"] = a["by"] in owners
            a["meets_target"] = meets_target(goal.get("measure"), a.get("measured"))
            a["inconsistent"] = (a["meets_target"] is not None
                                 and a["verdict"] in ("achieved", "not_achieved")
                                 and a["meets_target"] != (a["verdict"] == "achieved"))
            assessments.append(a)
        goal["assessments"] = assessments

        qualifying = [a for a in assessments if not a["self_assessed"]]
        latest = qualifying[-1] if qualifying else None
        outcome = {"state": latest["verdict"] if latest else "unassessed",
                   "assessed_seq": latest["seq"] if latest else None,
                   "stale": bool(latest) and any(
                       delivered_at.get(t, 0) > latest["seq"] for t in goal["tasks"]),
                   "self_assessed": bool(assessments) and assessments[-1]["self_assessed"],
                   "inconsistent": bool(latest) and latest["inconsistent"]}
        goal["outcome"] = outcome

    for gid, goal in goals.items():
        # Parents never inherit: children are counted, never folded into
        # the parent's own outcome.
        kids = sorted(g for g, v in goals.items() if v.get("parent") == gid)
        live = [k for k in kids if goals[k]["status"] == "open"]
        goal["children"] = kids
        goal["children_achieved"] = {
            "achieved": sum(goals[k]["outcome"]["state"] == "achieved" for k in live),
            "total": len(live)}
        flags = []
        if goal["delivery"]["state"] == "delivered" and goal["outcome"]["state"] == "unassessed":
            flags.append("awaiting_assessment")
        for flag in ("stale", "self_assessed"):
            if goal["outcome"][flag]:
                flags.append(flag)
        if goal["outcome"]["inconsistent"]:
            flags.append("assessment_inconsistent")
        if goal["unknown_tasks"]:
            flags.append("unknown_tasks")
        goal["flags"] = flags
    return goals


def budget_status(goal: dict, policy: dict) -> dict | None:
    """Report-only (ADR-006 §7): spend against the goal's budget in the
    policy's unit. Kept out of the persisted view because the threshold is
    config, and replay must be a function of the log alone."""
    unit = policy.get("unit", "output_tokens")
    budget = (goal.get("budget") or {}).get(unit)
    if budget is None:
        return None
    spent = goal["activity"].get(unit, 0)
    ratio = round(spent / budget, 3) if budget else None
    warn_at = policy.get("warn_at_ratio", 0.8)
    return {"unit": unit, "budget": budget, "spent": spent, "ratio": ratio,
            # A zero budget has no ratio; any spend against it is over.
            "warn": (spent > 0) if ratio is None else ratio >= warn_at,
            "enforced": bool(policy.get("enforce"))}


def gaps(goals: dict[str, dict], tasks: dict[str, dict], policy: dict) -> dict:
    """The discipline view. Information, not a gate: nothing refuses an
    ungoaled task. Closed goals drop out; their history stays readable."""
    open_goals = {g: v for g, v in goals.items() if v["status"] == "open"}
    ungoaled: dict[str, list[str]] = {}
    dangling: dict[str, list[str]] = {}
    for t in sorted(tasks.values(), key=lambda t: t["id"]):
        if not t.get("goal"):
            ungoaled.setdefault(t.get("project") or "", []).append(t["id"])
        elif t["goal"] not in goals:
            dangling.setdefault(t["goal"], []).append(t["id"])

    def flagged(flag):
        return sorted(g for g, v in open_goals.items() if flag in v["flags"])

    budget = []
    for gid, goal in sorted(open_goals.items()):
        status = budget_status(goal, policy)
        if status and status["warn"]:
            budget.append({"goal": gid, **status})
    return {
        "ungoaled_tasks": ungoaled,
        "awaiting_assessment": flagged("awaiting_assessment"),
        "stale": flagged("stale"),
        "self_assessed": flagged("self_assessed"),
        "assessment_inconsistent": flagged("assessment_inconsistent"),
        "key_results_unassessed": sorted(
            g for g, v in open_goals.items()
            if v.get("level") == "key_result" and v["outcome"]["state"] == "unassessed"),
        "unknown_tasks": {g: v["unknown_tasks"] for g, v in sorted(open_goals.items())
                          if v["unknown_tasks"]},
        "tasks_linked_to_undefined_goal": dangling,
        "budget_warnings": budget,
    }


def render_tree(goals: dict[str, dict], policy: dict) -> str:
    """mission -> objectives -> key results, each with delivery/outcome/spend."""
    if not goals:
        return "No goals defined. `company goal define --level mission --title ...` starts one."
    unit = policy.get("unit", "output_tokens")
    lines = []

    def node(gid, depth):
        g = goals[gid]
        d = g["delivery"]
        outcome = g["outcome"]["state"] + "".join(f" [{f}]" for f in g["flags"])
        line = (f"{'  ' * depth}{gid} {g.get('level')}: {g.get('title')}"
                + (" (closed)" if g["status"] == "closed" else ""))
        lines.append(line)
        detail = (f"delivery {d['state']} ({d['done']} done, {d['merged']} merged, "
                  f"{d['open']} open of {d['total']}) | outcome {outcome} | "
                  f"spend {g['activity'].get(unit, 0)} {unit}")
        if g["children"]:
            c = g["children_achieved"]
            detail += f" | children {c['achieved']}/{c['total']} achieved"
        lines.append(f"{'  ' * depth}  {detail}")
        for kid in g["children"]:
            node(kid, depth + 1)

    for gid in sorted(g for g, v in goals.items() if v.get("parent") not in goals):
        node(gid, 0)
    return "\n".join(lines)


def tree(goals: dict[str, dict]) -> list[dict]:
    """Nested form of the same tree, for `--json`."""
    def node(gid):
        g = goals[gid]
        return {"id": gid, "level": g.get("level"), "title": g.get("title"), "status": g["status"],
                "delivery": g["delivery"], "outcome": g["outcome"], "flags": g["flags"],
                "activity": g["activity"], "children": [node(k) for k in g["children"]]}
    return [node(g) for g in sorted(g for g, v in goals.items() if v.get("parent") not in goals)]


# --- files ------------------------------------------------------------------

def goal_path(company_root: Path, gid: str) -> Path:
    return Path(company_root) / "goals" / f"{gid}.json"


def write_views(company_root: Path, goals: dict[str, dict]) -> list[Path]:
    # No goals, no directory: a log that predates ADR-006 leaves .company/
    # exactly as it was.
    if not goals:
        return []
    d = Path(company_root) / "goals"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for gid, goal in goals.items():
        p = d / f"{gid}.json"
        p.write_text(canonical(goal), encoding="utf-8")
        out.append(p)
    return out


def verify_views(company_root: Path, goals: dict[str, dict]) -> list[str]:
    """Same rules as tasks/: byte-identical replay, and a stray file is a mismatch."""
    mismatches = []
    for gid, goal in goals.items():
        p = goal_path(company_root, gid)
        if not p.exists():
            mismatches.append(f"{p}: missing — replay produces it, disk does not have it")
        elif p.read_text(encoding="utf-8") != canonical(goal):
            mismatches.append(f"{p}: differs from replay")
    gdir = Path(company_root) / "goals"
    if gdir.exists():
        for stray in sorted(gdir.glob("*.json")):
            if stray.stem not in goals:
                mismatches.append(f"{stray}: on disk but no events produce it")
    return mismatches
