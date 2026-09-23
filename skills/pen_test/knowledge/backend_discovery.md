---
name: backend-discovery
description: Methodology for figuring out the backend when it's hidden — the DB engine and data model, the real APIs behind a SPA / TanStack data layer / BFF, internal services, and acquiring the source itself (exposed .git, source maps, JS bundles, decompilation). Turns an opaque app into a mapped attack surface that feeds every other probe.
---

# Backend, DB & Source Discovery

You can't attack what you can't see. Modern apps hide the backend behind a client data
layer or a BFF, so the first job is recovering the *real* endpoints, data model, and (when
possible) the source. This feeds `sql_injection.md`, `idor_and_authz.md`,
`api_and_protocols.md`, `auth_bypass.md`, and `source_aware_review.md`.

## When "everything is behind TanStack / a BFF / a SPA"

The frontend abstraction is not a boundary — **the app still makes real HTTP calls to real
endpoints.** Recover them:

- **TanStack Query / Router** — `queryFn`/`mutationFn` and route `loader`/`action` functions
  call real URLs. They're in the JS bundle. Grep the bundle/source maps for `fetch(`,
  `axios`, `/api/`, base URLs, and query keys; each is an endpoint to enumerate.
- **TanStack Start / RSC / server functions** — these compile to **RPC-style endpoints**
  (a POST to a generated URL carrying a server-function id + serialized args). Find the
  server-function manifest/ids in the bundle; each server function is a real backend entry
  point whose **authz must be checked individually** (a classic BFLA source — the UI never
  shows it, but the endpoint is callable directly). Same for Next.js Server Actions
  (`frameworks.md`).
- **BFF (Backend-for-Frontend)** — a thin server (often `/api/*`, `/bff/*`) between the SPA
  and the real backend/microservices. Key shifts:
  - **Auth moves to the BFF.** The SPA usually has *no* token — the BFF holds an httpOnly
    session cookie and attaches the real credential server-side. So token attacks
    (`authn_jwt_session.md`) target the BFF session; test session flaws + the BFF's own
    routes for IDOR/authz (`idor_and_authz.md`).
  - **The prize is the backend behind it.** Can you reach the internal API directly
    (bypassing the BFF's authz)? Look for the backend host in configs/source maps/CORS/
    error messages; try it directly; or reach it via **SSRF** through a BFF proxy/fetch
    feature (`ssrf_and_injection.md`).
  - **Trust abuse.** The BFF often injects a service token / `X-User-Id` to the backend. If
    you can influence what it forwards (header injection, `semantic_confusion.md`, a
    parameter the BFF reflects), you may hit the backend with elevated trust.
- **Live capture is the fast path** — drive the app in `claude-in-chrome` and record the
  actual XHR/fetch/RPC traffic (network panel); that *is* the real endpoint list, already
  authenticated. Then replay/tamper with `repeater.py`. `katana` (JS-aware crawl) does this
  headless at scale (`tooling.md`).

## DB & backend fingerprinting

- **Engine** — from SQLi error strings (`sqli_probe.py` names MySQL/Postgres/MSSQL/Oracle/
  SQLite), time-based dialect (`SLEEP` vs `pg_sleep` vs `WAITFOR`), default ports
  (`port_scan.py`: 3306/5432/1433/1521/27017/6379/9200), and ORM tells (Django/Prisma/
  TypeORM error shapes — `frameworks.md`).
- **Data model** — from a confirmed SQLi, read `information_schema`/catalog for tables/
  columns (`sql_injection.md` → sqlmap `--tables`/`--columns`); from APIs, infer it from
  response fields, id formats (sequential vs UUID → enum vs IDOR), and error messages;
  from GraphQL, dump the schema (`graphql_probe.py`).
- **Internal services** — exposed data stores with no auth (redis/mongo/elasticsearch —
  `port_scan.py` flags these), admin panels, message queues, metrics endpoints
  (`technologies.md` Grafana/Prometheus), cloud metadata via SSRF (`cloud_and_infra.md`).

## Getting the source (whitebox from a blackbox start)

Source turns guessing into `source_aware_review.md`:
- **Exposed `.git`** — `http_recon.py` flags `/.git/HEAD`; recover the tree with a
  git-dumper technique (fetch objects, reconstruct). Full source + history (secrets!).
- **Source maps** — `/_next/static/**/*.js.map`, `//# sourceMappingURL=` in bundles →
  reconstruct original TS/JSX. `http_recon.py` / `recon_and_fingerprinting.md`.
- **JS bundle analysis** — even without maps, beautify the bundle; endpoints, feature
  flags, role logic, embedded keys, and `NEXT_PUBLIC_*`/`import.meta.env` values are there.
- **Package/config leaks** — `/package.json`, `/.env`, `/config.json`, `composer.json`,
  `/actuator/env`, backup files (`http_recon.py`).
- **Decompilation** — mobile (`client_and_mobile.md`: APK/IPA), Electron (`app.asar`),
  WASM. Recover client logic and hardcoded endpoints/secrets.
- **Registry / metadata** — exposed CI configs, Docker images, or a leaked internal
  package reveal service names and endpoints.

## Validation bar

A "discovered endpoint" is a lead until you hit it and get a real response; a "data model"
is confirmed by real returned data (`exploitation_depth.md`), not inferred field names.
Recovered source is evidence of exposure; the vulns you then find in it still meet their own
class bars.
