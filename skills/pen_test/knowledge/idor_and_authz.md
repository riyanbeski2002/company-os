---
name: idor-and-authz
description: Original methodology for IDOR, broken function-level authorization, and business-logic abuse.
---

# IDOR, Broken Function-Level Authorization, Business Logic

## Run it (native tooling)

`native/idor_probe.py` now has two modes. Use `diff` — it is the only one that
actually proves an authorization bypass rather than mere ID reachability:

```bash
# TWO-ACCOUNT diff (strongest): A must NOT be allowed to see B's object 501.
python3 native/idor_probe.py diff --url "https://api/orders/{id}" \
    --a-bearer "$TOKEN_A" --a-id 500 \
    --b-bearer "$TOKEN_B" --b-id 501
# write-direction IDOR is a SEPARATE finding — test it too:
python3 native/idor_probe.py diff --url "https://api/orders/{id}" -X PUT \
    --a-bearer "$TOKEN_A" --a-id 500 --b-bearer "$TOKEN_B" --b-id 501 \
    --body '{"note":"pwned"}' --location json

# single-account enumeration (weaker — proves reachability, not authz bypass):
python3 native/idor_probe.py enum --url "https://api/orders/{id}" \
    --bearer "$TOKEN_A" --ids 1-50,100,101
```

The `{id}` placeholder works in the URL path; use `--location query|json|form|
header` + `--param` when the id lives elsewhere. The tool establishes B's own
response as ground truth, so a "confirmed" verdict means A genuinely received
B's object — not a shared page or an empty 200.

## IDOR / BOLA (Broken Object-Level Authorization)

Any endpoint that takes an identifier (`/api/orders/123`, `?user_id=456`,
a UUID in a body) and returns/modifies that object is a candidate, even
when the ID "looks unguessable" (UUIDs stop enumeration, not authorization
bypass — if you can obtain or observe *any* valid ID for another user's
object, the test is the same).

**Method** — use `native/idor_probe.py` (this skill's own script) or do it
manually:
1. Authenticate as two distinct low-privilege accounts (User A, User B) if
   at all possible — testing with only one account and guessed IDs proves
   less than a real cross-account diff.
2. As User A, capture a real request for User A's own object.
3. Replay the identical request, authenticated as User A, but with User
   B's object ID substituted. A `200` returning User B's real data (not an
   empty/error/redacted response) is the finding.
4. Test both read and write directions separately — read-IDOR and
   write-IDOR are different findings even on the same endpoint (a `GET`
   might correctly 403 while a `PUT`/`DELETE` on the same resource
   pattern doesn't).
5. Test nested/indirect references too — an endpoint that takes a
   `report_id` which internally maps to a `customer_id` you don't
   directly control can still leak cross-tenant if the second-hop lookup
   isn't scoped.

## Broken Function-Level Authorization (BFLA)

Same idea, one level up: can a lower-privileged role reach an action
reserved for a higher one, by calling the endpoint directly rather than
through the UI that would normally hide/disable it? Enumerate admin/
privileged routes (often discoverable from client-side JS bundles, API
docs, or predictable naming — `/admin/*`, `/internal/*`) and call them
with a low-privilege token.

## Business Logic Abuse

Not a single technique — this is "does the feature's real-world
assumptions hold under adversarial use," found by reasoning about the
feature, not by running a scanner:
- **Race conditions**: can a coupon/discount/inventory-limited action be
  triggered concurrently (parallel requests) to bypass a check meant to
  be atomic (e.g. redeem the same one-time code twice, apply a discount
  N times, overdraw a balance)? Fire the same request many times in quick
  succession and check whether the "already used" check actually holds
  under concurrency (a classic TOCTOU gap: check-then-act without a lock/
  atomic operation).
- **Price/quantity manipulation**: can a client-supplied price, discount
  percentage, or currency field override server-computed values, or does
  the server always recompute from trusted state?
- **Workflow/state-machine bypass**: can a multi-step process (checkout,
  approval flow, KYC) be short-circuited by calling a later-stage endpoint
  directly, skipping an earlier required step?
- **Negative/boundary values**: negative quantities, zero-amount
  transactions, extremely large numbers (integer overflow) in any
  quantity/amount field.

## Validation bar

IDOR/BFLA: an actual response showing another account's real data, or an
actual state change (data modified/deleted) that shouldn't have been
permitted for that role — reproduced, not a single ambiguous response.
Business logic: an actual successful abuse of the flow (double-redeemed
code, bypassed step, manipulated total), not just "this looks like it
could race."
