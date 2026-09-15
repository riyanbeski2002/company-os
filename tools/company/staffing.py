"""Staffing engine (D4, D9): the risk table runs first, and it cannot be argued with.

Gate selection is a pure table lookup over the request text and the paths a
task touches. The PM may only ever ADD gates beyond what this produces, and
only with a recorded reason — never subtract one. That is what makes identical
requests produce identical mandatory staffing, and what means nobody has to
remember to ask for a security review.

`fast_path` (D9, efficiency addendum v1) is the same principle pointed the
other way: a request with zero trigger hits and a small enough predicted diff
is Tier 0 by default, not a judgment call. Escalating past it needs the same
recorded reason a gate addition needs.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pathrules

PLUGIN_CONFIG = Path(__file__).resolve().parents[2] / "config"


def load_config(company_root: Path, name: str) -> dict:
    """Repo config wins; the plugin default is the fallback."""
    import yaml
    for candidate in (Path(company_root) / "config" / name, PLUGIN_CONFIG / name):
        if candidate.exists():
            return yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    raise FileNotFoundError(f"no config {name!r} in repo or plugin defaults")


def _keyword_hit(text: str, keywords) -> str | None:
    lowered = text.lower()
    for kw in keywords or ():
        if re.search(rf"(?<![a-z0-9]){re.escape(kw.lower())}(?![a-z0-9])", lowered):
            return kw
    return None


def _path_hit(paths, patterns) -> str | None:
    for path in paths or ():
        # A task declares owned globs, not concrete files. Compare glob-to-glob
        # by testing the pattern against the glob with its wildcards stripped.
        probe = path.replace("**", "x").replace("*", "x")
        for pattern in patterns or ():
            if pathrules.matches(probe, pattern) or pathrules.matches(probe.rstrip("/x"), pattern):
                return path
    return None


def evaluate(config: dict, request: str = "", paths=None,
             files_touched: int | None = None, diff_lines: int | None = None) -> dict:
    """Return the mandatory gates and which triggers produced them.

    Deterministic: same inputs, same output, every time.

    `files_touched`/`diff_lines` are optional (D9, efficiency addendum v1).
    When given, and no trigger fired, and both are within the configured
    `fast_path` bounds, the result recommends Tier 0 — the PM does it
    inline, no staffing pipeline. Omitting them (the default) leaves
    tier recommendation unset; only the gate lookup runs, exactly as before.
    """
    fired = []
    gates: list[str] = []

    for trigger in config.get("triggers", []):
        kw = _keyword_hit(request, trigger.get("keywords"))
        ph = _path_hit(paths, trigger.get("paths"))
        if not (kw or ph):
            continue
        fired.append({
            "trigger": trigger["name"],
            "matched_keyword": kw,
            "matched_path": ph,
            "gates": trigger.get("gates", []),
        })
        for gate in trigger.get("gates", []):
            if gate not in gates:
                gates.append(gate)

    for gate in config.get("baseline_gates", []):
        if gate not in gates:
            gates.append(gate)

    fp = config.get("fast_path") or {}
    fast_path = False
    recommended_tier = None
    if fp.get("enabled") and not fired and files_touched is not None and diff_lines is not None:
        if files_touched <= fp.get("max_files_touched", 0) and diff_lines <= fp.get("max_diff_lines", 0):
            fast_path = True
            recommended_tier = 0

    return {"gates": gates, "triggers_fired": fired,
            "fast_path": fast_path, "recommended_tier": recommended_tier}


def order_gates(gates, quality_gates: dict) -> list[str]:
    order = quality_gates.get("order", [])
    return sorted(gates, key=lambda g: order.index(g) if g in order else len(order))


def reconcile(proposed_gates, mandatory_gates, reason: str | None = None) -> tuple[list[str], list[str]]:
    """Merge the PM's proposal with the table's mandate.

    Returns (final_gates, additions). Anything the table mandates is present in
    the result whether the PM asked for it or not. Anything the PM added beyond
    the table is kept only if a reason was recorded.
    """
    final = list(mandatory_gates)
    additions = []
    for gate in proposed_gates or ():
        if gate not in final:
            if not reason:
                continue  # an addition without a recorded reason is dropped
            final.append(gate)
            additions.append(gate)
    return final, additions


# --- default grouped gating (cost audit, 2026-09-14) -------------------------
#
# `gategroup.py` already lets several tasks share one gate launch instead of
# one each, but it only ever fired when a PM remembered to set `gate_group`
# on every task by hand — measured the same day: gate roles were 66 of 99
# launches and 64% of the day's cache_creation tokens, almost entirely because
# grouping stayed opt-in. This makes it the default instead: tasks planned
# together in one `company plan` call are gated together in one call too,
# the same way `reconcile()` above already makes every OTHER staffing
# decision the table's by default, not the PM's to remember.
#
# A task only stays solo if it explicitly says so, with a reason — the same
# "an override without a recorded reason is dropped" rule `reconcile()` uses,
# just pointed at opting OUT instead of in.

def default_gate_group(planned_tasks: list[dict], project: str) -> tuple[str | None, list[str]]:
    """Assign one shared `gate_group` to every eligible task in a plan batch.

    Eligible: Tier 2, carries at least one mandatory gate, didn't already
    arrive with its own `gate_group` (a PM's explicit grouping is never
    overridden), and isn't opted out via `solo_gate: true` with a
    `solo_gate_reason` (opting out without a reason is ignored, same as
    `reconcile()` ignores an ungated addition without one).

    Returns (group_id, task_ids_assigned). group_id is None when fewer than
    2 tasks are eligible — grouping 1 task has nothing to batch, and
    `cmd_gate_group` already refuses a group that small; that task stays on
    the solo `company run` path, which is correct, not a fallback failure.

    The id is deterministic (project + sorted task ids), not random: running
    `company plan` again over the same task set reproduces the same group
    instead of minting a new one every time.
    """
    eligible = [
        t for t in planned_tasks
        if int(t.get("tier") or 0) == 2
        and t.get("gates")
        and not t.get("gate_group")
        and not (t.get("solo_gate") and t.get("solo_gate_reason"))
    ]
    if len(eligible) < 2:
        return None, []

    digest = hashlib.sha1(
        "|".join(sorted(t["id"] for t in eligible)).encode("utf-8")
    ).hexdigest()[:8]
    group_id = f"{project}-plan-{digest}"
    task_ids = []
    for t in eligible:
        t["gate_group"] = group_id
        task_ids.append(t["id"])
    return group_id, task_ids


# --- model/effort policy (D11) -----------------------------------------------

def model_policy(config: dict, tier: int, gated: bool, role: str | None = None) -> dict:
    """Look up the model/effort/thinking row for a launch.

    `config` is staffing.yaml's full document (`policy` + optional
    `role_overrides`). `gated` means the task carries at least one
    risk-trigger gate (review alone from a PM-added reason still counts) —
    only a genuinely gated Tier-2 task gets the expensive row. Falls back to
    the Tier-1 row for anything the table doesn't name, since that's the
    conservative middle ground rather than silently going cheap.

    `role_overrides` (2026-08-25, cost audit — `company costs`: code-reviewer
    and qa-engineer were the two largest gate-cost lines, both riding the
    same tier2_gated row security-reviewer uses) lets a specific role sit on
    a cheaper effort than its tier/gated row would otherwise give it, without
    touching that row for every OTHER role that shares it. Only fields the
    override actually names are changed — everything else (model, thinking)
    stays whatever the base row said, so an override can't silently also
    change the model.
    """
    policy = (config or {}).get("policy", {})
    if tier == 2:
        key = "tier2_gated" if gated else "tier2_ungated"
    elif tier == 0:
        key = "tier0"
    else:
        key = "tier1"  # covers tier 1 and any tier the table doesn't name
    base = dict(policy.get(key) or policy.get("tier1") or {})

    overrides = (config or {}).get("role_overrides", {}) or {}
    if role and role in overrides:
        base.update(overrides[role])
    return base


# --- duplicate staffing detection (cost audit, 2026-09-14) ------------------
#
# finos-5a, real incident: the same admin-self-attach fix was staffed three
# separate times across three waves under three different task ids — one
# gated and merged, two produced nothing. `company plan`/`staff` had no
# cross-wave check for "this title already exists somewhere, check status
# before staffing" — the only reason it surfaced was a worker refusing to
# fabricate a pass on an empty branch and writing an honest handoff instead.
# That's the system working by luck of a conscientious worker, not by
# tooling — this is the tooling.

RESOLVED_STATUSES = {"DONE", "MERGED", "ABANDONED", "FAILED"}
DUPLICATE_TITLE_THRESHOLD = 0.6


def _title_tokens(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (title or "").lower()) if len(w) > 2}


def _title_similarity(a: str, b: str) -> float:
    """Jaccard similarity over normalized title tokens. Deliberately crude —
    this is a check-before-staffing nudge, not a semantic dedup system, so a
    cheap deterministic measure that's easy to reason about beats a fancier
    one that isn't."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def find_duplicate_staffing(planned_tasks: list[dict], existing_tasks: list[dict],
                             threshold: float = DUPLICATE_TITLE_THRESHOLD) -> list[dict]:
    """Newly planned tasks whose title closely matches a still-live existing
    task's title. Not a hard block by itself — `cmd_plan` decides whether to
    refuse or just warn — this only finds the candidates, deterministically,
    same inputs same output, like every other check in this file.
    """
    live = [t for t in existing_tasks if t.get("status") not in RESOLVED_STATUSES]
    hits = []
    for new_task in planned_tasks:
        new_title = new_task.get("title", "")
        if not new_title:
            continue
        for existing in live:
            if existing.get("id") == new_task.get("id"):
                continue  # replanning the same task id is not a duplicate
            sim = _title_similarity(new_title, existing.get("title", ""))
            if sim >= threshold:
                hits.append({
                    "new_task": new_task["id"], "new_title": new_title,
                    "existing_task": existing["id"], "existing_title": existing.get("title"),
                    "existing_status": existing.get("status"),
                    "similarity": round(sim, 2),
                })
    return hits


