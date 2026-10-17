#!/bin/bash
# Render one comp of a SAVED project with aerender (renders the .aep on disk — save in AE first).
#   render.sh <project.aep> "<Comp name>" <out.mp4|out.mov> [output-module-template]
# Default template: "H.264 - Match Render Settings - 15 Mbps" (AE's built-in H.264; no ffmpeg needed).
# Other useful built-ins: "H.264 - Match Render Settings - 40 Mbps", "High Quality" (.mov), "Lossless".
set -eu
AEP="$1"; COMP="$2"; OUT="$3"; OM="${4:-H.264 - Match Render Settings - 15 Mbps}"
AER="$(ls -d /Applications/Adobe\ After\ Effects\ 20[0-9][0-9]/aerender 2>/dev/null | sort | tail -1)"
[ -x "$AER" ] || { echo "render.sh: aerender not found" >&2; exit 1; }
mkdir -p "$(dirname "$OUT")"; rm -f "$OUT"
"$AER" -project "$AEP" -comp "$COMP" -RStemplate "Best Settings" -OMtemplate "$OM" -output "$OUT" > "${OUT%.*}.aerender.log" 2>&1 || true
if [ -s "$OUT" ]; then echo "$OUT"; else echo "render.sh: no output, see ${OUT%.*}.aerender.log" >&2; tail -20 "${OUT%.*}.aerender.log" >&2; exit 1; fi
