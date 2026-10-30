# Harness-agnostic migration: audit, matrix, and first-milestone plan

Response to Architecture Directive V2 (2026-10-30). This is the audit and plan
the directive's "immediate instruction" asks for **before** any code changes.
**Status:** M0 (safe worktree lifecycle) implemented 2026-10-30; see
KNOWN_GAPS.md #8. M1–M5 not started.

Evidence base: a full read of `tools/company/{harness,worker,integrate,gategroup,sessions,slots,eventlog}.py`,
`config/harness.yaml`, `hooks/*`; a repo-wide sweep for Claude-specific
assumptions; `--help`/installed-doc verification of every CLI on this machine
(no model calls); and a read of ECC at pinned commit `76aaa77`.

---

## 1. Where company-os actually stands

**Already harness-agnostic (keep):** the event log as the single source of
truth, the derived task views, the Evidence Rule, the risk table/gates, the
staffing engine, baseline/integrate-on-green, goals, escalations, the
`company` CLI as the only state mutator. None of these read Claude session
data — no code reads Claude transcripts.

**A harness seam exists but is launch-only.** `harness.py` + `config/harness.yaml`
resolve a per-role argv template; `codex` runs through
`adapters/codex_adapter.py` and was live-validated on 2026-10-19. What the
seam does *not* cover:

| Gap | Where | Consequence |
|---|---|---|
| **Enforcement is Claude-only** | `hooks/guard_paths.py`, `guard_secrets.py`, `protect_branches.py` read Claude's `tool_name`/`tool_input` and answer in Claude's `permissionDecision` shape; registered only via `hooks/hooks.json` (plugin) and `install.sh` (`~/.claude/settings.json`) | A non-Claude worker runs with **no ownership guard, no secret-read guard, no branch guard**. `doc/BYO-MODEL.md` says switching harness changes "nothing else" — that is wrong today. |
| OS sandbox is a Claude `--settings` schema | `worker.py:200-261` | Only Claude and Codex (own `sandbox_mode`) are contained. |
| Output parsing assumes Claude's result JSON | `worker.py:536-590, 675-715, 721-743, 812-820`; `costs.py`, `backfill.py`, `cli.py:831,982` | Every adapter must impersonate Claude's shape; `_read_result` silently yields `{}` on JSONL. |
| Tool names are Claude's | `worker.py:50-57` `ROLE_TOOLS`, `agents/*.md` `tools:`/`disallowedTools:` | When a persona is inlined for a non-native harness the frontmatter is stripped, so **read-only advisors lose their "no Write/Edit" restriction**. |
| Models named by Claude family | `config/staffing.yaml` (all `sonnet`) | Works only through each harness's `model_map`. |
| PM is a Claude session | `agents/company-pm.md:3`, uses `Agent`/`SendMessage`/`ListAgents` | Only workers are pluggable; the PM is not. |
| Skills/agents discovered as a Claude plugin | `.claude-plugin/`, `install.sh`, `worker.py:153-180` | Other CLIs never see `skills/` or `agents/`. |

**Worktree lifecycle — the directive's non-negotiable — is essentially absent:**

- Task worktrees (`worker.py:101-121`) are created and **never removed**; `MERGED` (`integrate.py:174`) leaves worktree and branch in place. No `git worktree prune` anywhere.
- The only removal code, `gategroup.py:68-69`, is `git worktree remove --force` + `shutil.rmtree` — exactly what §15 forbids (destroys uncommitted work unconditionally).
- `_integration` is permanent by design; gate-group worktrees are rebuilt, never cleaned after the verdict.
- `ensure_worktree` returns an existing directory without checking git still registers it.
- Stale handling exists for *processes/claims* (`slots.reap`, `CLAIM_STALE_AFTER_S`), not directories; `live_worker_on` lacks the zombie check `slots._alive` has.

## 2. Verified harness capabilities (this machine, 2026-10-30)

States per directive §6. Sources: `--help`, installed docs, config key names; "bin" = string found in the binary (weakest — code path exists, behavior unconfirmed). Full evidence table kept in the session scratchpad; summary:

| Capability | claude 2.1.314 | codex 0.163.0 | agy 1.4.11 | opencode 2.2.2 |
|---|---|---|---|---|
| Headless | `-p` | `exec` | `-p` | `run` |
| Packet via stdin | SUPPORTED | SUPPORTED (`-`) | UNKNOWN for text (stream-json only) | UNKNOWN |
| JSON output | `--output-format json` | `--json` (JSONL) | `--output-format json` | `run --format json` (shape UNKNOWN) |
| Schema-constrained result | `--json-schema` (string) | `--output-schema` (file) | `--json-schema` (string or file) | UNKNOWN |
| Model select / list | `--model` / none | `-m` / `codex debug models` | `--model` / `agy models` | `-m p/m` / `opencode models` |
| Effort | `--effort` | config `-c model_reasoning_effort=` | `--effort` | `#variant` suffix (partial) |
| Resume | `--resume`, caller-chosen `--session-id` | `exec resume <id>`, id from `thread.started` | `--conversation <id>`, id source UNKNOWN | `-s <id>` (caller-chosen) |
| Blocking pre-tool hook | SUPPORTED (PreToolUse) | SUPPORTED (PreToolUse; hooks must be trusted first) | SUPPORTED (`.agents/hooks.json` PreToolUse deny) | **UNKNOWN** — on-disk plugin typings are v1.1.59; v2 binary lacks `tool.execute.before` |
| Session end event | SessionEnd | SessionEnd | Stop / PostInvocation | UNKNOWN |
| Native persona file | `--agent` | AGENTS.md / `.codex/agents` (bin) | `--agent`, `.agents/agents` | `run --agent`, agents dir |
| OS sandbox | `--settings` sandbox | `-s workspace-write` (seatbelt) | `--sandbox` (behavior UNKNOWN) | **none found** |
| Tool allowlist flag | `--allowedTools` | none (execpolicy rules) | UNKNOWN | config permissions only |
| BYOK / base URL | `ANTHROPIC_BASE_URL`, Bedrock/Vertex | `model_providers`, `--oss` local | UNKNOWN | `baseURL`, openai-compatible |
| Cost in output | `total_cost_usd` | tokens only | UNKNOWN | `opencode stats` |

Install notes: `agy` lives at `~/.gemini/bin/agy` and is **not on PATH**; `~/.antigravity/antigravity/bin/agy` is a dead symlink. `gemini` 0.32.1 is also installed (not in V1 scope; adapter-ready later).

**Implication:** opencode is the weak link — no verified blocking hook and no OS sandbox. Until one is verified, it must not be staffed onto write roles (see invariant H3).

## 3. KEEP / MODIFY / REPLACE / PORT / DEFER

