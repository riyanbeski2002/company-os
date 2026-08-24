# Efficiency Addendum (v1) — implementation plan

Source: pasted addendum, "COMPANY OS — EFFICIENCY ADDENDUM (v1)". Mapped onto
the actual repo (README's prose principles ≈ the addendum's D1–D8; there is no
literal D-numbered doc in this repo).

## Resolved: D10 overrides the existing `baseline_gates: [review]` rule

Riyan confirmed the addendum overrides existing rules where they conflict.
`baseline_gates: [review]` (unconditional review on every staffed task) is
removed; review becomes risk-based, the same as qa/security. Adding it back
on an untriggered task is a scope addition and needs a recorded reason —
which `reconcile()` already enforces structurally for *any* gate addition
beyond the table's mandate, so this needs a config change, not new logic.

## What I'll actually build

1. **`fast_path` (D9)** — add to `config/risk-triggers.yaml` +
   `.company/config/risk-triggers.yaml`. Extend `staffing.evaluate()` to take
   optional `files_touched`/`diff_lines`; when in-bounds and no trigger
   fires, return `{"tier": 0, "gates": [], "fast_path": true}`. Backward
   compatible — existing callers that don't pass diff stats are unaffected
   (all current tests keep passing unmodified).
2. **Model/effort table (§2)** — new `config/staffing.yaml` +
   `.company/config/staffing.yaml`: tier → model/effort/thinking. Wire into
   `worker.py: build_command()` and `launch_readonly()` via `--model`
   `--effort`, and `MAX_THINKING_TOKENS=0` in `build_env()` for the
   mechanical/no-thinking case (no CLI flag for thinking exists — verified
   via `claude -p --help`).
3. **`cmd_gates` CLI surface** — add `--files-touched`/`--diff-lines` so the
   PM can actually call the fast-path check before staffing.
4. **§5 native-features mapping + §9/§10 policy** — document in README under
   a new `## Efficiency` section. Doc-only, no behavior claims not already true.
5. **PM hygiene checklist (§6) + D9 framing** — fold into
   `agents/company-pm.md`'s existing "Pick the cheapest tier" section.
6. **Tests** — extend `tests/test_staffing.py` for fast-path; run full suite.

## Review

Done. `python3 -m unittest discover -q tests` → 301 passed, 0 failed
(includes 12 new tests: fast-path bounds/trigger-suppression/unset-without-stats,
model-policy per tier, review-needs-a-reason). `company doctor` still green.
Manually verified `company gates` for all three cases (fast path hit, over
bounds, trigger fires) — output above matches design.

Also fixed in passing: `.company/config/risk-triggers.yaml` (this repo's own
onboarded config) had drifted from `config/risk-triggers.yaml` — missing the
`governance-mechanism` and `untrusted-content` triggers added in a later
session. Synced it while touching the file anyway, since a stale copy of the
exact table this addendum tightens would undercut the point.

`agents/security-reviewer.md` shows modified in `git status` but I did not
touch it — pre-existing uncommitted change from before this session.

## Explicitly not doing
- D10 as literally written (see conflict above).
- `verify-ungated.sh` hook (§4) — `worker.py` already runs the verify command
  and emits a real exit code for every task regardless of gates; a duplicate
  hook would be redundant machinery, not a fix.
- Hard-enforcing "reason required to escalate past Tier 0" in code — there's
  no task object yet at that decision point (it's pre-staffing), so this
  stays a documented PM discipline (§6), same as today's other judgment calls.
