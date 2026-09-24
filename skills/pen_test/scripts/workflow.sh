#!/bin/bash
# workflow.sh — named one-shot pentest workflows that chain the native probes.
#
# Packages our probes + knowledge into the way engagements are actually scoped
# (OWASP Top 10 / API security / web-app black-box), with quick|standard|deep
# depth (modelled on Strix's scan modes). It runs the AUTOMATABLE steps —
# recon, posture, discovery — itself, then prints the precise targeted commands
# for the per-parameter steps that need a human/agent to pick the injection
# point. This is a guided workflow, not a fire-and-forget scanner: the manual
# steps are manual on purpose (that's where the real findings are).
#
# Usage:
#   workflow.sh <preset> <target-url> [--depth quick|standard|deep] [-- <probe passthrough args>]
#   presets: recon | infra | webapp | api | owasp
#   passthrough (after --): shared _httpcore flags, e.g. -H "Cookie: s=..." --proxy http://127.0.0.1:8080
#
# Examples:
#   workflow.sh recon  https://target
#   workflow.sh webapp https://target --depth standard -- -H "Cookie: session=abc"
#   workflow.sh api    https://api.target/graphql --depth deep
#
# AUTHORIZATION: runs live probes — authorized targets only (see agents/pen_test.md).
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="python3"; [ -x "$SKILL_DIR/.venv/bin/python" ] && PY="$SKILL_DIR/.venv/bin/python"
N="$SKILL_DIR/native"

PRESET="${1:-}"; TARGET="${2:-}"
[ -z "$PRESET" ] || [ -z "$TARGET" ] && { sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 1; }
shift 2
DEPTH="standard"; PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --depth) DEPTH="$2"; shift 2;;
    --) shift; PASS=("$@"); break;;
    *) PASS+=("$1"); shift;;
  esac
done

OUT="$(mktemp -d)/wf"; mkdir -p "$OUT"
EV="$OUT/evidence"; mkdir -p "$EV"   # structured findings sink -> report.py (mandatory deliverable)
echo "=== workflow: $PRESET  depth=$DEPTH  target=$TARGET ==="
echo "    output -> $OUT   evidence -> $EV   passthrough -> ${PASS[*]:-(none)}"
echo

runx() {  # like run(), but WITHOUT the _httpcore passthrough (for non-HTTP infra tools)
  local label="$1"; shift
  local log="$OUT/${label}.txt"
  echo "--- $label ---"
  "$PY" "$N/$1" "${@:2}" >"$log" 2>&1
  grep -E "\[(critical|high|medium|low)\]|OPEN|VULNERABLE|CVE-|no unauth" "$log" | head -20
  echo "    (full: $log)"
}

run() {  # label  probe.py  args...
  local label="$1"; shift
  local log="$OUT/${label}.txt"
  echo "--- $label ---"
  "$PY" "$N/$1" "${@:2}" ${PASS[@]+"${PASS[@]}"} >"$log" 2>&1
  # surface the probe's own verdict/finding lines, keep full output in the file
  grep -E "\[!\]|\[\?\]|CANDIDATE|CONFIRMED|REFLECTED|EXPOSED|\[(critical|high|medium)\]|MATCH|priority" "$log" | head -12
  echo "    (full: $log)"
}

manual() { echo "  [ ] $*"; }

HOST="$(echo "$TARGET" | sed -E 's#https?://##; s#/.*##; s#:.*##')"

content_discovery() {
  # Owned recon lists a fixed high-signal path set; wordlist-driven discovery is a
  # continuously-updated feed (own-stable / depend-on-current). Wire the tools in when present.
  if command -v katana >/dev/null 2>&1; then
    echo "--- content-discovery: katana (JS-aware crawl) ---"
    katana -u "$TARGET" -jc -silent -d 2 2>/dev/null | tee "$OUT/katana.txt" | head -20
    echo "    (full: $OUT/katana.txt)"
  fi
  if command -v ffuf >/dev/null 2>&1; then
    local wl="${SECLISTS_WORDLIST:-/usr/share/seclists/Discovery/Web-Content/common.txt}"
    if [ -f "$wl" ]; then
      echo "--- content-discovery: ffuf (dir/file brute, $wl) ---"
      ffuf -u "$TARGET/FUZZ" -w "$wl" -mc 200,204,301,302,307,401,403 -s 2>/dev/null \
        | tee "$OUT/ffuf.txt" | head -20
      echo "    (full: $OUT/ffuf.txt)"
    else
      echo "  [i] ffuf present but no wordlist at $wl — set SECLISTS_WORDLIST=/path/to/list.txt"
    fi
  fi
  command -v katana >/dev/null 2>&1 || command -v ffuf >/dev/null 2>&1 || \
    echo "  [i] no content-discovery tool found — install ffuf/katana (scripts/install_extra_tools.sh)"
}

