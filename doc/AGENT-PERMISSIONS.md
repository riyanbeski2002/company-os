# Agent permission defaults

Paperclip (github.com/paperclipai/paperclip) documents an explicit
granted/not-granted table per trust tier (`doc/agent-permission-defaults.md`
in that repo) so a role's real reach is auditable without reading every
prompt. This is company-os's version of that table.

**This file is a summary, not a second source of truth.** The actual
enforcement is `agents/<role>.md`'s `tools:`/`disallowedTools:` frontmatter
(what Claude Code itself restricts a role to) and `tools/company/worker.py`'s
`ROLE_TOOLS` dict (the deliberately narrower set a *headless* Tier-2 launch
actually gets — see that file's comment on why interactive-only tools like
`ListAgents`/`SendMessage` are excluded there). If this table and either of
those ever disagree, the code is right and this file is stale — regenerate it
from `agents/*.md` and `worker.py` rather than trusting this prose.

## By role

| Role | Tier | Worktree | Write/Edit? | Headless tool set (worker.py ROLE_TOOLS) | Interactive-only extras (agents/*.md) |
|---|---|---|---|---|---|
| `company-pm` | 0 | main checkout | yes | — (runs as the main session, never a headless launch) | `Agent`, `Skill`, `ListAgents`, `SendMessage` |
| `backend-engineer` | 2 | own worktree | yes | `Read,Grep,Glob,Edit,Write,Bash` | `ListAgents`, `SendMessage` |
| `frontend-engineer` | 2 | own worktree | yes | `Read,Grep,Glob,Edit,Write,Bash` | `ListAgents`, `SendMessage` |
| `video-editor` | 2 | own worktree | yes | `Read,Grep,Glob,Edit,Write,Bash` | `ListAgents`, `SendMessage` |
| `code-reviewer` | 1 | none (reads a branch) | **no** | `Read,Grep,Glob,Bash` | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `qa-engineer` | 1 | none | **no** | `Read,Grep,Glob,Bash` | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `security-reviewer` | 1 | none | **no** | `Read,Grep,Glob,Bash` | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `cto-advisor` | 1 | none (reads the repo itself) | **no** | `Read,Grep,Glob,Bash` (launch_readonly's fixed set) | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `ciso-advisor` | 1 | none | **no** | `Read,Grep,Glob,Bash` | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `cfo-advisor` | 1 | none | **no** | `Read,Grep,Glob,Bash` | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `coo-advisor` | 1 | none | **no** | `Read,Grep,Glob,Bash` | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `pen_test` | 1 | none | **no** | `Read,Grep,Glob,Bash` | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `finance-analyst` | 1 | none | yes | n/a (not launched by worker.py's headless path) | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `legal-analyst` | 1 | none | **Write only — `Edit` is explicitly disallowed** | n/a | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |
| `product-designer` | 1 | none | Write only (no Bash/Edit) | n/a | `Skill`, `WebSearch`, `ListAgents`, `SendMessage` |

## What's consistent across every role

- **Read-only by construction, not by convention**, for every gate/advisor
  role (`code-reviewer`, `qa-engineer`, `security-reviewer`, `cto/ciso/cfo/
  coo-advisor`, `pen_test`): `disallowedTools: Write, Edit, NotebookEdit` is
  in the frontmatter itself, so a prompt-level mistake can't grant a write a
  judgment role was never supposed to have.
- **`legal-analyst` gets `Write` but not `Edit`** — a deliberate, narrower
  carve-out than the advisor roles' full read-only lock: it authors new
  redline/summary files but can never modify a source contract in place (see
  that file's "What you never do" section).
- **No role gets `NotebookEdit`.** Nothing in this system's workflow touches
  notebooks; it is absent everywhere rather than granted and unused.
- **`ListAgents`/`SendMessage` only ever matter in the interactive-tmux-pane
  case.** A headless `company run --detach`/`company advise` launch
  overrides the agent file's `tools:` line with `worker.py`'s fixed,
  narrower set, so granting these in `agents/*.md` costs nothing extra for
  the common (headless) path — see each file's own comment to this effect.
- **Only Tier-2 implementers and `company-pm` itself can write code.** Every
  Tier-1 role that isn't `finance-analyst`/`legal-analyst`/`product-designer`
  (none of which touch the codebase under review) is read-only against the
  repo.

## Exceptions and known gaps (paperclip's "rollout" section, company-os's version)

- There is **no automatic permission audit on role creation** — a new
  `agents/<role>.md` with an overly broad `tools:` line is caught only by a
  human reading the diff, same as any other code review. Paperclip's
  equivalent (`doc/agent-permission-defaults.md`) is server-enforced; this is
  prompt-and-frontmatter-enforced, which is weaker by construction. Treat a
  new or edited `agents/*.md` as security-review-trigger material.
- **This table has no automated regeneration step.** It will drift if a role
  file changes and this file isn't updated alongside it. A future
  improvement would be a small script that diffs this table against
  `agents/*.md`/`worker.py`'s `ROLE_TOOLS` and fails `company doctor` on
  mismatch — not built yet.
