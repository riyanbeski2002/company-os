---
name: tooling
description: Usage cookbook for the external tools this skill wires in — nmap, ffuf, feroxbuster, httpx, katana, naabu, subfinder, subzy, nuclei, trivy, grype, semgrep, sqlmap, hurl, python, and the browser. For each - the exact command, when to reach for it over a native probe, and which knowledge doc/class it serves.
---

# Tooling Cookbook

Our native probes own the stable technique classes; these external tools cover breadth,
live feeds, and recon scale. Install/refresh via `scripts/install_extra_tools.sh` and
`scripts/update_engines.sh` (check availability with `update_engines.sh --check`). Rule
of thumb: **native probe first** for a class we own; reach for a tool when it's a live
feed (nuclei/trivy), a scale problem (recon), or depth beyond our detector (sqlmap).

## Recon & discovery

- **subfinder** — passive subdomain enumeration. `subfinder -d target.com -silent`.
  Scope-gated: only for domains you're authorized on. → `recon_and_fingerprinting.md`.
- **httpx** — probe a host list for live web servers + fingerprint.
  `subfinder -d target.com -silent | httpx -silent -title -tech-detect -status-code`.
- **naabu** — fast port discovery (breadth beyond `native/port_scan.py`).
  `naabu -host target.com -top-ports 1000 -silent` → pipe open ports to httpx.
- **katana** — crawler / endpoint + param discovery. `katana -u https://target -jc -silent`
  (JS crawling). Feeds URLs/params to `sqli_probe.py`/`xss_probe.py`/`param_probe.py`.
- **ffuf / feroxbuster** — content & parameter fuzzing.
  `ffuf -u https://target/FUZZ -w wordlist.txt -mc 200,301,403` ;
  `feroxbuster -u https://target --depth 2`. Recursive dir/file discovery.
- **nmap** — full service/version depth beyond `port_scan.py`.
  `nmap -sV -sC -p- --min-rate 1000 target` (add `--script` for NSE). Authorized only.
- **subzy** — subdomain takeover check on a subdomain list.
  `subzy run --targets subs.txt`. → `cloud_and_infra.md`.

## Live-feed engines (the value is the up-to-date database)

- **nuclei** — templated CVE/misconfig scanning. Refresh first (`nuclei -update-templates`),
  then `nuclei -u https://target -tags <tech>` (target the fingerprint from `http_recon.py`).
  → `cve_playbook.md`.
- **trivy / grype** — dependency & container CVEs (SCA). `trivy fs .` / `trivy image <img>` ;
  `grype dir:.`. Refresh DB before an engagement. → `secrets_and_supply_chain.md`.
- **sqlmap** — SQLi *extraction* depth once `sqli_probe.py` confirms a point.
  `python3 engines/sqlmap/sqlmap.py -u '<url>' --batch --level=2 --risk=1` then `--dbs`,
  `-D <db> --tables`, `--dump`. `--os-shell` only under explicit execution authz.
  → `sql_injection.md`, `rce.md`.

## Code review

- **semgrep** — rule-driven SAST / taint. `semgrep --config=auto` (or `--config=p/owasp-top-ten`,
  `-p/<lang>`). Rules self-update per run. Candidates → confirm via `source_aware_review.md`.
- **python** — the escape hatch: when no tool fits, script it against `_httpcore` or with
  `requests`/`pwntools` for a custom exploit/PoC. The native probes are the worked examples.

## Request crafting & verification

- **hurl** — plain-text HTTP request files with assertions; good for scripted multi-step
  flows and regression-checking a fix. `hurl --test flow.hurl`. Our `native/repeater.py`
  covers the interactive send/raw/race/diff case; hurl is for repeatable scripted chains.
- **agent_browser (claude-in-chrome)** — real browser control for what needs a DOM/JS
  engine: XSS *execution* proof, CSRF/clickjacking, auth/SSO flows, DOM-based bugs.
  This is our browser tool — use it to *prove* a candidate `xss_probe.py` flagged.
  → `xss.md`, `web_infra.md`.
- **hypothesis** — property-based test generation (fuzz-with-invariants) for a target's
  own API/parsers when you have code and want to shake out edge-case handling; pairs with
  `source_aware_review.md` and `data_handling.md` (parser abuse / ReDoS).

## Utility

- **gitleaks / trufflehog** — broader secret scanning than `native/secret_scan.py`
  (trufflehog adds live verification; AGPL — see `secrets_and_supply_chain.md`).
- **prowler / scoutsuite** — cloud posture (AWS/Azure/GCP). `prowler aws` / `scout aws`.
  → `cloud_and_infra.md`. **checkov** — IaC misconfig. **syft** — SBOM.

## The rule

A tool's output is a **candidate**, same as a native probe's — it meets its class's
validation bar and `finding_validation.md` before it's a finding. Redirect verbose tool
output to a file and read only what matters (see the agent's context-hygiene note).
