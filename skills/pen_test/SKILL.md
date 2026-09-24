---
name: pen_test
description: Full local exploitation capability for the pen_test agent — original, owned methodology and native tooling for SQLi, SSRF/XXE/injection, JWT/auth, IDOR/business-logic, and secrets, plus continuously-updated engines (sqlmap, nuclei, trivy, semgrep) for the classes where a live feed is the actual value. Triggers on - run a pentest, exploit this endpoint, SQL injection test, full exploitation, penetration test.
---

# Pen Test

The capability behind the `pen_test` agent, built on one principle: **own
what's stable, depend on what has to stay current — never freeze a copy of
either.** Two different things were being conflated in earlier iterations
of this skill, and they need different treatment:

1. **Technique knowledge that doesn't meaningfully change** (how boolean-blind
   SQLi detection works, how JWT `alg:none` forgery works, how IDOR
   cross-account diffing works) — this is genuinely ours to own. Written
   directly into `knowledge/*.md`, executed by `native/*.py`. No external
   repo, no re-fetching, no staleness risk because the underlying technique
   is stable, published, well-understood security knowledge.
2. **Engines whose entire value IS a continuously-updated feed** (nuclei's
   template library, Trivy's CVE database, semgrep's rule registry,
   sqlmap's evolving tamper/technique scripts) — reimplementing these from
   scratch would produce something stale the day it's written and unable
   to track new CVEs. These are kept as real dependencies, refreshed on a
   schedule, not frozen snapshots and not badly-cloned reimplementations.

**Authorization is not optional.** Everything below does real, active
exploitation or automated attack technique execution. Never run any of it
against a target you don't own or don't have explicit written authorization
to test.

---

## Engagement lifecycle (how a run actually goes)

Don't jump straight to a class-specific probe. Work the surface in order — each
stage feeds the next, and skipping recon wastes the whole engagement:

1. **Recon & map** — `http_recon.py` (+ `port_scan.py` for non-web).
   Fingerprint the stack, list exposed artifacts, enumerate params/endpoints
   (swagger/openapi/GraphQL introspection). Output = the attack surface.
2. **Triage per class** — for each candidate point, run the matching native
   probe *after* reading its `knowledge/*.md`. Parallelize independent classes
   as Tier-1 subagents when a target has several angles.
3. **Confirm** — a probe hit is a *candidate*. Reproduce it independently (the
   per-class validation bar in each knowledge file), ruling out jitter/parser
   quirks/shared pages.
4. **Exploit end-to-end** — a benign proof (`7*7`, `alert(document.domain)`, a DNS
   hit) is a *candidate, not the deliverable*. For an authorized target, carry it to
   **demonstrated impact** per `knowledge/exploitation_depth.md`: `sqlmap --dump` a
   bounded redacted sample, use the forged token to reach the protected resource,
   return the actual cross-tenant record, extract+validate the SSRF'd cloud creds,
   steal the session behind the XSS. Discipline is non-negotiable even when authorized:
   bounded/redacted evidence, non-destructive, reversible, no DoS, no persistence/pivot
   beyond proof, in-scope only, honor evidence caps. Destructive/DoS/persistent steps
   are out of scope regardless of authorization.
5. **Report** — severity-first, every finding tied to its end-to-end impact artifact
   (not just a PoC). This is **mandatory and tool-produced**: run every probe with
   `--evidence-dir <DIR>`, then `python3 native/report.py <DIR>` for the `report.md`/
   `report.json` deliverable. Proof-less candidates are quarantined, never counted. See
   the report section below and `agents/pen_test.md`.

### Decision matrix — native vs. engine vs. browser

| Situation | Reach for |
|---|---|
| First contact with any web target | `http_recon.py` |
| Network/infra VA (host + services) | `workflow.sh infra <host>` → `port_scan.py` + `service_probe.py` + `tls_probe.py` + nmap/nuclei |
| TLS/SSL crypto assessment | `tls_probe.py <host> [--starttls smtp\|imap\|pop3\|ftp]` |
| Exposed unauth service (redis/mongo/ES/docker/k8s/...) | `service_probe.py <host> [--snmp]` |
| Service-version → CVE depth | `nmap -sV --script vuln` + `nuclei -tags network` (refresh feed first) |
| Detect a vuln class (any injection point) | the matching `native/*.py` probe |
| Find hidden params before class-probing | `param_probe.py` (then `arjun` for breadth) |
| CORS / open-redirect / CSRF detection | `cors_probe.py` / `redirect_probe.py` / `csrf_probe.py` |
| SSTI / cmd-injection / traversal-LFI / XXE / file-upload | `ssti_probe.py` / `cmdi_probe.py` / `traversal_probe.py` / `xxe_probe.py` / `upload_probe.py` |
| Assemble the engagement deliverable | `report.py <evidence-dir>` (every probe run with `--evidence-dir`) |
| Confirmed SQLi, need data extraction | `engines/sqlmap/sqlmap.py` |
| Request smuggling / CORS breadth | `engines/` — `smuggler` / `Corsy` (see `engines/CATALOG.md`); SSTI is now native (`ssti_probe.py`) |
| Known framework/version, want CVE breadth | `nuclei -tags <tech>` (refresh feed first) |
| Dependency / container / IaC CVEs | `trivy` / `grype` / `checkov` |
| Cloud posture / subdomain takeover | `prowler`/`scoutsuite` / `subzy` (scope-gated) |
| Code-level pattern review | `semgrep --config=auto` + `Read`/`Grep` |
| XSS/CSRF/auth-flow/clickjacking execution proof | `claude-in-chrome` (real browser) |
| Blind SSRF/OOB confirmation | `ssrf_probe.py --callback` + a collaborator |

### Field-learning capture loop

The whole point of "own what's stable, depend on what's current" is that the
owned side improves from real engagements. When a run teaches something durable
— a new CVE for a stack we test, a bypass a probe missed, a new secret format —
capture it back into the skill so the next run has it:
- named CVE → add to `knowledge/cve_playbook.md` **and** a trigger in
  `http_recon.py`'s `cve_hints()`.
- new technique/payload class → the matching `knowledge/*.md` + probe.
- new secret format → `secret_scan.py`'s `PATTERNS`.

The `pen_test` **agent** can't do this itself (it has no Write tool, by design —
see `agents/pen_test.md`); it reports the learning back to the PM/Riyan, who
updates the skill. That keeps the capability improving without giving the
exploitation runner write access to its own tooling.

