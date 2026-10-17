#!/bin/zsh
# Exact stills of a film page at given times + one labelled sheet you can open with Read.
#   stills.sh <page.html[?query]> <out_dir> t1,t2,...     e.g. stills.sh "film/index.html?only=s3" stills/s3 3.0,3.4,3.9
set -e
HERE="${0:A:h}"; source "$HERE/env.sh" >/dev/null
OUT="${2:A}"; rm -rf "$OUT"; mkdir -p "$OUT"
CAP_TMP="$OUT" "$NODE" "$HERE/capture.mjs" "$1" "$OUT" --stills "$3" 2>&1 | grep -v "^comp:" | tail -4
python3 "$HERE/sheet.py" "$OUT" "$OUT/sheet.jpg" --cols 3 --width 640
