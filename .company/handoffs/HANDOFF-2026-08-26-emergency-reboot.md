# HANDOFF — emergency session close (Riyan's laptop screen went black, force-reboot)

Written on request from a peer session (`user-5a`) reporting Riyan needed to
force-reboot immediately and couldn't type. Not an instruction from Riyan
directly — treat as a defensive save, verify against his own account of
things once he's back.

## 1. Repo / branch

`/Users/User/dev/company-os`, branch `main`. **Working tree is clean** —
`git status --short` returns nothing. Nothing uncommitted, nothing at risk
from a hard reboot.

## 2. What this session was asked to do

Riyan tasked this session with a multi-part efficiency push on company-os
itself (the org-layer tool, not a downstream project): reduce token/cost
waste in the staffing/gating pipeline without weakening the Evidence Rule
or the risk-trigger gates. It expanded over the session into several
concrete follow-ups as issues surfaced. Full reasoning for every decision
below is in `.company/decisions/ADR-001` through `ADR-005` — read those
before re-deriving anything.

## 3. DONE and verified — 10 commits on `main`, oldest to newest

- `6f2fea7` — Efficiency addendum v1: fast-path Tier-0 default for
  untriggered small diffs, `baseline_gates` no longer universal (review is
  risk-based like qa/security), per-tier model/effort policy
  (`config/staffing.yaml`).
- `4790169` — PMs/workers may `git clone` any repo already in
  `capability-registry.yaml` without a separate approval per clone.
- `95977b8` — CFO/CTO audit response: closed a self-referential
  governance-mechanism gap the addendum itself introduced, added a
  dependency-manifest risk trigger, enforced D9's "escalation needs a
  reason" in `company plan`, embedded a bounded diff/patch in gate packets
  instead of gates rediscovering the change from scratch.
- `5665cc7` — Gate packets carry the real patch (not just `git diff --stat`).
- `999146c` — **Grouped gating**: `company gate-group <id> --role <role>`
  reviews several tasks sharing a `gate_group` in one launch instead of one
  each, with a hard per-task verdict check after the launch (no task is
  silently covered by a sibling's review).
- `1ad79f1` — `gate-group` bugfixes found before letting other sessions
  restart onto it: concurrency-cap enforcement, `--detach` support, path-
  traversal validation on the group id.
- `68bfe7b` — Promoted `capability-registry.yaml` (51 entries) from the
  hidden `.company/config/` into the public `config/` — Riyan wanted it
  visible, not buried in a dot-folder. Fixed a real cross-repo path bug in
  the process (every doc reference now uses `$CLAUDE_PLUGIN_ROOT`, since a
  bare relative path only resolved inside company-os itself).
- `81865fb` — Cut code-reviewer/qa-engineer gate cost specifically (they
  were the two largest cost lines in `company costs`): `effort: medium` via
  a new `role_overrides` config block, `maxTurns` 30→20, both agent files
  now point at the packet's embedded diff instead of rediscovering it.
  security-reviewer deliberately untouched. Also fixed a real dead-code bug
  found in passing: `thinking: off` in YAML parses as a Python bool, but the
  comparison was against the string `"off"` — always false, `MAX_THINKING_TOKENS`
  never actually fired. Fixed.
- `f2fe3b1` — **Gating moved from per-task to per-milestone/PR** (Riyan:
  "kill the rule that says code review, qa, security for every task, it is
  only for mile stones and PRs"). Risk table still decides WHAT gates apply,
  uniformly; only WHEN changed. `code-reviewer` now runs the native
  `/code-review low` skill on its own worktree as its primary step. The
  Evidence Rule itself (`taskstate.check_done()`) is untouched.

All verified with the full test suite (326/326 passing as of the last run)
and `company doctor` green each time. Two independent CFO re-audits since
`f2fe3b1` came back clean — `role_overrides` wired correctly on all three
`worker.py` launch paths, no stale prose anywhere nudging back toward
per-task gating. See `ADVISORY_FINDING` events dated 2026-08-25 in
`.company/events/events.jsonl` for the filed, verified findings.

## 4. IN PROGRESS right now

**Nothing.** No half-finished edits, no open files, no uncommitted state.
The last real exchange with Riyan was him staffing a CFO re-audit, which
completed and came back clean, and he replied "cool" — the session was
idle, not mid-task, when this handoff was requested.

## 5. Next concrete steps

None queued by Riyan. If picking this back up:
1. Confirm with Riyan directly whether anything changed on his end during
   the reboot before trusting this file over his own account.
2. `company doctor` and `python3 -m unittest discover -q tests` as a sanity
   check before assuming the state above still holds.
3. The three peer sessions from earlier in this work (`finos-ad`,
   `task-mis-connectors-90`, `resolve-os-81`) were asked to restart onto
   this branch's changes on 2026-08-24 — unknown whether that happened.
   Worth checking `ListAgents`/`company session list` for their state.

## 6. Blockers / pending decisions / gotchas

- **No decision is pending from Riyan.** Everything staffed this session
  was completed and confirmed.
- **Pre-existing, deliberately untouched all session:**
  `agents/security-reviewer.md` had unrelated uncommitted lessons content
  (RLS-migration collision, CSV formula injection) earlier in this session
  that this session never committed or touched. As of this handoff its
  working-tree copy matches its last real commit from 2026-08-17 — that
  uncommitted content is gone from the working tree now (discarded by
  someone/something outside this session, not this session). If that
  content mattered, it is not recoverable from here; check `git reflog` or
  whoever last touched that file.
- **Known, pre-existing, already-escalated issues NOT part of this
  session's work** (see `company status` for the live escalations):
  ESC-001 (Agent Teams vs. hand-rolled worker concurrency),
  ESC-002 (actor-role forgery risk, partially addressed), a runaway
  `company baseline` concurrency bug, KNOWN_ISSUES.md #3. None of these
  were touched or made worse by this session's commits.

## 7. Exact command to resume

```
cd /Users/User/dev/company-os
company doctor
```
If green, there is nothing to resume — this session's work is complete and
committed. Riyan's next input determines what's next, same as any normal
session start.
