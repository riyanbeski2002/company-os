# BYO-model: running company-os on a harness other than Claude Code

company-os's Tier-1/Tier-2 workers used to be a hardcoded `claude -p ...`
subprocess (`tools/company/worker.py`, pre-2026-10-19). `tools/company/harness.py`
and `config/harness.yaml` are the seam that removed that: a **harness** is a
declarative command template plus a small amount of env policy, resolved per
role. The shipped default (`claude`) reproduces the old hardcoded behavior
byte-for-byte — see `tests/test_harness.py`'s
`TestClaudeHarnessIsUnchanged`, which pins the exact argv and stripped env
vars down so this can't silently drift.

This is modeled on the same problem paperclip
(github.com/paperclipai/paperclip) solves with its "any model, any agent, one
org chart" adapter layer — company-os needed its own version, scoped to a
single-user, terminal-native, evidence-first system rather than a hosted
multi-tenant one.

## What switching a role's harness actually changes

**Guards (2026-10-30).** The ownership, secret-read and shell guards are
harness-neutral policy (`hooks/policy.py`). What differs per harness is how
that policy reaches the worker, declared as `guards:`:

- `claude-plugin`: Claude Code loads `hooks/hooks.json` via `--plugin-dir`.
  It is inferred when that flag is in the command, so older configs keep
  working.
- `shim`: company-os installs `hooks/guard.py` into the harness's own
  blocking pre-tool hook for each launch. Counts only once `guards_verified` records a
  live smoke test (migration doc §4.6), because a CLI that silently skips an
  untrusted hook is otherwise indistinguishable from one that enforces it.
- `external`: you assert equivalent enforcement by other means. This is
  recorded in every `WORKER_STARTED`.

A harness with no guard mode gets **no launches at all**, advisors included,
because the secret-read guard matters for read-only roles too.
`worker._guarded_spec` refuses before anything is claimed, created or
logged. That was not true before 2026-10-30: a role pointed at `codex` ran
with none of the guards. The integrate-time ownership check
(`integrate.paths_outside_ownership`) still applies to every harness as an
after-the-fact backstop. It is not an enforcement guarantee. The OS sandbox
is a separate layer; `codex` provides its own through `sandbox_mode`.

`refuse_project_paths` lists project config the harness would run without
review. codex needs `--dangerously-bypass-hook-trust` for the guard hook to
fire headless, and that flag also waives review of the project's own
`.codex/` hooks. So a worktree containing `.codex/` (for an advisor, a
repo) is refused before `WORKER_STARTED`.

**Which harnesses are usable right now:** `company harnesses` (installed
path, version, drift from `verified_with`, guard mode, launchable or why
not); `--check` exits 1 if a harness that `default`/`roles` actually uses
can't launch or has drifted. After an upgrade, re-verify with
`company harnesses --smoke <name>`: one live worker turn that spends tokens,
then it prints what to record. An entry with no `command` is *catalogued
only*: its capabilities are recorded, but it's refused at resolve until an
invocation has been verified live.

Mechanically, `config/harness.yaml`'s `roles:` map is the entire integration
surface:

```yaml
roles:
  backend-engineer: my-other-cli
```

No edit to `worker.py`, `agents/backend-engineer.md`, or `staffing.yaml` is
needed. Every other role keeps using `default:` unless it has its own entry.

## The contract an alternate harness must meet

1. **Read the packet on stdin, exit 0 on a clean run.** `worker.py` always
   writes the task packet (or, for a non-native-agent-loading harness, the
   role's persona + the packet — see below) to the child process's stdin and
   closes it; a harness that blocks waiting for more input will hang until
   `worker.py`'s timeout kills it.
2. **Declare its stdout format as `output:`** (2026-10-30; before this, every
   harness had to print Claude's own result JSON, usually via a wrapper
   script). An adapter in `tools/company/adapters/` turns that format into
   one normalized result (`session_id`, `is_error`, `terminal_reason`,
   `structured_output`, `cost_usd`, `num_turns`, `usage`; field meanings in
   `adapters/__init__.py`), which is all `worker.py` and the event log ever
   see. Shipped formats: `claude-json` (the default when `output:` is absent)
   `codex-jsonl` and `agy-json`. A CLI with a new format means a new adapter module with
   one `parse(raw, exit_code)` function plus its tests against recorded real
   output, not a wrapper that impersonates Claude. An unknown `output:` is
   refused when the role is resolved, before anything launches. The
   normalized result is written to `state/workers/<actor>/result.json` next
   to the raw `stdout.json`.
3. **Declare `native_agent_loading: false`** if the backend has no
   equivalent of `claude --agent <role>` — no native way to load
   `agents/<role>.md` as the running persona. `worker.py` then prepends that
   file's body (frontmatter stripped, via `harness.load_persona`) to whatever
   it sends on stdin, so the role's actual instructions still reach the
   model. Leaving this `true` on a harness that can't do native agent
   loading means the model never sees its own job description.
4. **Never push.** A worker's whole world is its worktree (see `worker.py`'s
   `build_env`), and nothing about company-os's event-log-is-truth design
   expects a Tier-2 worker to reach outside it onto the network. A harness
   that can shell out arbitrary commands (`codex` can — Codex runs shell
   commands inside its own sandbox) must not let a
   `git push` (or any other network-reaching git operation) happen from
   inside a worker's turn. This is paperclip's own rule for its adapters
   (`packages/adapters/AUTHORING.md`, enforced there by a static scanner);
   company-os has no scanner for it yet — treat it as a manual review point
   when writing a new adapter script, the way the sandbox flags below are a
   manual review point for `codex`.

