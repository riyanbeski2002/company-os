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


def _all_presentational(paths, presentational_patterns) -> bool:
    """True only when every owned path matches a presentational pattern —
    and there's at least one path to judge at all. No paths (the common case
    for a request text with no declared owned_globs yet) can't be judged
    presentational and must not be treated as if it were; that would make
    the exemption fire on strictly less evidence than today's behavior,
    the opposite of the conservative direction this is supposed to err in.
    """
    if not paths or not presentational_patterns:
        return False
    for path in paths:
        probe = path.replace("**", "x").replace("*", "x")
        if not any(pathrules.matches(probe, pattern) or pathrules.matches(probe.rstrip("/x"), pattern)
                   for pattern in presentational_patterns):
            return False
    return True


def evaluate(config: dict, request: str = "", paths=None,
             files_touched: int | None = None, diff_lines: int | None = None) -> dict:
    """Return the mandatory gates and which triggers produced them.

    Deterministic: same inputs, same output, every time.

    `files_touched`/`diff_lines` are optional (D9, efficiency addendum v1).
    When given, and no trigger fired, and both are within the configured
    `fast_path` bounds, the result recommends Tier 0 — the PM does it
    inline, no staffing pipeline. Omitting them (the default) leaves
    tier recommendation unset; only the gate lookup runs, exactly as before.

    `presentational_paths` context downgrade (Riyan, 2026-10-19 — "a UI
    landing page with 'auth' written... should not trigger security, waste
    of effort"): a keyword-only hit (no path corroboration for that specific
    trigger) on a task whose OWNED PATHS are entirely presentational content
    — copy, marketing text, landing pages — is downgraded rather than forced.
    Still fully deterministic and still fail-safe in every direction that
    matters: a real path hit (the keyword also matches the trigger's own
    `paths` list) is never downgraded regardless of content; a task with no
    declared paths at all is never downgraded (nothing to judge
    presentational from); and a downgrade is always recorded in
    `downgraded_triggers` with its evidence, never silently dropped — the PM
    can still add the gate back with a reason, same as it could add any
    gate the table didn't mandate. This is the table declining to fire on
    specifically-scoped, auditable grounds, not a judgment call overriding it.
    """
    fired = []
    downgraded = []
    gates: list[str] = []
    presentational = config.get("presentational_paths") or []

    for trigger in config.get("triggers", []):
        kw = _keyword_hit(request, trigger.get("keywords"))
        ph = _path_hit(paths, trigger.get("paths"))
        if not (kw or ph):
            continue
        if kw and not ph and _all_presentational(paths, presentational):
            downgraded.append({
                "trigger": trigger["name"], "matched_keyword": kw,
                "owned_paths": list(paths or []),
                "reason": "keyword matched only in request text, and every owned "
                          "path is presentational content — no path corroborated "
                          "real implementation for this trigger",
            })
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

    return {"gates": gates, "triggers_fired": fired, "downgraded_triggers": downgraded,
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


# --- cross-plan-call gate joining --------------------------------------------
#
# default_gate_group() above only merges tasks staffed in the SAME `company
# plan` call — resolve-os, 2026-09-16/17 (wecare/vendor-payment-automation):
# 18 tasks staffed across 6 separate plan calls in ~29 hours produced 6
# gate_groups, each its own PR, because every call only ever looked at its
# own batch. Two pairs overlapped the exact same owned files across calls
# (IAM-7 vs. an earlier wave's move-ticket.ts; a later VP-11 vs. an earlier
# vp-document-classification's slack.ts/cards.ts/ticket-actions.ts) and still
# got separate PRs — one pair only avoided it because a human noticed and
# hand-merged two branches after the fact.

JOINABLE_STATUSES = {"DRAFT", "PLANNED", "READY", "IN_PROGRESS", "IMPLEMENTATION_READY"}


def join_existing_gate_groups(planned_tasks: list[dict],
                              existing_tasks: list[dict]) -> list[dict]:
    """Attach a newly planned task to an existing task's still-open gate_group
    when they share owned files, instead of minting a new group for it.

    A candidate group must still be OPEN: none of its member tasks may have
    reached REVIEW or beyond. A PASSED verdict is bound to the exact commit
    it reviewed (see eventlog._rejects_stale_gate_verdict) — joining a new
    diff into an already-gated group would invalidate that verdict, not
    extend it, so this only ever reaches into work that hasn't been gated
    yet.

    Runs before default_gate_group(), which already skips any task that
    already carries a gate_group — so a task that joins here is simply no
    longer eligible for a fresh batch group of its own. Only the first
    matching candidate is used per task, ties broken by task id so this is
    deterministic across reruns like everything else in this file.
    """
    joined = []
    for new_task in planned_tasks:
        if (new_task.get("gate_group")
                or int(new_task.get("tier") or 0) != 2
                or not new_task.get("owned_globs")):
            continue
        candidates = sorted(
            (t for t in existing_tasks
             if t.get("project") == new_task.get("project")
             and t.get("gate_group")
             and t.get("status") in JOINABLE_STATUSES
             and t.get("id") != new_task.get("id")),
            key=lambda t: t["id"],
        )
        for existing in candidates:
            if _glob_intersections(new_task.get("owned_globs"), existing.get("owned_globs")):
                new_task["gate_group"] = existing["gate_group"]
                joined.append({"task": new_task["id"], "matched_task": existing["id"],
                               "joined_group": existing["gate_group"]})
                break
    return joined


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
    return _title_matches(planned_tasks, live, threshold)


def find_similar_resolved_work(planned_tasks: list[dict], existing_tasks: list[dict],
                               threshold: float = DUPLICATE_TITLE_THRESHOLD) -> list[dict]:
    """The other half of `find_duplicate_staffing`: newly planned tasks whose
    title closely matches an already-RESOLVED task's. Restaffing shipped or
    abandoned work is legitimate, so this is informational only — it never
    feeds a refusal — but "this was done before, and ended MERGED/FAILED" is
    worth seeing before the work starts, not after. Live tasks are left to
    `find_duplicate_staffing`; the two never report the same pair.
    """
    resolved = [t for t in existing_tasks if t.get("status") in RESOLVED_STATUSES]
    hits = _title_matches(planned_tasks, resolved, threshold)
    goals_by_task = {t["id"]: t["goal"] for t in resolved if t.get("goal")}
    for hit in hits:
        if hit["existing_task"] in goals_by_task:
            hit["existing_goal"] = goals_by_task[hit["existing_task"]]
    return hits


def _title_matches(planned_tasks: list[dict], candidates: list[dict],
                   threshold: float) -> list[dict]:
    hits = []
    for new_task in planned_tasks:
        new_title = new_task.get("title", "")
        if not new_title:
            continue
        for existing in candidates:
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


# Lesson text is prose, not a title: a Jaccard score against a whole
# pattern + fix paragraph is diluted to near zero by length alone. So the
# measure here is how much of the NEW TITLE the lesson talks about, with a
# floor on shared words so a one-word title can't match everything. Function
# words — and generic task verbs every lesson's fix text uses — are dropped
# first, or "fix the ..." would match every lesson ever recorded.
LESSON_MATCH_THRESHOLD = 0.5
LESSON_MATCH_MIN_SHARED = 2
_LESSON_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "not", "are",
    "was", "were", "but", "has", "have", "had", "its", "all", "any", "can",
    "when", "then", "than", "them", "they", "what", "which", "who", "will",
    "would", "should", "could", "also", "only", "just", "each", "every",
    "fix", "fixed", "add", "added", "bug", "task", "update", "updated",
}


