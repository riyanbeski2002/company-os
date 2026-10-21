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

## Phase 1 — Reliability foundation (in progress)

- [ ] Backfill historical `WORKER_EXITED` token events from
      `.company/state/workers/*/stdout.json` as an append-only
      correction/migration event (never mutate historical events in
      place) — closes KNOWN_ISSUES.md #1's last open item.
- [ ] Add regression tests proving: (a) the exclusive-lease fix actually
      rejects a second launch on the same owned globs, (b) a gate worker
      ending `end_turn` with no verdict event always produces
      `GATE_NO_VERDICT` and never silently re-runs under a new actor name,
      (c) token backfill is idempotent and never double-counts on re-run.
- [ ] Re-run full suite, confirm zero regressions, record before/after
      counts here.

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

## Phase 3 — Organizational operating system (approved, implementing)

- [x] ADR-006 (`.company/decisions/ADR-006-organization-goal-hierarchy.md`)
      — goal entity (mission/objective/key_result), 4 new event types,
      task-goal linking inside `taskstate.fold()`, delivery/outcome split,
      report-only per-goal budgets. Approved as written (Riyan, 2026-10-21)
      — the 10-repo/cross-log question is a per-device onboarding detail,
      not an architecture concern, so it stays correctly deferred as the
      ADR already scoped it.
- [ ] Implement ADR-006: `tools/company/goals.py`, 4 new event types in
      `eventlog.py`, `company goal` CLI group, launcher-only guard +
      worker-actor guard, golden test proving the existing log replays
      byte-identical.
- [ ] Side fix (Riyan, 2026-10-21): extend `governance-mechanism` trigger
      in `config/risk-triggers.yaml` to cover `taskstate.py`/`eventlog.py`
      — same class of gap ADR-002 closed for `staffing.py`, now closed
      before ADR-006's implementation touches those exact files.
- [ ] Side fix (Riyan, 2026-10-21): investigate and fix the test-isolation
      bug that leaked 278 `LESSON_RECORDED` events (project `p`, patterns
      `"x"`/`"a repeated pattern"`) into the real `.company/events/
      events.jsonl`; decide with Riyan how to handle the already-leaked
      entries (event-sourcing discipline forbids silently rewriting
      history — needs an explicit decision, not a unilateral delete).

## Phase 4 — Intelligence, skills, memory (not started)

- [ ] Context-efficient skill loading (selective, not load-everything) —
      the capability-registry/category work from this session is the
      foundation; build real selective retrieval on top.
- [ ] Derived memory/retrieval layer, explicitly subordinate to the event
      log — never an alternate source of operational truth.

## Phase 5 — Control plane and business workflows (not started)

- [ ] Backend APIs over the event log's projections.
- [ ] Departmental workflow packs (non-engineering) reusing one
      orchestration engine, not duplicating it per department.
- [ ] Web dashboard — only after the backend state it would display is
      itself trustworthy (explicit master-prompt constraint).

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