| Component | Verdict | Why / what changes |
|---|---|---|
| Event log, Evidence Rule, taskstate, rebuild/replay | **KEEP** | Already the harness-neutral state system §28 asks for. |
| Staffing engine, risk table, gates, gate-groups, baseline, integrate-on-green | **KEEP** | Harness-independent. Staffing gains a harness-eligibility step (MODIFY below). |
| Goals, routines, escalations, lessons, board, capability router | **KEEP** | No harness coupling. |
| `company` CLI as sole mutator | **KEEP** | It *is* the cross-harness control plane — any harness can call it. |
| `harness.py` command templates | **MODIFY** → adapter modules | A template can't parse output, detect, or declare capabilities. Becomes `tools/company/adapters/<id>.py` implementing a small contract (§4.1); YAML keeps role routing, model maps, policy. |
| `adapters/codex_adapter.py` | **MODIFY** | Folded into the codex adapter's `parse()`; use `--output-schema` (verified) instead of free-text JSON scraping. |
| Claude result parsing in `worker.py`/`costs.py`/`backfill.py`/`cli.py` | **REPLACE** | Consume one `NormalizedResult`; Claude's shape is parsed only in the claude adapter. Historical `stdout.json` reads stay for backfill. |
| `hooks/guard_*.py`, `protect_branches.py` | **MODIFY** | Split into a harness-neutral policy core (`check_write(path)`, `check_read(path)`, `check_command(cmd)`) plus per-harness payload shims (claude, codex, agy; gemini later). Logic and tests carry over unchanged. |
| `hooks/hooks.json`, `install.sh` hook wiring | **MODIFY** | Generated per harness from one source (§4.4); install becomes per-harness. |
| `sandbox_settings()` | **MODIFY** | Becomes a neutral policy (writable roots, denied reads, network off) each adapter renders, or declares UNSUPPORTED. |
| `ROLE_TOOLS` + agents frontmatter `tools:` | **MODIFY** | Neutral capability names (`read`, `search`, `edit`, `shell`, `web`) mapped per harness, **fail-closed** (unmapped ⇒ refuse, never blank ⇒ all). |
| `staffing.yaml` `model: sonnet` | **MODIFY** | Tiers name abstract classes (`high`/`standard`/`economy`); `models.yaml` maps class → eligible (harness, provider, model). Back-compat: `sonnet`→`standard` alias. |
| `worker.ensure_worktree` | **MODIFY** | Records `WORKTREE_CREATED`; verifies registration of an existing dir. |
| `gategroup.build_group_review` force-remove | **REPLACE** | Use the safe remover; gate-group worktrees are clean scratch by construction, so normal removal succeeds — if it doesn't, that's a signal, not something to force. |
| Task worktree cleanup, reconciliation, `company cleanup` | **PORT** (ECC `worktree-lifecycle`) + new | Port `classifyWorktree`/`planCleanup`/porcelain parser/`merge-tree` conflict prediction/git-env scrub; fix ECC's fail-open `isDirty`; add ownership + path-root checks it lacks. |
| Rollback ledger for partial launches | **PORT** (ECC tmux orchestrator, idea) | Undo only what this launch created, reverse order, recorded as events. **Not** its `--force`/`rmSync`/`branch -D` cleanup. |
| Fail-closed tool-list emission | **PORT** (ECC `agent-emit-pi`) | Never emit blank lists; unmapped tools are warnings/refusals. |
| Harness capability manifest + `--check` drift test | **PORT** (ECC compliance, idea) | Manifest with states + `last_verified_at` + verifying CLI version; `company harnesses --check` re-probes and fails on drift. |
| ECC session-adapters, session-manager, provider SDK code, hook configs | **SKIP** | Scrape on-disk transcripts / mtime-as-liveness / SDK deps / `CLAUDE_PLUGIN_ROOT` baked into codex hooks. company-os's stdout-stream approach is better. |
| `.claude-plugin/` packaging | **KEEP** (as the claude adapter's packaging) | Not removed — becomes one generated target among several. |
| `company-pm` persona | **MODIFY** | Drive workers only via `company` verbs (works under any harness); Claude-only tools (`Agent`, `SendMessage`) become optional enhancements, never required. |
| tmux sessions view | **DEFER** (V1 late) | `sessions.ping_via_tmux` stays a fallback; a `company workers --attach` tmux view is presentation, never state. |
| BYOK provider config | **NEW** (M4) | See §4.5. |
| Model routing by cost/budget, provider failover, leases, multi-repo | **DEFER** to V2 | Per directive §34. |
| `docker/untrusted-review` | **DEFER** | Hardcoded `claude -p`; route through adapters after M1. |

## 4. Designs

### 4.1 Adapter contract (Python, stdlib; mirrors §5 minus what CLIs can't do)

```python
class Adapter:
    id: str
    def detect(self) -> Detection            # binary path, version, or absent
    def capabilities(self) -> Manifest        # verified states, version-stamped
    def build_launch(self, req: LaunchRequest) -> Launch   # argv, env, stdin, temp files (e.g. schema file)
    def parse(self, stdout: str, stderr: str, exit_code: int) -> NormalizedResult
    def resume_argv(self, session_id: str, message: str) -> list[str] | Unsupported
```

`interrupt`/`terminate` are process operations owned by `worker.py` (process-group SIGTERM, already implemented), not per-adapter. `observe` (live event streaming) is DEFERRED: V1 supervises by exit + final result, which every harness supports. Any unsupported operation returns an explicit `Unsupported(reason)` — never a fake success.

`NormalizedResult`: `session_id, status (success|error|timeout|interrupted), terminal_reason, structured_output, usage{input, output, cache_read, cache_write}, cost_usd|None, cost_source (harness|estimated|none), num_turns|None, harness, harness_version, provider, model`.

### 4.2 Events — extend, don't duplicate (§22 "avoid proliferation")

The directive's vocabulary mostly already exists under other names: `WORKER_SPAWNED`≈`WORKER_STARTED`, `WORKER_STOPPED`≈`WORKER_EXITED`, `TEST_*`≈`TEST_RUN`, `INTEGRATION_COMPLETED`≈`MERGED`, `APPROVAL_*`≈`ESCALATION_*`. Renaming would break replay of every existing log. Plan: keep names, add a documented alias table in `doc/EVENTS.md`, version the contract (events carry no version field today — add an optional `v` that defaults to 1 when absent, so existing logs replay unchanged), and add only what has no equivalent:

- `WORKTREE_CREATED` (path, branch, base, task, owner) — **the ownership record**
- `WORKTREE_REMOVED` (path, branch, head_sha, bytes_reclaimed, trigger)
- `WORKTREE_CLEANUP_BLOCKED` (path, reason, recovery_ref) — requires evidence
- `WORKER_STARTED`/`WORKER_EXITED` data gain `harness`, `harness_version`, `provider`, `model`.

### 4.3 Worktree invariants (§15, enforced in one module `worktrees.py`)

A worktree may be removed only if **all** hold; any failed check ⇒ `WORKTREE_CLEANUP_BLOCKED`, never a forced delete:

- **W1 Ownership:** a `WORKTREE_CREATED` event exists for this exact path. Human-made worktrees are invisible to cleanup.
- **W2 Containment:** `realpath(path)` is strictly under `realpath(.company/worktrees)` and ≠ the main worktree (`git rev-parse --show-toplevel` of the repo).
- **W3 No live owner:** no live, non-zombie pid in claims/slots/`state/workers` for the task; no tmux pane whose cwd is inside it.
- **W4 Terminal state:** the task is DONE/MERGED/CANCELLED, or FAILED with recovery done.
- **W5 Clean:** `git status --porcelain` succeeds **and** is empty. A failing status counts as dirty (fixes ECC's fail-open bug).
- **W6 Integrated or checkpointed:** branch tip is reachable from integration/base, **or** recorded as a `checkpoint/<task>` ref (refs are cheap; directories aren't). A dirty crashed worktree is first committed to `checkpoint/<task>` on its own branch — only if that commit succeeds does removal proceed.
- **W7 Git-native removal only:** `git worktree remove <path>` (no `--force`), then `git worktree prune`. `shutil.rmtree` is never the cleanup path.
- **W8 Recorded and idempotent:** `WORKTREE_REMOVED` written; a second run finds nothing to do.

Triggers: on `MERGED`, `TASK_COMPLETED`, cancellation and post-verdict for gate-group worktrees (in-process, synchronous with the CLI verb that writes those events — deterministic, no hook required); plus `company cleanup [--dry-run]` reconciliation at `company status`/startup and on demand. Staleness = W3 + W4 evidence, never mtime (§16). `company cleanup --dry-run` reports managed/active/pending/blocked counts and reclaimable bytes (§18).

### 4.4 Canonical source → generated harness config (§11)

`agents/*.md` and `skills/` stay canonical. At launch, the adapter materializes what its harness needs **inside the worktree only** (e.g. `.agents/agents/<role>.md` + `.agents/hooks.json` for agy; codex hooks + persona; Claude keeps `--plugin-dir`), each file stamped with a generated-from header and git-excluded so it never reaches a commit. Persona frontmatter is translated, not stripped — the tool restrictions survive.

### 4.5 BYOK (§4)

`config/providers.yaml` (repo default) + `.company/config/providers.yaml` (local override):

```yaml
providers:
  anthropic: {auth: native}
  openai:    {auth: native}
  google:    {auth: native}
  openrouter: {auth: env, key_ref: OPENROUTER_API_KEY, trust: third_party, max_classification: INTERNAL}
  local:     {type: openai-compatible, base_url: "http://127.0.0.1:1234/v1", auth: none, trust: local}
```

- Only `key_ref` names are stored; validation **rejects** any value shaped like a key.
- The key is read from env/keychain at launch and injected only into the child's env — never argv, packet, event, or log. Logged argv/env pass through a redactor.
- Routing refuses a provider whose `max_classification` is below the project's `data_classification` (CONFIDENTIAL source never reaches a third-party/free endpoint). No silent downgrade: an ineligible request fails with an escalation, it doesn't fall through to a weaker provider.

### 4.6 Enforcement parity — the rule that prevents a quiet security regression

- **H1:** policy logic lives in one neutral module; each harness gets a shim translating its native pre-tool event.
- **H2:** the integrate-time ownership check (`paths_outside_ownership`, already exists) remains the backstop for every harness — it's post-hoc, and documented as such (§24: never call a fallback an enforcement guarantee).
- **H3:** staffing **refuses** to put a write role (Tier 2) on a harness whose manifest lacks a SUPPORTED blocking pre-tool hook *and* an OS sandbox. Read-only roles additionally require a verified way to deny edits. Today that means: claude ✓, codex ✓ (once hook shim + trust handled), agy pending verification, opencode read-only roles only until its v2 hook surface is confirmed.

## 5. First milestone — sequenced

Goal (directive §"first milestone"): one PM coordinating a small mixed-harness workforce, real changes, automatic worktree cleanup, retained evidence.

| # | Step | Depends on | Verifiable by |
|---|---|---|---|
| M0 | `worktrees.py` (W1–W8), `WORKTREE_*` events, `company cleanup [--dry-run]`, cleanup on MERGED/terminal states, replace `gategroup` force-remove | — | Tests for §39's scenarios: completion, cancel, crash-dirty (checkpoint), interrupted cleanup, active owner, orphan registration, human worktree untouched, idempotent re-run |
| M1 | Adapter contract + `NormalizedResult`; claude adapter (byte-identical argv, pinned by existing `TestClaudeHarnessIsUnchanged`); codex adapter using `--output-schema`; worker/costs/cli consume normalized results | — | Full suite green; recorded fixtures of real claude/codex output parse identically |
| M2 | Neutral policy core + shims for claude, codex, agy; fail-closed tool mapping; H3 staffing check | M1 | Existing guard tests run against every shim; a staffing test refuses an unenforced harness |
| M3 | agy + opencode adapters; `company harnesses [--check]` with version-stamped manifests | M1, M2 | Live smoke on a fixture repo (costs real tokens — needs approval) |
| M4 | `providers.yaml`, key_ref resolution, redaction, classification gate | M1 | Test that a planted key never appears in events/stdout logs; ineligible-provider refusal |
| M5 | PM persona driven via `company` verbs; mixed-workforce run on `fixtures/expense-demo` (PM Claude; backend Codex; QA agy), then repeated with a different PM harness | M0–M4 | §37 acceptance; `company cleanup --dry-run` reports zero safely-removable worktrees afterwards |

M0 and M1 are independent and can run in parallel. M0 is first in priority: it's the directive's non-negotiable, it fixes a live unsafe path (`gategroup.py:68`), and it doesn't depend on any harness question.

## 6. Decisions that need Riyan

1. **Live cross-harness runs cost money on four accounts** (M3, M5). Approve a budget, or say which accounts are available — codex's catalog was previously rejecting named models on the ChatGPT login.
2. **opencode's enforcement gap.** Accept "read-only roles only" until its v2 hook surface is verified, or prioritize finding it?
3. **`agy` not on PATH.** Add `~/.gemini/bin` to PATH, or let the adapter resolve that path explicitly? (Recommendation: adapter probes known paths; no shell-profile edits.)
4. **Directory layout.** §29 is explicitly conceptual. Recommendation: keep `tools/company/` and add modules (`worktrees.py`, `adapters/*.py`, `policy.py`, `providers.py`) rather than a repo-wide move that would churn every import and test for no behavioral gain.