def find_matching_lessons(planned_tasks: list[dict], lessons: list[dict],
                          threshold: float = LESSON_MATCH_THRESHOLD,
                          min_shared: int = LESSON_MATCH_MIN_SHARED) -> list[dict]:
    """Recorded lessons (`lessons.fold` output) whose pattern/fix text shares
    meaningful words with a newly planned task's title. `lessons.fold` can
    only be queried by exact `skill` tag; this is the "has this mistake been
    made before?" check by content, at the one moment it's cheapest to act on.
    Informational, never a refusal. Same crude, deterministic spirit as
    `_title_similarity`."""
    hits = []
    for new_task in planned_tasks:
        title_words = _title_tokens(new_task.get("title", "")) - _LESSON_STOPWORDS
        if not title_words:
            continue
        for lesson in lessons:
            lesson_words = _title_tokens(
                f"{lesson.get('pattern') or ''} {lesson.get('fix') or ''}")
            shared = title_words & lesson_words
            overlap = len(shared) / len(title_words)
            if len(shared) >= min_shared and overlap >= threshold:
                hits.append({
                    "new_task": new_task["id"], "new_title": new_task.get("title"),
                    "lesson": lesson.get("id"), "pattern": lesson.get("pattern"),
                    "fix": lesson.get("fix"), "shared_words": sorted(shared),
                    "overlap": round(overlap, 2),
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


def config_drift(repo: Path, root: Path) -> list[str]:
    """`company doctor`'s self-hosted-only check: `.company/config/<name>.yaml`
    is this repo's own OPERATIVE copy (`load_config` above checks it before
    falling back to the plugin's own `config/<name>.yaml`) — for any OTHER
    onboarded repo that's deliberate per-repo customization, but for
    company-os's own checkout the two are supposed to be the same source of
    truth, and a silent divergence means a policy fix never actually took
    effect here.

    Real incident, found 2026-10-19: `config/risk-triggers.yaml` got
    "Restore review as a baseline gate" on 2026-09-15 (a direct fix for
    untriggered tasks shipping with zero review) — `.company/config/
    risk-triggers.yaml` never received it, so this repo ran with no baseline
    review gate for roughly five weeks after the fix was believed to be
    live. Byte comparison only, not semantic — a reordered-but-equivalent
    YAML file still counts as drifted, which is the conservative direction
    to be wrong in here.
    """
    drifted = []
    for cfg in sorted((repo / "config").glob("*.yaml")):
        repo_copy = root / "config" / cfg.name
        if repo_copy.is_file() and repo_copy.read_bytes() != cfg.read_bytes():
            drifted.append(cfg.name)
    return drifted