---

## 1. Owned — knowledge/ + native/ (default path, use this first)

**Start at `knowledge/vulnerability_taxonomy.md`** — the coverage map over every
vulnerability domain the skill knows about (the full domain taxonomy), each
row pointing at the knowledge file / native probe / engine that handles it and a
one-line test. Use it to pick the right methodology for a candidate, and to see
what is owned tooling vs. manual vs. an external engine.

`knowledge/*.md` — original methodology write-ups, written for this skill,
not copied from any external source. Each opens with a "Run it" block wiring
it to the native tool above, a decision tree, and a per-class validation bar:
- `recon_and_fingerprinting.md` — the recon pass that precedes everything; turns a fingerprint into a targeted plan
- `sql_injection.md` — boolean-blind, time-blind, error-based, UNION-based detection and extraction
- `xss.md` — reflected/stored/DOM XSS, context→breakout table, browser-proven execution bar
- `ssrf_and_injection.md` — SSRF (incl. cloud metadata endpoints, filter bypass), XXE, command injection, argument injection, SSTI
- `authn_jwt_session.md` — JWT forgery classes (`alg:none`, RS256→HS256, `kid`/`jku`, weak-secret), session management
- `auth_bypass.md` — consolidated auth-wall bypass: SQLi/NoSQL login bypass, default creds, forced-browse/BFLA, response/status manipulation, 2FA/MFA bypass, session/reset abuse, param tampering (`auth_probe.py`)
- `credential_attacks.md` — brute/spray/stuffing + offline cracking (hashcat/john modes, hydra/ffuf for scale) with controlled-testing discipline
- `backend_discovery.md` — finding the hidden backend: DB/engine fingerprint, data-model inference, real APIs behind a SPA / **TanStack** / **BFF**, and source acquisition (.git dump, source maps, bundle/decompile)
- `oauth_oidc_sso.md` — OAuth/OIDC/SSO flow flaws: redirect_uri, state/nonce, PKCE, code handling, scope/consent, account linking, SSO logout
- `idor_and_authz.md` — IDOR/BOLA cross-account diffing, broken function-level authorization, business-logic abuse (races, price/state manipulation)
- `web_infra.md` — CSRF, CORS, open redirect, host-header injection, HTTP request smuggling, web cache poisoning, clickjacking, security headers/CSP
- `api_and_protocols.md` — BOPLA/mass assignment, verb tampering/HPP, API/shadow discovery, rate-limiting/resource abuse, WebSockets, webhooks, gRPC, realtime, background jobs
- `modern_stack.md` — GraphQL, NoSQL injection, insecure deserialization, prototype pollution, SSTI
- `multitenancy_and_baas.md` — Supabase/Firebase RLS gaps, service-role key exposure, tenant isolation, vibe-coded apps, account lifecycle, deletion/privacy, search ACL
- `cloud_and_infra.md` — cloud storage/IAM, containers/K8s, serverless, CI/CD, DNS/subdomain takeover, email domain, TLS/crypto, network/MITM, signed URLs
- `ai_llm.md` — prompt injection (direct + indirect), tool/agent authorization, data exfil, RAG/vector-store ACL and tenant isolation
- `data_handling.md` — file upload, path traversal/Zip Slip, CSV formula injection, PDF/image processing, input normalization, ReDoS
- `client_and_mobile.md` — browser storage/service workers, mobile (storage, exported components, deep links, WebView), desktop/Electron
- `cve_playbook.md` — specific high-value CVEs the fingerprint should trigger (incl. Next.js CVE-2025-29927); the field-learning capture point
- `exploitation_depth.md` — **the evidence standard**: carry every confirmed vuln end-to-end to demonstrated (bounded, redacted) impact, not a detection/PoC; per-class "candidate vs. full exploitation"
- `finding_validation.md` — the meta-skill: counter-evidence (disprove your own finding), honest severity calibration, fix verification — what makes a finding defensible vs. a scanner dump
- `source_aware_review.md` — white-box source→sink discovery + SAST: instance discipline, control-centric reading, family sweeps
- `rce.md` — the roads to remote code execution (cmd/deser/SSTI/upload/resolution/SQLi→RCE) + safe benign-proof bar
- `semantic_confusion.md` — parser differentials, normalization drift, field overloading, lifecycle carryover, boundary translation, resolution fallback
- `frameworks.md` — Django, FastAPI, NestJS, Next.js — per-framework defaults, misconfig, and sinks
- `technologies.md` — Active Directory, Auth0, Grafana/Prometheus (+ pointers to Firebase/Supabase/LLM/Electron)
- `tooling.md` — usage cookbook for every wired external tool (nmap/ffuf/httpx/katana/naabu/subfinder/nuclei/trivy/semgrep/sqlmap/hurl/hypothesis/python/browser)
- `workflows.md` — named packaged workflows (recon/webapp/api/owasp) + quick/standard/deep depth, driven by `scripts/workflow.sh`
- `secrets_and_supply_chain.md` — secret detection patterns and when to escalate to a real CVE-feed tool instead of native

