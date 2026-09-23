---
name: auth-bypass
description: Consolidated methodology for getting past an authentication wall — every road, in one place - SQLi/NoSQLi login bypass, default/weak creds, logic flaws, forced-browsing/BFLA, response/status manipulation, 2FA/MFA bypass, OAuth/SSO abuse, JWT, session fixation, password-reset abuse, parameter tampering. Driven by native/auth_probe.py.
---

# Authentication Bypass

Getting past the login is a class of its own, not a footnote to JWT. This is the
one-stop map; deep dives live in `authn_jwt_session.md` (tokens), `oauth_oidc_sso.md`
(SSO flows), `idor_and_authz.md` (post-login authz). Attack the wall, don't admire it.

## Run it

`native/auth_probe.py` fires the automated part and detects success by differential
against a known-bad login (session cookie / redirect / status / size), no need to know
the app's success string:

```bash
python3 native/auth_probe.py bypass -u https://app/login -X POST --location form \
    --user-field username --pass-field password        # SQLi/NoSQL/default-cred battery
python3 native/auth_probe.py enum  -u https://app/login ... --users users.txt   # user-enum oracle
```
Then confirm any hit end-to-end (log in, capture REAL authed data) per `exploitation_depth.md`.

## The roads past the wall

1. **SQLi / NoSQLi login bypass** — the username/password reaches an auth query.
   SQL: `' OR '1'='1'-- -`, `admin'-- -`. NoSQL (JSON body): `{"$ne":null}`, `{"$gt":""}`,
   `{"$regex":".*"}`. `auth_probe.py bypass` covers both. → `sql_injection.md`, `modern_stack.md`.
2. **Default / weak / reused credentials** — vendor defaults, `admin:admin`, seeded/test
   accounts, creds from a prior leak. `auth_probe.py` battery + `credential_attacks.md`.
3. **Response / status manipulation** — the client trusts a server field: intercept the
   `{"authenticated":false}`/`{"role":"user"}` response and flip it, or a `302→login` the
   client honors but the resource still serves on `200` if requested directly. Use `repeater.py`.
4. **Forced browsing / BFLA** — skip the wall entirely: request the post-login resource,
   API route, or admin page directly with no/low-priv session. → `idor_and_authz.md`.
5. **Parameter tampering** — `?admin=true`, `role=admin`, `debug=1`, `authenticated=1`,
   step-skipping (`?step=3`), or a `redirect`/`next` that lands you inside. → `api_and_protocols.md`.
6. **JWT / token forgery** — `alg:none`, RS256→HS256, `kid`/`jku`, weak secret, claim tamper.
   → `authn_jwt_session.md` + `jwt_tool.py`.
7. **Session flaws** — fixation (login accepts an attacker-set session id), predictable
   session ids, logout that doesn't revoke, session not rebound after privilege change.
8. **OAuth / OIDC / SSO abuse** — `redirect_uri` laxity, missing `state`, IdP-confusion,
   account-linking takeover, `prompt=none` silent auth. → `oauth_oidc_sso.md`.
9. **2FA / MFA bypass** — the second factor not enforced server-side on the final request,
   OTP with no rate limit / reuse / predictable, "remember device" forgeable, backup-code
   weakness, or the MFA step skippable by going straight to the post-MFA endpoint.
10. **Password-reset / account-recovery abuse** — predictable/reusable reset tokens, host-
    header poisoning of the reset link, reset that doesn't invalidate sessions, user-
    controlled email/username in the reset. → `authn_jwt_session.md` (weak-password section).
11. **Registration / self-provisioning** — register an admin-ish account (email domain trust,
    mass-assignment `role` at signup → `api_and_protocols.md`), or confirm-email bypass.
12. **Race conditions** — TOCTOU on login/OTP/reset (`repeater.py race`). → `idor_and_authz.md`.

## Validation bar

A confirmed bypass = you are **actually authenticated** (a valid session/token that the
app accepts on a protected request) and you captured the **real** protected resource it
grants — per `exploitation_depth.md`. A differential on the login response alone is a
candidate; "the payload returned 302" is not "I got in" until you use the session.
