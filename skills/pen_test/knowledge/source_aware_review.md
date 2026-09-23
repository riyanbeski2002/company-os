---
name: source-aware-review
description: Owned methodology for white-box / source-aware discovery — using code access to trace source→sink, enumerate every instance of a broken control (not just the loudest), sweep code families, and run source-driven SAST. What black-box testing structurally cannot find.
---

# Source-Aware (White-Box) Review

When you have the code, black-box discipline leaves findings on the table. Source
access lets you see *which* path an attacker actually reaches, find the same broken
control duplicated across packages, and spot branch-specific bypasses invisible from
outside. This is the discovery discipline; exploitation still follows the per-class docs.

> Methodology adapted from Strix (usestrix/strix, Apache-2.0) `skills/analysis/
> source_aware_discovery.md` + `skills/custom/source_aware_sast.md`.

## Two failure modes to avoid

- **Over-collapse** — merging distinct bugs into one. *One root cause is not one
  candidate.* Two call sites to the same dangerous helper are two findings, each with
  its own source location, closest control point, and line number. Command injection
  and an authz bypass on the same endpoint are separate vulnerabilities.
- **Premature closure** — stopping at the loudest sink. The reusable win is finding a
  broken **control** (resolver, allowlist, filter, guard) that many sinks depend on.

## Control-centric reading

Prioritize locating reusable broken controls over chasing dramatic sinks. The
transport that reaches a sink *proves reachability — it doesn't replace it*. Watch for
**branch-specific transforms** that bypass a shared validator; keep the branch
predicate itself as a candidate location. Preserve both wrapper and shared-helper
visibility — lose either and the fix is impossible to place.

## Family sweep — after one instance, enumerate the whole family

- **Deserialization** — every registered codec/deserializer/converter separately; a
  top-level parser fix doesn't close concrete codecs that recursively re-invoke parsing.
- **XML parsers** — factories, readers, converters, validators separately; secure-
  processing flags don't suppress caller-supplied factory paths.
- **Archive extraction (Zip Slip)** — per operation, track member name → destination
  join → containment check → write call. A write that overwrites config or a peer
  tenant's dir is impact even without escaping app root.
- **Filesystem ops** — each exported op (restore/import/export/copy/move) with decode,
  join, normalize, destination-selection lines visible.
- **Command runners** — separate controls per argument type and execution mode;
  frontend constraints are not controls.
- **Query APIs** — carry every attacker-input→syntax path; don't drop it because it's
  insert-only or "pre-filtered."
- **Auth state machines** — track principal/credential installation *after* transitions;
  a missing rebind authenticates the wrong identity.
- **SSO/SAML** — keep validators, authorizers, and assertion-selection lines distinct.
  Hunt the **validated-vs-consumed mismatch**: a validation loop followed by a separate
  fixed-index / first-element access (ties into `semantic_confusion.md`).

## Tooling

`semgrep --config=auto` (and targeted `--config=p/<ruleset>`) for rule-driven taint/
pattern discovery, `Read`/`Grep`/`Glob` for the manual source→sink tracing above, and
the language's own AST/tools where useful. semgrep finds candidates; the source→sink
trace confirms reachability and the closest broken control.

## White-box vs black-box

White-box uniquely enables: direct control-flow observation (which path is *reachable*);
detection of duplicated broken controls across packages (each live until individually
fixed); branch-specific bypasses invisible without reading source; and cross-boundary
analysis of stored values later rendered/evaluated without proof of trust. Black-box
cannot enumerate specialized subclass helpers, branch predicates, or internal control
duplication — so a white-box engagement that only reproduces the black-box findings has
under-delivered.

## Validation bar

Label every location — entrypoint, root control, sink, or concrete implementation —
with file+line. A source→sink finding still needs a demonstrated reachable path (the
transport that reaches it), not just a scary-looking sink. Record swept families,
including the clean results, so coverage is provable.
