# Paperclip donation catalog — phased execution

Source: full donation inventory across skills/agents/orchestrators/policy/evals
(2026-10-19). User confirmed: don't skip self-service skill authoring or visual
persona identity (scoped to cmd-center); proceed through the rest in phases.

## Phase A — independent, no dependency on the adapters/ research fork

- [x] `doc/GOAL.md` — company-os's missing top-level "what and why"
- [x] `tasks/lessons.md` — paperclip's engineering-discipline principles,
      added as text
- [x] `agents/company-pm.md` — task-splitting heuristic added
- [x] `tools/company/eventlog.py` — new-event-needs-a-rationale convention
      comment added
- [x] Untrusted-review container profile (`docker/untrusted-review/`,
      `doc/UNTRUSTED-REVIEW.md`) — built and documented; image itself was
      NOT build-tested (OrbStack daemon wouldn't come up headlessly this
      session) — pieces validated individually (bash -n, frontmatter-strip
      dry run, real npm package names), full pipeline is not yet proven
- [x] Capability-registry hardening — `source_commit` + `content_shape`
      added to every `capability-index.yaml` unit (tools/
      build_capability_index.py), with a T3/T4-vs-scripts-executables
      mismatch warning printed at build time; `sync_external_
      capabilities.py`'s unpinned-branch gap is documented, not fixed
      (retroactively pinning ~76 existing entries needs a real audit pass,
      not a mechanical edit — scoped out deliberately, not forgotten)
- [x] `company pause <task>` — shipped, tested (3 new tests in
      test_worker_lifecycle.py)
- [x] Team bundle manifest — `teams/README.md`, `teams/web-app.yaml` (real,
      validated example), `tools/company/teams.py`, `company team show
      <name>` CLI, 9 tests
- [x] Self-service skill authoring — `tools/propose_skill.py` +
      `tools/promote_skill.py`, documented in `skills/capability-curator/
      SKILL.md`, 13 tests (caught one real bug pre-ship: promote_skill.py
      crashed instead of raising a clean error on a malformed append)
- [x] cmd-center `PROJECT.md` — visual persona identity (Phase 10) and the
      memory-landscape two-layer contract (Phase 4) flagged, plus a note
      connecting company-os's new `company pause` to the Phase 7
      lifecycle-state discussion already there

## Phase B — depends on the adapters/ research fork

- [x] Second real harness: `codex` in `config/harness.yaml` +
      `tools/company/adapters/codex_adapter.py`. Invocation read from
      paperclip's own codex-local adapter source, then LIVE smoke-tested
      end to end on this machine (codex-cli 0.163.0) — not shipped on
      reading alone. The live test caught one thing the research pass
      missed (`cache_write_input_tokens` is real, not absent) and one thing
      worth knowing (a plausible-looking model id was rejected outright by
      this account) — `model_flag` is deliberately left unset rather than
      shipping a guessed mapping. Not staffed to any role yet — a real,
      tested, unused harness, by design.
- [ ] Extend `native_agent_loading` into a wider capability-flag vocabulary
      — SKIPPED. `codex` didn't need a second flag; inventing one with no
      real backend requiring it would be speculative, the same mistake
      flagged elsewhere in this review (don't build for a backend that
      doesn't exist yet).
- [ ] Generated per-harness agent definition files (e.g. a `.codex/agents/
      <role>.toml`) — SKIPPED, and now believed unnecessary rather than
      just deferred: company-os's persona-injection design (worker.py
      folds agents/<role>.md into the packet for any non-native-loading
      harness) already solves what paperclip's generated-static-file
      pattern solves, without needing a generated file per harness at all.
      Revisit only if a future harness turns out to need something a
      dynamic packet can't provide.

## Drive-by fixes (found while reading code for the above, fixed on the spot)

- `tools/capability.py`: `search` was defined (`cmd_search`) but never
  wired into `COMMANDS` — a previously-identified bug, fixed, 3 new tests.

## Review

- 480 tests passing (411 at the start of this conversation), zero
  regressions throughout — every change above was run against the full
  suite before moving to the next.
- What's genuinely NEW capability vs. documentation-only: harness/codex
  (real, tested, unstaffed), `company pause`, `company team show`,
  `propose_skill.py`/`promote_skill.py`, capability-index content_shape/
  source_commit, `capability.py search` fix. Everything else this pass is
  docs/comments/config (GOAL.md, lessons.md, AGENT-PERMISSIONS.md,
  BYO-MODEL.md updates, cmd-center PROJECT.md notes, eventlog.py comment).
- What's deliberately left undone, and why: the untrusted-review Docker
  image wasn't build-tested (daemon unavailable, not a design gap);
  `sync_external_capabilities.py` still tracks moving branches, not pinned
  SHAs, for all ~76 existing entries (a real audit, not a mechanical fix);
  the two Phase B capability-flag/generated-file items were judged
  unnecessary rather than deferred.
- Nothing here was staffed into default use — `codex` harness, `teams/
  web-app.yaml`, and the skill-authoring scripts all exist and are tested,
  but none of them changed what actually runs by default today. That's a
  deliberate choice for all of them: proving a seam works is different from
  deciding to rely on it.
