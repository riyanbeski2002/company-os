# ADR-003 — Grouped gating: one gate launch for several tasks sharing a core

- **Status**: accepted
- **Date**: 2026-08-24
- **Decided by**: Riyan ("not every tasks deserves it's own gate... one
  review pass instead of 3", then "not limited to 3 into one group — can be
  5, can be 10 as well")

## Context

ADR-002 cut the cost of a gate launch (sonnet not opus, real patch embedded
instead of rediscovered) but didn't reduce *how many* launches a related set
of tasks triggers — a dependency chain like IAM design → IAM UI → onboarding
still paid for 3 (or 9, if all three trip review+qa+security) independent
gate launches, each seeing only its own slice of one feature.

## Decision

A task may carry a `gate_group` (arbitrary string, no size limit). Tasks
sharing one still implement, commit, and test independently — nothing about
`company plan`/`company staff`/`company run` changes. Gating changes:
`company gate-group <group> --role <role>` replaces N separate
`company run --role <role>` calls with one, reviewing every group member's
combined diff at once.

Mechanically: `gategroup.build_group_review()` rebuilds a throwaway worktree
from scratch on every call (never reused — a stale merge after a FAILED
verdict sent a task back for rework would review superseded code) and merges
each task's branch into it, same `git merge --no-ff` `integrate.py` already
uses for one branch, just extended to N. A merge conflict refuses the whole
group launch outright — v1 does not attempt automatic conflict resolution or
reordering. The combined diff is embedded via the same bounded
`git diff`-or-`--stat` fallback ADR-002 introduced for solo gates
(`gitutil.diff_patch_or_stat`, shared by both call sites now).

**The Evidence Rule does not change.** Each task in the group still needs
its own `REVIEW_PASSED`/`QA_PASSED`/`SECURITY_REVIEW_PASSED` event,
authored by someone other than its owner — `taskstate.check_done()` is
untouched. The group packet instructs the launched worker to emit one
verdict per task, and `worker.launch_group()` checks after exit that every
task actually got one (reusing `gave_no_verdict()` unchanged, per task) —
any task that didn't is `GATE_NO_VERDICT`, identical to a solo gate that
exits with no verdict, never silently covered because a sibling in the group
was reviewed.

## Scope, v1

Sequential / dependency-chain groups only. Tasks are merged in the order
found (task-creation order, or an explicit `--tasks` order) — this is not a
topological merge of genuinely parallel siblings with disjoint history, and
a group whose members don't merge cleanly in that order refuses rather than
guessing at a resolution. No upper bound on group size (Riyan: 5, 10, or
more) — the only practical limit is the packet's existing ~2000-token budget,
which a very large combined diff will hit exactly like a single large task
would, forcing the same "split it" response as always.

## Verified

Full unit coverage in `tests/test_gategroup.py` (merge success, merge
conflict names the right task, rebuild-from-scratch discards stale state,
diff-patch bound and fallback, missing-verdict detection, packet rendering
and its own budget enforcement) plus a live end-to-end run against two
throwaway git repos: a 3-task conflicting case (correctly refused, logged a
real `TASK_BLOCKED` event) and a 3-task non-conflicting case (merged cleanly,
produced a 534-token packet embedding all three real patches). 321/321 tests
pass (15 new).
