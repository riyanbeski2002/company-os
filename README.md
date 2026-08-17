# Company OS

An organisational operating layer over Claude Code. One loop:

```
CEO request → PM → staffing decision → isolated workers → structured state
→ independent review → integration → executive report
```

Built on Claude Code v2.1.233. Verified on macOS.

## The two ideas everything else serves

**Events are truth.** `.company/events/events.jsonl` is append-only and
authoritative. Task files in `.company/tasks/` are a *view*, rebuilt by
replaying the log. Workers never mutate task files — they append events. This
removes write races between concurrent processes and makes crash recovery a
replay rather than a repair.

**Evidence, not assertion.** A task cannot reach `DONE` without a commit SHA, a
`TEST_RUN` event carrying a real exit code of 0, and — where the risk table
requires a gate — a review event authored by a **different worker** than the
implementer. The state machine refuses the transition otherwise. No agent
certifies its own work.

## Install

```bash
./install.sh          # PATH + plugin registration + a self-check
```

Idempotent, backs up `settings.json`, and refuses to finish if the tests fail.

## Onboarding a real repo

Company OS is aimed at **brownfield work** — half-built and live repos being
upgraded, not greenfield scaffolds. Four commands, in this order:

```bash
cd /path/to/your/repo
company init            # scaffold .company/
company detect --write  # find the stack and the strongest verify command
company baseline        # record how the repo behaves BEFORE any work
company doctor          # preflight; fix whatever it flags
```

**`company baseline` is the one people skip and regret.** V1 required a green
test run to close a task. On a repo that is already red — which most real repos
are — every task would be refused forever for damage the worker did not do, and
the only escapes are to fix unrelated code or to lie about the exit code.

The baseline changes the rule to **no worse than when we started**:

| Baseline | To close a task |
|---|---|
| green | must be green. Strict, unchanged from V1. |
| red | must add no failures, and must not turn a passing check red. |

It is recorded as an event, so it cannot be quietly adjusted later to make a red
run look acceptable. And a red baseline is reported loudly rather than adopted:
the pre-existing failures stay your problem, they just stop being *the worker's*
problem.

### What `doctor` checks

git repo · not `$HOME` · has commits · **working tree clean** · current branch ·
**paths without spaces** · a verify command exists · `.company/` initialised ·
baseline recorded.

Two of those are easy to underestimate on a live repo:

- **A dirty working tree.** Worktrees branch from a *committed* ref, so
  uncommitted work is invisible to every worker and at risk if you later reset.
  Commit or stash first.
- **Paths containing spaces.** Ownership globs and shell commands must quote
  them. Real repos have `Asset Audit.js` in them.

### What counts as "green" in your stack

`company detect` picks the strongest available check and tells you how much it
proves:

| Strategy | Strength |
|---|---|
| `npm test` / pytest / unittest / `go test` / `cargo test` / `make test` | **behaviour** |
| Apps Script or plain JS with no tests → `node --check` on every source file | **syntax-only** |
| Python with no tests → `compileall` | **syntax-only** |

A syntax-only check is reported with a warning, because a worker can satisfy it
while breaking behaviour completely. It is real evidence — it genuinely fails on
a genuine break — but treat "green" as weak, and add real tests before trusting
it on live code. `npm init`'s placeholder test script is deliberately *not*
accepted: it exits 1 and tests nothing.

If nothing is detected, `detect` refuses to invent a command and says so. Set
`verify:` in `.company/config/project.yaml` yourself.

### Watching consumption

```bash
company costs
```

**Nothing here is billed in dollars.** Workers authenticate through your
claude.ai login — `worker.py` strips `ANTHROPIC_API_KEY` specifically so a stale
key cannot divert them to separate API billing — so runs draw down **subscription
usage**, not money.

Claude Code still reports `total_cost_usd` in every result. That is a
**client-side estimate** of what the same work would have cost through the API,
computed from token counts against list prices. It is useful for comparing runs
against each other and useless as a bill, so `company costs` labels it
`api_equivalent_usd` and leads with tokens instead.

Tokens are what a subscription actually meters, and the shape is not what you'd
guess. Across 16 fixture runs:

| | tokens |
|---|---|
| output | 98,215 |
| cache read | **2,488,591** |

Cache reads dominate by ~25x, because a worker re-reads its cached context every
turn. That is the number to watch when runs start hitting plan limits.

### The single biggest lever: an agent's `tools:` list

An agent with no tool restriction carries **every tool definition** in context on
every turn. Measured on one machine with an identical trivial prompt:

| configuration | base context per turn |
|---|---|
| no agent — all tools | 36,151 |
| `--agent backend-engineer` (6 tools) | **6,016** |
| `--agent code-reviewer` (4 tools) | 5,221 |
| + `--strict-mcp-config` | 4,907 |

**83–86% of a worker's per-turn cost is tool definitions it never calls.** The
`tools:` line in an agent file removes the definitions, not just permission to
use them, and the saving is paid back on every turn.

