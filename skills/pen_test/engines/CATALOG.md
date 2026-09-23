# Engine Catalog — wired external tools, by domain

The native probes (`native/*.py`) own the stable single-technique classes. This
catalog is the **other half**: maintained external tools wired in for the
scan-heavy / feed-driven classes where reimplementing would be a regression.
Install/refresh them with `scripts/install_extra_tools.sh` (binaries + pipx) and
`scripts/update_engines.sh` (git-cloned engines + live feeds).

Rule of thumb: reach for a **native probe first** (owned, authenticated session,
no dependency); escalate to the engine here when you need breadth, a live feed,
or a class no native probe covers. Redirect verbose engine output to a file and
read the tail (see `agents/pen_test.md`).

## Cloned engines (`engines/`, git-pull refreshed)

| Engine | Domain | Knowledge doc | Invoke |
|---|---|---|---|
| `sqlmap` | SQLi extraction depth | `sql_injection.md` | `python3 engines/sqlmap/sqlmap.py -u '<url>' --batch` |
| `smuggler` | HTTP request smuggling | `web_infra.md` | `python3 engines/smuggler/smuggler.py -u <url>` |
| `Corsy` | CORS (breadth) | `web_infra.md` | `python3 engines/Corsy/corsy.py -u <url>` — pairs with `native/cors_probe.py` |
| `SSTImap` | SSTI detect + exploit | `ssrf_and_injection.md`, `modern_stack.md` | `python3 engines/SSTImap/sstimap.py -u '<url>'` |

## Live-feed engines (binaries; feeds self-update)

| Engine | Domain | Knowledge doc | Invoke |
|---|---|---|---|
| `nuclei` | CVE / misconfig breadth, takeover, exposures | `cve_playbook.md` | `nuclei -u <url> -tags <tech>` (refresh templates first) |
| `trivy` / `grype` | dependency & container CVEs | `secrets_and_supply_chain.md` | `trivy image <img>` · `grype <target>` |
| `semgrep` | code-level pattern review | (whitebox) | `semgrep --config=auto <path>` |

## Single-purpose tools (binaries / pipx)

| Tool | Domain | Knowledge doc | Companion native probe |
|---|---|---|---|
| `arjun` | hidden-parameter discovery (large wordlists) | `api_and_protocols.md` | `native/param_probe.py` |
| `xsrfprobe` | CSRF scanning | `web_infra.md` | `native/csrf_probe.py` |
| `subzy` | subdomain takeover | `cloud_and_infra.md` | — |
| `subfinder` | subdomain enumeration (in-scope only) | `recon_and_fingerprinting.md` | — |
| `httpx` | live-host / tech probing at scale | `recon_and_fingerprinting.md` | `native/http_recon.py` (depth) |
| `katana` | crawler / endpoint discovery | `api_and_protocols.md` | — |
| `naabu` | fast port discovery | `recon_and_fingerprinting.md` | `native/port_scan.py` |
| `ffuf` / `feroxbuster` | content / directory discovery | `recon_and_fingerprinting.md` | — |
| `graphw00f` | GraphQL engine fingerprint | `modern_stack.md` | `native/graphql_probe.py` |
| `scoutsuite` | multi-cloud posture (AWS/GCP/Azure) | `cloud_and_infra.md` | — |
| `prowler` | cloud (esp. AWS) posture audit | `cloud_and_infra.md` | — |
| `gitleaks` / `trufflehog`* | secret scanning breadth / liveness | `secrets_and_supply_chain.md` | `native/secret_scan.py` |

\* `trufflehog` is AGPL — flagged, not installed by default (see SKILL.md §2).

## Scope discipline

`subfinder`/`katana`/`naabu`/`ffuf`/`nuclei` and the cloud auditors reach beyond a
single authorized URL. An authorized URL does **not** authorize its whole domain,
subdomains, or cloud account — confirm scope against `config/authorized-targets.yaml`
and the agent's authorization gate before running any breadth/enumeration tool.
