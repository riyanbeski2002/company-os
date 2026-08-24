# ADR-002 — CFO/CTO audit response to ADR-001

- **Status**: accepted
- **Date**: 2026-08-24
- **Decided by**: Riyan, staffing `cfo-advisor` + `cto-advisor` in parallel
  ("CFO check the entire company-os arch to see where we leak tokens
  unnecessarily — while CTO checks where we have build, tech and security
  gaps — without compromising on both, propose a solution")

## Context

ADR-001 landed same-day. Both officers audited it plus the surrounding
architecture (company-os itself and `~/.claude/`'s root-level config). Full
findings are in the event log (`company advise --show --project company-os`);
this records what was actually acted on and why, and what was deliberately
left for later.

## CTO findings acted on

1. **HIGH — self-referential governance gap.** `governance-mechanism`
   (`config/risk-triggers.yaml`) did not cover `tools/company/staffing.py`,
   `tools/company/cli.py`, or `config/staffing.yaml` — the exact files ADR-001
   introduced or expanded. Verified live: a 12-line edit to
   `fast_path`/`reconcile`/`model_policy` matched no trigger. **Fix:** added
   those paths/keywords to the trigger. This is a narrower reopening of
   ESC-002 (item 2, already queued) against files that didn't exist when
   ESC-002 was raised.
2. **MEDIUM — no dependency-manifest trigger.** A 1-line lockfile bump — the
   dominant real-world small-diff supply-chain shape — matched nothing and
   would sail through fast_path with zero gates. **Fix:** new
   `dependency-manifest` trigger (package/lockfile globs across common
   ecosystems), deliberately path-only, always `[review, security]`.
3. **MEDIUM — D9's "escalation needs a reason" was unenforced.** `cmd_plan`
   never checked whether a task staffed above Tier 0 had a reason when
   fast_path applied — the commit that introduced D9 conceded this. **Fix:**
   `cmd_plan` now evaluates `fast_path` per task and refuses (exit 3, same
   pattern as the existing overlap-collision refusal) an unreasoned
   Tier-0→staffed escalation unless `--allow-tier-escalation` is passed or
   the task carries a `tier_reason`.
4. **LOW — `.company/decisions/` was empty.** D9/D10/D11 and the
   opus→sonnet-high change (see below) existed only as commit prose. **Fix:**
   this file and ADR-001.

## CFO findings acted on

1. **HIGH — triggered gates pay the full launch tax with zero context
   sharing.** Every gate (review/qa/security) launches as an independent
   Tier-2 process that rediscovers the entire diff itself via Bash before it
   can review anything — `packet.py`'s `render()` carried no diff/SHA field
   at all. **Fix:** `packet.render()` takes an optional `diff_summary`;
   `cmd_run` computes `git diff --stat` + HEAD SHA in the task's worktree for
   gate-role launches only (code-reviewer/qa-engineer/security-reviewer) and
   embeds it in the packet. This does not reduce what a gate verifies — it
   still runs its own checks — it only removes redundant rediscovery of what
   changed. Degrades silently to no diff summary on any git error; never
   blocks a launch.
2. **MEDIUM — `company-pm.md` had no `maxTurns`.** Every other agent file
   caps turns (25–60); the longest-running agent in the system, the one that
   made today's ~200-launch call, had no backstop. **Fix:** `maxTurns: 200`
   — generous, a hard stop not a target.

## Explicitly not acted on now (real, but out of scope for this pass)

- **ESC-001, ESC-002 item 1 (actor-role forgery), the runaway `company
  baseline` concurrency bug, KNOWN_ISSUES #3 (silent gate-verdict exit).**
  All pre-existing, already tracked, and not introduced by ADR-001. Fixing
  them belongs to a dedicated pass, not folded silently into a token-cost
  response.
- **`~/.claude/settings.json` scoping.** CTO flagged that a Tier-2 worker's
  Bash tool inherits Riyan's full personal permission allowlist (spanning
  many unrelated projects — `sudo installer:*`, `docker run:*`, etc.), not a
  scoped subset. A real fix exists (`claude -p --settings <scoped-file>`) but
  touches session-wide behavior across every project Riyan runs, not just
  company-os — his call, not a unilateral edit to his personal config.
  Recommended, not applied.
- **CFO's gate-tier-inflation visibility gap** (nothing audits whether a
  gate that ran as Tier 2 could have been Tier 1, the way task-tier
  inflation already is) and **moving `agents/security-reviewer.md`'s growing
  incident-lesson content into a referenced skill** instead of the agent file
  itself (it is repaid on every one of that gate's launches). Both are real,
  both are mechanism choices with their own design space — queued, not
  decided here.

## Separately recorded: `tier2_gated` model change

Riyan changed `config/staffing.yaml`'s `tier2_gated` row from `opus` to
`sonnet` directly (uncommitted at the time, comment-only justification: cost
discipline — "no extensive use of Opus for things sonnet can do" — reinforced
by an active Opus-specific outage that stalled 6 gated tasks the same
session). CTO flagged the decision itself as sound but under-recorded (no
escalation event, no lesson, no ADR) for the highest-stakes tier. Recorded
here formally: effort stays `high`; only the model changed. If gate quality
regresses on genuinely hard reviews, escalate back up per-task via a recorded
judgment call, not by reverting this default.
