---
name: workflows
description: Named, packaged pentest workflows (recon / web-app / API / OWASP Top 10) with quick|standard|deep depth — how the skill's probes and knowledge chain into the way engagements are actually scoped. Driven by scripts/workflow.sh.
---

# Packaged Workflows

Engagements are scoped in named shapes — "run the OWASP Top 10", "black-box the
web app", "test the API" — not "run probe X". `scripts/workflow.sh` packages our
probes + knowledge into those shapes, runs the automatable parts, and hands you
the precise targeted commands for the rest. It's a guided workflow, not a
fire-and-forget scanner: the manual steps are where the real findings live.

```bash
scripts/workflow.sh <preset> <target-url> [--depth quick|standard|deep] [-- <passthrough>]
# passthrough after -- goes to every probe: -H "Cookie: s=.." --proxy http://127.0.0.1:8080 --rate 5
```

## Depth (modelled on scan modes)

| Depth | What it does | When |
|---|---|---|
| `quick` | recon/posture only (`http_recon`, preset's no-param probes) | triage, is-this-worth-time, CI gate |
| `standard` (default) | quick + param discovery (`param_probe`) + the preset's probes | normal first pass |
| `deep` | standard + you then work every targeted step below to exhaustion | a real engagement |

## Presets

- **`recon`** — `http_recon` (+ `param_probe`, `port_scan`). Map the surface first; the
  output tells every other preset what to aim at. See `recon_and_fingerprinting.md`.
- **`webapp`** — recon + `cors` + `redirect` + `csrf` posture, then targeted SQLi/XSS/IDOR/
  auth/business-logic steps. Black-box web app.
- **`api`** — recon + `graphql` + `cors`, then targeted BOPLA/mass-assignment, BOLA/IDOR,
  SQLi/NoSQLi, verb-tampering. See `api_and_protocols.md`, `modern_stack.md`.
- **`owasp`** — the OWASP Top 10 (2021) coverage map below, running the automatable items.

## OWASP Top 10 (2021) → this skill

| # | Category | Tooling / knowledge |
|---|---|---|
| A01 | Broken Access Control | `idor_probe.py diff`, BFLA/BOPLA — `idor_and_authz.md`, `api_and_protocols.md` |
| A02 | Cryptographic Failures | `secret_scan.py`, TLS + cookie flags — `secrets_and_supply_chain.md` |
| A03 | Injection | `sqli_probe.py` / `xss_probe.py` / `ssrf_probe.py` — per-param |
| A04 | Insecure Design | business logic via `repeater.py race`/`diff` — `idor_and_authz.md` |
| A05 | Security Misconfiguration | `http_recon.py` (headers, exposed artifacts, CORS) |
| A06 | Vulnerable/Outdated Components | `trivy`/`grype`; dependency & npx confusion — `secrets_and_supply_chain.md` |
| A07 | Identification/Auth Failures | `jwt_tool.py`, login/session/MFA — `authn_jwt_session.md`, `oauth_oidc_sso.md` |
| A08 | Software/Data Integrity Failures | deserialization, supply chain — `modern_stack.md`, `secrets_and_supply_chain.md` |
| A09 | Logging/Monitoring Failures | review-only; out of active-probe scope |
| A10 | SSRF | `ssrf_probe.py` (metadata, bypass, OOB) — `ssrf_and_injection.md` |

## The rule every workflow ends on

Everything a workflow prints is a **candidate**. Confirm it with counter-evidence
+ a working PoC and calibrate severity per `finding_validation.md` before it's a
finding. A workflow that hands back "12 candidates" and no confirmation is a
scanner dump, which is exactly what this skill is built not to be.
