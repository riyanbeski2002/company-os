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

Run the bundled script rather than eyeballing dates — deterministic, tested,
never "roughly recent":
```bash
scripts/check_registry.py .company/config/capability-registry.yaml
```
Anything it reports `stale` genuinely needs a fresh check before you trust it
as still-vetted; anything `fresh` you can use as-is.

## How to research well, not just procedurally
Research is targeted investigation, not a link dump. For any real candidate:
1. **Maintainer** — active in the last 6 months, responds to issues? A
   year-stale project is a red flag regardless of stars.
2. **License** — read the actual file, not marketing copy. Catch GPL/MIT
   mismatches before they become someone else's problem later.
3. **Actual behaviour** — skim the source. What does it add: a runtime
   dependency, network calls, shell access, filesystem access? Each is a
   surface the repo inherits, whether or not it's ever mentioned in the docs.
4. **Real adoption**, not popularity — issue backlog age and response time
   beat star count. 2k stars with fast fixes beats 50k with a 3-month backlog.
5. **When comparing candidates**, one table: name, maintainer status, license,
   what it adds, the one dimension that actually matters here. The winner is
   usually obvious once it's written down — don't skip writing it down.

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

## Data classification gates what a query may contain

`.company/config/project.yaml` carries `data_classification`: `PUBLIC`,
`INTERNAL`, `CONFIDENTIAL`, or `SECRET` (defaults to `INTERNAL`). It governs
what a `WebSearch`/`WebFetch` query during research may contain — a search
query is data leaving this repo, same as any other external call.

```
PUBLIC / INTERNAL    — generic technique questions freely.
                        Still never paste proprietary business logic,
                        customer data, or unreleased-feature details.
CONFIDENTIAL / SECRET — technique-only queries. "What's the current
                        recommended way to rate-limit a public API" is fine.
                        "How do I fix this bug in <this repo's specific
                        pricing logic>" is not — genericise the question
                        before it leaves this repo, or don't ask it.
```

When in doubt, treat the repo as more sensitive than stated, not less.

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

## How a skill actually gets loaded, once approved

Most external skill repos in `capability-registry.yaml` are installed the
same way, via `vercel-labs/skills` (T2, MIT, itself registered) — the CLI
behind the `npx skills add <owner>/<repo>` command referenced elsewhere in
this repo:

```
npx skills add <owner>/<repo>              # installs it
npx skills use <owner>/<repo> | claude     # or use it once, without installing
```

This is the mechanism, not a new proposal target — cite it when telling
Riyan or another role how to actually get a registered skill loaded, don't
re-explain installation from scratch each time.

## What never needs a proposal

- Anything already in the registry. This includes actually `git clone`-ing
  the repo when a task needs to read or reuse its source — registration
  already carries `approved_by`/`approved_at`, so cloning it is not a new
  adoption decision. This applies to any role a task hands the work to, not
  only `company-pm` itself. What still needs a proposal: adopting something
  NOT yet in the registry, or a use of a registered entry outside what its
  `purpose` line actually covers (e.g. `caveman`'s BSL-1.1 engine, which its
  own entry says needs a fresh `company escalate` before real adoption).
- Official Anthropic documentation, tools, or first-party skills (T1) — cite
  and use directly. `anthropics/skills` (T1, registered in
  `capability-registry.yaml`) is Anthropic's own public reference repo —
  good source of real patterns when *writing* a new skill for this repo
  (pairs with `superpowers:writing-skills` for the mechanics), not
  something to fork or propose adopting wholesale.
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
