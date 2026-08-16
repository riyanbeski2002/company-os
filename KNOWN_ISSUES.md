# Known issues

Open defects, with evidence. Every one of these was found by the `cfo-advisor`
running against the fixture project — not by a human reading code. They are
recorded here because the event log they came from lives in a disposable fixture
repo that `tools/mkfixture.sh` recreates from scratch.

Severity is the officer's, not softened.

---

## 1. `company costs` reports zero tokens — HIGH

**Finding.** Cost reporting is blind. `company costs` returns
`tokens={cache_creation:0, cache_read:0, input:0, output:0}` for every run, so
nobody can see consumption.

**Evidence.** `cli.py` aggregates tokens exclusively from `data.tokens` on
`WORKER_EXITED` events, but 0 of 31 such events in the fixture log carry a
`tokens` field — they carry only `cost_usd`, `elapsed_s`, `exit_code`,
`session_id`. The data is not lost: `worker.py::_usage()` exists and all 16
`.company/state/workers/*/stdout.json` files contain complete usage blocks.
Reconstructing from those gives 2,488,591 cache read / 253,906 cache creation /
98,215 output over 234 turns. **The producer never writes what the consumer
reads.**

**Why it matters.** This is the exact condition that let the original 2.49M
overrun go unnoticed until a human found it by accident.

**Fix.** `worker.py` now writes `_usage()` into `WORKER_EXITED` as `tokens`, so
new runs are covered. Still outstanding: **backfill the historical events from
the `stdout.json` files**, so existing projects get a real baseline instead of
starting from zero. Adds no runtime cost and removes no checks.

---

## 2. One task implemented four times concurrently — HIGH

**Finding.** TASK-202 was implemented four separate times in seven minutes by
four different workers. Only one result could ever merge. The three redundant
implementations plus one abandoned run cost **659,577 cache-read tokens — 26.5%
of everything the project consumed** — for a task whose merged diff is 101 lines.

**Evidence.** Event timeline (seq 72–94): `frontend-engineer-202-fix` abandoned
mid-tool-call; `fe-202-detach-test`, `fe-202-detached` and `fe-202-collision`
each emitted `IMPLEMENTATION_READY` within 136 seconds. `fe-202-detached` and
`fe-202-collision` overlapped by 76 seconds on the same task and the same
`owned_globs`. Only `e53c9bc` merged. For comparison, all of TASK-201 —
implementation, fix, and three gates — cost 776,381.

**Cause.** These were launched while testing `--detach`. `worker.live_worker_on`
was added to prevent exactly this, but it keys off a `started_task` marker file
that the already-running workers predated, so the guard could not see them.

**Fix.** Make the task lease genuinely exclusive: refuse to start a worker on a
task that already has a live worker holding the same owned globs, the way
`BRANCH_GUARD` refuses conflicting writes. Removes no gate and no review — it
only stops the same task being built concurrently by workers whose output must
then be thrown away.

---

## 3. A gate worker can exit without a verdict, silently — HIGH

**Finding.** `security-reviewer-201` ran 11 turns to a clean `end_turn` and
emitted neither `SECURITY_REVIEW_PASSED` nor `SECURITY_REVIEW_FAILED`. The gate
was re-run as `security-reviewer-201b`, so TASK-201's security review was **paid
for twice** (228,835 combined cache read). That is a review whose result was
silently dropped, not a review that found nothing.

**Evidence.** Grouping all 104 events by actor: `security-reviewer-201` emitted
only `WORKER_STARTED` and `WORKER_EXITED`, despite `stdout.json` showing 11
turns, `stop_reason: end_turn`, `is_error: false`, 6,582 output tokens. Combined
with the deliberate `frontend-timeout-test`, dead spend was 109,262 cache-read
tokens.

**Fix.** Treat a gate worker that exits without emitting a verdict as a **failed
run** and surface it, rather than silently re-running the gate under a new actor
name. A reviewer ending cleanly with no verdict is either a prompt fault or a
harness fault, and right now both look identical to success in the cost report.
This is about not paying twice for the same review — **the review itself must
still happen.**

---

## What is explicitly NOT wrong

Recorded so a future cost review does not "fix" the wrong thing:

- **All 10 agents carry an explicit `tools:` list.** Per-turn context is lean.
- **Cache-read to output ratio is 25.3x**, inside the normal 20–40x band. Mean
  cache read per turn is 10,635 over 234 turns. Treat drift above ~40x as the
  trigger to re-audit.
- **The gates paid for themselves.** `security-reviewer-202` spent 180,219 tokens
  to find that `_decide` checked role but never compared `actor.id` to
  `expense.owner_id` — a self-approval hole letting a manager approve their own
  expense — and the CLI then correctly refused the DONE transition.

Both tasks are tier 2 with small merged diffs, which *looks* like tier inflation
until you note the tier-2 security gate is what caught the bug.

> **Change nothing about `tools:`, gate coverage, or tier for this class of work.
> The real overspend was duplicated work and lost telemetry, not context bloat or
> excessive checking.**
> — `cfo-advisor`