recon_stage() {
  run recon http_recon.py "$TARGET"
  [ "$DEPTH" != "quick" ] && run params param_probe.py -u "$TARGET"
  [ "$DEPTH" = "deep" ] && content_discovery
  echo "  [i] if the backend is hidden (SPA/TanStack/BFF): recover real endpoints via bundle/"
  echo "      source maps/live capture — see knowledge/backend_discovery.md"
}

case "$PRESET" in
  recon)
    recon_stage
    run ports port_scan.py "$HOST"
    ;;
  infra)
    # network/infra VA: discovery -> native unauth/misconfig + TLS -> engine CVE depth
    echo "--- host: $HOST ---"
    runx ports    port_scan.py "$HOST" --ports "1-1024,1433,2375,2376,3306,3389,5432,5601,5900,6379,6380,8443,9200,10250,10255,11211,15672,27017"
    runx services service_probe.py "$HOST" --snmp --evidence-dir "$EV"
    runx tls      tls_probe.py "$HOST" --port 443 --evidence-dir "$EV"
    if command -v nmap >/dev/null 2>&1; then
      echo "--- nmap -sV --script vuln (service/version + NSE CVE feed) ---"
      nmap -sV --script vuln -Pn "$HOST" -oN "$OUT/nmap.txt" 2>/dev/null \
        | grep -E "open|VULNERABLE|CVE-" | head -30
      echo "    (full: $OUT/nmap.txt)"
    else
      echo "  [i] nmap not installed — service/version + NSE vuln depth skipped (scripts/install_extra_tools.sh)"
    fi
    if command -v nuclei >/dev/null 2>&1; then
      echo "--- nuclei -tags network (continuously-updated network CVE feed) ---"
      nuclei -u "$HOST" -tags network -silent 2>/dev/null | tee "$OUT/nuclei-net.txt" | head -20
      echo "    (full: $OUT/nuclei-net.txt)"
    else
      echo "  [i] nuclei not installed — network CVE templates skipped"
    fi
    echo; echo "=== infra follow-ups — see knowledge/network_va.md ==="
    manual "SMB depth: nmap --script smb-enum-shares,smb-vuln-* -p139,445 $HOST"
    manual "SNMP walk: snmpwalk -v2c -c public $HOST  (if community valid above)"
    manual "TLS depth: testssl.sh / sslscan $HOST:443  (Heartbleed/ROBOT/DH-modulus)"
    manual "Default creds on exposed DBs: bounded, lockout-aware, authorized-only (credential_attacks.md)"
    ;;
  webapp)
    recon_stage
    run cors     cors_probe.py     "$TARGET"
    run redirect redirect_probe.py -u "$TARGET" --param url
    run csrf     csrf_probe.py     recon --url "$TARGET"
    echo; echo "=== targeted steps (pick the param/endpoint, then run) — see knowledge/workflows.md ==="
    manual "SQLi:  $PY native/sqli_probe.py -u '$TARGET' --param <p> --evidence-dir '$EV'   (sql_injection.md)"
    manual "XSS:   $PY native/xss_probe.py  -u '$TARGET' --param <p>   (knowledge/xss.md)"
    manual "SSTI:  $PY native/ssti_probe.py -u '$TARGET' --param <p> --escalate --evidence-dir '$EV'   (rce.md)"
    manual "CmdInj:$PY native/cmdi_probe.py -u '$TARGET' --param <p> --oob-host <h> --evidence-dir '$EV'   (rce.md)"
    manual "LFI:   $PY native/traversal_probe.py -u '$TARGET' --param <p> --evidence-dir '$EV'   (backend_discovery.md)"
    manual "Upload:$PY native/upload_probe.py -u '<upload>' --field <f> --evidence-dir '$EV'"
    manual "IDOR:  $PY native/idor_probe.py diff --url '<obj>/{id}' --a-bearer .. --b-bearer ..  (idor_and_authz.md)"
    manual "Auth wall: $PY native/auth_probe.py bypass -u '<login>' --location form|json  (auth_bypass.md)"
    manual "Creds: $PY native/auth_probe.py spray/brute/enum -u '<login>' ...  (credential_attacks.md)"
    manual "Token: $PY native/jwt_tool.py decode <token>              (authn_jwt_session.md)"
    manual "Biz-logic race: $PY native/repeater.py race -u '<state-change>' -X POST -n 30  (idor_and_authz.md)"
    ;;
  api)
    recon_stage
    run graphql graphql_probe.py "$TARGET"
    run cors    cors_probe.py    "$TARGET"
    echo; echo "=== targeted steps (API) — see knowledge/api_and_protocols.md ==="
    manual "BOPLA/mass-assignment: send extra privileged fields (role,isAdmin) via repeater.py"
    manual "BOLA/IDOR: idor_probe.py diff on each object endpoint (two accounts)"
    manual "SQLi/NoSQLi on filter/search params: sqli_probe.py --location json (modern_stack.md for NoSQL)"
    manual "XXE: $PY native/xxe_probe.py -u '<xml-endpoint>' --json-flip '<json-body>' --evidence-dir '$EV'"
    manual "Cmd/SSTI/LFI on JSON fields: {cmdi,ssti,traversal}_probe.py --location json --param <f> --evidence-dir '$EV'"
    manual "Verb tampering + auth on each route (api_and_protocols.md)"
    ;;
  owasp)
    # OWASP Top 10 (2021) -> our tooling. Run the automatable, checklist the rest.
    recon_stage
    run cors     cors_probe.py     "$TARGET"
    run redirect redirect_probe.py -u "$TARGET" --param url
    run graphql  graphql_probe.py  "$TARGET"
    echo; echo "=== OWASP Top 10 (2021) coverage map — see knowledge/workflows.md ==="
    manual "A01 Broken Access Control -> idor_probe.py diff; BFLA/BOPLA (idor_and_authz.md, api_and_protocols.md)"
    manual "A02 Cryptographic Failures -> secret_scan.py; TLS/cookie flags (secrets_and_supply_chain.md)"
    manual "A03 Injection -> sqli_probe.py / xss_probe.py / ssrf_probe.py / ssti_probe.py / cmdi_probe.py / traversal_probe.py / xxe_probe.py (per-param, --evidence-dir '$EV')"
    manual "A04 Insecure Design -> business-logic via repeater.py race/diff (idor_and_authz.md)"
    manual "A05 Security Misconfig -> http_recon.py (done above: headers/exposed artifacts)"
    manual "A06 Vulnerable Components -> trivy/grype (secrets_and_supply_chain.md); npx confusion"
    manual "A07 Auth Failures -> auth_probe.py bypass/spray/brute/enum + jwt_tool.py (auth_bypass.md, credential_attacks.md)"
    manual "A08 Integrity Failures -> deserialization/supply-chain (modern_stack.md, secrets_and_supply_chain.md)"
    manual "A09 Logging/Monitoring -> review-only (out of active-probe scope)"
    manual "A10 SSRF -> ssrf_probe.py (done partially if url params found)"
    ;;
  *) echo "unknown preset '$PRESET' (recon|infra|webapp|api|owasp)"; exit 1;;
esac

echo
echo "Every finding above is a CANDIDATE. Confirm it (counter-evidence + PoC) and calibrate"
echo "severity per knowledge/finding_validation.md before it counts. Full outputs in $OUT"
echo
echo "=== deliverable (mandatory) ==="
if [ -s "$EV/findings.jsonl" ]; then
  "$PY" "$N/report.py" "$EV" --title "$PRESET workflow — $TARGET"
else
  echo "  no structured findings captured yet — run the targeted steps above with"
  echo "  --evidence-dir '$EV', then: $PY native/report.py '$EV'"
fi
