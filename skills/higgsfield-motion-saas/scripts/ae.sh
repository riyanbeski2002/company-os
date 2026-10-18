#!/bin/bash
# Run an ExtendScript file inside After Effects and wait for its result file.
#
#   ae.sh <script.jsx> <out.txt> [config-json | @config.json]
#
# Placeholders replaced in the script before it runs:
#   __OUT__     absolute path of <out.txt>        (SM.run writes its log there)
#   __LIB__     absolute path of saas_motion.jsx  (load with $.evalFile(new File("__LIB__")))
#   __CONFIG__  the JSON you pass (a JS literal), default null
#
# Why a result file: DoScriptFile's return value is unreliable (often "0", and
# dropped while AE renders), so every script writes its result to disk and we poll.
# Env: AE_APP (app name, auto-detected), AE_TIMEOUT (seconds, default 180).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TPL="$1"; OUT="$2"; CFG="${3:-null}"
LIB="$HERE/saas_motion.jsx"
TIMEOUT="${AE_TIMEOUT:-180}"

if [ -z "${AE_APP:-}" ]; then
  # newest installed After Effects, e.g. "Adobe After Effects 2026"
  APP_PATH="$(ls -d /Applications/Adobe\ After\ Effects\ */Adobe\ After\ Effects\ 20[0-9][0-9].app 2>/dev/null | sort | tail -1)"
  AE_APP="$(basename "${APP_PATH:-Adobe After Effects 2026.app}" .app)"
fi

case "$CFG" in @*) CFG="$(cat "${CFG#@}")" ;; esac
OUT="$(python3 -c 'import os,sys;print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$OUT")"
RUN="$(mktemp -t ae_run).jsx"

python3 - "$TPL" "$RUN" "$OUT" "$LIB" "$CFG" <<'PY'
import sys
tpl, run, out, lib, cfg = sys.argv[1:6]
s = open(tpl, encoding="utf-8").read()
s = s.replace("__CONFIG__", cfg).replace("__OUT__", out).replace("__LIB__", lib)
open(run, "w", encoding="utf-8").write(s)
PY

rm -f "$OUT"
osascript -e "tell application \"$AE_APP\" to DoScriptFile POSIX file \"$RUN\"" >/dev/null 2>&1
for _ in $(seq 1 $((TIMEOUT * 2))); do [ -f "$OUT" ] && break; sleep 0.5; done
if [ ! -f "$OUT" ]; then
  echo "ae.sh: no result after ${TIMEOUT}s from \"$AE_APP\" — AE may be busy rendering, showing a modal dialog, or the script threw before SM.run." >&2
  echo "       Inspect $RUN, or run it from File > Scripts > Run Script File." >&2
  exit 1
fi
sleep 0.2
# ExtendScript writes CR line endings; normalise so grep/head work later.
python3 -c 'import sys;p=sys.argv[1];d=open(p,"rb").read().replace(b"\r\n",b"\n").replace(b"\r",b"\n");open(p,"wb").write(d)' "$OUT"
cat "$OUT"