Two things this measurement corrected:

- Disabling MCP servers and plugins saves only ~3% (35,883 → 34,706). It is the
  obvious lever and it is nearly worthless on its own.
- `company-pm` originally had no `tools:` list, so it paid 36,151 per turn as the
  longest-running agent in the system. Adding one took it to 10,811 — **~659,000
  tokens saved on a single 26-turn run.**

So: give every agent an explicit `tools:` list, and add a tool to it only when
the agent genuinely cannot work without one.

### The second lever: what accumulates

Base context is only part of it — measured workers averaged 8,000–15,600 per
turn against a 6,000 base. The rest is conversation: file contents and command
output, re-read on every subsequent turn. The worker agents are instructed to
send bulky output to a file and read the tail, and to grep rather than read whole
files. Explicitly **not** to check less — only to carry less.

## Commands

| Command | Purpose |
|---|---|
| `company init` | Scaffold `.company/` in this repo. Idempotent. |
| `company event <task> <TYPE> [--data JSON] [--evidence ...]` | Append one event. **Worker-facing.** |
| `company handoff <task> --from R --to R --stdin` | Write a handoff. **Worker-facing.** |
| `company gates --request "..." --paths <globs>` | Deterministic risk-table lookup. |
| `company plan [--spec f.json]` | Apply the risk table to a proposed task graph; refuse colliding parallel work. |
| `company staff [--project P]` | Apply a plan: tasks in the log, branches and worktrees on disk. |
| `company run <task> --role <agent>` | Launch a Tier-2 worker: worktree, packet, supervision, budget. |
| `company task show\|advance <id>` | Inspect, or transition (enforces the Evidence Rule). |
| `company integrate [--task T]` | Rebase into `integration`, run the suite there, merge **only** on green. |
| `company rebuild [--verify]` | Replay events into views; `--verify` compares instead of writing. |
| `company status [--json]` | Derived state only. Never estimated. |
| `company report` | Executive summary: outcomes, not activity. |
| `company escalate --kind K --need "..."` | Ask the CEO for something the PM cannot do or decide. |
| `company resolve <ESC-id> --resolution "..."` | CEO: answer an escalation. |
| `company gallery [--script\|--open]` | Compute how many tmux panes the run needs, or open them. |
| `company stop` | Kill every worker; preserve every worktree. |
| `company session announce --doing "..." [--globs g,g]` | Tell peer PM sessions on this checkout what you're doing right now. |
| `company session list` | Every announced session, most-recent first — check before staffing new work. |
| `company session done` | Clear your entry (on finish, handoff, or session end). |

Workers only ever see two of these: `event` and `handoff`.

Exit codes: `0` ok · `1` usage/environment · `2` missing evidence · `3`
Evidence Rule refusal · `4` replay mismatch.

## Execution tiers

Pick the cheapest that works. Tier inflation is the main failure mode.

- **Tier 0** — the PM does it inline. Most requests.
- **Tier 1** — a subagent. Read-heavy work whose output is a judgment: review,
  QA, security, research. No worktree, no branch, no supervision.
- **Tier 2** — a headless `claude -p` worker with its own worktree, branch, and
  permission set. Only for parallel implementation producing substantial diffs.

A task that could have been Tier 1 but ran as Tier 2 is a defect.

## Why `claude -p` and not `--bg`

They are mutually exclusive: `claude -p` rejects `--bg`. Background sessions
give a nicer human surface (agent view, automatic worktrees) but no
machine-checkable return value. `-p` returns a structured result, an exit code,
and a `session_id` for a process we own. The Evidence Rule is made of
checkable things, so the checkable surface wins.

The consequence is permanent: **agent view cannot observe Company OS workers.**
Watch `.company/state/workers/<id>/` instead.

## Things that will bite you

These were all found the hard way, in real runs.

- **`claude -p` hangs forever on an inherited open stdin.** Workers get the
  packet on stdin and an explicit close. Never launch one with stdin attached
  to a live pipe.
- **`--allowedTools` is variadic and will eat your prompt.** Written as
  `claude -p --allowedTools "Read,Bash" "do the thing"`, the prompt is parsed as
  another tool name and Claude Code exits with *"Input must be provided either
  through stdin or as a prompt argument"*. Always pass the prompt on **stdin**,
  which is what `worker.py` does anyway.
- **`ANTHROPIC_API_KEY` silently overrides your claude.ai login.** If it is set
  and invalid, `claude -p` returns `terminal_reason: "api_error"` with zero
  tokens consumed and no useful message. `worker.py` strips it.
- **A worker lives inside its worktree.** Owned globs must resolve against the
  worktree, not the main checkout, or the ownership guard locks the worker out
  of its own files.
- **`--bare` skips hooks**, so it cannot be used for Tier-2 workers — the
  ownership guard would not load.
