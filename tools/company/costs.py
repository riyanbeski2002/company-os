"""Consumption reporting (`company costs`) — pure aggregation over the event
log, kept separate from cli.py's argparse/emit plumbing so it's directly
testable (same discipline as staffing.evaluate/taskstate.check_done).

Task-level and turn-level attribution (donor review, 2026-10-19 —
cfo-advisor's own finding: a raw cache-read total and one aggregate
cache-read-to-output ratio can't tell a genuinely thorough run apart from one
that re-reads redundantly per turn, and can't say what any ONE task actually
cost). `aggregate`'s `by_task` splits a run's cost evenly across every task
it touched — exact for a normal single-task launch, an explicit, labelled
estimate for a gate-group run covering several tasks at once (there's no way
to know a group's real per-task split, so this doesn't pretend to). Each
`by_actor` entry adds `avg_cache_read_per_turn`/`avg_output_per_turn` once
`num_turns` was captured for at least one of its runs — a turn count
normalizes for how much work a run actually did, in a way the old
output-token denominator couldn't, since a short, narrow run and a long,
thorough one can land on the same aggregate ratio for different reasons.
"""

from __future__ import annotations


def aggregate(events: list[dict], project: str | None = None) -> dict:
    by_actor: dict[str, dict] = {}
    by_task: dict[str, dict] = {}
    untasked = {"runs": 0, "output_tokens": 0, "cache_read_tokens": 0,
                "seconds": 0.0, "usd_equivalent": 0.0}
    totals = {"output": 0, "input": 0, "cache_read": 0, "cache_creation": 0}
    estimate = 0.0
    seconds = 0.0

    for ev in events:
        if ev.get("event") != "WORKER_EXITED":
            continue
        if project and ev.get("project") != project:
            continue
        data = ev.get("data") or {}
        # `cost_usd` is the pre-V2 field name; read both so old logs still fold.
        cost = data.get("cost_usd_estimate", data.get("cost_usd"))
        tokens = data.get("tokens") or {}
        if cost is None and not tokens:
            continue
        num_turns = data.get("num_turns")
        elapsed = data.get("elapsed_s") or 0

        entry = by_actor.setdefault(ev["actor"], {
            "runs": 0, "output_tokens": 0, "cache_read_tokens": 0,
            "seconds": 0.0, "usd_equivalent": 0.0, "tasks": [],
            "turns": 0, "runs_missing_turns": 0,
            "_output_with_turns": 0, "_cache_read_with_turns": 0})
        entry["runs"] += 1
        entry["output_tokens"] += tokens.get("output", 0)
        entry["cache_read_tokens"] += tokens.get("cache_read", 0)
        entry["seconds"] = round(entry["seconds"] + elapsed, 1)
        entry["usd_equivalent"] = round(entry["usd_equivalent"] + (cost or 0), 4)
        if ev.get("task") and ev["task"] not in entry["tasks"]:
            entry["tasks"].append(ev["task"])
        if num_turns:
            # The per-turn average's numerator must come ONLY from runs that
            # actually reported a turn count — mixing in a pre-capture run's
            # tokens (counted in output_tokens/cache_read_tokens above, but
            # with no turns to divide by) would silently inflate the average
            # with uncounted tokens, the exact kind of misleading signal this
            # feature exists to replace.
            entry["turns"] += num_turns
            entry["_output_with_turns"] += tokens.get("output", 0)
            entry["_cache_read_with_turns"] += tokens.get("cache_read", 0)
        else:
            entry["runs_missing_turns"] += 1

        # A normal launch() carries a single `task` on the event itself; a
        # gate-group run carries no `task` but a `tasks` list in data
        # (worker.py's launch_group — one review covering several tasks at
        # once); an advisor/readonly run carries neither, since it was never
        # staffed against a task at all.
        task_ids = [ev["task"]] if ev.get("task") else (data.get("tasks") or [])
        split = len(task_ids) or 1
        if task_ids:
            for tid in task_ids:
                tentry = by_task.setdefault(tid, {
                    "runs": 0, "output_tokens": 0, "cache_read_tokens": 0,
                    "seconds": 0.0, "usd_equivalent": 0.0, "actors": [],
                    "split_across_tasks": 1})
                tentry["runs"] += 1
                tentry["output_tokens"] += round(tokens.get("output", 0) / split)
                tentry["cache_read_tokens"] += round(tokens.get("cache_read", 0) / split)
                tentry["seconds"] = round(tentry["seconds"] + elapsed / split, 1)
                tentry["usd_equivalent"] = round(tentry["usd_equivalent"] + (cost or 0) / split, 4)
                if ev["actor"] not in tentry["actors"]:
                    tentry["actors"].append(ev["actor"])
                if split > 1:
                    tentry["split_across_tasks"] = max(tentry["split_across_tasks"], split)
        else:
            untasked["runs"] += 1
            untasked["output_tokens"] += tokens.get("output", 0)
            untasked["cache_read_tokens"] += tokens.get("cache_read", 0)
            untasked["seconds"] = round(untasked["seconds"] + elapsed, 1)
            untasked["usd_equivalent"] = round(untasked["usd_equivalent"] + (cost or 0), 4)

        for k in totals:
            totals[k] += tokens.get(k, 0)
        estimate += cost or 0
        seconds += elapsed

    for entry in by_actor.values():
        if entry["turns"]:
            entry["avg_cache_read_per_turn"] = round(entry["_cache_read_with_turns"] / entry["turns"])
            entry["avg_output_per_turn"] = round(entry["_output_with_turns"] / entry["turns"])
        del entry["_output_with_turns"], entry["_cache_read_with_turns"]

    runs = sum(e["runs"] for e in by_actor.values())
    return {
        "worker_runs": runs,
        "tokens": totals,
        "wall_clock_minutes": round(seconds / 60, 1),
        "api_equivalent_usd": round(estimate, 2),
        "by_actor": dict(sorted(by_actor.items(), key=lambda kv: -kv[1]["output_tokens"])),
        "by_task": dict(sorted(by_task.items(), key=lambda kv: -kv[1]["cache_read_tokens"])),
        "untasked": untasked,
    }
