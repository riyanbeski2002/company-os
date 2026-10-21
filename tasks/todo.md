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

## Phase 6 — Production hardening (not started)

- [ ] Threat model, multi-tenant isolation tests, failure injection,
      restore testing — deferred until Phases 1-5 exist to harden.

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

(updated as each phase completes)
