---
name: authn-jwt-session
description: Original methodology for authentication, session, and JWT vulnerabilities.
---

# Authentication, Session, and JWT

## JWT-specific attacks

Use `native/jwt_tool.py` (this skill's own script, no external `jwt-cli`
dependency) to decode/manipulate. Start with `decode <token>` — it now
inspects the header and tells you which of the attacks below the token's
`alg`/`kid`/`jku`/`x5u`/`jwk` fields actually expose. Full command set:

```bash
python3 native/jwt_tool.py decode      <token>                         # triage: what's attackable
python3 native/jwt_tool.py alg-none    <token>                         # emits none/None/NONE/nOnE variants
python3 native/jwt_tool.py crack       <token> [--wordlist f]          # weak HS256 secret
python3 native/jwt_tool.py forge-hs256 <token> --public-key pub.pem    # RS256->HS256 confusion
python3 native/jwt_tool.py kid-inject  <token> --kid "../../dev/null" --secret ""   # kid path-traversal/SQLi
python3 native/jwt_tool.py jku-forge   <token> --jwks-url https://you/jwks.json     # attacker-hosted JWKS (or --header x5u)
python3 native/jwt_tool.py tamper      <token> --claim role=admin --claim isAdmin=true --secret <s>
```

Check, in order:

1. **`alg: none`.** Some libraries historically accepted an unsigned token
   if the header claims `"alg":"none"`. Try it — this is a config/library
   bug, not universal, but still shows up.
2. **Algorithm confusion (RS256 → HS256).** If the server uses RS256
   (asymmetric — public key verifies, private key signs) but the
   verification code doesn't pin the expected algorithm, an attacker who
   knows the RS256 *public* key (often published, e.g. at a JWKS endpoint
   or embedded in client-side code) can forge an HS256 token, signing it
   with the public key content treated as an HMAC secret. This is a real,
   well-documented class, not theoretical — confirm the server's JWKS
   endpoint or client bundle for an exposed public key first.
3. **Weak/guessable HMAC secret.** For HS256 tokens, brute-force common
   secrets (`secret`, `changeme`, the app name, empty string) — a real
   attack surface distinct from stealing the secret. `jwt_tool.py` has a
   `--crack` mode against a small built-in wordlist; extend the wordlist
   file for anything project-specific.
4. **`kid` (Key ID) header injection.** If the server looks up the
   verification key by the `kid` value from the (attacker-controlled)
   token header, check whether `kid` can be manipulated to point at a
   predictable file (path traversal, e.g. `kid: "../../../../dev/null"`
   with an empty-string HMAC signature) or a value the attacker can
   influence the content of (e.g. a database field, a Redis key).
5. **Missing expiry/audience/issuer validation.** Decode a real token,
   check whether `exp`/`aud`/`iss` claims exist at all and whether removing
   or altering them (then re-signing, if you have a valid secret from
   another vector, or just observing whether the app rejects an
   unsigned/tampered token) changes acceptance.
6. **Claim tampering when the signature isn't actually checked** — the
   simplest and most common real-world bug: change `role`/`user_id`/`sub`
   in the payload, re-encode (no valid signature needed), and see if the
   server accepts it. Always try this first, before anything cryptographic.

## Session management, non-JWT

- **Session fixation**: can a session ID be set (via URL param, cookie set
  before login) and then reused post-authentication, letting the attacker
  who set it hijack the now-authenticated session?
- **Token lifetime and revocation**: does logout actually invalidate the
  token server-side, or just clear the client-side cookie? Is there a
  refresh-token rotation, and does an old refresh token still work after
  rotation (should be revoked)?
- **Concurrent session handling**: does changing a password / triggering
  "log out everywhere" actually invalidate *other* active sessions, or
  only the current one?

## Authorization checks that belong here too

- **Server-side enforcement, not just UI hiding.** The single most common
  real bug: a role check exists in the frontend/route guard but the
  underlying API endpoint doesn't re-verify it.
- **Object-level checks on every path that takes an ID** — see
  `idor_and_authz.md` for the dedicated methodology.

## Validation bar

A forged/tampered token that the server actually accepts as valid,
demonstrated end-to-end (the forged token used against a real protected
endpoint, showing the unauthorized response) — not "the JWT library used
looks old" or "the algorithm choice looks weak" without a working forgery.

## Weak password / credential testing

Distinct from JWT/session mechanics: the strength and handling of the credentials themselves.
- **Default & weak creds** — try vendor defaults (`admin/admin`, documented service accounts)
  and a small high-signal list; never a noisy brute-force without explicit authz + rate agreement.
- **Password policy** — register/reset flows accepting `123456`, `password`, the username, or
  a 1-char password = a finding on its own.
- **Credential stuffing surface** — no lockout / no rate limit / no CAPTCHA on login; confirm
  with a *small* controlled burst (see `native/repeater.py race`), not a real stuffing run.
- **User enumeration** — login/reset/registration responses (or timing) that distinguish
  "no such user" from "wrong password" — feeds the above.
- **Reset-token weakness** — predictable/sequential/short-lived-but-reusable reset tokens,
  or reset links that don't invalidate on use. Overlaps `finding_validation.md` severity calibration.
- **MFA** — bypass/downgrade (fallback to SMS/no-MFA), OTP reuse, missing rate limit on OTP.
Validation: an actual accepted weak credential, a confirmed missing lockout under a controlled
burst, or a reproduced enumeration oracle — not "the policy looks weak."
