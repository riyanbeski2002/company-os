# pen_test skill + agent hardening

Scope: harden the artifacts only (no live testing). Make capabilities, methods,
and engine depth genuinely stronger across native scripts, coverage, operational
knowledge, and agent workflow.

## Phase 0 — Shared HTTP core (force-multiplier)
- [x] `native/_httpcore.py` — session (cookies/auth headers), proxy passthrough
      (Burp/ZAP), configurable injection point (query/form/json/header/cookie/path),
      concurrency + rate-limit, retries/timeouts, consistent Response/Result objects.
      Every probe adopts it.

## Phase 1 — Deepen the 5 existing probes
- [x] `sqli_probe.py` — add error-based (DBMS error-signature DB) + UNION column
      discovery; all injection points; session/auth; concurrency. Stays a detector
      that hands confirmed points to sqlmap.
- [x] `idor_probe.py` — true two-identity diff (User A vs User B tokens), read+write
      directions, sequential + UUID enumeration, placeholder in url/body/header.
- [x] `jwt_tool.py` — add `kid` injection, `jku`/`x5u` header abuse, JWKS confusion
      checks on top of existing alg:none / RS256->HS256 / crack / tamper.
- [x] `secret_scan.py` — expand pattern DB, add Shannon-entropy detection, per-finding
      severity, JWT/PEM detection.
- [x] `port_scan.py` — top-ports service map + modest banner/version heuristics.

## Phase 2 — New engines (close field-coverage gaps)
- [x] `http_recon.py` — security headers, tech/version fingerprint, exposed artifacts
      (.git/.env/source maps/backups), CORS misconfig, CVE-hint mapper. (Directly
      closes the Next.js CVE-2025-29927 gap seen in the field.)
- [x] `xss_probe.py` — reflection detection + context classification (HTML/attr/JS/URL);
      hands off to claude-in-chrome for execution proof.
- [x] `ssrf_probe.py` — SSRF candidate detection, cloud-metadata + filter-bypass
      payloads, out-of-band/callback support.
- [x] `graphql_probe.py` — introspection dump + field/type mapping + batching/alias hints.