A CLI that can't natively satisfy (1)/(2) — most can satisfy (1), fewer
emit exactly the right JSON shape unprompted — gets wrapped in a thin adapter
script that does the stdin/stdout translation. Point `command` at that script
instead of the raw CLI.

## harness.yaml fields, in full

```yaml
default: claude          # harness every role uses unless overridden
roles:
  some-role: some-harness # per-role override, optional

harnesses:
  some-harness:
    native_agent_loading: false   # see contract point 3
    output: codex-jsonl            # stdout format, see contract point 2
                                    # (default claude-json)
    guards: shim                   # how hooks/policy.py reaches this
                                    # harness's workers: claude-plugin |
                                    # shim | external. A harness with none
                                    # gets NO launches (see "Guards" below).
    command: [...]                 # argv template, see placeholders below
    binary: agy                    # how `company harnesses` finds the CLI:
    binary_paths: ["~/.gemini/bin/agy"]  # PATH first, then these (only
                                    # used in argv when not on PATH)
    verified_with: "agy 1.4.11"    # version this entry was checked against;
                                    # a different installed version is drift
    capabilities:                  # SUPPORTED | UNSUPPORTED | UNKNOWN |
      headless: SUPPORTED           # DISABLED | REQUIRES_CONFIGURATION —
                                    # never optimistic; unconfirmed = UNKNOWN
    trailing_args: ["-"]           # appended after every flag build_command
                                    # adds (e.g. a stdin-prompt marker)
    model_flag: --model            # omit if the CLI takes no model flag
    effort_flag: --effort          # omit if the CLI takes no effort flag
    skip_permissions_flag: --foo   # omit if the CLI has nothing like it;
                                    # harness.build_command just won't pass
                                    # skip_permissions through
    model_map:                     # staffing.yaml's abstract tier model
      sonnet: gpt-5.1               # names (sonnet/opus/haiku) remapped to
      opus: gpt-5.1-high            # this backend's own model ids; an
      haiku: gpt-5.1-mini           # unmapped name passes through unchanged
    effort_map:
      medium: standard
    strip_env: [SOME_VENDOR_TOKEN]  # stripped before launch (secrets,
                                     # parent-session identity leakage, etc.)
    extra_env:
      OTHER_CLI_MODE: headless
    provider_env:                  # how a non-native model provider
      key: ANTHROPIC_AUTH_TOKEN     # (providers.yaml) reaches this worker;
      base_url: ANTHROPIC_BASE_URL  # omit and the harness takes only its
                                    # own login (see "Model providers")
```

### Command template placeholders

`command` is a plain argv list. Any token that is exactly `{name}` gets
substituted:

| Placeholder | Value |
|---|---|
| `{role}` | the role name (`backend-engineer`, `code-reviewer`, ...) |
| `{plugin_root}` | absolute path to the company-os checkout |
| `{allowed_tools}` | the role's comma-joined tool list (`worker.py`'s `ROLE_TOOLS`, narrower than the role's `agents/*.md` frontmatter — see that file's comment on why) |
| `{schema_json}` | `RESULT_SCHEMA` as a JSON string, or **absent** on a readonly/advisor launch |

**A placeholder that resolves to nothing (only `{schema_json}` on a
schema-less launch today) is dropped along with the literal flag token
immediately before it.** This is what lets one `claude` entry serve both the
schema-bearing Tier-2 launch and the schema-less Tier-1 advisor launch
without two near-duplicate templates — see `harness.build_command`'s
docstring. Design a new harness's template the same way if it also has an
optional flag+value pair.

An unrecognized `{placeholder}` raises `HarnessError` at launch time rather
than silently keeping the literal braces in the command.

## Worked example: `codex` (real, as of 2026-10-19)

