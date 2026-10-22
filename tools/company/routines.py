"""Recurring work: a plan spec plus a cron schedule.

A routine never runs anything. Firing one turns its spec into PLANNED tasks
through the same planning rules `company plan` applies (mandatory gates,
duplicate-work and goal checks — cli.plan_spec), and records which scheduled
occurrence ("slot") produced them. A human or PM session picks the tasks up
the normal way.

Two events, folded here: ROUTINE_DEFINED (a complete definition, last one
wins; retiring is a re-definition with enabled: false) and ROUTINE_FIRED
(routine, slot, tasks). A slot fires at most once — EventLog.append refuses a
second ROUTINE_FIRED for the same (routine, slot) under its own lock.

Times are UTC. The cron matcher is stdlib-only and supports five fields
(minute hour day-of-month month day-of-week) with `*`, numbers, `a-b`
ranges, comma lists and `/step` on any of those; day-of-week is 0-7 with 0
and 7 both Sunday. No names (MON, JAN) and no @-shortcuts. Day-of-month and
day-of-week combine the way Vixie cron does: when both are restricted, a day
matching either one matches.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eventlog import ORG_PROJECT, EventLog, make_event, validate

FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
# How far back `due` looks for a missed slot. Bounds the scan; a routine
# that hasn't matched in a year isn't owed a catch-up.
LOOKBACK = timedelta(days=366)


# --- cron -------------------------------------------------------------------

def parse_cron(expr: str) -> dict:
    """5-field cron -> the set of values each field allows. Raises ValueError."""
    fields = str(expr).split()
    if len(fields) != 5:
        raise ValueError(f"cron {expr!r} must have 5 fields: minute hour dom month dow")
    sets = []
    for field, (lo, hi) in zip(fields, FIELD_RANGES):
        allowed = set()
        for part in field.split(","):
            m = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", part)
            if not m:
                raise ValueError(f"cron field {field!r} in {expr!r} is not supported")
            base, step = m.group(1), int(m.group(2) or 1)
            if base == "*":
                start, end = lo, hi
            elif "-" in base:
                start, end = map(int, base.split("-"))
            else:
                start = int(base)
                end = hi if m.group(2) else start
            if step < 1 or not lo <= start <= end <= hi:
                raise ValueError(f"cron field {field!r} in {expr!r} is out of range {lo}-{hi}")
            allowed.update(range(start, end + 1, step))
        sets.append(allowed)
    dow = {0 if d == 7 else d for d in sets[4]}
    return {"minute": sets[0], "hour": sets[1], "dom": sets[2], "month": sets[3], "dow": dow,
            "dom_any": fields[2].startswith("*"), "dow_any": fields[4].startswith("*")}


def _day_matches(cron: dict, t: datetime) -> bool:
    if t.month not in cron["month"]:
        return False
    dom = t.day in cron["dom"]
    dow = (t.weekday() + 1) % 7 in cron["dow"]  # cron: Sunday is 0
    if cron["dom_any"] or cron["dow_any"]:
        return dom and dow
    return dom or dow


def matches(cron: dict, t: datetime) -> bool:
    return _day_matches(cron, t) and t.hour in cron["hour"] and t.minute in cron["minute"]


def latest_slot(cron: dict, after: datetime, now: datetime) -> datetime | None:
    """The latest minute in (after, now] the schedule matches, or None.
    Skips whole days and hours that can't match, so a year's scan is cheap."""
    t = now.replace(second=0, microsecond=0)
    floor = max(after, now - LOOKBACK)
    while t > floor:
        if not _day_matches(cron, t):
            t = t.replace(hour=0, minute=0) - timedelta(minutes=1)
        elif t.hour not in cron["hour"]:
            t = t.replace(minute=0) - timedelta(minutes=1)
        elif t.minute not in cron["minute"]:
            t -= timedelta(minutes=1)
        else:
            return t
    return None


def parse_time(raw: str) -> datetime:
    """ISO 8601 -> aware UTC. A naive time is taken as UTC."""
    t = datetime.fromisoformat(raw)
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def slot_id(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%MZ")


# --- the fold ---------------------------------------------------------------

def next_id(events: list[dict]) -> str:
    """R-NNN, one past the highest id ever defined."""
    nums = [int(m.group(1)) for e in events if e.get("event") == "ROUTINE_DEFINED"
            for m in [re.fullmatch(r"R-(\d+)", str((e.get("data") or {}).get("id")))] if m]
    return f"R-{max(nums, default=0) + 1:03d}"


def fold(events: list[dict]) -> dict[str, dict]:
    """routine id -> its latest definition plus its firing history. Pure."""
    out: dict[str, dict] = {}
    for i, ev in enumerate(events, 1):
        name = ev.get("event")
        data = ev.get("data") or {}
        if name == "ROUTINE_DEFINED" and data.get("id"):
            prior = out.get(data["id"]) or {}
            routine = {k: v for k, v in data.items() if k != "reason"}
            routine["defined_by"] = prior.get("defined_by", ev.get("actor"))
            routine["defined_at"] = prior.get("defined_at", ev.get("ts"))
            # The schedule is anchored at the latest definition: re-enabling
            # a paused routine doesn't owe it the slots it was paused for.
            routine["revised_at"] = ev.get("ts")
            routine["revisions"] = prior.get("revisions", []) + (
                [{"by": ev.get("actor"), "at": ev.get("ts"), "reason": data.get("reason")}]
                if prior else [])
            routine["fired"] = prior.get("fired", [])
            out[data["id"]] = routine
        elif name == "ROUTINE_FIRED" and data.get("routine") in out:
            out[data["routine"]]["fired"].append(
                {"slot": data.get("slot"), "tasks": data.get("tasks"),
                 "seq": ev.get("seq", i), "by": ev.get("actor"), "at": ev.get("ts")})
    return out


def fired_slots(routine: dict) -> set[str]:
    return {f["slot"] for f in routine.get("fired") or []}


def due(routines: dict[str, dict], now: datetime) -> list[dict]:
    """Enabled routines whose latest scheduled slot since their last
    definition hasn't fired yet. At most one slot per routine: a scheduler
    that was down for a week catches up once, not seven times."""
    out = []
    for rid, r in sorted(routines.items()):
        if not r.get("enabled"):
            continue
        slot = latest_slot(parse_cron(r["cron"]), parse_time(r["revised_at"]), now)
        if slot and slot_id(slot) not in fired_slots(r):
            out.append({"routine": rid, "slot": slot_id(slot)})
    return out


def instantiate(spec: dict, slot: str) -> dict:
    """The routine's spec with every task id made unique to this slot, so a
    second occurrence never collides with the first's tasks (or branches,
    which worker.ensure_worktree derives from the id's last segment)."""
    stamp = re.sub(r"\D", "", slot)
    ids = {t["id"]: f"{t['id']}-{stamp}" for t in spec["tasks"]}
    tasks = []
    for t in spec["tasks"]:
        t = dict(t, id=ids[t["id"]])
        if t.get("depends_on"):
            t["depends_on"] = [ids.get(d, d) for d in t["depends_on"]]
        tasks.append(t)
    return {**spec, "tasks": tasks}


# --- writing ----------------------------------------------------------------

def define(company_root: Path, *, actor: str, data: dict) -> dict:
    """Validate and append one ROUTINE_DEFINED. ROUTINE_FIRED is written by
    `company routine fire` alone (`company event` refuses both)."""
    log = EventLog(company_root)
    ev = make_event(event="ROUTINE_DEFINED", actor=actor, project=ORG_PROJECT, data=data)
    validate(ev)
    parse_cron(data["cron"])
    if data["id"] in fold(log.read()) and not str(data.get("reason") or "").strip():
        raise ValueError(f"routine {data['id']!r} is already defined — redefining it "
                         f"requires a reason")
    return log.append(ev)
