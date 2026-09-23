#!/bin/bash
# Maintains the small set of tools whose real value IS a continuously-updated
# feed/database, not static logic we could reasonably own ourselves:
#   - sqlmap: engine + tamper/technique scripts genuinely improve over time
#     (new WAF bypasses, new DBMS support) — cloned from source and kept
#     current via git pull, since it has no clean single-binary package on
#     most platforms.
#   - nuclei: the templates ARE the product — thousands of community/vendor
#     CVE templates, updated constantly. Binary installed via brew; templates
#     refreshed via nuclei's own updater.
#   - trivy: vulnerability DB is the product — refreshed via trivy's own
#     downloader, same reasoning.
#   - semgrep: rule registry auto-fetches per invocation (--config=auto /
#     --config=p/owasp-top-ten) — nothing to pre-clone, noted here so it's
#     not mistaken for something this script forgot.
#
# Run this before a real engagement, and periodically otherwise — these are
# living databases, a stale copy is actively misleading, not just outdated.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINES_DIR="$SKILL_DIR/engines"

# --- readiness check (read-only) -----------------------------------------
# `update_engines.sh --check` installs/clones NOTHING. It reports what the
# agent can actually rely on for THIS engagement — because the installs are
# best-effort (brew/go/pipx + GitHub egress) and silently no-op in a
# locked-down environment, so "the script ran" != "the tool is here".
run_check() {
  local present=0 missing=0
  _line() { printf "  %-14s %-9s %s\n" "$1" "$2" "$3"; }
  _bin() {  # name  "what it enables"
    if command -v "$1" >/dev/null 2>&1; then _line "$1" "present" "$2"; present=$((present+1))
    else _line "$1" "MISSING" "$2"; missing=$((missing+1)); fi
  }
  _clone() {  # dirname  entrypoint-relpath  "what it enables"
    local d="$ENGINES_DIR/$1"
    if [ -d "$d/.git" ] && [ -e "$d/$2" ]; then _line "$1" "present" "$3"; present=$((present+1))
    else _line "$1" "MISSING" "$3 — run update_engines.sh (no args)"; missing=$((missing+1)); fi
  }

  echo "=== pen_test readiness check (read-only; nothing installed) ==="
  echo
  echo "[native probes] (in-repo — need only Python + requests/pyjwt)"
  local py="python3"
  [ -x "$SKILL_DIR/.venv/bin/python" ] && py="$SKILL_DIR/.venv/bin/python"
  if "$py" -c "import requests, jwt" >/dev/null 2>&1; then
    _line "native/*.py" "ready" "using ${py#$SKILL_DIR/} — all 13 probes runnable"; present=$((present+1))
  else
    _line "native/*.py" "DEGRADED" "pip install -r native/requirements.txt (requests/pyjwt missing)"; missing=$((missing+1))
  fi
  echo
  echo "[cloned engines] (git-pull refreshed under engines/)"
  _clone sqlmap  sqlmap.py    "SQLi extraction depth  -> sql_injection.md"
  _clone smuggler smuggler.py "HTTP request smuggling -> web_infra.md"
  _clone Corsy    corsy.py    "CORS breadth           -> web_infra.md"
  _clone SSTImap  sstimap.py  "SSTI detect+exploit    -> ssrf_and_injection.md"
  echo
  echo "[feed engines] (value is a live database — refresh before engagement)"
  _bin nuclei  "CVE/template scanning (run: nuclei -update-templates)"
  _bin trivy   "dependency/container CVEs (run: trivy image --download-db-only)"
  _bin semgrep "static rules (self-updates per run via --config=auto)"
  echo
  echo "[utility toolbox] (install_extra_tools.sh; each is optional/companion)"
  _bin gitleaks    "secret scan (broader than native/secret_scan.py)"
  _bin subfinder   "subdomain discovery (scope-gated)"
  _bin httpx       "host probing/fingerprint"
  _bin katana      "crawler / endpoint discovery"
  _bin naabu       "fast port scan (beyond native/port_scan.py)"
  _bin ffuf        "content/param fuzzing"
  _bin feroxbuster "recursive content discovery"
  _bin subzy       "subdomain takeover"
  _bin arjun       "hidden-param wordlists (companion to param_probe.py)"
  _bin xsrfprobe   "CSRF scanning (companion to csrf_probe.py)"
  _bin graphw00f   "GraphQL engine fingerprint (companion to graphql_probe.py)"
  _bin scout       "multi-cloud posture (ScoutSuite) -> cloud_and_infra.md"
  _bin prowler     "AWS/Azure/GCP posture -> cloud_and_infra.md"
  _bin grype       "SCA vuln scan"
  _bin syft        "SBOM generation"
  _bin checkov     "IaC misconfig"
  _bin jwt         "jwt-cli (companion to native/jwt_tool.py)"
  _bin docker      "OWASP ZAP headless (zaproxy/zap-stable image)"
  echo
  echo "[network egress] (needed to clone/refresh the git + feed tools)"
  if command -v curl >/dev/null 2>&1 && curl -sfI -m 6 https://github.com >/dev/null 2>&1; then
    _line "github.com" "reachable" "clone/pull + go-install will work"
  elif command -v curl >/dev/null 2>&1; then
    _line "github.com" "BLOCKED" "offline/locked-down — rely only on what's already present above"
  else
    _line "github.com" "unknown" "curl not available to test egress"
  fi
  echo
  echo "Summary: $present present/ready, $missing missing/degraded."
  echo "Owned native probes need no network and cover the core classes; missing"
  echo "engines only limit the specific classes noted beside each. See engines/CATALOG.md."
  return 0
}

