# Goal

Paperclip-style documentation layering (`doc/GOAL.md` → product → design →
spec) puts a one-page vision statement above everything else. company-os's
`README.md` already covers mechanics in depth; this is the page above it —
what problem this solves, for whom, and what would make it a failure, so a
mechanical change can be checked against intent, not just against tests.

## The problem

Running several AI agents against real work (not toy examples) breaks down in
one specific way: an agent's own report of what it did is the only evidence
anyone has that it actually happened, and that report is cheap to produce and
expensive to verify by hand. Multiply that by several concurrent workers, a
few days, and a laptop that occasionally force-reboots, and the honest answer
to "did this actually ship, and was it reviewed by something other than the
agent that wrote it" becomes unknowable without re-deriving it from scratch
every time.

## What company-os actually is

A thin operating layer that makes an agent's own self-report structurally
unable to be the only source of truth. Every fact a task claims — "tests
pass," "this was reviewed," "this is done" — has to be backed by something a
different process can check independently: a commit SHA, a real exit code, a
review event from a different worker than the implementer. The event log is
append-only and authoritative; everything else (task state, status reports,
executive summaries) is a view, rebuilt by replaying it. See `README.md`'s
"The two ideas everything else serves" for the mechanics.

## Who this is for

One person (today: a single machine, a single git identity, no server, no
multi-tenant concept) running more coding/review/research work through AI
agents than they can personally re-verify line by line — and who would rather
trust a system that makes lying about progress structurally hard than trust
their own vigilance to catch it every time.

## What success looks like

- A status report never says more than the event log can prove.
- A task that reaches `DONE` genuinely shipped, was genuinely tested, and —
  where the risk table required it — was genuinely reviewed by something
  other than its own implementer.
- A crash (reboot, kill -9, a hard classifier block) loses at most the
  in-flight turn, never the record of what already happened.
- Adding a role, a gate, or a capability source doesn't require trusting a
  new category of self-report — it has to produce the same kind of checkable
  evidence everything else does.

## What this deliberately is not

- **Not a hosted product.** No server, no UI, no account system, no
  multi-tenant concept. (A narrow, read-only macOS companion for alerts and
  cost overview is being built as a *separate* project, `cmd-center` — see
  that repo's own `PROJECT.md` — not as a feature of company-os itself.)
- **Not vendor-exclusive by design**, even though it started that way: the
  agent-launch mechanism is now a configurable seam (`tools/company/
  harness.py`, see `doc/BYO-MODEL.md`), not a hardcoded dependency on one
  CLI.
- **Not a replacement for judgment.** The risk table, gates, and evidence
  rule catch "unverified" and "unreviewed" — they do not catch "verified but
  still a bad idea." A human still decides what's worth building.
