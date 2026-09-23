---
name: multitenancy-and-baas
description: Owned methodology for multi-tenant isolation and vibe-coded / Backend-as-a-Service apps — Supabase/Firebase RLS gaps, service-role key exposure, tenant-context trust, direct BaaS API access bypassing the app, plus account lifecycle, org membership, deletion/privacy, and search-ACL issues that ride on tenancy. The highest-value area for internal vibe-coded tools.
---

# Multi-tenancy & Vibe-Coded / BaaS Apps

This is the area where modern internal tools break most often, because the
security model was never a backend — it's client-side logic plus a database
policy that may not exist. Test the data boundary directly, not through the UI.

## The vibe-coded failure mode

Typical architecture: `Frontend → Supabase/Firebase → DB + Storage`, with no
server of your own in the path. Consequences to test:

- **Client-side-only authorization** — the UI hides `/admin` or a button, but the
  BaaS API is reachable directly with the same anon key. The frontend restriction
  is not a boundary. Pull the endpoint + anon key from the JS bundle and call the
  database/storage API straight.
- **Service-role / admin key in the frontend** — grep the bundle and network
  calls for a Supabase `service_role` JWT, a Firebase `Admin`-privileged config,
  or any key that bypasses RLS. This is a full-database-read/write, critical.
- **Exposed project config** — Supabase project URL + anon key are *meant* to be
  public; they are only safe if RLS is on. Their presence is the start of the
  test, not the finding.
- **Debug/dev routes and prod/dev confusion** — dev endpoints shipped to prod,
  prod data reachable from a staging build (see env separation below).

## Supabase / PostgREST RLS

The anon/auth key is designed to be public; **Row-Level Security is the entire
boundary**. Test it directly against the REST (PostgREST) or client SDK:

- **RLS disabled on a table** — `GET /rest/v1/<table>?select=*` with the anon key
  returns every row. The most common critical bug. Enumerate tables (from the
  bundle, from `/rest/v1/` where introspectable, or guessing `users`,
  `profiles`, `orders`).
- **Policy covers SELECT but not INSERT/UPDATE/DELETE** — reads are scoped but a
  `PATCH`/`DELETE` on `?id=eq.<other>` succeeds. Test every verb separately.
- **Policy uses a client-supplied predicate** — a policy that trusts a
  `tenant_id` sent by the client rather than derived from `auth.uid()`/JWT
  claims. Change the filter and reach another tenant.
- **Column-level leakage** — `select=*` returning columns the app never shows.
- **RPC / `SECURITY DEFINER` functions** — Postgres functions that run as owner
  and skip RLS; call them directly with tampered args.
- **Storage policies** — the storage bucket has its own policies; an RLS-tight DB
  with an open bucket still leaks files (see storage below and `cloud_and_infra.md`).

**Systematic method (do this, in order):** identify the PostgREST / Auth / Storage
endpoints (from the bundle + the `*.supabase.co` base); **enumerate the schema** via
PostgREST (`/rest/v1/` + `?select=*&limit=1` per guessed/known table, OpenAPI at the root)
to map tables/columns; then **exercise every CRUD verb across both roles — anon vs
authenticated** — and diff. `RLS enabled but no policy = deny-all` (safe); `RLS disabled`
or a permissive policy = the bug.
- **"Ghost Auth" bypass** — many apps allow **self-signup of unconfirmed users**; an
  unconfirmed-but-authenticated session escapes the `anon` RLS rules and lands in the
  `authenticated` policies (often far more permissive). Register, don't confirm, retest.
- **`SECURITY DEFINER` RPCs** — audit every one: a function taking a `user_id`/`tenant_id`
  arg and reading a table **without checking `auth.uid()` against it** is a *complete* RLS
  bypass. Call them directly with another tenant's id.
- **PostgREST parameterization abuse** — embedded resource expansion (`?select=*,other(*)`),
  operator filters, and `Prefer` headers can pull related rows a naive policy didn't scope.
- **Edge Functions** — separate Deno functions with their own (often missing) authz; enumerate
  and test them directly, and check whether they use the **service-role key** (bypasses RLS).

## Firebase

- **Firestore/RTDB security rules** — `allow read, write: if true;` or overly
  broad `if request.auth != null;` (any logged-in user reads everything). Test by
  reading a collection you don't own with an authenticated client; the REST API
  (`https://<proj>.firebaseio.com/<path>.json`) is the quick check for RTDB.
- **Storage rules** — same pattern for Cloud Storage for Firebase.
- **Client-enforced-only writes** — validation in the app, none in rules.

## Tenant isolation (any stack)

- **Tenant id taken from the client** — a `tenant_id`/`org_id` in the body,
  header, or JWT that the server trusts without binding it to the authenticated
  identity. Swap it.
- **Tenant switching without re-authorization** — a "switch org" action that
  changes context but doesn't re-check membership.
- **Shared cache / storage leakage** — cache keyed without tenant, or object keys
  predictable across tenants.
- **Background-job / async tenant confusion** — the worker trusts a tenant id in
  the job payload (see `api_and_protocols.md`).
- **Admin cross-tenant** — a support/admin function that reaches all tenants;
  check it's logged and re-authenticated (see impersonation below).

## Account lifecycle & invitations

- **Stale invite** — an invitation link reused, accepted after expiry, or
  granting privileges the inviter no longer has.
- **Deleted / reactivated user** — a deleted user's token/session still valid; a
  reactivated user inheriting old privileges.
- **Email transfer** — changing an account's email to a victim's, or an invite to
  an email that later changes hands.

## Org membership & ownership

Unauthorized org join, self-service role escalation within an org, ownership
transfer abuse, orphaned access after removal (member removed from the UI but
their token/API access still works — test the API directly after removal).

## Deletion, privacy, search

- **Deletion** — a "deleted" record still retrievable by direct id, present in an
  export, or in a stale cache; soft-delete with no authz on the underlying row.
- **Search** — results that bypass row ACLs (the search index wasn't scoped),
  autocomplete leaking other tenants' names, stale deleted/private data still
  indexed.

## Environment separation & feature flags

Prod data in staging, shared credentials across environments, prod APIs callable
from a dev origin, test accounts with production privileges, client-controlled
feature flags exposing unfinished/privileged functionality the server doesn't
re-gate.

## Validation bar

The finding is another tenant's/user's **actual data** returned or modified
through the data API (not the UI), or a cross-tenant state change reproduced —
with the specific request (endpoint, key used, the id/tenant swapped). A public
anon key or a hidden UI route alone is not a finding until the boundary behind it
actually fails.