case "${1:-}" in
  --check|-c|check) run_check; exit $? ;;
  -h|--help) echo "Usage: update_engines.sh [--check]"; echo "  (no args) clone/refresh engines + feeds; --check reports readiness only"; exit 0 ;;
esac

mkdir -p "$ENGINES_DIR"

echo "=== sqlmap (cloned, kept current via git pull — no clean single-binary package) ==="
SQLMAP_DIR="$ENGINES_DIR/sqlmap"
if [ -d "$SQLMAP_DIR/.git" ]; then
  git -C "$SQLMAP_DIR" pull --ff-only origin master
else
  git clone --depth 50 https://github.com/sqlmapproject/sqlmap.git "$SQLMAP_DIR"
fi
echo "  sqlmap ready: python3 $SQLMAP_DIR/sqlmap.py --version"

# Wrapped single-technique engines: cloned (not reimplemented) because they are
# maintained tools whose evasion/technique surface improves over time and there
# is no clean binary package. Each covers a class our native/ probes DON'T (see
# engines/CATALOG.md for the domain->engine map). git-pull refreshed, deps
# installed on clone.
clone_engine() {  # name  repo_url  [pip?]
  local name="$1" url="$2" pipreq="${3:-}"
  local dir="$ENGINES_DIR/$name"
  echo "=== $name (cloned engine) ==="
  if [ -d "$dir/.git" ]; then
    git -C "$dir" pull --ff-only || echo "  (pull skipped)"
  else
    git clone --depth 20 "$url" "$dir" || { echo "  clone failed: $url"; return; }
  fi
  if [ -n "$pipreq" ] && [ -f "$dir/requirements.txt" ]; then
    pip install -q -r "$dir/requirements.txt" --break-system-packages 2>/dev/null \
      || pip install -q -r "$dir/requirements.txt" 2>/dev/null || echo "  (install deps for $name manually)"
  fi
  echo "  $name ready under $dir"
}

clone_engine smuggler https://github.com/defparam/smuggler.git         # HTTP request smuggling  -> web_infra.md
clone_engine Corsy     https://github.com/s0md3v/Corsy.git       pip   # CORS deep scan          -> web_infra.md
clone_engine SSTImap   https://github.com/vladko312/SSTImap.git  pip   # SSTI detect+exploit     -> ssrf_and_injection.md / modern_stack.md

echo "=== nuclei (binary + template database) ==="
if ! command -v nuclei >/dev/null 2>&1; then
  command -v brew >/dev/null 2>&1 && brew install nuclei || echo "  install nuclei manually: https://github.com/projectdiscovery/nuclei"
fi
command -v nuclei >/dev/null 2>&1 && nuclei -update-templates

echo "=== trivy (binary + vulnerability DB) ==="
if ! command -v trivy >/dev/null 2>&1; then
  command -v brew >/dev/null 2>&1 && brew install trivy || echo "  install trivy manually: https://github.com/aquasecurity/trivy"
fi
command -v trivy >/dev/null 2>&1 && trivy image --download-db-only

echo "=== semgrep (rule registry — self-updating per run, nothing to pre-fetch) ==="
if ! command -v semgrep >/dev/null 2>&1; then
  command -v brew >/dev/null 2>&1 && brew install semgrep || echo "  install semgrep manually: https://github.com/semgrep/semgrep"
fi
echo "  semgrep pulls current rules per invocation via --config=auto or --config=p/<ruleset>"

echo
echo "Done. Re-run this before any real engagement — these three are living"
echo "databases; a stale copy actively misreports what's actually current."
