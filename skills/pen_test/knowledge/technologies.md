---
name: technologies
description: Owned methodology for specific technologies with their own attack surface — Active Directory, Auth0, and Grafana/Prometheus. Complements the tech coverage already in multitenancy_and_baas.md (Firebase/Supabase), ai_llm.md (LLM apps), and client_and_mobile.md (Electron).
---

# Technology-Specific Playbooks

Some technologies have an attack surface distinct enough to warrant their own play.
This doc covers Active Directory, Auth0, and Grafana/Prometheus. Others already have
homes: **Firebase/Supabase** → `multitenancy_and_baas.md`, **LLM apps** → `ai_llm.md`,
**Electron/desktop** → `client_and_mobile.md`.

## Active Directory

> Adapted from Strix (usestrix/strix, Apache-2.0) `skills/technologies/active_directory.md`.

Enterprise-internal, not a web surface — only in scope on an explicitly authorized
internal engagement. Surface: Kerberos (88), LDAP (389/636), SMB (445), AD CS, WinRM,
RPC, DNS. Objects that matter: users/computers/gMSA, `servicePrincipalName`, delegation
flags, `msDS-KeyCredentialLink`, and trust boundaries.

**Sequential methodology:**
1. Validate foothold (`nxc`/NetExec over ldap/smb); note `MachineAccountQuota` + password policy.
2. BloodHound collection (`bloodhound-ce-python` or `nxc --bloodhound`); graph owned → Domain Admin paths.
3. Low-noise harvest: **AS-REP roasting** (accounts with `DONT_REQ_PREAUTH`, no auth needed),
   **Kerberoasting** (any authenticated user requests an RC4 `$krb5tgs$23$` service ticket
   for any SPN account → crack offline), LAPS/gMSA enumeration.
4. **AD CS sweep** — `certipy find -vulnerable` (ESC1–ESC17; ESC1 = template allows
   enrollee-supplied SAN + client-auth EKU → request a cert *as* administrator).
5. **DACL abuse** — walk ACL edges from owned principals: `GenericAll`/`GenericWrite`
   → targeted Kerberoasting, Shadow Credentials (`msDS-KeyCredentialLink`), or ACL priv-esc.
6. **Delegation + coercion** — unconstrained (TGT capture → DCSync), constrained
   (S4U2Self/S4U2Proxy), RBCD (chains with computer creation when `MachineAccountQuota>0`);
   coerce privileged auth via MS-EFSR/PrinterBug/PetitPotam and **relay** unsigned LDAP/AD CS.
7. **Dominance** — DCSync via replication rights dumps `krbtgt` (golden ticket). Avoid
   persistence unless in scope.

**Tools:** NetExec (`nxc`), impacket (roasting/S4U/relay/secretsdump/ticketer), Certipy,
BloodHound CE, Responder/ntlmrelayx/Coercer, hashcat/john. **Validation:** show the exact
misconfig (SPN flag / template setting / ACE / missing patch) with raw tool output, the
privilege gained (cracked password or DCSync hash), and the full chain with evidence per hop.

## Auth0 (and hosted IdP/SSO)

Generic OAuth/OIDC flaws live in `oauth_oidc_sso.md`; the Auth0-specific angles:
- **Tenant/app config exposure** — `https://<tenant>.auth0.com/.well-known/openid-configuration`
  and `/.well-known/jwks.json`; enumerate the tenant, clients, and connection types.
- **Misconfigured callback/allowed-origins** — overly broad `callback_urls`/`web_origins`
  enabling token theft via open redirect / origin reflection (ties to `web_infra.md`).
- **Rules/Actions/Hooks** — server-side custom code; if you reach it, it can leak secrets
  or make authz decisions on attacker-influenced claims.
- **Weak grant types** — implicit flow, ROPG (password grant) enabled, missing PKCE on
  public clients, `prompt=none` silent-auth abuse.
- **Management API scope** — a leaked M2M token with broad `read:users`/`update:users`
  scopes is full account takeover; check bundles/env for Auth0 client secrets.

## Grafana / Prometheus (exposed observability)

Frequently exposed unauthenticated on internal-turned-public hosts — `http_recon.py`
often finds these.
- **Grafana** — default creds (`admin/admin`), anonymous org access, historical path-
  traversal/SSRF CVEs (e.g. CVE-2021-43798 plugin path traversal — `/public/plugins/<p>/../../../../etc/passwd`);
  datasource proxy as an **SSRF** primitive to internal services; API token/`/api/datasources`
  leakage of DB creds.
- **Prometheus / Alertmanager / node_exporter** — no auth by design; `/metrics`,
  `/api/v1/targets`, `/api/v1/status/config` leak internal hostnames, tokens in scrape
  configs, and topology (feeds recon). Pushgateway can allow metric injection; Alertmanager
  webhooks can be an SSRF/notification-abuse vector.
- Validate as usual: reached data / SSRF hit / cracked-or-default login, not just "it's exposed."
