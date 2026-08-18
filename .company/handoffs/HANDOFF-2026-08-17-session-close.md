# Handoff — company-os session, 2026-08-17

⏩ RESUME HERE: nothing in flight, no blockers, safe to restart anytime.
This session did direct Tier-0 work on company-os itself (not a staffed
`company` task) — 12 commits, working tree clean except one file that
belongs to a different, still-live session (see "Not mine" below).

## Current state

- Branch: `main`. 12 commits ahead of where this session started (`4157cd4`
  through `99c44b6` — full list in `git log --oneline -12`).
- Working tree: clean, except `tools/company/escalations.py`, which is
  **another session's in-progress fix, not mine** — it's applying the same
  malformed-event guard I added to `taskstate.py`'s `STATUS_CHANGED`
  handler to `escalations.py`'s `ESCALATION_RAISED` handler. Leave it
  alone; don't commit it, don't revert it, don't finish it for them.
- Full test suite: 285/285 green as of the last commit.
- `.company/config/capability-registry.yaml`: 51 entries, all checked
  today, all verified against the real GitHub API (`gh api
  repos/<owner>/<repo>`) before being registered — see "How research was
  actually verified" below, this is the single most important working
  pattern from this session.

## What got done, in order

1. **Evidence Rule gap (finos, live bug)**: a Tier-2 worker could report
   `IMPLEMENTATION_READY` with a commit SHA that was 0 commits ahead of
   base — a no-op run self-reporting completion, tests trivially green
   because nothing changed. `cli.py` now runs `git rev-list --count
   base..sha` before allowing the event onto the log. 4 new tests
   (`tests/test_evidence_diff.py`).
2. **Cross-session coordination**, built after two top-level sessions
   edited this exact repo concurrently with zero visibility into each
   other: `company session announce|list|done|ping` (new
   `tools/company/sessions.py`), `SendMessage`/`ListAgents` granted to all
   11 agent roles (interactive-pane use only — headless launches via
   `worker.py`'s `ROLE_TOOLS` are untouched, deliberately), and a full
   "Coordinating with other sessions" section in `agents/company-pm.md`.
   `company session ping --target <tmux> --message "..."` is the
   SendMessage fallback (two-call `tmux send-keys` race fixed).
3. **`taskstate.fold()` crash fix**: a `STATUS_CHANGED` event with no
   `data.to` crashed replay for every project on the machine (this file is
   shared source). Now recorded under `_malformed_events`, replay stays
   total. 5 new tests (`tests/test_taskstate.py`).
4. **Corrected my own bad advice, with evidence**: told a peer session to
   fix a missing tool with `/exit` + `claude --continue`. It didn't work
   live. Reproduced it deliberately (widened a throwaway agent's `tools:`
   on disk, tried `-c` and `-r <session-id>` — both kept serving the
   original frozen tool list). **Only a genuinely new session (no
   `-c`/`-r` at all) re-reads the agent file** — documented in
   `company-pm.md`, recorded via `company lesson`.
5. **Two new agent roles**: `finance-analyst` and `legal-analyst` (Tier 1,
   no worktree) — real business deliverables (DCF/LBO/comps/pitch decks;
   contract review/NDA triage), backed by official Anthropic plugins
   (`anthropics/financial-services-plugins`, `anthropics/knowledge-work-
   plugins/legal`, both T1 Apache-2.0), not reimplemented from training
   knowledge. `install.sh` re-run — both symlinked into `~/.claude/agents/`
   and verified working from `/tmp`.
6. **~64 external GitHub repos/sites researched and classified** across
   four sweeps (Riyan supplied the lists in batches) — wired into
   `frontend-engineer`, `security-reviewer`, `cto-advisor`, `company-pm`,
   `cfo-advisor`, `finance-analyst`, `legal-analyst`, or registered as
   known-available with no owning agent, or explicitly skipped with a
   reason. Full breakdown is the registry itself plus the last ~8 commit
   messages.

## How research was actually verified — the pattern to keep using

Two Haiku research passes (fan-out subagents, then a WebFetch spot-check)
produced numbers that disagreed with each other enough to distrust both.
Went to the real GitHub API (`gh api repos/<owner>/<repo>`) as ground
truth for every single repo before registering or wiring it in. This
caught real errors:
- `shadcn-ui/ui` called T1 ("Anthropic-adjacent") — it isn't Anthropic,
  corrected to T2.
- `ByteByteGoHq/system-design-101` called "actively maintained through
  Feb 2026" — real last push is April 2025, 16 months stale. Now marked
  "least preference of anything in this file" in `cto-advisor.md`.
- `daytonaio/daytona`: I initially wrote "no license detected, skip" from
  the API's `license: null` field — **Riyan caught this as lazy**. The
  field was null because the LICENSE file isn't at the current
  default-branch HEAD (removed when the project was archived); fetched it
  directly at the pinned `v0.190.0` tag and it's real AGPL-3.0. Corrected
  to T2 reference/fallback — the real reason to prefer
  `vercel:vercel-sandbox` is that Daytona's own README says unmaintained
  since June 2026, not a fabricated licensing gap.
- Two "404s" (`leonxinx/taste-skill`, `vercel-lab/skills`) were typo'd
  slugs, not nonexistent repos — corrected to `Leonxlnx/taste-skill` and
  `vercel-labs/skills`, both real (also caught by Riyan).
- `nilbuild/driver.js` — confirmed legitimate via a GitHub API redirect
  check (`kamranahmedse/driver.js` transparently redirects to it — a real
  ownership transfer, not an impostor fork). Same check confirmed
  `block/goose` → `aaif-goose/goose` (Linux Foundation transfer, real).

**Lesson for whoever picks this up: don't trust a subagent's specific
numeric/factual claims (stars, license, "actively maintained") without an
independent check against the primary source — even when two passes agree
with each other, they can both be wrong the same way.**

## Standing rules this session established or reinforced

- A `tools:` grant and all agent-file prose is frozen into a session's
  system prompt at start — **nothing updates a running session**, not
  `-c`, not `-r`. Only a bare `claude --agent <role>` (losing history)
  picks up a changed file. Write a handoff first if there's context to
  lose — this file is that, for this session.
- Company-os's own agent files are symlinked (`~/.claude/agents/` →
  `~/dev/company-os/agents/`), so a committed (or even just saved,
  uncommitted) change is live for any *new* session immediately — no
  reinstall step, `install.sh` only needs re-running when a *new* agent
  file is added (not when an existing one is edited).
