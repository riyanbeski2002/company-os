#!/bin/bash
# Installs the pen_test toolbox-expansion tools registered 2026-09-17
# (config/capability-registry.yaml). These are single CLI binaries, not
# source repos with methodology content worth vendoring like Strix/sqlmap/
# h4cker — installed via the host's own package manager instead. Best-effort:
# prints what it tried and what actually succeeded, doesn't hard-fail the
# whole script on one missing package manager.
set -uo pipefail

ok() { command -v "$1" >/dev/null 2>&1 && echo "  [present] $1" || echo "  [MISSING] $1 — see note below"; }

echo "=== Installing via Homebrew (macOS) ==="
if command -v brew >/dev/null 2>&1; then
  brew install gitleaks trivy grype syft semgrep || true
  # network/infra VA depth engines: nmap (service/version + NSE vuln scripts) and
  # sslscan (companion to native/tls_probe.py). See knowledge/network_va.md.
  brew install nmap sslscan || true
else
  echo "  brew not found — install these manually, see https://brew.sh"
fi

echo "=== Installing via pipx (Python tools) ==="
if command -v pipx >/dev/null 2>&1; then
  pipx install checkov || true
  pipx install prowler || true
  pipx install arjun || true          # hidden-param discovery (companion to native/param_probe.py, larger wordlists)
  pipx install xsrfprobe || true      # CSRF scanner (companion to native/csrf_probe.py)
  pipx install scoutsuite || true     # multi-cloud posture (AWS/GCP/Azure) -> knowledge/cloud_and_infra.md
  pipx install graphw00f || true      # GraphQL engine fingerprint (companion to native/graphql_probe.py)
else
  echo "  pipx not found — 'brew install pipx' first, or pip install --user arjun xsrfprobe scoutsuite graphw00f checkov prowler"
fi

echo "=== ProjectDiscovery recon suite + Go single-purpose tools ==="
# subfinder/httpx/katana/naabu = the recon pipeline referenced in
# knowledge/recon_and_fingerprinting.md; subzy = subdomain takeover
# (knowledge/cloud_and_infra.md); ffuf/feroxbuster = content discovery.
if command -v brew >/dev/null 2>&1; then
  brew install subfinder httpx katana naabu ffuf feroxbuster nuclei || true
fi
if command -v go >/dev/null 2>&1; then
  go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest || true
  go install github.com/projectdiscovery/httpx/cmd/httpx@latest || true
  go install github.com/projectdiscovery/katana/cmd/katana@latest || true
  go install github.com/projectdiscovery/naabu/v2/cmd/naabu@latest || true
  go install github.com/ffuf/ffuf/v2@latest || true
  go install github.com/PentestPad/subzy@latest || true
else
  echo "  go not found — install Go, or use the brew line above, for the ProjectDiscovery suite + subzy"
fi

echo "=== jwt-cli (Rust, via cargo if available, else Homebrew tap) ==="
if command -v cargo >/dev/null 2>&1; then
  cargo install jwt-cli || true
elif command -v brew >/dev/null 2>&1; then
  brew install mike-engel/jwt-cli/jwt-cli || echo "  tap install failed — check https://github.com/mike-engel/jwt-cli for current install instructions"
fi

echo "=== OWASP ZAP — GUI cask install is NOT what you want for headless/CLI scanning ==="
echo "  Use the official Docker image instead: docker pull zaproxy/zap-stable"
echo "  Then: docker run -v \$(pwd):/zap/wrk/:rw zaproxy/zap-stable zap-baseline.py -t <authorized-url>"

echo
echo "=== Verification ==="
for t in gitleaks trivy grype syft semgrep checkov prowler jwt cargo docker \
         arjun xsrfprobe scout graphw00f subfinder httpx katana naabu ffuf feroxbuster subzy nuclei \
         nmap sslscan; do ok "$t"; done
echo
echo "Anything MISSING above needs manual install — see each tool's registry"
echo "entry (config/capability-registry.yaml) for its source repo."
