---
name: semantic-confusion
description: Owned methodology for semantic-confusion bugs — where a security control and a downstream consumer interpret the same attacker value differently (parser differentials, normalization drift, field overloading, lifecycle carryover, boundary translation, resolution fallback). The class that underlies request smuggling, path confusion, WAF bypass, and cache poisoning.
---

# Semantic Confusion

The bug isn't missing validation — it's **representation divergence across a trust
boundary**. A value passes the check in one form and becomes dangerous in another,
because the control and the consumer don't assign it the same meaning at the moment
a security decision is made. This class underlies request smuggling, path/handler
confusion, many WAF bypasses, cache poisoning, and npx/resolution confusion.

> Methodology adapted from Strix (usestrix/strix, Apache-2.0)
> `skills/vulnerabilities/semantic_confusion.md`, reworked into our voice.

The governing question: **does every consumer assign this value the same meaning at
the instant it makes a security decision?**

## The six sub-classes

- **Parser differentials** — two components parse the same bytes differently:
  duplicate fields, comma-joined values, invalid-token recovery, structured formats
  (URL, MIME, JSON, cookies, HTTP framing). Treat leniency as safe *only* if every
  downstream consumer is equally lenient.
- **Normalization drift** — sequential transforms (percent-decode, Unicode fold,
  path cleanup, case fold) make the *checked* form differ from the *consumed* form.
  Classic: validate before decode, use after decode.
- **Field overloading** — one field does two jobs across its lifecycle (a path reused
  as a URL; content-type picking both policy *and* handler). Watch implicit fallback
  to an alternate field when the intended one is empty.
- **Lifecycle state carryover** — metadata survives error paths, retries, internal
  redirects, cache entries, or background jobs; a decision made for one phase leaks
  into a later phase with stale data.
- **Boundary translation** — protocol conversion (HTTP/2→1.1), proxy rewriting,
  URL→filesystem resolution introduces gaps. **Never assume a WAF/authz sidecar sees
  the full body or the final normalized request.**
- **Resolution fallback** — names resolve across scopes (filesystem, `PATH`,
  registries, autoloaders) in a documented order; a protected name exposes an
  unprotected alias. (This is the root of npx/package-runner confusion — see
  `secrets_and_supply_chain.md`.)

## Detection method

1. **Map the transformation graph** — list every parser, validator, rewrite, and sink
   in execution order.
2. **Locate the decision points** — where do the security checks sit relative to those
   transforms?
3. **Build a differential matrix** — vary **one representation axis at a time**
   (encoding depth, delimiter style, path format, transport framing).
4. **Compare consumer interpretations** — status, headers, body, timing, redirects,
   side effects across variants. Record *which component saw which representation*.
5. **Prove safely** — synthetic canaries / reversible markers / constant OAST
   identifiers; never put target secrets in an OAST label.

The discipline that makes this class tractable: **change one axis at a time**, so the
disagreement stays attributable to a specific boundary. Isolate the disagreement;
don't spray payloads. The reusable unit is *the boundary and its invariant*, not a
vendor payload string.

## Escalation (primitive → impact)

- auth/ACL bypass → protected route or file access
- path confusion → source disclosure, SSRF, or unintended handler
- detector/consumer mismatch → active upload processing / inline execution (→ `rce.md`)
- internal-redirect carryover → handler selection or policy bypass
- search-path fallback → attacker-controlled code resolution (→ `rce.md`)

## Validation bar

A finding must show: the exact input bytes; how the **control** interpreted them; how
the **final consumer** interpreted them differently; the specific transform/lifecycle
event causing the divergence; a reproducible control-vs-exploit pair; and the version/
protocol/config context. Impact must not depend on unrelated undefined behavior.