`native/*.py` — original scripts implementing the above directly (stdlib +
`requests`/`pyjwt`, see `native/requirements.txt` — normal library
dependencies, not vendored tool source). All the HTTP probes share
`native/_httpcore.py`, so every one of them supports a real authenticated
session, proxy passthrough (`--proxy` into Burp/ZAP), injection into ANY
location (`--location query|form|json|header|cookie|path`), concurrency and
rate-limiting — pass `-H`, `-b`, `--bearer`, `-k`, `--rate` to any of them:

- `http_recon.py` — **run first.** Security-header audit, tech/version
  fingerprint, exposed-artifact discovery (`.git`/`.env`/actuator/source maps),
  CORS misconfig, and a CVE-hint mapper. Points every other probe at the right target.
- `sqli_probe.py` — error-based + boolean-blind + time-blind + UNION column
  discovery, any injection location. Detector; hands confirmed points to sqlmap.
- `xss_probe.py` — reflection detection + context classifier (html/attr/script/
  href) + unencoded-char survival; emits the context's breakout payload.
- `idor_probe.py` — `diff` (true two-account cross-object) and `enum` modes; read+write.
- `ssrf_probe.py` — cloud-metadata (AWS/GCP/Azure/DO/Alibaba), filter-bypass
  encodings, and out-of-band callback for blind SSRF.