# --- overlap prediction -----------------------------------------------------

def predict_overlap(tasks: list[dict]) -> list[dict]:
    """Find pairs of tasks whose owned globs intersect.

    Computed before launching parallel work. Overlap means sequence the tasks or
    split ownership explicitly — never launch and hope.
    """
    collisions = []
    for i, a in enumerate(tasks):
        for b in tasks[i + 1:]:
            shared = _glob_intersections(a.get("owned_globs"), b.get("owned_globs"))
            if shared:
                collisions.append({
                    "tasks": [a["id"], b["id"]],
                    "overlapping_globs": shared,
                })
    return collisions


def _glob_intersections(a_globs, b_globs) -> list[str]:
    shared = []
    for a in a_globs or ():
        for b in b_globs or ():
            if a == b:
                shared.append(a)
                continue
            a_probe = a.replace("**", "x").replace("*", "x").rstrip("/x")
            b_probe = b.replace("**", "x").replace("*", "x").rstrip("/x")
            if pathrules.matches(a_probe, b) or pathrules.matches(b_probe, a):
                shared.append(f"{a} ∩ {b}")
    return sorted(set(shared))


# --- team sizing ------------------------------------------------------------

# (min_tier2_workers, name, concurrency cap, typical shape)
SIZE_BANDS = [
    (0, "trivial", 0, "PM inline — Tier 0"),
    (1, "small", 1, "one specialist, Tier-1 review"),
    (2, "medium", 4, "pod plus Tier-1 QA and review"),
    (5, "large", 7, "pod with contracts published first"),
    (8, "program", 7, "multiple pods, staged; leads only if they reduce coordination"),
]


def size_band(tier2_count: int) -> dict:
    name, cap, shape = SIZE_BANDS[0][1:]
    for threshold, band_name, band_cap, band_shape in SIZE_BANDS:
        if tier2_count >= threshold:
            name, cap, shape = band_name, band_cap, band_shape
    return {"size": name, "shape": shape, "tier2_cap": cap}
