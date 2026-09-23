---
name: oauth-oidc-sso
description: Owned methodology for OAuth 2.0 / OIDC / SSO flaws — redirect_uri validation, state/nonce, PKCE, authorization-code handling, scope and consent, account linking, and SSO session/logout issues. The SaaS login surface the JWT doc doesn't cover.
---

# OAuth / OIDC / SSO

`authn_jwt_session.md` covers the token once issued; this covers the *flow* that
issues it. All manual (`claude-in-chrome` for the browser legs, `_httpcore`/
`curl` for the token endpoints). Map the flow first: response_type, the exact
`redirect_uri`, whether `state`/`nonce`/PKCE are present, and where the code/
token is delivered.

## redirect_uri validation (the highest-value bug)

The single most common serious OAuth flaw — a weak `redirect_uri` check sends
the auth code/token to an attacker.

- Try an unregistered redirect: does the AS reject it, or reflect it?
- Partial-match weaknesses: `redirect_uri=https://app.com.evil.com`,
  `https://app.com@evil.com`, `https://app.com/../evil`, appended path/params
  (`https://app.com/callback/../../evil`), open redirect *on the legit callback
  host* (chain from `web_infra.md`) to bounce the code out.
- `localhost`/loopback and wildcard subdomain registrations are frequent holes.

Confirm: the authorization `code` (or token in implicit flow) actually lands on
a host you control.

## state / nonce

- **Missing/unvalidated `state`** → login CSRF: attacker starts a flow, feeds the
  victim the attacker's code, victim's account gets linked to attacker's IdP
  identity (or vice versa). Drop/reuse `state` and see if the callback still
  completes.
- **Missing `nonce`** (OIDC) → ID-token replay across sessions.

## PKCE

For public clients (SPA/mobile), PKCE should be enforced. Test: start a flow with
a `code_challenge`, then redeem the code **without** `code_verifier`, or with a
wrong one. If the token endpoint still issues a token, PKCE isn't enforced and an
intercepted code is usable.

## authorization-code handling

- **Code reuse** — redeem the same code twice; it must be single-use.
- **Code substitution / injection** — inject a code obtained for a different
  client_id or user into your session's callback.
- **Client authentication** — confidential clients must present a secret at the
  token endpoint; check it isn't optional, and that the secret isn't in a
  frontend bundle (`secrets_and_supply_chain.md`).

## scope & consent

- **Scope escalation** — add scopes at the token/refresh step beyond what was
  consented; does the AS re-check?
- **Consent bypass** — for a trusted/first-party client, is consent skipped in a
  way an attacker-controlled client can imitate (client confusion)?

## account linking

Linking an SSO identity to an existing local account without verifying control
of the email → account takeover ("login with Google" onto a pre-registered
victim email that was never verified). Test the link flow with an email you don't
control but the app trusts from the IdP claim.

## SSO session & logout

- **SSO session fixation** — a pre-set session surviving the SSO round-trip.
- **IdP/SP logout inconsistency** — SP logout that doesn't kill the IdP session
  (or vice versa), leaving a re-login silent.
- **Multi-tenant SSO confusion** — a token/assertion issued for tenant A accepted
  by tenant B; overlaps `multitenancy_and_baas.md`.
- **SAML variants** (if SAML rather than OIDC) — signature wrapping (XSW),
  unsigned-assertion acceptance, `<!ENTITY` XXE in the SAML XML
  (`ssrf_and_injection.md`).

## Validation bar

A confirmed finding is an actual session/token obtained for an account you should
not control, or a code/token delivered to an attacker-controlled host —
demonstrated end-to-end, not "the `state` parameter looked short."
