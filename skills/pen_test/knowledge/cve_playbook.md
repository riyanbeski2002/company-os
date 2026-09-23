---
name: cve-playbook
description: Owned, growing playbook of specific high-value CVEs the fingerprint pass should trigger a test for — starting with the ones this engagement history actually hit. This is the field-learning capture point for named CVEs.
---

# CVE Playbook

`native/http_recon.py` fingerprints the stack and emits CVE hints; this file is
the detail behind those hints, and the place new field-learned CVEs get written
so the next engagement tests them automatically.

> **Feed the loop.** When an engagement confirms (or newly learns of) a
> stack-specific CVE, add it here with a detection method, and add its trigger
> to `http_recon.py`'s `cve_hints()`. That is how the skill stays current on
> named CVEs without freezing a stale copy of a scanner.

## How to use this

1. `http_recon.py` reports the framework/version.
2. Match it below; run the listed detection (benign proof only unless authz
   covers exploitation).
3. For breadth beyond this list, run `nuclei` (its template feed is the
   continuously-updated source — refresh with `update_engines.sh` first) and
   `trivy`/`grype` for dependency CVEs.

## Next.js — CVE-2025-29927 (middleware authorization bypass)

**Seen in the field.** Affected Next.js versions trust an internal header
(`x-middleware-subrequest`) to prevent middleware recursion — but if a client
sets it, middleware (including auth/redirect gates) is skipped entirely.

- **Detect:** pick a path that middleware protects (redirects unauthenticated
  users, or enforces a role). Re-request it adding:
  `x-middleware-subrequest: middleware` — and also try
  `x-middleware-subrequest: src/middleware` and chained values like
  `middleware:middleware:middleware:middleware:middleware` (nesting-depth
  dependent across versions).
- **Confirm:** the protected content returns instead of the redirect/403.
- **Also on Next.js:** enumerate `/_next/static/` for publicly-served source
  maps and `NEXT_PUBLIC_*` env vars baked into the client bundle (real leaks
  seen in the field — GitLab org/repo/commit metadata, internal URLs).

```bash
# quick manual check via the shared engine or curl:
curl -sI "https://target/protected" -H "x-middleware-subrequest: middleware"
```

## Apache httpd — CVE-2021-41773 / CVE-2021-42013 (path traversal → RCE)

- **Applies:** Apache 2.4.49 / 2.4.50 with a mis-`Require`'d filesystem root.
- **Detect:** `GET /icons/%2e%2e/%2e%2e/etc/passwd` (and the double-encoded
  `%%32%65` variant for 42013). Root contents returned = vulnerable; with
  `mod_cgi` enabled it escalates to RCE.

## Spring Boot Actuator (exposure, multiple CVEs / misconfig)

- **Detect:** `http_recon.py` flags `/actuator`. Then pull `/actuator/env`,
  `/actuator/heapdump` (a heapdump can be grepped for live secrets/tokens),
  `/actuator/mappings`. `/actuator/gateway/` on Spring Cloud Gateway has had
  SpEL-injection RCE CVEs — check the version.

## Adding a new CVE (template)

```
## <Product> — CVE-YYYY-NNNNN (<one-line effect>)
- Applies: <versions / fingerprint that triggers it>
- Detect: <the benign request/response that proves it, non-destructively>
- Confirm: <the exact signal that distinguishes vulnerable from patched>
- Exploit: <only referenced; run only under explicit exploitation authorization>
```

## Validation bar

A CVE is a lead until you reproduce its distinguishing signal against *this*
target (version banners lie, and back-ports patch without changing the version).
Prove it with the non-destructive detection above before reporting; escalate to
weaponized exploitation only under explicit authorization.