- `jwt_tool.py` — decode/triage, `alg:none` (case variants), RS256→HS256
  confusion, `kid` injection, `jku`/`x5u` JWKS spoofing, weak-secret crack, claim tamper.
- `graphql_probe.py` — introspection dump, field-suggestion leak, dangerous-mutation
  + batching detection.
- `cors_probe.py` — deep CORS: reflected/null/prefix/suffix/subdomain Origin variants
  **plus credentials** — the combination that makes an authenticated cross-origin read.
- `redirect_probe.py` — open redirect: filter-bypass payload battery (`//`, `\\`, `@`,
  whitelist-prefix), off-host `Location` detection; chains into OAuth (`oauth_oidc_sso.md`).
- `csrf_probe.py` — CSRF posture (token/SameSite/Origin enforcement, replayed) + auto-generated
  PoC HTML to prove execution in `claude-in-chrome`.
- `param_probe.py` — Arjun-style hidden-parameter discovery (reflection + response-diff over
  baseline noise); feeds discovered params to the other probes.
- `port_scan.py` — concurrent TCP connect scan, service map + weak-default flags.
- `tls_probe.py` — TLS/SSL VA (network/infra): accepted-protocol test (SSLv3/1.0/1.1),
  weak-cipher offer-tests + forward-secrecy, certificate (expiry/self-signed/host-mismatch/
  weak-key/weak-sig/untrusted-chain), STARTTLS, HSTS. Connect-only; prints its own honest
  limits (Heartbleed/ROBOT/DH-modulus need testssl/nmap). See `network_va.md`.
- `service_probe.py` — exposed-service VA: benign unauth/misconfig checks for redis, mongodb,
  elasticsearch, kibana, memcached, ftp-anon, vnc, docker/k8s/kubelet, snmp, rabbitmq(guest),
  mysql/postgres, smb/rdp negotiate — each verdict requires a positive real-resource payload,
  captured as evidence. Delegates SMB/Oracle/CVE depth to nmap+nuclei. See `network_va.md`.
- `secret_scan.py` — 20+ named formats + Shannon-entropy detection, severity-ranked
  (working tree + git history).
- `repeater.py` — Burp-Repeater-lite: `send` / `raw` (replay a captured request) /
  `race` (concurrent N× for business-logic races) / `diff` (two variants, diff
  responses). The manual instrument for hand-confirming a candidate and crafting the PoC.
- `auth_probe.py` — login/auth-wall attack: `bypass` (SQLi/NoSQL/default-cred battery +
  success detection) / `spray` / `brute` / `enum` (user-enum oracle). Bounded, rate-limited,
  lockout-aware, authorized-only.
- `ssti_probe.py` — Server-Side Template Injection: evaluation-vs-reflection differential
  (randomized-operand arithmetic, inert-sibling + numeric controls), engine fingerprint
  (Jinja2/Twig/Freemarker/Velocity/ERB/Mako/Thymeleaf/Razor), and ONE benign read-only
  context proof. Detector — RCE escalation is out of scope (`rce.md`).
