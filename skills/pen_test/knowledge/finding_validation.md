---
name: finding-validation
description: Owned methodology for the discipline that separates a pentester from a scanner — disproving your own finding before you report it (counter-evidence), calibrating severity honestly, and verifying fixes. The meta-skill that sits on top of every class-specific probe.
---

# Finding Validation: Counter-Evidence, Severity, Fix Verification

Every class doc in this skill ends with a validation bar. This doc is the layer
above them: how to decide a candidate is *real*, how severe it *actually* is, and
how to confirm a fix. A probe hit is a hypothesis; this is how you turn it into a
finding a reputable firm would put its name on — or correctly kill it.

> Methodology adapted from Strix (usestrix/strix, Apache-2.0) `skills/analysis/`,
> reworked into this skill's voice and tooling. We mine the technique; we don't
> run their agent.

## 1. Counter-evidence — argue against yourself first

Before filing anything, build the strongest case that the candidate is **safe**.
A finding survives only if you tried to kill it and couldn't.

**Do this, in order:**
1. **Attack your own hypothesis.** Hunt for the guard you missed: input validation
   on a different path, a WAF rule, a deploy constraint, an assumption you made
   about reachability.
2. **Record what you actually checked** — name the real constraints you found and
   why they don't neutralize the issue; if you found none, list what you tested.
   This becomes the finding's `confidence_rationale`.
3. **Calibrate confidence honestly:** working PoC against the live system = `high`;
   static/inferred trace only = `medium` at best, with the gap named; can't
   reproduce = `open_proof_gap`, never a silent pass or a confident report.
4. **Name the one piece of evidence** that would raise or lower the verdict.

**What does NOT prove safety (do not close a finding on these alone):**
- "The library is trusted" / "the framework handles that"
- A control that sits on a *different* code path than the one you hit
- A control that runs at the wrong time (after the sink, or fail-open)
- A safe *sibling* instance/endpoint while this one is untested
- "It's internal-only" / "an operator could configure it safely"
- **Missing information.** *Missing evidence is not evidence of absence.* If you
  couldn't reach it to test, that's an `open_proof_gap`, not a clean bill.

**What DOES prove safety (any one):**
- You ran the attack and it demonstrably failed, and you understand *why*
- A specific control on **every** attacker path *before* the sink
- The sink is provably inert in this context
- The input traces to a fully trusted origin
- **Negative control:** the malicious payload is blocked while a benign variant of
  the same request succeeds — this strengthens both "safe" and "vulnerable" verdicts.

## 2. Severity — a conclusion, not a starting assumption

Establish reachability and finish the counter-evidence pass *before* assigning
severity. The governing test:

> **Would this be accepted as high/critical in serious audit or bug-bounty triage,
> by a firm putting its reputation on the line?** If acceptance needs a chain of
> assumptions, downgrade it.

| Tier | What belongs here |
|---|---|
| **Critical** | Unauth RCE on an internet-exposed surface; full auth bypass / trivially forgeable creds; mass extraction of other tenants'/users' data; signing-key or infra-cred compromise; complete cross-tenant isolation failure |
| **High** | Authenticated RCE; priv-esc across a trust boundary; object-level authz failure at scale; SQLi reaching real data; SSRF reaching internal services/credentials; exploitable credential/PII exposure |
| **Medium** | Stored/reflected XSS with constraints; CSRF on state change; authz gaps on low-value objects; info disclosure that aids further attack; otherwise-high findings blocked by a real constraint (internal-only, privileged role required, narrow preconditions) |
| **Low / Info** | Missing headers; self-XSS; standalone open redirect without leakage; rate-limiting gaps with no demonstrated impact; defense-in-depth gaps with no reachable path |

**Elevates High → Critical:** no auth required · internet-reachable · zero user
interaction · self-propagating · tenant-wide blast radius.

**Commonly *over*rated (keep Medium-or-below unless something unusual applies):**
self-XSS, clickjacking on non-sensitive actions, standalone open redirects,
theoretical memory issues with no reachable input, anything needing pre-existing
admin/shell, session issues that assume the attacker already holds the victim's
secret, enumeration that only confirms existence.

**Acceptance checklist for High/Critical — all must hold; a miss drops it a level:**
- [ ] Attack path is realistic and in-scope (not lab-only, not "assume X is compromised")
- [ ] `privileges_required` / `attack_complexity` stated honestly
- [ ] Impact is demonstrated and material, not asserted
- [ ] Counter-evidence found no limiting constraint (or you explained why constraints don't save it)
- [ ] Concrete reachability evidence exists — deployment assumptions don't substitute
- [ ] You could defend it to the client's face

When CVSS output and intuition diverge, fix the *metrics* (usually
`privileges_required`, `attack_complexity`, impact) to reflect reality — don't
override the score by feel.

## 3. Fix verification

A finding isn't closed until the fix is proven, the same way the bug was:
- **Re-run the exact PoC** against the patched target — it must now fail.
- **Confirm you're hitting the fix**, not a different path (bypass the patch: encoding,
  alternate parameter/location, the sibling endpoint the fix missed).
- A fix that only blocks your *specific* payload but not the *class* is not a fix —
  re-test with variants (see each class doc's payload set).
- Record before/after: vulnerable request+response, then the same request now blocked.

## How this feeds the report

Every finding this skill emits carries: the PoC (evidence), a `confidence`
(high/medium/open_proof_gap) with rationale, a calibrated severity that passes the
checklist above, and — once remediated — a fix-verification result. This is what
makes `SECURITY_REVIEW_PASSED/FAILED` defensible rather than a scanner dump.
