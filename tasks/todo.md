# Universal AI operating system transformation — phased execution

Source: Riyan's master prompt (2026-10-21) to evolve company-os toward a
universal, organization-wide AI operating system, selectively porting
Ruflo/ECC/Paperclip strengths without replacing company-os's event-sourced,
evidence-first core. Riyan confirmed: go all-in, phased, steady, no missed
steps, don't rush — and route all actual engineering/design work through
Opus 5.5 subagents, not Sonnet.

**Grounding pass (done before writing this plan, not assumed):** several
things the master prompt's Phase 0/1 ask for already exist for real,
discovered by reading code, not docs:
- `KNOWN_ISSUES.md` issues #2 (duplicate concurrent execution) and #3
  (silent gate-verdict loss) already have real, committed fixes
  (`worker.py`'s exclusive-lease `started_task` marker; `GATE_NO_VERDICT`
  wired through `worker.py`/`render.py`/`packet.py`/`eventlog.py`).
- Issue #1 (blind cost reporting) is fixed for new runs (`worker.py`
  writes `_usage()` into `WORKER_EXITED`) — only the historical backfill
  is still open, exactly as `KNOWN_ISSUES.md` itself flags.
- A real BYO-model harness seam already exists (`harness.py`,
  `config/harness.yaml`) with two live-tested backends (`claude`, `codex`)
  — a working slice of the master prompt's "universal agent runtime" ask,
  not zero as the prompt's framing might suggest.
- `config/budgets.yaml` already implements a V1 budget/kill-switch.
- No organization/department/goal/program hierarchy exists anywhere —
  genuinely MISSING, matches the master prompt's section 7.1/7.2 ask.

This changes where real Phase 1 work starts: not re-fixing already-fixed
defects, but the one real open item plus the regression-proofing the
master prompt's section 4 asks for.

## Phase 1 — Reliability foundation (done)

- [x] Backfill historical `WORKER_EXITED` token events from
      `.company/state/workers/*/stdout.json` as an append-only
      correction/migration event (never mutate historical events in
      place) — closes KNOWN_ISSUES.md #1's last open item. Shipped as
      `company backfill-tokens`; run against the real log: 1 of 35
      tokenless runs reconstructed, 34 honestly unreconstructable
      (overwritten/missing stdout.json), 28 already had tokens.
- [x] Also fixed, same commit: a live-blocking `NameError: reasons` in
      `cmd_integrate` from commit 6cdd62d (deleted assignment, kept the
      read) — found via a real bug report, verified independently,
      fixed, regression test added (`test_cmd_integrate_regression.py`).
- [x] Regression tests proving: (a) exclusive lease, (b) `GATE_NO_VERDICT`
      fail-closed, (c) backfill idempotency — `test_backfill.py`,
      `test_launch_regressions.py`, `test_cmd_integrate_regression.py`.
- [x] Committed `baf0d74`. 594/594 passing at the time.

## Phase 2 — Universal execution core (done, scoped down from the master prompt)

- [x] Formalize the existing `harness.py` contract into a documented
      adapter interface — found already real and sufficient on inspection:
      3-point contract documented in `doc/BYO-MODEL.md` (171 lines), 26
      conformance tests in `test_harness.py` against both live backends
      (`claude`, `codex`). Did NOT add the master prompt's speculative
      extras (streaming, cancellation, checkpointing, health checks) —
      no backend needs them yet; same judgment call as this session's
      earlier rejection of a speculative capability-flag vocabulary.