`config/harness.yaml`'s `codex` entry is company-os's second real harness —
not a template. Its invocation was read from paperclip's own codex-local
adapter source (`packages/adapters/codex-local/src/server/{codex-args.ts,
parse.ts}`, github.com/paperclipai/paperclip, MIT), then live-smoke-tested
end to end on this machine (codex-cli 0.163.0) before being committed, and
one correction the live test caught: the research pass that read the
paperclip source reported no cache-write usage field; the real, running
`codex exec --json` output has one (`cache_write_input_tokens`), and
`tools/company/adapters/codex.py` reads it. (Until 2026-10-30 that parsing
lived in a wrapper script, `adapters/codex_adapter.py`; the harness now runs
`codex exec` with the identical argv and declares `output: codex-jsonl`. The
script remains as a shim for older `.company/config/harness.yaml` copies.) Confirm-by-running beats
confirm-by-reading-someone-else's-source, even when that source is real and
MIT-licensed — this is why.

It is **not staffed to any role** — it exists, passes
`tests/test_harness.py`/`tests/test_adapters.py`, and a real
`codex exec` invocation was verified to work, but pointing a live role's
`roles:` entry at it is a deliberate staffing choice for later, and
`model_flag` is deliberately left unset (see the comment in
`config/harness.yaml`: a plausible-looking model id was rejected outright by
this account when live-tested, so no `model_map` is shipped rather than one
that would silently misroute every launch).

Wiring in a **third** backend (Cursor, Gemini CLI, OpenCode, ...) means
repeating the same discipline:

1. Confirm its actual non-interactive invocation syntax from that project's
   own current docs or source — don't copy flags from memory or from
   another tool's convention.
2. Name its stdout format in `output:`. If no adapter exists for that
   format yet, write one in `tools/company/adapters/` (contract point 2),
   tested against recorded real output. A wrapper script is only for a CLI
   that can't take the packet on stdin (contract point 1).
3. **Live-smoke-test the exact invocation** before trusting anything read
   about it, the same way `codex`'s flags were confirmed by actually running
   them, not just by reading paperclip's source.
4. Add a `harnesses:` entry, and extend `tests/test_harness.py` with the
   same pinning-test treatment `TestClaudeHarnessIsUnchanged`/
   `TestCodexHarnessIsReal` get, so the new entry can't silently drift.
5. Only then point a real role's `roles:` entry at it.

## Model providers: bring your own key (providers.yaml, M4)

A harness is the CLI; a provider is whose endpoint and credentials it uses.
Every role defaults to `native`, the CLI's own login, which injects nothing.
To run a role on another endpoint, declare the provider in
`config/providers.yaml` (or `.company/config/providers.yaml`) and route the
role to it:

```yaml
default: native
roles:
  code-reviewer: openrouter
providers:
  openrouter:
    auth: env                      # env | none
    key_ref: OPENROUTER_API_KEY    # the env var's NAME, never the key
    trust: third_party             # first_party | third_party | local
    max_classification: INTERNAL   # most sensitive project it may see
    base_url: https://openrouter.ai/api
```

Then `export OPENROUTER_API_KEY=...` in the shell that launches workers.

- **No key in config.** A value shaped like a key, anywhere in the file
  (comments included), fails the load.
- **The key goes in one place.** It's read from the launcher's env and set
  only in the variable the harness declares in `provider_env`. The
  `key_ref` variable itself is removed from the worker's env. After the run,
  it's scrubbed from `stdout.json`/`stderr.log` before anything parses them,
  so events and `result.json` can't carry it.
- **Classification gate.** If project.yaml's `data_classification` is above
  the provider's `max_classification`, the launch is refused before
  anything is claimed, and a `decision` escalation is raised. It never falls
  back to another provider. `native` has no ceiling.
- **Refused up front:** an unset key, or a harness with no `provider_env`
  (today only `claude` has one).
- `company harnesses` lists the providers, the routing, and whether each key
  is set (yes/no only). A broken providers.yaml fails `--check`.

Not covered yet: keychain lookup (env only), and provider wiring for codex
(which takes providers through `-c model_providers…`, not env).

## What this does *not* solve

- **Session/pane runtime** (spawning a terminal pane, reattaching after a
  reboot, herdr vs. tmux) is a different abstraction, owned by cmd-center's
  `Runtime` port (see `~/dev/cmd-center/.planning/ROADMAP.md`, Phase 7) — this
  module is about *which process runs a worker's turn*, not *which terminal
  multiplexer hosts the session*. The two are complementary, not competing.
- **staffing.yaml's tier policy** (which tier gets which model/effort) stays
  expressed in Claude's own vocabulary (`sonnet`/`opus`/`haiku`,
  `low`/`medium`/`high`) on purpose — `model_map`/`effort_map` translate that
  vocabulary at the harness boundary instead of rewriting the policy file
  for every backend.
