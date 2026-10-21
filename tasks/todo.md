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

## Phase 2 — Universal execution core (not started)

- [ ] Formalize the existing `harness.py` contract into a documented
      adapter interface (identity, capabilities, input, tool permissions,
      execution, streaming, cancellation, usage, errors, health) — most
      of this already exists implicitly; make it explicit and testable.
- [ ] Add one more live-tested adapter beyond `claude`/`codex` (candidate:
      Antigravity CLI — blocked earlier this session on exact JSON field
      names; needs a live session to confirm before any code is written).
- [ ] Extend `config/budgets.yaml`'s V1 kill-switch with per-role/per-task
      attribution, building on this session's cost-attribution tooling.

## Phase 3 — Organizational operating system (not started)

- [ ] Design (ADR first, before code) an organization/goal/program/project
      hierarchy as events + projections, consistent with the existing
      event-sourcing model — never a second source of truth.
- [ ] Roles, permissions, budgets at the org/department level, reusing
      `config/risk-triggers.yaml`'s deterministic-table pattern rather
      than inventing a parallel policy engine.

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
