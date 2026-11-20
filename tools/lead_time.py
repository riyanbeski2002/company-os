#!/usr/bin/env python3
"""Lead time per merged task, by creation cohort, with idle time attributed.

FIRST-PRINCIPLES-REVIEW Part 4 #1. Reproduces the review's numbers from an
event log instead of hand computation. Stdlib only, read-only.

    python3 tools/lead_time.py /path/to/repo/.company/events/events.jsonl [--json]

For each task with a MERGED event, the wall-clock time from TASK_CREATED to its
first MERGED is split into four buckets. Each moment counts once, in priority
order:
  busy        a worker or gate is running on the task (WORKER_STARTED..EXITED;
              a gate-group launch counts for every task in data.tasks)
  riyan       an escalation that names this task is open (with --upper-bound,
              ALSO any open blocking escalation that names no task, counted
              against every task: most escalations aren't task-tagged, so the
              truth lies between the default and the upper bound)
  dependency  the task is in DEPENDENCY_WAITING (until its next WORKER_STARTED)
  nobody      none of the above
Rework, per merged task: implementer launches, gate launches, failed verdicts.
Cohort = the month the task was CREATED (not the month it merged): per-month
launches/merges ratios count work in flight as waste.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import statistics

GATE_ROLES = {"code-reviewer", "qa-engineer", "security-reviewer"}
IMPL_ROLES = {"backend-engineer", "frontend-engineer", "video-editor"}
FAILED = {"REVIEW_FAILED", "QA_FAILED", "SECURITY_REVIEW_FAILED"}


def ts(s: str) -> float:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def task_of(e: dict):
    return e.get("task") or (e.get("data") or {}).get("task")


def load(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # torn tail; the CLI refuses it, we just skip it
    return sorted(out, key=lambda e: e.get("seq", 0))


def intervals(events: list[dict], upper: bool = False):
    """Per task: lists of (start, end) for busy, riyan, dependency."""
    busy = collections.defaultdict(list)
    riyan = collections.defaultdict(list)
    dep = collections.defaultdict(list)
    running = {}      # actor -> (start, [tasks])
    esc_open = {}     # esc id -> (start, task, blocking)
    global_riyan = []  # untagged blocking escalations (upper bound only)
    dep_open = {}     # task -> start
    end_of_log = ts(events[-1]["ts"]) if events else 0.0
    for e in events:
        t, d, name = ts(e["ts"]), e.get("data") or {}, e["event"]
        if name == "WORKER_STARTED":
            tasks = [task_of(e)] if task_of(e) else list(d.get("tasks") or [])
            running[e["actor"]] = (t, tasks)
            for k in tasks:
                if k in dep_open:
                    dep[k].append((dep_open.pop(k), t))
        elif name == "WORKER_EXITED" and e["actor"] in running:
            start, tasks = running.pop(e["actor"])
            for k in tasks:
                busy[k].append((start, t))
        elif name == "ESCALATION_RAISED" and d.get("id"):
            esc_open[d["id"]] = (t, task_of(e), bool(d.get("blocking")),
                                 bool(d.get("project_wide")))
        elif name == "ESCALATION_RESOLVED" and d.get("id") in esc_open:
            start, k, blk, pw = esc_open.pop(d["id"])
            if k:
                riyan[k].append((start, t))
            elif pw or (blk and upper):  # explicitly project-wide counts in both bounds
                global_riyan.append((start, t))
        elif name == "DEPENDENCY_WAITING" and task_of(e):
            dep_open.setdefault(task_of(e), t)
    for start, k, blk, pw in esc_open.values():
        if k:
            riyan[k].append((start, end_of_log))
        elif pw or (blk and upper):
            global_riyan.append((start, end_of_log))
    if global_riyan:
        for k in set(busy) | set(riyan) | set(dep) | {task_of(e) for e in events if task_of(e)}:
            riyan[k].extend(global_riyan)
    for k, start in dep_open.items():
        dep[k].append((start, end_of_log))
    return busy, riyan, dep


def covered(ivs, lo, hi, minus=()):
    """Seconds of [lo, hi] covered by ivs and not by any interval in minus."""
    pts = sorted((max(a, lo), min(b, hi)) for a, b in ivs if b > lo and a < hi)
    merged = []
    for a, b in pts:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    total = 0.0
    minus = union(minus)
    for a, b in merged:
        total += b - a
        for x, y in minus:
            total -= max(0.0, min(b, y) - max(a, x))
    return max(0.0, total)


def union(*lists):
    pts = sorted(p for l in lists for p in l)
    out = []
    for a, b in pts:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def analyse(events: list[dict], upper: bool = False) -> dict:
    created, merged = {}, {}
    impl = collections.Counter(); gates = collections.Counter(); fails = collections.Counter()
    for e in events:
        k, d = task_of(e), e.get("data") or {}
        if e["event"] == "TASK_CREATED" and k:
            created.setdefault(k, e["ts"])
        elif e["event"] == "MERGED" and k:
            merged.setdefault(k, e["ts"])
        elif e["event"] == "WORKER_STARTED":
            tasks = [k] if k else list(d.get("tasks") or [])
            for x in tasks:
                if d.get("role") in GATE_ROLES:
                    gates[x] += 1
                elif d.get("role") in IMPL_ROLES:
                    impl[x] += 1
        elif e["event"] in FAILED and k:
            fails[k] += 1
    busy, riyan, dep = intervals(events, upper)
    cohorts = collections.defaultdict(list)
    for k, m in merged.items():
        if k not in created or m < created[k]:
            continue
        lo, hi = ts(created[k]), ts(m)
        lead = hi - lo
        b = covered(busy[k], lo, hi)
        r = covered(riyan[k], lo, hi, minus=busy[k])
        dp = covered(dep[k], lo, hi, minus=union(busy[k], riyan[k]))
        nobody = max(0.0, lead - b - r - dp)
        cohorts[created[k][:7]].append({
            "lead_h": lead / 3600, "busy": b, "riyan": r, "dep": dp, "nobody": nobody,
            "impl": impl[k], "gates": gates[k], "fails": fails[k]})
    report = {}
    for month, rows in sorted(cohorts.items()):
        tot = sum(x["lead_h"] for x in rows) * 3600 or 1.0
        leads = sorted(x["lead_h"] for x in rows)
        report[month] = {
            "merged_tasks": len(rows),
            "lead_h_p50": round(statistics.median(leads), 1),
            "lead_h_p90": round(leads[int(0.9 * (len(leads) - 1))], 1),
            # time-weighted shares of all lead time in the cohort
            "share_busy_pct": round(100 * sum(x["busy"] for x in rows) / tot, 1),
            "share_riyan_pct": round(100 * sum(x["riyan"] for x in rows) / tot, 1),
            "share_dependency_pct": round(100 * sum(x["dep"] for x in rows) / tot, 1),
            "share_nobody_pct": round(100 * sum(x["nobody"] for x in rows) / tot, 1),
            "impl_launches_per_task": round(statistics.mean(x["impl"] for x in rows), 2),
            "gate_launches_per_task": round(statistics.mean(x["gates"] for x in rows), 2),
            "failed_verdicts_per_task": round(statistics.mean(x["fails"] for x in rows), 2),
        }
    unmerged = {m: 0 for m in report}
    for k, c in created.items():
        if k not in merged:
            unmerged[c[:7]] = unmerged.get(c[:7], 0) + 1
    for m, n in unmerged.items():
        report.setdefault(m, {})["created_not_merged"] = n
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("events")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--upper-bound", action="store_true",
                    help="count untagged blocking escalations against every task")
    a = ap.parse_args()
    rep = analyse(load(a.events), a.upper_bound)
    if a.json:
        print(json.dumps(rep, indent=2))
        return
    cols = ["merged_tasks", "created_not_merged", "lead_h_p50", "lead_h_p90", "share_busy_pct",
            "share_riyan_pct", "share_dependency_pct", "share_nobody_pct",
            "impl_launches_per_task", "gate_launches_per_task", "failed_verdicts_per_task"]
    print("cohort  " + "  ".join(c.replace("_pct", "%").replace("_per_task", "/task") for c in cols))
    for m, r in rep.items():
        print(f"{m}  " + "  ".join(str(r.get(c, "-")) for c in cols))


if __name__ == "__main__":
    main()