## Phase 3 — Operational knowledge
- [x] Rewrite existing 5 knowledge/*.md into operator playbooks: candidate ID ->
      technique/payload ref -> decision tree -> validation bar -> escalation.
- [x] New: `recon_and_fingerprinting.md`, `xss.md`, `modern_stack.md`
      (GraphQL/NoSQLi/deserialization/prototype-pollution/SSTI), `cve_playbook.md`
      (capture field CVEs incl. Next.js 29927 w/ detection method).

## Phase 4 — Methods / engine depth (SKILL.md)
- [x] Add engagement lifecycle (recon -> surface map -> per-class triage -> exploit ->
      PoC -> report), native-vs-sqlmap-vs-nuclei-vs-browser decision matrix, expanded
      tooling index, field-learning capture loop, nuclei/trivy/semgrep command recipes.

## Phase 5 — Agent workflow (agents/pen_test.md)
- [x] Add the engagement lifecycle, evidence discipline, and field-learning capture
      loop (report-back, since agent has no Write tool). Align to new capabilities.

## Phase 6 — Verify
- [x] `python3 -m py_compile` every native script; run each `--help`; offline
      self-checks (arg parsing / import) with no live-target traffic.
- [x] `requirements.txt` updated for any new deps (keep minimal).
- [x] Record review notes here.

---

## Review (2026-09-23)

Delivered, artifacts only, no live testing (per scope):
- **_httpcore.py** — new shared engine: session/auth, Burp/ZAP proxy, injection into
  query/form/json/header/cookie/path, concurrency + rate-limit. Every probe adopts it.
- **5 probes deepened**: sqli (error-based+UNION+all locations), idor (true two-account
  diff + enum), jwt (kid/jku/x5u/alg-none variants), secret_scan (20+ formats + entropy +
  severity; fixed single-file bug), port_scan (service map + weak-default flags).
- **4 new engines**: http_recon (fingerprint/exposed-artifacts/CORS/CVE-hints —
  closes the Next.js CVE-2025-29927 field gap), xss_probe (context classifier),
  ssrf_probe (metadata + bypass + OOB), graphql_probe (introspection/batching).
- **Knowledge**: 5 files wired to tooling (Run-it + decision tree); 4 new
  (recon, xss, modern_stack, cve_playbook).
- **SKILL.md**: engagement lifecycle + decision matrix + field-learning loop + tool index.
- **agent**: lifecycle + learning-capture (report-back, no Write tool).

Verification: all 9 native scripts `py_compile` + `--help` clean; pure functions unit-tested;
end-to-end integration vs a localhost mock confirmed real detection (SQLi error+boolean,
XSS context+char-survival, recon headers/fingerprint). Import resolves from any cwd.

Open items flagged to Riyan (NOT changed — his call):
1. `agents/pen_test.md` runs on `model: haiku` — underpowered for exploit-chaining /
   business-logic reasoning; biggest remaining capability limiter. Cost vs. capability tradeoff.
2. `skills/pen_test.zip` (23MB, git-tracked) is a stale Sep-18 snapshot that bundles a
   `.venv`; nothing loads from it. Either regenerate on release or drop it from git.
3. `cryptography` not in the venv — jwt_tool `jku-forge` degrades to manual instructions
   until `pip install -r native/requirements.txt`.

---

## Sync from ~/Downloads/pen_test.zip (2026-09-23)

Adopted the externally-produced superset version (it critically reviewed and fixed
this session's work). Overlaid onto skills/pen_test/ (rsync, no --delete) so .venv
and engines/sqlmap clone were preserved; synced agents/pen_test.md to repo root;
deleted the stale git-tracked 23MB skills/pen_test.zip.

Added: 4 probes (cors/csrf/param/redirect), 9 knowledge domains + vulnerability_taxonomy.md,
engines/CATALOG.md, skills/pen_test/.gitignore. Fixed ~6 real bugs from this session
(rate-limiter lock serialization, Session thread-safety, sqli UNION false-positive,
jwt forge-hs256 broken + crack false-negative on exp tokens, idor false-positive).
Verified: all 14 native scripts compile + --help; jwt crack/forge fixes proven with fixtures.

FLAG (Riyan's call): skills/pen_test/agents/pen_test.md is a nested duplicate of the
canonical root agents/pen_test.md (identical now). The zip ships the skill self-contained;
in-repo it's a drift hazard. Decide: keep the bundle copy, or make root the single source.

---

## Native gap-closing (Strix comparison) — 2026-09-23

Route chosen: close the gap inside Claude Code, no new deps (do NOT wrap/run Strix).
- [x] (1) Mine Strix (Apache-2.0) OSS knowledge/technique coverage → enrich our KB/probes
      (read-only; adapt methodology into our own docs with attribution; no dependency added)
- [x] (2) Build owned HTTP repeater/replay on _httpcore (intercept-lite: send/modify/replay/diff)
- [x] (3) Package workflow skills — named one-shot runners (owasp-top-10, api-security, web-app)
      chaining existing probes + knowledge
- [x] Wire into SKILL.md / agent / vulnerability_taxonomy; verify compile + --help

### Native gap-closing — done (2026-09-23)
- (1) Mined Strix (Apache-2.0) analysis/ meta-methodology -> new knowledge/finding_validation.md
  (counter-evidence + severity calibration + fix verification, adapted+attributed); enriched
  secrets_and_supply_chain.md with npx/package-runner confusion. Rest of Strix's vuln coverage
  we already had.
- (2) native/repeater.py — send/raw/race/diff on _httpcore; validated (diff caught privilege
  differential, race surfaced rare success, raw replayed captured request).
- (3) scripts/workflow.sh (recon|webapp|api|owasp × quick|standard|deep) + knowledge/workflows.md
  (OWASP Top 10 map). Chains existing probes; validated live.
- Wired into SKILL.md, agents/pen_test.md (lifecycle steps 2-3), vulnerability_taxonomy.md.
- Verify: 15 native files compile, 14 probes --help, 3 scripts bash -n. No new deps.

---

## Full Strix parity — close ALL real gaps (2026-09-23)
New knowledge docs:
- [x] source_aware_review.md  (white-box source->sink discovery + SAST)
- [x] frameworks.md           (django, fastapi, nestjs, nextjs)
- [x] technologies.md         (active_directory, auth0, grafana_prometheus)
- [x] rce.md                  (dedicated RCE: cmd/deser/SSTI/upload -> RCE chains)
- [x] semantic_confusion.md   (parser/normalization/unicode + request-semantics confusion)
- [x] tooling.md              (per-tool usage cookbook: nmap/ffuf/httpx/katana/naabu/subfinder/
                               nuclei/semgrep/sqlmap/hurl/hypothesis/python/agent_browser)
Enrichments:
- [ ] authn_jwt_session.md  += weak_password_detection
- [x] ai_llm.md             += agentic_system_security
- [x] client_and_mobile.md  += browser_security
- [x] recon_and_fingerprinting.md += asset_discovery + infrastructure_lifecycle
- [x] cloud_and_infra.md    += per-provider aws/azure/gcp/k8s depth
- [x] wire all into SKILL.md + vulnerability_taxonomy.md; verify