- `cmdi_probe.py` — OS command injection: three benign signals — time-based **with scaling
  confirmation** (rules out WAF tarpit/jitter), split/computed echo marker (reflection can't
  fake it), and OOB (`--oob-host`). Unix+Windows separators, quote-breakout, `${IFS}`.
- `traversal_probe.py` — path traversal / LFI: `../` depth-ladder × every bypass encoding
  (URL/double-URL/overlong-UTF8/`....//`/backslash) against content-signature targets, with a
  bogus-path baseline; PHP `php://filter` base64 source disclosure; `--prefix`/`--suffix` tuning.
- `xxe_probe.py` — XXE / XML injection: in-band external-entity file read, inert-canary parser
  control, XInclude, **JSON→XML content-type flip** (dormant XML parsers), blind OOB with the
  external-DTD exfil skeleton. Single-level benign entities only — no billion-laughs/DoS.
- `upload_probe.py` — malicious file upload: accepted-vs-control differential, locate + fetch-
  back, and the **executed** (computed marker) / **dangerously-served** (SVG/HTML stored-XSS)
  proof. Benign inert markers only; records URLs for cleanup. Never drops a working webshell.

**Evidence is the deliverable, and it is mandatory.** Run every probe with
`--evidence-dir <DIR>`; each appends a structured, proof-bearing `Finding` to
`<DIR>/findings.jsonl`. End the engagement with `python3 native/report.py <DIR>`
to produce the severity-ranked `report.md` + `report.json`. A finding whose proof
is empty is **quarantined, not counted** — a bare signal or benign PoC is a
candidate; only real, source-extracted, benign evidence is a finding
(`knowledge/exploitation_depth.md`).

Named **workflows** package these into how engagements are scoped —
`scripts/workflow.sh <recon|webapp|api|owasp> <url> [--depth quick|standard|deep]`
runs the automatable steps and prints the targeted ones (see `knowledge/workflows.md`).

**Workflow:** read the matching `knowledge/*.md` file for the suspected
vulnerability class before testing it — this is the actual discipline, not
optional context. Run the matching `native/*.py` script (or the equivalent
manual requests, `Bash`/`curl`) to execute. For anything browser-driven
(XSS, CSRF, auth-bypass flows, clickjacking), use `claude-in-chrome` — real
browser control, not a simulation. For code-level review, `Read`/`Grep`/`Glob`
plus `semgrep` (below) for rule-driven static analysis beyond plain grep.
Parallelize independent vulnerability classes as Tier-1 subagents (`Agent`
tool) when a target has several angles worth investigating at once.

**Validate with a real PoC** before reporting anything — every
`knowledge/*.md` file states its own validation bar. A pattern match or a
"this looks vulnerable" is not a finding.

## 2. Installed, not cloned — static utility binaries

Single CLI tools with no meaningfully "updating" internal database — a
normal package-manager install, refreshed by their own maintainers'
release cycle like any other software dependency, not something to clone
or reimplement:

```bash
bash skills/pen_test/scripts/install_extra_tools.sh
```

| Tool | License | What it's for |
|---|---|---|
| `gitleaks` | MIT | Secret scanning — broader pattern coverage than `native/secret_scan.py` |
| `zaproxy` (OWASP ZAP) | Apache-2.0 | Dedicated web-app scanner (spider/fuzzer/active-scan), headless via `zaproxy/zap-stable` Docker image |
| `checkov` | Apache-2.0 | IaC misconfiguration (Terraform/K8s/CloudFormation) |
| `grype` | Apache-2.0 | Dependency/container vulnerability scanning (SCA) |
| `syft` | Apache-2.0 | SBOM generation (SPDX/CycloneDX) |
| `jwt-cli` | MIT | JWT CLI, if you want it alongside `native/jwt_tool.py` |
| `prowler` | Apache-2.0 | Cloud security posture auditing (AWS/Azure/GCP) |

**Flagged, not installed by default:** `trufflehog` (AGPL-3.0, live
credential verification `gitleaks`/`native/secret_scan.py` lack) — real
capability, real copyleft consideration, needs a fresh `company escalate`
before adoption (same treatment as `caveman`/`daytona` elsewhere in the
registry).

