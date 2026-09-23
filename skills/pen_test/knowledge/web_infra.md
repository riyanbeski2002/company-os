---
name: web-infra
description: Owned methodology for the web/HTTP-infrastructure classes the injection docs don't cover — CSRF, CORS, open redirect, host-header injection, HTTP request smuggling, web cache poisoning, clickjacking, and the security-header/CSP posture that ties them together.
---

# Web / HTTP Infrastructure

These are the classes that live between the browser's security model and the
server's HTTP handling. Most have no native probe — they are confirmed with
`_httpcore`/`curl` and, for the browser-enforced ones, `claude-in-chrome`.
`http_recon.py` surfaces the header posture that flags several of them.

## CORS misconfiguration

**Run it:** `python3 native/cors_probe.py -u <url> --bearer $T` fires the full
Origin battery (arbitrary/null/subdomain/prefix/suffix/pre-domain/downgrade) and
flags any that reflect **with credentials**. `http_recon.py`'s `cors_check` is the
quick single-origin version; `engines/Corsy` adds breadth. The dangerous shapes:

- **Origin reflection + credentials** — `ACAO: <your origin>` **and**
  `ACAC: true`. Any site can read authenticated responses. Critical if the
  endpoint returns user data.
- **`null` origin trusted** — `ACAO: null` (reachable from sandboxed iframes,
  `data:` URLs).
- **Regex/suffix trust errors** — `evil-app.com` matching an `app.com` check,
  or `app.com.evil.com` passing a prefix check. Test sibling/suffix origins.

Validation bar: a cross-origin `fetch(..., {credentials:'include'})` from an
attacker origin that actually returns another user's data — CORS is never
authentication, so an ACAO on a public endpoint is not a finding.

## CSRF

**Run it:** `python3 native/csrf_probe.py -u <url> -X POST --data "..." -b "session=..."
[--token-param csrf_token]` replays the state change with a foreign Origin and
with the token dropped, reports whether either is enforced, and prints a ready
PoC to fire in `claude-in-chrome`. (`engines/`-side: `xsrfprobe` for breadth.)

State-changing request that relies only on an ambient cookie. Check, in order:

1. Is there an anti-CSRF token, and is it actually **validated** (drop it / reuse
   another user's / swap it for empty — does the action still succeed)?
2. `SameSite` on the session cookie — `None` (or unset on an old browser
   assumption) leaves it CSRF-able cross-site; `Lax` still allows top-level
   `GET` state changes.
3. Origin/Referer validation — present but bypassable (missing Referer allowed,
   substring match on Origin)?
4. JSON endpoints: does it require `Content-Type: application/json` (a real
   barrier to simple-request CSRF) or accept form-encoded?

Validation bar: an attacker-hosted HTML page that, loaded by an authenticated
victim, performs the state change. Login/logout CSRF and password/email-change
CSRF are each their own finding.

## Open redirect

**Run it:** `python3 native/redirect_probe.py -u "<url>?next=/x" --param next`
throws the filter-bypass battery and reports any payload that yields an off-host
3xx `Location`. `?next=`, `?url=`, `?return=`, `redirect_uri` reflected into a `Location`.
Bypasses for naive checks: `//evil.com`, `https:evil.com`, `/\evil.com`,
`https://trusted@evil.com`, whitelisted-host prefix `https://trusted.evil.com`.
Impact is usually the chain: **open redirect on an OAuth `redirect_uri`** leaks
the auth code/token (see `oauth_oidc_sso.md`); otherwise it's phishing-grade.

## Host-header / `X-Forwarded-*` injection

The app trusts a client-supplied host for building absolute URLs or cache keys.

- **Password-reset poisoning** — set `Host:` (or `X-Forwarded-Host:`) to your
  domain; if the reset email link uses it, the victim's token comes to you.
- **Cache-key / routing** — a reflected host that gets cached serves your
  content to others (overlaps cache poisoning below).
- **Client-IP spoofing** — `X-Forwarded-For` trusted for rate-limit or authz
  bypass (`X-Forwarded-For: 127.0.0.1` to reach an "internal only" gate).

Test by changing `Host`/`X-Forwarded-Host`/`X-Forwarded-For` and watching where
the value resurfaces (email, response body, redirect, cache).

## HTTP request smuggling / desync

Front-end and back-end disagree on where one request ends. Classic forms:
**CL.TE** (front-end uses `Content-Length`, back-end uses `Transfer-Encoding`)
and **TE.CL**. Symptoms: a crafted request that makes the *next* user's request
receive your smuggled prefix, or a time-delay on a deliberately malformed
`Transfer-Encoding`. This is high-blast-radius and easy to break shared infra —
test with timing-based detection first, and only against a target where that
disruption is explicitly authorized. `nuclei`/Burp's smuggling probe are the
practical detectors.

## Web cache poisoning / deception

- **Poisoning** — an *unkeyed* input (a header like `X-Forwarded-Host`,
  `X-Original-URL`) is reflected into a cacheable response; poison once, served
  to everyone. Find unkeyed inputs, reflect a marker, confirm it persists on a
  clean request from a second client.
- **Deception** — request `/account/profile/nonexistent.css`; if the origin
  serves the authenticated page but the CDN caches it as a static asset, other
  users can fetch the victim's cached private page.

## Clickjacking / UI redress

Missing `X-Frame-Options: DENY` / CSP `frame-ancestors 'none'` on a page with a
sensitive one-click action. Prove it: an attacker page that iframes the target
and overlays bait over the real button, captured in `claude-in-chrome`. A
missing header on a page with no sensitive action is informational only.

## Security-header & CSP posture

`http_recon.py` audits HSTS/CSP/X-Frame-Options/nosniff/Referrer-Policy/
Permissions-Policy. Read these as **force-multipliers**, not standalone findings:
no CSP means a found XSS runs unhindered; `unsafe-inline`/`unsafe-eval` in CSP
neuters it as an XSS defense; missing `frame-ancestors` enables the clickjacking
above. Report a missing header at the severity of what it fails to contain.

## Validation bar

Each class above is confirmed by the *effect*, not the header: CORS by an actual
cross-origin data read, CSRF by a working attacker page, host-header by the
poisoned link/response landing where a victim would hit it, smuggling/poisoning
by a second client actually receiving the injected content. Headers are leads.
