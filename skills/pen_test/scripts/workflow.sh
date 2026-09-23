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
#   presets: recon | webapp | api | owasp
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
echo "=== workflow: $PRESET  depth=$DEPTH  target=$TARGET ==="
echo "    output -> $OUT   passthrough -> ${PASS[*]:-(none)}"
echo

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

recon_stage() {
  run recon http_recon.py "$TARGET"
  [ "$DEPTH" != "quick" ] && run params param_probe.py -u "$TARGET"
}

case "$PRESET" in
  recon)
    recon_stage
    run ports port_scan.py "$(echo "$TARGET" | sed -E 's#https?://##; s#/.*##; s#:.*##')"
    ;;
  webapp)
    recon_stage
    run cors     cors_probe.py     "$TARGET"
    run redirect redirect_probe.py -u "$TARGET" --param url
    run csrf     csrf_probe.py     recon --url "$TARGET"
    echo; echo "=== targeted steps (pick the param/endpoint, then run) — see knowledge/workflows.md ==="
    manual "SQLi:  $PY native/sqli_probe.py -u '$TARGET' --param <p>   (knowledge/sql_injection.md)"
    manual "XSS:   $PY native/xss_probe.py  -u '$TARGET' --param <p>   (knowledge/xss.md)"
    manual "IDOR:  $PY native/idor_probe.py diff --url '<obj>/{id}' --a-bearer .. --b-bearer ..  (idor_and_authz.md)"
    manual "Auth:  $PY native/jwt_tool.py decode <token>              (authn_jwt_session.md)"
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
    manual "A03 Injection -> sqli_probe.py / xss_probe.py / ssrf_probe.py (per-param)"
    manual "A04 Insecure Design -> business-logic via repeater.py race/diff (idor_and_authz.md)"
    manual "A05 Security Misconfig -> http_recon.py (done above: headers/exposed artifacts)"
    manual "A06 Vulnerable Components -> trivy/grype (secrets_and_supply_chain.md); npx confusion"
    manual "A07 Auth Failures -> jwt_tool.py; login/session (authn_jwt_session.md, oauth_oidc_sso.md)"
    manual "A08 Integrity Failures -> deserialization/supply-chain (modern_stack.md, secrets_and_supply_chain.md)"
    manual "A09 Logging/Monitoring -> review-only (out of active-probe scope)"
    manual "A10 SSRF -> ssrf_probe.py (done partially if url params found)"
    ;;
  *) echo "unknown preset '$PRESET' (recon|webapp|api|owasp)"; exit 1;;
esac

echo
echo "Every finding above is a CANDIDATE. Confirm it (counter-evidence + PoC) and calibrate"
echo "severity per knowledge/finding_validation.md before it counts. Full outputs in $OUT"
