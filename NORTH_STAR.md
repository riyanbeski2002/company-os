# Company OS — North Star

## The one sentence

**Riyan states an outcome; the system delivers it with evidence, and asks him
only when he is genuinely the one who can answer.**

Everything below is in service of that sentence. Anything that does not serve it
does not ship, however clever.

---

## What this is actually for

Riyan runs more projects than one person can hold: an expense platform, a
compliance migration, a fleet dashboard, a follow-up PWA, half a dozen Apps
Script automations, most of them half-built or already live. The bottleneck is
not writing code. It is **holding context across all of them, remembering what
was decided, noticing what broke, and re-deriving the same conclusions weeks
later.**

Company OS exists to absorb that. Not to write code faster — to make the
coordination, memory, and verification stop being a human job.

The measure of success is not lines shipped. It is: **how much of Riyan's day is
spent deciding, versus scheduling.**

---

## The end state

One instruction in, one report out, on any repo he owns:

```
$ claude --agent company-pm
> Add SSO to the compliance portal.

  Staffing: 2 workers (backend, frontend) + independent security review
  — forced by the risk table on "SSO", not requested.
  Baseline: hv-compliance is red (4 pre-existing failures). Judging as no-regression.

  ... 40 minutes later ...

  SSO is implemented and passed authorization review. Integration is green
  against a 4-failure baseline with no new failures. Two decisions need you:

  ESC-004 [decision]  Session lifetime: 8h (matches current app) or 1h (matches
                      the security review's recommendation)?
  ESC-005 [approval]  This adds an external IdP dependency. Policy says you
                      approve new third-party auth surfaces.
```

He answers two questions. He did not decide who worked, in what order, what ran
in parallel, what needed review, or whether it actually worked.

---

## The CEO is not all-knowing

A CEO has a CTO, a CISO, a CFO and a COO because no one person holds every
domain. Company OS is not only a way for Riyan to be less involved — it is the
expertise he does not have to supply.

The proof that this layer is needed is in Company OS's own history: a build
consumed 2.49M cache-read tokens, 83% of it tool definitions no worker ever
called, and **nothing in the system noticed**. A human found it by hand, weeks
in. Every implementer role was doing its job correctly; none of them was asked
to watch that, because none of them owned it.

Four advisors close the gap. They are read-only, they run unprompted, and they
produce evidence-backed findings — never opinions:

| Officer | The question nobody else asks |
|---|---|
| **CTO** | Is this the right approach at all — or should it not be built? |
| **CISO** | What is our standing exposure, beyond any single diff? |
| **CFO** | What does this consume per unit delivered, and where is the waste? |
| **COO** | Is the delivery machine working, or just producing motion? |

They advise; they never decide. Anything irreversible or genuinely the CEO's
call becomes an escalation. And they are bound by the same rule as everyone
else: a finding without evidence is refused by the CLI, because an officer's
unsupported opinion is exactly the noise this system exists to remove.

The line they must never cross: **no advisor may recommend spending less by
checking less.** Cutting a gate to save tokens is not a saving.

## What must always be true

These are load-bearing. If a future version breaks one of these, it is not
Company OS any more.

1. **Events are truth.** Task files are a view. Recovery is replay, never repair.
2. **No agent certifies its own work.** A gated change needs a signature from a
   different actor, and a worker cannot choose its own name.
3. **Evidence, not assertion.** Nothing reaches DONE without a diff, a real exit
   code, and — where risk is real — an independent review. "It works" is not a
   fact.
4. **Risk gates are table-driven.** Identical requests produce identical
   mandatory staffing. Nobody has to *remember* to ask for a security review.
5. **Ownership is enforced, not requested.** A hook blocks writes outside a
   task's globs.
6. **The cheapest tier that works.** Tier inflation is the failure mode. Most
   requests should never spawn a worker at all.
7. **The system survives session death.** Kill everything; `company rebuild &&
   company status` tells the truth and the work survives.
8. **Riyan is a capability, not an obstacle.** Being blocked in silence is worse
   than asking. Ask precisely, with the exact command or the real options.
9. **Advisors bring expertise, not opinions.** Every finding carries evidence,
   and no advisor may propose saving cost by reducing rigour.
10. **Never quietly lower the bar.** A red baseline is reported loudly, not
   adopted. A syntax-only check is labelled weak. "Unknown" beats a made-up
   number.

---

## Where it goes

### V1 — the loop works *(done)*
Event log, Evidence Rule, ownership enforcement, headless workers, contract-first
parallelism, independent gates, integration on green, executive report. Proven on
a fixture: security caught a real self-approval defect nobody asked it to look
for, and blocked the merge until it was fixed.

### V2 — usable on real repos *(current)*
Stack and verify detection · **baseline capture, so half-built repos are judged
fairly** · `doctor` preflight · escalations and the tmux gallery · concurrency
budget · detached workers · cost reporting · one-command install.

The V2 question was never "can it build software" — V1 answered that. It was
**"can it be pointed at code that already exists, is imperfect, and matters."**

### V3 — the PM runs the loop
Today the PM can staff and triage from one sentence, but a human still nudges it
between phases. V3 closes that: the PM polls its own detached workers, drives the
fix-review-integrate cycle to completion, and comes back only with outcomes and
escalations.

Also here: ADRs so settled architecture is never re-derived; TruthGraph as the
cross-project memory Company OS writes to, not a second store beside it.

### V4 — many projects at once
Riyan's real workload is a portfolio. One `company status` across every repo.
Escalations queued by urgency, not by which terminal happens to be open. Standing
work — dependency upgrades, security sweeps, flaky-test triage — that runs
without being asked and only surfaces what needs a decision.

### V5 — it earns its keep unprompted
The system notices: this repo has no tests and three risky merges landed last
month; this Apps Script project only has syntax checking; this decision
contradicts ADR-007. It proposes work rather than waiting to be told.

---

## What we will not build

Not from timidity — because each one is a plausible-looking way to lose the plot.

- **A second orchestration platform.** Verify the native primitive first. Most
  of what a custom framework would provide, Claude Code already does.
- **Agents for organisational realism.** Six roles because six are needed. A
  "VP of Engineering" that only forwards messages is cost with a title.
- **A dashboard before the loop is trusted.** A UI over unreliable state makes
  unreliable state look official.
- **Self-modifying governance.** The system may propose changes to its own rules.
  It may never apply them.
- **Anything whose first user does not exist yet.**

---

## How we will know it worked

Not by test count or event volume. By these:

| Signal | Today | Target |
|---|---|---|
| Instructions per delivered outcome | several | **one** |
| Human coordination between phases | required | **none** |
| Escalations that were genuinely his call | mixed | **all of them** |
| Defects caught before merge, unasked | 1 (real, in the fixture) | routine |
| Repos he trusts it on | 1 fixture | **all the live ones** |
| Cost per delivered task | ~$3 | known, and falling |

And one question, asked honestly every few weeks:

> **Is Riyan spending his time deciding, or scheduling?**

If the answer drifts back toward scheduling, something in here stopped being
true, and that is the thing to fix — not the next feature.
