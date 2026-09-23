---
name: frameworks
description: Owned methodology for framework-specific attack surface — Django, FastAPI, NestJS, Next.js. The misconfigurations, default behaviors, and per-framework sinks that generic class testing misses; strongest with source access (see source_aware_review.md).
---

# Framework-Specific Testing

Every framework ships defaults and idioms that create (or prevent) whole vuln classes.
Fingerprint first (`http_recon.py`), then apply the matching section. These pair with
`source_aware_review.md` when you have the code.

## Django (Python)

- **`DEBUG=True` in prod** — the highest-value find: full stack traces, settings dump
  (SECRET_KEY, DB creds), and the `/__debug__/` toolbar. Test error pages / a bad route.
- **`SECRET_KEY` exposure** → forge session cookies, signed tokens, password-reset tokens.
- **SSTI** — only if user input hits `Template().render()` with attacker-controlled
  template *source* (not normal context vars); rare but critical (`{% debug %}`, `{{}}`).
- **ORM injection** — `.extra()`, `.raw()`, `RawSQL`, and `QuerySet.annotate` with
  attacker input; `order_by` with a user-supplied field name (can't be parameterized).
- **Mass assignment** — `ModelForm`/DRF serializers with `fields = '__all__'` → set
  privileged fields (`is_staff`, `is_superuser`). See `api_and_protocols.md`.
- **Open redirect** — `next=` params in login/logout not validated against allowed hosts.
- **Admin** — `/admin/` exposed; weak creds; `list_filter`/`search_fields` info leak.

## FastAPI (Python)

- **Auto docs exposed** — `/docs`, `/redoc`, `/openapi.json` in prod = full API map
  (feed to `param_probe.py`/`idor_probe.py`). Often unauthenticated.
- **Pydantic over-permissive models** — extra fields accepted / mass assignment; check
  `model_config` `extra="allow"`.
- **Dependency-injection authz gaps** — auth enforced per-route via `Depends(...)`; a
  route missing the dependency is an unauthenticated hole (a classic BFLA source-aware find).
- **Async SQL** — raw string queries in `databases`/SQLAlchemy `text()` with f-strings.
- **CORS** — `allow_origins=["*"]` with `allow_credentials=True` (invalid but seen) →
  see `web_infra.md` / `cors_probe.py`.
- **SSRF** — `httpx`/`requests` calls on user-supplied URLs (webhook/import features).

## NestJS (Node/TypeScript)

- **Guards/interceptors coverage** — authz via `@UseGuards()`; a controller/route missing
  the guard, or a global guard with a `@Public()` escape hatch misapplied, is the bug.
- **`ValidationPipe` not global / `whitelist:false`** — mass assignment: extra body
  properties reach the entity (set `role`, `isAdmin`). `forbidNonWhitelisted` off = silent.
- **TypeORM/Prisma raw** — `query()`/`$queryRawUnsafe` with interpolation → SQLi.
- **Exposed GraphQL** — Nest's GraphQL module with introspection on → `graphql_probe.py`.
- **SSRF/deserialization** — `class-transformer` on untrusted input; URL-fetch features.
- Fingerprint: `X-Powered-By: Express`, Nest error shape, `/graphql` endpoint.

## Next.js (React SSR/SSG)

- **CVE-2025-29927 middleware bypass** — see `cve_playbook.md` (the field find):
  `x-middleware-subrequest` header skips middleware auth/redirect gates.
- **Source maps + `NEXT_PUBLIC_*`** — `/_next/static/**` often serves `.js.map` and bakes
  `NEXT_PUBLIC_*` env into the bundle; grep for keys, internal URLs, build metadata
  (`recon_and_fingerprinting.md`, `secrets_and_supply_chain.md`).
- **API routes / Server Actions / Route Handlers** — auth must be re-checked server-side
  in each `app/api/**` handler and each Server Action; client-side gating is not a boundary.
  Enumerate them and test authz/IDOR directly.
- **SSRF in `next/image`** — the image optimizer (`/_next/image?url=`) fetching remote
  URLs → SSRF / internal-metadata (`ssrf_probe.py` against the `url` param).
- **`getServerSideProps`/RSC** — user input reaching a DB/fs/exec sink server-side.
- **Open redirect** — `redirect()`/`router.push()` on unvalidated params.

## Validation bar

Framework knowledge points you at *where to look*; the finding still meets the class's
own bar (`sql_injection.md`, `idor_and_authz.md`, etc.). "Uses framework X" is never a
finding — a reachable, demonstrated sink or a confirmed missing control is.