## 3. Cloned and kept updated — living engines

The one legitimate case for cloning: tools whose real value is a
continuously-refreshed feed, not static logic. Freezing a copy of these
would be actively misleading (a stale CVE database says "clean" about a
vulnerability disclosed last week). Refresh before any real engagement:

```bash
bash skills/pen_test/scripts/update_engines.sh           # clone/refresh engines + feeds
bash skills/pen_test/scripts/update_engines.sh --check    # read-only: what's actually present/reachable
```

`--check` installs nothing — it reports which engines, feed tools, companion
utilities, and GitHub egress are actually available on this machine, so an
engagement plans around what it can rely on (installs are best-effort and no-op
in a locked-down environment). Run it at the start of every engagement.

- **`sqlmap`** (GPL-2.0) — cloned to `skills/pen_test/engines/sqlmap`
  (gitignored, `git pull`-refreshed, not a static snapshot) because its
  tamper/technique scripts genuinely improve over time and it has no clean
  single-binary package on most platforms. Use once `native/sqli_probe.py`
  confirms a candidate injection point and you need full extraction depth
  (DBMS-specific dumping, `--os-shell`) — that depth is a real, continuously
  maintained engineering effort, not worth badly re-cloning from scratch.
  ```bash
  python3 skills/pen_test/engines/sqlmap/sqlmap.py -u "<authorized-url>?id=1" --batch --level=2 --risk=1
  python3 .../sqlmap.py -u "<url>" --dbs   # then -D <db> --tables, -D <db> -T <table> --dump
  ```
  Only escalate to `--os-shell`/`--os-pwn` when authorization explicitly
  covers OS-level access, not just data read. Run `--help`/`-hh` for the
  full, current flag set — the surface is large and versioned.
- **`nuclei`** (MIT, binary installed via brew) — the templates are the
  actual product: thousands of community/vendor CVE templates, updated
  constantly. `update_engines.sh` runs `nuclei -update-templates`.
- **`trivy`** (Apache-2.0, binary installed via brew) — vulnerability DB is
  the product. `update_engines.sh` runs `trivy image --download-db-only`.
- **`semgrep`** (LGPL-2.1 core, used arm's-length — doesn't extend
  copyleft here) — rule registry self-updates per invocation
  (`--config=auto` or `--config=p/<ruleset>`); nothing to pre-fetch, listed
  here so it's not mistaken for an oversight.
- **`smuggler`** (HTTP request smuggling), **`Corsy`** (CORS breadth),
  **`SSTImap`** (SSTI detect+exploit) — maintained single-technique engines
  cloned into `engines/` for the classes the native probes don't own. These pair
  with `native/csrf_probe.py`/`cors_probe.py`/`redirect_probe.py`/`param_probe.py`
  and the recon/cloud tools in `scripts/install_extra_tools.sh`.

**The full external-tool map is `engines/CATALOG.md`** — every wired engine and
single-purpose tool, the taxonomy domain it serves, its knowledge doc, and its
companion native probe. Read it to decide native-probe-vs-engine for a class.

---

## How this feeds `pen_test`'s report

Every finding should carry its **end-to-end impact artifact**, not just a
detection or a benign PoC (`knowledge/exploitation_depth.md`): the bounded,
redacted evidence that the chain actually worked — the dumped sample, the
cross-tenant record read, the credential validated, the action performed, the
session taken over. Sources: `native/*.py` output, a `sqlmap`/`nuclei`/`trivy`
confirmed result, `repeater.py` replays, or a `claude-in-chrome`-captured
exploit — never a `knowledge/*.md` citation alone (methodology, not evidence),
and never a candidate inflated to "proven." A point that couldn't be carried to
impact is reported as an explicit `open_proof_gap`. See `agents/pen_test.md` for
the reporting format (`SECURITY_REVIEW_PASSED`/`FAILED` with concrete evidence).
