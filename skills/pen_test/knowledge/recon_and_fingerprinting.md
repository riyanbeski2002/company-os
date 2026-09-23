---
name: recon-and-fingerprinting
description: Owned methodology for the recon pass that precedes every class-specific attack — surface mapping, tech/version fingerprinting, exposed-artifact discovery, and turning that into a targeted attack plan.
---

# Recon & Fingerprinting

Recon is not optional throat-clearing — it is what points every other probe at
the right target. A blind SQLi sweep of a static site wastes the engagement;
recon tells you the site is Next.js with no backend API, so you test middleware
bypass and source-map leaks instead. Do this first, always.

## Run it

`native/http_recon.py` does the whole pass in one call:

```bash
python3 native/http_recon.py https://target                    # full pass
python3 native/http_recon.py https://target --no-artifacts     # skip path probing (quieter)
python3 native/http_recon.py https://target -H "Cookie: session=..."   # authenticated view
```

It returns, and you act on, four things:

1. **Security-header audit** — missing CSP/HSTS/X-Frame-Options/nosniff/
   Referrer-Policy/Permissions-Policy. Each missing header is a real (usually
   low/medium) finding *and* a hint: no CSP means an XSS, once found, executes
   unhindered.
2. **Technology fingerprint** — `Server`, `X-Powered-By`, and body signatures
   (Next.js, Nuxt, React, Angular, Vue, WordPress, Django, Laravel, ASP.NET).
   This decides which CVE playbook applies — see `cve_playbook.md`.
3. **Exposed artifacts** — `/.git/HEAD`, `/.env`, `/actuator/env`, source maps,
   swagger/openapi, `/server-status`, phpinfo. Each reachable one is a leak;
   `.git` exposure means full source recovery, `/actuator/env` and heapdumps
   mean live secrets.
4. **CORS misconfig** — reflected `Origin` with credentials.

## Turning recon into a plan

- **API schema found** (swagger/openapi/GraphQL introspection) → enumerate
  every endpoint; feed object endpoints to `idor_probe.py`, url-taking params
  to `ssrf_probe.py`, search/filter params to `sqli_probe.py`/`xss_probe.py`.
- **Framework + version** → look up known CVEs (`cve_playbook.md`, then
  `nuclei` for template-based confirmation). Version in a header/bundle is gold.
- **Static-only site** (no backend, thin SPA/redirect stub) → shift focus to
  client-side: source-map/env leaks, DOM XSS, open-redirect/param injection in
  the client, and any deep-linked downstream flow (note it, don't test out of scope).
- **`.git` exposed** → recover source with `git-dumper`-style techniques, then
  review it for secrets and logic bugs you can now see whitebox.

## Deeper recon beyond the native pass

- **Subdomain / asset discovery** is an out-of-scope-risk step — only enumerate
  hosts you are explicitly authorized for (see the agent's authorization gate;
  an authorized URL does not authorize its whole domain).
- **Content discovery** (dirs/files) with a wordlist (`ffuf`, `feroxbuster`) —
  install as a utility tool if the engagement needs it; keep it rate-limited.
- **`nuclei`** for template-based CVE/misconfig scanning once the tech is known
  (`-tags <tech>`), and **`nmap`** for full service/version depth beyond
  `native/port_scan.py`.

## Validation bar

Recon findings are candidates and information, not confirmed exploits: a missing
header is confirmed by observation; an "exposed" path is a finding only when it
actually returns the sensitive content (the probe checks a body signature, not
just a 200). A fingerprint is a lead — the CVE it implies still has to be tested.
