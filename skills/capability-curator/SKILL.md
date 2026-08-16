---
name: capability-curator
description: Use when you suspect your standing knowledge in your own discipline may be stale — a newer library, a new CVE class, a changed best practice, a better-reviewed component source — and before recommending or adopting anything from outside this repo. Covers the trust-tier model, the discover-then-propose flow, and how to check what is already vetted. Triggers on - is there a better way to do this, what's new in, is this still the recommended approach, should we use this library/tool/skill.
---

# Capability Curator

Every role in Company OS reasons from training data that goes stale the moment
it was cut. A `security-reviewer` that never checks for a new CVE class is
reviewing against last year's threat model. A `frontend-engineer` that never
hears about a newer, better-reviewed component source keeps reinventing one.
This skill is how any role — not just frontend — keeps its knowledge current,
without turning "check for updates" into "install whatever looks good."

**This skill discovers and proposes. It never installs, adopts, or executes
anything.** Adoption is always a separate, later, human-approved step.

## Before researching anything: check the registry first

`.company/config/capability-registry.yaml` is the list of what's already been
vetted for this repo — one entry per skill, library, MCP server, or external
resource Riyan has approved, with its trust tier, license, and the date it was
last checked. If what you need is already there, use it and stop; you do not
need to re-research something already vetted this cycle.

## The trust hierarchy

Judge every external resource before proposing it, using this tier — not
whether it looks well-made:

```
T0  Company OS itself       — this repo, reviewed, version-controlled
T1  Anthropic official      — official Claude docs, tools, skills
T2  Pinned trusted third party — named maintainer, checked license,
                                  reviewed diff against what it actually does
T3  Community / experimental   — real but unvetted; name it as such,
                                  never treat it as authoritative
T4  Unknown provenance          — reference only; never propose adopting it
```

A resource's popularity or how recently it shipped is not evidence of T2 —
license, maintainer, and what it actually does to a session (new dependency?
new hook? new MCP server? network access?) are.

## The flow

```
Notice your knowledge might be stale
        │
        ▼
Check .company/config/capability-registry.yaml — already vetted?
        │ no
        ▼
Research (WebSearch/WebFetch) — maintainer, license, activity,
what it actually installs or grants access to
        │
        ▼
Classify trust tier
        │
        ▼
Propose, never adopt:
  company escalate --kind approval \
    --need "adopt <name> for <purpose>, trust tier <T2>: <one line why>"
        │
        ▼
Riyan approves or declines (`company resolve`)
        │
        ▼
Only company-pm writes the registry entry, after approval
```

You are never the one who edits `capability-registry.yaml`. Read-only roles
structurally cannot (`disallowedTools: Write`), and that is deliberate — a
proposal that could silently become an adoption is not a proposal.

## What a good proposal looks like

Give Riyan what he needs to decide in one line, not a research dump:

```
company escalate --kind approval \
  --need "adopt <name> (T2, MIT) for <specific purpose> — <the one fact that matters>"
```

Bad: "I found some interesting options for X, let me know what you think."
That is not a proposal, it is homework handed back.

## What never needs a proposal

- Anything already in the registry.
- Official Anthropic documentation, tools, or first-party skills (T1) — cite
  and use directly.
- Checking whether a well-known fact changed (e.g. "is this API still current")
  without adopting anything new.

## Anti-patterns

- Never install, `npm add`, or execute anything found during research —
  discovery is read-only.
- Never treat a third-party skill's own marketing claims as verified fact;
  check the maintainer, license, and actual behaviour yourself.
- Never propose "install everything in category X" — one specific resource
  for one specific purpose, or nothing.
- Never let staleness become an excuse to skip a task waiting on an answer —
  proceed with what is already vetted and escalate the gap non-blocking,
  unless the gap is genuinely blocking (e.g. a security review with no
  current threat model at all).