- [ ] Antigravity adapter — SKIPPED for now (Riyan's call, 2026-10-21).
      Still blocked on exact JSON field names (cost key, usage shape);
      revisit only with a live `agy -p ... --output-format json` sample.
- [ ] Extend `config/budgets.yaml`'s V1 kill-switch with per-role/per-task
      attribution — deferred to whenever Phase 3's org/budget work makes
      it load-bearing, rather than built speculatively now.

## Phase 3 — Organizational operating system (core shipped)

- [x] ADR-006 (`.company/decisions/ADR-006-organization-goal-hierarchy.md`)
      — goal entity (mission/objective/key_result), 4 new event types,
      task-goal linking inside `taskstate.fold()`, delivery/outcome split,
      report-only per-goal budgets. Approved as written (Riyan, 2026-10-21).
- [x] Implemented ADR-006 in full (§1-§7): `tools/company/goals.py`
      (pure `fold(events, tasks)`, history checks, id assignment, tree/
      gaps/budget rendering), 4 event types + validation in `eventlog.py`,
      `company goal define|link|assess|close|tree|show|gaps`, raw-event
      guard + worker-actor guard, `goal_budgets` in `budgets.yaml`
      (report-only), `agents/company-pm.md` staffing instruction. Migration
      safety verified on copies of the real log: all 12 existing task
      views replay byte-identical, no `goal` key added, `.company/goals/`
      stays absent, `rebuild --verify`/`status`/`costs`/`report` output
      unchanged. 48 new tests (`test_goals.py`).
- [x] Side fix: extended `governance-mechanism` trigger in
      `config/risk-triggers.yaml` to cover `taskstate.py`/`eventlog.py` —
      same class of gap ADR-002 closed for `staffing.py` — done before
      ADR-006's implementation touched those exact files.
- [x] Side fix: root-caused and fixed the test-isolation bug that leaked
      278 `LESSON_RECORDED` events (project `p`) into the real event log
      (`tests/test_lessons.py`/`test_onboard.py` invoked the CLI via
      subprocess with only `cwd=`, which doesn't override an inherited
      `COMPANY_ROOT` — worker.py exports that into every worker's env, so
      running the suite inside a worker leaked fixtures into the live
      log). Fixed going forward; audited every other subprocess-based
      test and confirmed none else was exposed.
- [x] The 278 already-leaked entries: quarantined via a new append-only
      `LESSONS_QUARANTINED` event (modeled on `backfill.py`'s
      `TOKENS_BACKFILLED` pattern), run for real against the live log
      (Riyan's decision — "append a quarantine event"). `lessons.fold()`
      now skips them; nothing deleted, history stays intact. New module
      `tools/company/quarantine.py`, `company quarantine-lessons`
      CLI, 10 tests (`test_quarantine.py`).
- [x] Full suite 655/655 passing after both pieces of work landed
      together (both touched `cli.py`/`eventlog.py` in disjoint,
      non-conflicting hunks — verified by diff before committing).
- [ ] Not yet done: no README entry for `company goal`/
      `company quarantine-lessons`. Riyan hasn't yet defined any real
      mission/objective/key_result — the system is ready, nothing is
      populated.

## Phase 4 — Intelligence, skills, memory (done, scoped down from the master prompt)

- [x] Context-efficient skill loading — found already real and mature on
      inspection: no agent bulk-loads skills (`tools:` lists are tool
      names, not skill preloads), `worker.py` never folds skill bodies
      into a packet, `capability.py`'s `search`/`load` is already
      on-demand, `capability-curator`'s SKILL.md already documents the
      discover-then-load flow. No gap, no code change.
- [x] Derived memory — found already correctly subordinate to the event
      log: `lessons.py`/`escalations.py`/`advise.py` are pure folds with
      no independent state, `capability-index.yaml` is header-marked
      "auto-generated... do not hand-edit" and rebuildable.
- [x] The one real gap: `find_duplicate_staffing()` only ever considered
      LIVE tasks, so resolved/completed work was invisible at staffing
      time. Added `find_similar_resolved_work()` and
      `find_matching_lessons()` (both reusing the existing deterministic
      Jaccard/keyword machinery, no vector search/embeddings/ML),
      surfaced informationally in `company plan`'s JSON output, never a
      new blocking gate. 13 new tests, 668/668 passing.

## Phase 5 — Control plane and business workflows (scoped down — real conflict found)

- [x] Found a genuine architectural conflict before building anything:
      the master prompt's Phase 5 ask (backend API, web dashboard inside
      company-os) directly contradicts `doc/GOAL.md` ("not a hosted
      product... no server, no UI"), `NORTH_STAR.md` ("a dashboard before
      the loop is trusted" / "anything whose first user does not exist
      yet" are both refused outright), and ADR-006's own scope section
      (no web dashboard/API — that's `cmd-center`'s job). Surfaced to
      Riyan rather than silently picking a side.
- [x] Riyan's decision (2026-10-21): keep GOAL.md as-is. No server or UI
      inside company-os, ever.
- [x] Real scoped output instead: `doc/integrations/cli-json-contract.md`
      documents the CLI's existing `--json`/default-JSON output (56
      `emit()` call sites, `canonical()`-serialized) as a stable,
      versioned contract for `cmd-center` (a separate, plan-only project)
      to consume — scoped to exactly what cmd-center's own GUI-01..05
      requirements need. `test_cli_json_contract.py` locks the current
      key shapes so a future refactor can't silently break the contract
      — verified to actually catch drift. Zero new runtime code, no
      server, no behavior change. 680/680 passing.
- [ ] Not done, deliberately: departmental non-engineering EXECUTION
      (cfo/ciso/coo/cto-advisor already exist and are used, but
      finance-analyst/legal-analyst/product-designer have never run an
      actual task end-to-end through the evidence loop — 0 events each
      in the real log). Connectors (GitHub API, CRM, etc.) — zero exist,
      and no ADR/lesson names an actual near-term need for one; building
      ahead of a real use case would repeat the exact mistake ADR-006
      explicitly avoided.
- [ ] 3 findings surfaced, not fixed (each is a real behavior change, not
      a free fix): `costs.aggregate()`'s deliberate by-token ranking is
      lost in JSON because `canonical()`'s `sort_keys=True` re-sorts
      alphabetically; `status --json`'s `progress` is a string ("42%"),
      not a number; only `status`/`goal tree` take `--json`, the rest are
      always-JSON (inconsistent flag surface).

## Phase 6 — Production hardening (done, scoped down to what fits a single operator)

- [x] Found the real, single most consequential gap before building
      anything: `.company/events/events.jsonl` — the sole authoritative
      source of truth — had no backup and no corruption-recovery path.
      `append()`'s own concurrency safety (flock + atomic seq + fsync)
      was already sound; nothing around it protected against a crash
      leaving a torn tail, and backup coverage across onboarded repos was
      pure accident (one repo had zero copy anywhere, 4.7MB of history).
- [x] Shipped exactly that, nothing broader (no multi-tenant isolation,
      no deployment validation, no sprawling threat model — none of it
      fits a single-operator, no-server tool): `company backup`
      (timestamped, atomic, fsync'd, outside the repo), two new
      `company doctor` checks (integrity — blocking; backup freshness —
      advisory only), `append()` refuses rather than guesses on a torn
      tail (same discipline as `backfill.py`/`quarantine.py`).
- [x] Auto-backup deliberately left manual-only — wiring it into
      onboard/session-done/event would have leaked real writes into
      `~/.company-backups` on every test run, the same class of leak
      `quarantine.py` just cleaned up for lessons. `events.jsonl`-in-git
      is a separate decision, deliberately not bundled in.
- [x] `KNOWN_ISSUES.md` wording corrected — all 3 documented defects were
      already fixed in code (confirmed earlier this session), the doc
      still read as open.
- [x] 31 new tests, including a real SIGKILL-mid-append crash test (both
      before and after the fsync point) and a corrupt → restore →
      `rebuild --verify` test. 711/711 passing. Committed `0830a04`.

## Operating notes

- Every phase ships as small, reviewable, tested increments — no
  big-bang rewrite, per the master prompt's own Phase 14 and this
  session's standing simplicity/minimal-blast-radius instructions.
- All actual engineering/design/architecture work for this initiative
  runs through Agent calls with `model: opus` per Riyan's explicit
  instruction — this top-level session remains the Sonnet 5 orchestrator/
  PM, not the implementer.
- `.company/escalations/ESC-004.md`..`ESC-008.md` and
  `.company/config/authorized-targets.yaml` remain untouched/unstaged in
  every commit (standing "ignore anything related to hyperverge"
  instruction).

## Review

All 6 phases of the 2026-10-21 master prompt are now done, each scoped
down from the prompt's original language to what was real and
non-speculative — none of the 6 shipped as originally written, and that
was the right outcome every time, not a shortfall:

- **Phase 1**: 2 of 3 "known issues" were already fixed; shipped the one
  real gap (token backfill) plus a live-blocking `cmd_integrate` bug found
  via a real bug report mid-stream.
- **Phase 2**: the "universal adapter contract" was already real,
  documented and tested; the only genuinely open item (a 3rd harness)
  stayed blocked on missing info, by Riyan's choice, not forced.
- **Phase 3**: the master prompt's 9-rung hierarchy needed only 2 new
  rungs (above "project", below "task") — ADR-006, approved then
  implemented, dogfooded with a real mission/objective/key-result.
- **Phase 4**: skill-loading and memory were already correctly built;
  shipped the one real narrow gap (resolved-work/lesson retrieval at
  staffing time).
- **Phase 5**: found a genuine conflict between the master prompt and
  company-os's own GOAL.md/NORTH_STAR/ADR-006 (no server/UI, ever) —
  surfaced rather than silently resolved either way; Riyan kept GOAL.md,
  so Phase 5 shipped a documented, tested JSON contract instead of a
  dashboard.
- **Phase 6**: found the one gap that actually mattered for a
  single-operator system (event-log durability) instead of building the
  multi-tenant/deployment-validation language the prompt used, which
  never fit this system to begin with.

**Pattern that held across every phase, worth remembering**: investigate
what's real before writing code. Every single phase turned out smaller,
more scoped, or materially different from its master-prompt description
once grounded against the actual repo — never once did the grounding pass
turn up "yes, build exactly what was asked, at that scale."

**What's deliberately NOT done, by explicit decision, not oversight**:
departmental non-engineering execution (advisor roles exist, have never
run a real task end-to-end), external connectors (zero exist, no named
use case), a 3rd harness adapter (blocked on missing info), 3 CLI-JSON
inconsistencies (real but each is a behavior change), `events.jsonl`-in-git
(a separate decision, explicitly deferred).

**Test count**: 536 at session start → 711 at this review, zero
regressions at any step, every commit verified independently (not just
trusting subagent reports) before being staged.

**Status**: 10 commits (`baf0d74`..`0830a04`) on top of the pre-initiative
`6cdd62d` — the first 9 (through Phase 5) pushed to `origin/main`
mid-session; Phase 6's commit (`0830a04`) plus this review update are not
yet pushed as of this review.

## Phase 7 — Close the genuinely-open follow-ups (2026-10-22)

Source: two external architecture reviews comparing company-os against
Paperclip/Ruflo/ECC. Most of their "roadmap" either already shipped in
Phases 1-6 above or is a decision already made and rejected (read-only
web dashboard — explicitly refused in Phase 5, GOAL.md/NORTH_STAR stand).
Three items are real, scoped, and don't need a new use case to justify
(unlike GitHub integration / external connectors / departmental
execution, which stay deliberately open per Riyan's earlier choice):

- [x] **Sandbox Tier-2 workers.** README admits Bash can write outside a
      worker's owned-file guards — a pattern-matching guard, not a real
      boundary. Ground first: how does `worker.py` currently enforce file
      ownership, what's the actual escape (symlink? absolute path? cwd
      escape?), what sandboxing primitives are available on this machine
      (container? `sandbox-exec`? Claude Code's own sandboxing?) before
      picking a fix.
- [x] **Routines as events.** No scheduling exists. A `company routine
      add --cron ... --template ...` registering a routine as an event,
      with a lightweight external trigger (cron/launchd) appending the
      task when it fires — fully auditable because the routine and every
      firing are themselves events, same pattern as every other piece of
      state in this system.
- [x] **Evidence-linked memory provenance.** Lessons are events but don't
      cite their source. Require each new lesson to reference a commit,
      test run, or review event it came from; render a queryable view.
      Keep lessons as events — this is a provenance field, not a new
      store.

- [x] **Wire the external capability catalog into real usage.** Acquisition
      is real and current: 82 forked repos under `external/` (synced as
      recently as 2026-10-21), indexed into a 1,661-unit catalog
      (`config/capability-index.yaml`) by `tools/build_capability_index.py`,
      loadable on-demand via `tools/capability.py load <unit_id>`
      (symlinks into `skills/`). Consumption has never fired once: 0
      symlinks in `skills/` today, 0 `CAPABILITY_*` events in the real log
      across 625 events. Nothing at staffing or packet-render time nudges
      an agent to check the catalog — it's only discoverable if an agent
      spontaneously runs `capability.py list` unprompted. Ground first:
      where staffing/packet rendering happens (`staffing.py`, `packet.py`),
      whether a cheap relevance nudge (surface top-N catalog matches for a
      task's title/description, same word-overlap idiom as
      `find_matching_lessons`) fits without becoming a second bulk-load
      path — the whole point of on-demand loading was avoiding context
      bloat from loading everything.

Ground each via a read-only Opus investigation agent before writing any
code, same pattern as Phases 1-6. Route implementation through Opus
subagents, not Sonnet.

**Review**: all 4 items done, each grounded read-only before any code,
then implemented serially (never in parallel) because all four shared
`cli.py` — the exact file this session already learned the hard way can
silently absorb a concurrent agent's in-progress edits. Independently
re-verified after every commit (`git log`/`git status`/full test run from
this session, not trusted from the subagent's own report):

- **Sandboxing** (`d853ebc`): the gap was worse than `README.md` admitted
  — 11 of 13 crafted escape commands succeeded against the old
  regex-only guard, and advisors had zero containment at all
  (`COMPANY_TASK` unset skipped the check entirely). Fixed with Claude
  Code's own Seatbelt sandbox at launch (`failIfUnavailable`,
  `allowUnsandboxedCommands: false` — no silent unsandboxed fallback) plus
  a merge-time `owned_globs` diff check in `integrate.py`. Live-tested,
  not just unit-tested: real `claude -p --settings` runs proved the OS
  sandbox denies the same escapes the regex missed. New known tradeoff:
  workers lose network access in normal mode (pip/npm installs mid-task
  will now fail). Known-unknown left open, not fixed: whether
  `git update-ref` on another branch from inside a worktree is still
  possible (git metadata stays writable for commits to work).
  Event-log append forgery (bypassing `$COMPANY_ACTOR`) stays explicitly
  out of scope — a separate problem, not a sandbox issue.
- **Routines as events** (`1762334`): `tools/company/routines.py`,
  `ROUTINE_DEFINED`/`ROUTINE_FIRED`, `company routine
  define/list/due/fire`, stdlib-only cron matcher (supports `*`, ranges,
  lists, `/step`, dual day-of-month/day-of-week). `fire` routes through
  the same `plan_spec` staffing/gate logic as `cmd_plan` (extracted from
  it, byte-identical output) rather than a direct `TASK_CREATED` —
  scheduled work cannot skip the risk table. Idempotent per
  `(routine, slot)` under the event-log's existing flock, proven with a
  real 4-concurrent-process race test. No daemon, by design — Riyan's own
  cron fires `company routine fire --due`; matches `GOAL.md`'s "no
  server" stance. Built with no named recurring task yet (Riyan's
  explicit choice: "build the generic plumbing anyway").
- **Evidence-linked memory provenance** (`9fd6b92`): optional
  `source_ref` on `LESSON_RECORDED` (`commit:<sha>` /
  `test_run:<seq>` / `review:<seq>` / `task:<id>`), deliberately NOT
  required — real-log data showed 6 of 7 genuine (non-quarantined)
  lessons have no natural source at all, so mandatory citation would
  have forced fabrication. Lessons now actually reach the worker (not
  just the PM's plan JSON) via `cmd_run` threading
  `find_matching_lessons` results into `packet.render(lessons=...)`,
  capped at 3 and 200 chars each (~300 tokens worst case), byte-identical
  packet when none match. Added `company lesson --search`.
- **Capability catalog wiring** (`a8f40fe`): 82 forked repos / 1,661
  indexed units had never once been consumed (0 symlinks, 0 load events
  ever, despite real recent syncs) — built but entirely unused.
  Deliberately wired at PLAN time only, not packet/worker time: loading a
  unit behaves like adding a native skill (real context cost), and a
  measured precision check against the real catalog found genuine noise
  (a capability-catalog-planning task matched "terminal-opener"; a
  rate-limiting task matched an unrelated legal unit) — informational
  hint for the PM to decide, never an automatic worker-facing suggestion
  or bulk-load. `company capability load` now appends `CAPABILITY_LOADED`
  so usage becomes visible going forward; the standalone
  `tools/capability.py` script is untouched and still records nothing
  when run directly.

**Test count**: 742 (pre-Phase-7) → 792, zero regressions at any step.
All four commits pushed-pending (not yet pushed to `origin/main` as of
this review — confirm before pushing).

## Review

(updated as each phase completes)