- Dual-use tools (sqlmap, Scrapling) get described factually with
  authorized-use-only framing, never refused outright — matches this
  session's actual operating constraints.
- "Publicly available" ≠ "licensed for reuse" — held this line on
  Dribbble when asked to scrape it for a reusable component library;
  Riyan agreed, it's now explicitly reference/inspiration-only in both
  `frontend-engineer.md` and `product-designer.md`'s research steps.

## What's genuinely still open (not blocking, just not done)

- The other session's `escalations.py` fix (see "Not mine" above) — will
  presumably land as its own commit at some point; not this session's job
  to finish or wait on.
- No `company session announce` was ever filed for this session's own
  work (the tooling didn't exist yet when this session started, and by
  the time it did, retrofitting it for already-completed work wasn't
  worth doing). A fresh session picking this up should announce itself if
  continuing similar work.
- Several registered-but-unwired capabilities (Dept-06-equivalent gaps
  from the original marketplace research, `pipecat`/`semantica`/`google-
  skills`/etc.) have no owning agent by design — that's intentional, not
  an oversight, per Riyan's "know it exists, don't force-fit" instruction.

## Files touched this session (by commit, newest first)

`99c44b6` agents/frontend-engineer.md, agents/product-designer.md
`3fb432d` .company/config/capability-registry.yaml, agents/frontend-engineer.md
`52d6f08` .company/config/capability-registry.yaml, agents/cto-advisor.md
`e50459c` .company/config/capability-registry.yaml, agents/company-pm.md, agents/cto-advisor.md, agents/frontend-engineer.md, agents/security-reviewer.md
`fbd2e09` .company/config/capability-registry.yaml, agents/company-pm.md, agents/security-reviewer.md
`3a461f7` .company/config/capability-registry.yaml, 6 agent files, README.md, skills/capability-curator/SKILL.md
`fc6234f` .company/config/capability-registry.yaml, README.md, agents/company-pm.md, tools/company/cli.py, tools/company/gallery.py, worker.py, tests/
`928d419` agents/finance-analyst.md (new), agents/legal-analyst.md (new), README.md, agents/company-pm.md, .company/config/capability-registry.yaml, tests/test_agents.py
`666160d` tools/company/taskstate.py, agents/company-pm.md, tests/test_taskstate.py (new)
`a4a660b` 5 agent files, tools/company/cli.py, gallery.py, worker.py, sessions.py (new), tests/
`3cbc9c5` tools/company/cli.py, sessions.py (new), gallery.py, worker.py, agents/company-pm.md, tests/
`4157cd4` tools/company/cli.py, tests/test_onboard.py (that one's the OTHER session's fix, committed separately/cleanly)

Ready for restart whenever Riyan wants to do it.
