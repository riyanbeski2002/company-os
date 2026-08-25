# ADR-004 — Cut code-reviewer/qa-engineer cost without weakening the gates

- **Status**: accepted
- **Date**: 2026-08-25
- **Decided by**: Riyan, from `company costs` lifetime totals: code-reviewer
  ($59.28, 69 runs) and qa-engineer ($33.76, 32 runs) were the two largest
  gate-cost lines. "We should really reduce the cost on code-reviewer and
  QA-engineer — like at least reduce it by 5 times", followed by "gates and
  review queues are meant to make life easier, not harder" — the explicit
  constraint on how far to push this.

## Context

`company costs` has no per-session filter — the numbers are lifetime totals,
most of them predating every fix in ADR-001 through ADR-003 (opus was the
silent default until 2026-08-24; gates rediscovered the diff from scratch
until the same day). Cache-read tokens dominate the totals (535.6M), and
cache-read scales with turn count — every turn re-sends the whole
conversation so far. That points at the real lever: how many turns a
review/QA run takes before it can render a verdict, not just which model it
runs on.

## Decision

Three changes, deliberately proportionate rather than maximal — a gate that
runs out of budget mid-review and has to be re-run in full is a worse
outcome than the cost problem it would be "solving":

1. **`role_overrides` in `config/staffing.yaml`.** `model_policy()` now takes
   an optional `role` and applies a per-role override on top of the
   tier/gated base row — only the fields named change, so an effort override
   can't silently also change the model. `code-reviewer` and `qa-engineer`
   drop from `effort: high` to `effort: medium`. `security-reviewer` is
   deliberately **not** overridden — it wasn't the cost complaint, and it's
   the one gate whose job is specifically to catch what a faster pass misses.
2. **`maxTurns` 30 → 20** on both `agents/code-reviewer.md` and
   `agents/qa-engineer.md`. A real cut, not a token gesture, but not halved
   either — enough headroom that a genuinely large gated change can still
   finish a real review rather than hit a wall and force a costly re-run.
3. **Both agent files now point explicitly at the packet's embedded diff**
   (`packet.py`'s `render()`, ADR-002) as step 1 of "what to do," instead of
   leaving diff-discovery implicit. The plausible single biggest cost item
   on these two roles was re-deriving what changed via `git log`/`git diff`
   before any real judgment started — the diff has been sitting in the
   packet since ADR-002 landed, but nothing told these two roles to actually
   start there instead of rediscovering it.

## Fixed in passing

`worker.py` compared `policy.get("thinking", "on") != "off"` against a YAML
value that PyYAML parses as a Python bool (`thinking: off` → `False`), not
the string `"off"` — a bool is never equal to a string, so this comparison
was always `True` regardless of config. `MAX_THINKING_TOKENS=0` has never
actually fired through this path. Harmless today (no launched tier currently
sets `thinking: off`), but a real dead lever directly adjacent to this
change — fixed to `bool(policy.get("thinking", True))`, which handles the
real (boolean) type YAML produces.

## What this does NOT claim

**No verified 5x.** `company costs` cannot isolate before/after by session,
so there is no controlled measurement to report — only the mechanism, which
plausibly compounds close to that range (fewer turns from diff-first
review, a lower per-turn reasoning budget from medium effort, on top of the
sonnet-not-opus and diff-embedding changes already in ADR-001/ADR-002 that
these lifetime numbers barely reflect). Verify against real data once enough
new gate runs accumulate under this config, not against this ADR's own
prose.

## Verified

326/326 tests pass (5 new — role-override selection, field-scoping,
no-role/unknown-role no-ops). `company doctor` green. Confirmed live:
`model_policy(..., role="code-reviewer")` and `role="qa-engineer"` both
return `effort: medium`; `role="security-reviewer"` is byte-identical to the
un-overridden base row.
