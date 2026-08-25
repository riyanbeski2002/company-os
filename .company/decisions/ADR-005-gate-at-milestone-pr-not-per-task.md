# ADR-005 — Gate at the milestone/PR boundary, not per task

- **Status**: accepted
- **Date**: 2026-08-25
- **Decided by**: Riyan — "kill the rule that says code review, qa, security
  for every task, it is only for mile stones and PRs," clarified through:
  - Gate unit: "either way — at some point in time they should have gone
    through a review, either at group gate or at PR — ideally at PR."
  - Risk scope: "Yes, uniformly — risk table still decides WHAT gates apply,
    only WHEN changes."
  - Interim evidence: "implementation ready comes just before PR commit."
  - Mechanism: "we can use /code-review low on that particular worktree with
    limited info provided and not the entire codebase."
  - Framing throughout: "gates and review queues are meant to make life
    easier, not harder" / "it's all about effective use of resources while
    staying as cheap as possible."

## Context

Every prior gate-cost fix this session (ADR-002's diff embedding, ADR-003's
grouped gating, ADR-004's role_overrides/maxTurns) reduced the cost of a
gate *launch*. None of them changed how often a launch happened at all — a
task tripping a risk trigger still needed its own gate cycle the moment it
reached `IMPLEMENTATION_READY`, whether reviewed alone or opportunistically
batched via `gate_group` when the PM happened to notice several tasks shared
a core. This is the next lever: change *when* gating happens by default, not
just how cheap each instance is.

## Decision

**The risk table still decides WHAT gates a piece of work needs — unchanged,
uniformly, including auth/payments/PII/migrations/secrets/the
governance-mechanism trigger.** What changes is WHEN: a task reaching
`IMPLEMENTATION_READY` + a green `TEST_RUN` no longer means "stage its gate
now." It means the task is ready for its PR. Gating is held until the
milestone/PR boundary and then applied to everything in it at once — via
`gate_group` (ADR-003) when a PR spans several tasks, or a direct
`company run --role <gate>` when a PR genuinely is one task. Either is
correct; PR is the preferred unit when there's a clean one to use.

**The Evidence Rule does not change.** `taskstate.check_done()` is
untouched — every task still needs its own `REVIEW_PASSED`/`QA_PASSED`/
`SECURITY_REVIEW_PASSED` event, still checked against the trusted
`WORKER_STARTED` actor-role binding (`gate_roles`, verified live in
`cli.py:316` and `:853` as this ADR was written — the strict role check is
actually wired at both real call sites, not just documented aspirationally).
`IMPLEMENTATION_READY` was already independent of gate evidence in the
Evidence Rule before this change; nothing there needed to move.

**For the review gate specifically, the mechanism also changed, not just the
timing.** `agents/code-reviewer.md` now runs the native `/code-review low`
skill on its own worktree as its primary review step — it already has
`Skill` in its tool grant, its packet already embeds the diff (ADR-002), and
its own cwd already IS the worktree once launched, so the skill scopes
itself to the diff by default rather than needing to be pointed at anything.
This was deliberately NOT built as a new, cheaper launch path invoked
directly by company-pm — that would mean the task's own orchestrating
session both ran the review and recorded its own verdict, which is
self-certification regardless of which tool did the reading. Independence
is preserved by keeping the launch inside `worker.py` (real `WORKER_STARTED`
with `role=code-reviewer`, satisfying the actor-role binding) and only
changing what that launched process does once it's running.

## What this does NOT do

- Does not exempt any risk category from ever being gated — the highest-risk
  triggers are gated the same way as everything else, just at the PR
  boundary instead of immediately per task.
- Does not weaken or bypass `check_done()`'s actor-role/self-certification
  check.
- Does not remove `gate_group`'s 2-task minimum (`cli.py`) — a single-task
  PR still goes through `company run` directly; that's not "per-task
  gating," that's a PR that happens to be one task.
- Does not touch QA or security's review methodology — only the `review`
  gate's mechanism changed (native skill); `qa-engineer`/`security-reviewer`
  keep their existing manual process, just gated at the same PR boundary now.

## Verified

326/326 tests pass (unaffected — this is a policy/process and agent-prompt
change layered entirely on top of ADR-003's already-built mechanism; no
`taskstate.py`/`worker.py`/`cli.py` logic changed). `company doctor` still
green. `check_done()`'s `gate_roles` actor-role binding confirmed wired at
both live call sites while writing this ADR, not assumed.
