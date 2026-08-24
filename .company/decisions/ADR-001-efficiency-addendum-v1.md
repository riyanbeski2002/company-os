# ADR-001 — Efficiency addendum v1: fast-path default, risk-based review, tier model/effort policy

- **Status**: accepted
- **Date**: 2026-08-24
- **Decided by**: Riyan (explicit: "addendum can overwrite existing rules" —
  authorizing D10 to override the prior universal-review rule)
- **Commits**: `6f2fea7`, `4790169`, plus the same-day governance-mechanism /
  dependency-manifest trigger extension and D9 enforcement follow-up (CTO/CFO
  audit response, see ADR-002)

## Context

`company status`/`company advise` showed real waste: ~200 full agent launches
in one live session across 4 parallel panes, most against genuinely small
diffs (copy fixes, lint errors, one-line checks), each paying a fixed launch
tax (CLAUDE.md auto-load + repo exploration) regardless of diff size. Tier
inflation was advisory ("hire the smallest team," a judgment call) and review
was universal (`baseline_gates: [review]`) regardless of risk.

## Decision

**D9 — fast path is the default, not a judgment call.** A request with zero
risk-trigger hits and a predicted diff within bounds (`config/risk-triggers.yaml`
`fast_path`: default ≤1 file, ≤50 lines) is Tier 0 by default. Escalating past
it needs a recorded reason (`tier_reason` on the task; `company plan` refuses
an unreasoned escalation as of the same-day follow-up — see ADR-002).

**D10 — review is risk-based, not universal.** `baseline_gates` is now `[]`.
Review fires only when a risk trigger does, same as qa/security. Adding it
back on an untriggered task is a scope addition and needs a recorded reason —
enforced by the pre-existing `staffing.reconcile()`, which already refused
any unreasoned gate addition; this required no new code, only removing
review's special-cased universal status.

**D11 — model/effort scale with tier and risk, not with anxiety.**
`config/staffing.yaml` maps tier → model/effort/thinking; `worker.py` sets
`--model`/`--effort`/`MAX_THINKING_TOKENS` from it on every launch.
Escalating the model needs the same "recorded reason" discipline as
everything else here.

## Consequences

- A docs/typo-scale change with no trigger hit skips the entire staffing
  pipeline: no packet, no gate launch, no fixed CLAUDE.md tax.
- An untriggered task no longer gets a free review pass — this is a real,
  deliberate trade of a marginal safety net (baseline review on trivial,
  provably-safe-bounded work) for a large, structural cost reduction.
  `reconcile()` is the backstop: anyone who wants review back on such a task
  can have it, on the record.
- **Same-day gap found by CFO/CTO audit (ADR-002):** the addendum's own
  mechanism (fast_path/reconcile/model_policy in `staffing.py`, the tier
  policy in `config/staffing.yaml`) was not itself covered by
  `governance-mechanism` — an edit to the addendum's own logic could have
  shipped ungated. Closed same day, see ADR-002.