- **Non-bare `-p` loads `~/.claude/CLAUDE.md` into every worker.** Keep it small
  or every worker pays for it.
- **`--worktree` names branches `worktree-<name>`** and enables a static Bash
  command-shape checker. We use plain `git worktree add` to control branch
  naming; see the residual gap below for what that costs.
- **There is no `--max-turns` CLI flag.** Turn ceilings come from `maxTurns` in
  agent frontmatter.
- **A worker does not get to name itself.** `$COMPANY_ACTOR` is set by the
  launcher and overrides any `--actor` a worker passes. Left unenforced, a
  worker can sign its own gate under a reviewer's name — a real reviewer run
  signed itself `qa/verifier` rather than its assigned id.
- **A finished worker leaves the same dead pid file as a crashed one.** Only a
  terminal event in the log distinguishes them, so liveness alone must never be
  the stall signal.
- **`os.kill(pid, 0)` succeeds on a zombie.** An exited-but-unreaped worker
  would otherwise hold its concurrency slot and queue everything behind a corpse.
- **A headless PM cannot leave work running past its own turn.** Claude Code
  kills a `-p` run's background shell tasks seconds after its final result, so a
  worker started with `company run ... &` dies mid-edit — however truthfully the
  PM reported it as running. Use `company run --detach`, which puts the
  supervisor in its own session. This is the single most important thing to know
  before letting a PM orchestrate headlessly.
- **Two workers in one worktree overwrite each other.** `--detach` makes this
  easy to do by accident, so `launch` refuses a second live worker on a task.

## Residual gap: Bash is not fully sandboxed

The ownership hook (`guard_paths.py`) sees `Write`, `Edit`, and `NotebookEdit`.
It does **not** see `Bash`. A shell redirect could therefore write outside a
task's owned globs.

`protect_branches.py` closes the common shapes — redirects, `tee`, `cp`/`mv`,
and `cd` to absolute paths outside the worktree — but this is pattern matching,
not a sandbox. A determined worker could still escape it, and Claude Code's own
worktree isolation (which refuses command shapes it cannot statically verify)
is not active because we create worktrees with plain git.

Treat the guards as protection against *mistakes*, not against an adversary.
If you need a real boundary, run workers under Claude Code sandboxing or in a
container.

## Layout

```
.claude-plugin/plugin.json
agents/          6 roles: company-pm, backend/frontend-engineer,
                 code-reviewer, qa-engineer, security-reviewer
hooks/           guard_paths.py · protect_branches.py · emit_exit.py · hooks.json
config/          risk-triggers.yaml · quality-gates.yaml · budgets.yaml
                 (copied into the target repo by `company init`)
tools/company/   eventlog · taskstate · pathrules · packet · worker · staffing
                 slots · integrate · render · cli
tools/mkfixture.sh
fixtures/expense-demo/
tests/
```

In a target repo, `.company/` holds operational truth: `events/`, `tasks/`,
`handoffs/`, `decisions/`, `escalations/`, `state/workers/`, `worktrees/`,
`reports/`.

`.claude/` describes behaviour. `.company/` describes truth. Nothing in
`.claude/` is ever the authoritative record of what the company is doing.

## The CEO is a capability, not just an approver

Riyan is CEO, CTO, product owner and client, and he is not a silent observer.
He can do things the PM structurally cannot: open tmux sessions, supply a
credential, reach a system the PM has no access to, decide between two options
that are both defensible, authorise spend.

So **being blocked in silence is the failure, not asking.** "Minimise
coordination" means don't make him schedule your work — it never meant never
ask. `company escalate` is the channel, and `status` puts a blocking ask above
everything else, ending with `Next  you — ESC-001: ...`.

Escalations are events like everything else. The files under
`.company/escalations/` are a rendered view, and a resolution stays in the log
as a permanent record of who decided what.

The tmux gallery works the same way: the PM runs `company gallery` to compute
how many sessions and panes the current run needs, then escalates that number
with the exact command. It never sits without observability because it cannot
open a window.

The gallery is display only — every pane is a `tail -f`. A test asserts the
generated script contains no `company event`, no `company run`, and no `git`.
Kill the tmux server mid-run and nothing about the loop changes.

## Not built yet

- **Tier-1 as true subagents.** `company run --role code-reviewer` launches a
  reviewer as a headless process so the gate is verifiable from the CLI. In
  normal operation the PM should spawn reviewers with the `Agent` tool, which is
  far cheaper. The Evidence Rule checks actor *identity*, not process type, so
  it holds either way.
- **`company decision`** for ADRs in `.company/decisions/`.
- **Escalation CLI.** `.company/escalations/` is read by `status` but nothing
  writes to it yet.

## Tests

```bash
python3 -m unittest discover -q tests
```

Stdlib only — no pytest, no dependencies. The event-log suite spawns 8
concurrent processes writing 200 events to prove the lock holds.
