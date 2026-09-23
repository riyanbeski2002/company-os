---
name: api-and-protocols
description: Owned methodology for API-shaped classes beyond GraphQL — BOPLA/mass assignment, REST verb tampering and parameter pollution, API/shadow-endpoint discovery, rate-limiting and resource-abuse, plus the non-REST transports (WebSockets, webhooks, gRPC, realtime/pub-sub) and async paths (background jobs, queues).
---

# APIs & Protocols

GraphQL has its own doc (`modern_stack.md`) and probe. This covers the rest of
the API surface. Most are manual/`_httpcore`; the shared engine's
`--location json|form|header|cookie` and auth flags carry all of it.

## BOPLA — property-level authorization (mass assignment)

Object-level authz (IDOR) is *which objects*; property-level is *which fields*.

- **Mass assignment / over-posting** — add fields the UI never sends
  (`"role":"admin"`, `"verified":true`, `"account_id":<other>`,
  `"price":0`) to a create/update body. If the server binds the whole object,
  it accepts them.
- **Server-generated field overwrite** — supply `id`, `created_at`, `owner_id`,
  `balance` and see if your value wins over the server's.
- **Excessive data exposure** — the *response* returns more than the UI shows
  (password hashes, internal flags, other users' fields). Read the raw JSON,
  not the rendered page.

Test: capture a legit write, add/echo privileged properties, confirm the change
persisted (re-read the object) — not just a 200.

## REST verb tampering, HPP, parameter precedence

- **Verb tampering** — an endpoint authorized for `GET` but not re-checked for
  `PUT`/`DELETE`/`PATCH`; try `X-HTTP-Method-Override`, `_method`, and raw
  alternate verbs. Also `HEAD`/`OPTIONS` leaking behavior.
- **HTTP parameter pollution** — duplicate keys (`?role=user&role=admin`);
  front-end and back-end may pick different occurrences. Array vs scalar
  confusion (`id=1&id=2` → `[1,2]`).
- **Query/body precedence** — same param in query *and* body; which wins? Put
  the benign value where validation reads and the malicious where the sink reads.
- **Content-type confusion** — send form-encoded to a JSON endpoint (or vice
  versa) to dodge a validator that only inspects one parser.

## API / shadow-endpoint discovery

**Run it:** `python3 native/param_probe.py -u <url> --location query|form|json`
discovers hidden parameters the server honors (debug flags, `admin=`, redirect
params, mass-assignment fields) via reflection + response-diff; `arjun` and
`katana` add wordlist/crawl breadth. `http_recon.py` finds swagger/openapi. Beyond it:
- **Version drift** — `/v1` still live and unpatched after `/v2` shipped; authz
  fixed on one version only. Enumerate `/v1`../`/v3`, `/internal`, `/beta`.
- **Shadow / debug / staging** — `/debug`, `/test`, `/__admin`, deprecated
  routes in old JS bundles, `.map` files listing endpoints the UI dropped.
- **Undocumented from the client** — grep the frontend bundle for `fetch(`/
  `axios`/route tables; endpoints the UI gates client-side are still callable.

## Rate limiting & resource abuse

- **Per-user vs per-IP** — a limit keyed on IP falls to a rotating `X-Forwarded-
  For` (if trusted); keyed on account falls to many accounts. OTP/reset/login
  flooding are the high-value targets (enables brute force / account takeover).
- **Cost amplification** — expensive search, unbounded pagination, GraphQL query
  complexity/aliasing (see `modern_stack.md`), report generation. A single cheap
  request that costs the server dearly.
- **Third-party paid amplification** — an endpoint that triggers SMS/email/AI
  calls with no throttle is a billing-DoS.

## WebSockets

- **Handshake auth** — does the `Upgrade` request require a valid session, or is
  auth only checked on the initial page? Replay the handshake without cookies.
- **Cross-Site WebSocket Hijacking (CSWSH)** — WS has no same-origin protection;
  if the handshake relies only on cookies and no origin check, an attacker page
  opens an authenticated socket. Test `Origin:` from a foreign value.
- **Message-level authz / channel isolation** — after connecting, can you
  subscribe to another tenant's channel or send admin messages? Auth-at-connect
  ≠ auth-per-message.

## Webhooks (inbound)

Endpoints *you* receive from a third party (Stripe, GitHub):
- **Signature validation** — is the HMAC signature verified at all, and is the
  secret strong? Forge an event with no/invalid signature.
- **Replay / timestamp** — resend a captured valid event; is there a nonce or
  timestamp window? Replaying a `payment.succeeded` can grant entitlements.
- **Tenant confusion / SSRF** — outbound webhook *destination* controlled by a
  user is an SSRF vector (see `ssrf_and_injection.md`).

## gRPC

Manual (no native probe). Enable/abuse **server reflection** to enumerate
services and methods; check **per-method authorization** (metadata/token
required on every method, not just the first); **metadata auth** replay; and
protobuf field-level validation gaps. `grpcurl` is the practical client.

## Realtime / pub-sub, background jobs, queues

- **Realtime (Firebase RTDB/Firestore, Supabase Realtime, Pusher, Ably)** —
  channel/topic authorization, wildcard subscriptions, tenant separation. Deep
  detail for BaaS in `multitenancy_and_baas.md`.
- **Background jobs** — authorization frequently *lost after enqueue*: the API
  checks the caller, but the worker runs with service privileges and a
  client-supplied `user_id`/`tenant_id` in the job payload. Forge or tamper the
  enqueued parameters.
- **Queues / events** — forged or unsigned internal messages, consumer trusting
  producer identity, replay, cross-tenant routing.

## Availability (test with controlled limits only)

App-level DoS — expensive operations, queue/worker/storage exhaustion,
dependency amplification. **Never** run destructive load against a shared or
production target; demonstrate with a single measured expensive request and
reason about the amplification factor, not a flood.

## Validation bar

A confirmed finding is the *effect* reproduced: a persisted privileged field, a
verb that actually mutates, a foreign WS channel's messages received, a forged
webhook that grants state, an enqueued job that runs cross-tenant — not a
request that merely didn't error.
