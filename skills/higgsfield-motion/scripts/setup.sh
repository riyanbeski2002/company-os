#!/bin/bash
# higgsfield-motion setup: run once per machine (bash or zsh). Idempotent.
# Checks Node 22+, a Chromium browser, swiftc, afconvert; compiles scripts/*.swift into ${HFT_BIN:-~/.cache/higgsfield-motion/bin}.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="${HFT_BIN:-$HOME/.cache/higgsfield-motion/bin}"
mkdir -p "$BIN"
ok=1
NODE_MAJOR=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
if [ "$NODE_MAJOR" -ge 22 ] 2>/dev/null; then echo "node      ok ($(node -v))"; else echo "node      FAIL: need Node 22+ (global WebSocket), found ${NODE_MAJOR}"; ok=0; fi
BR="${HFT_BROWSER:-}"
if [ -z "$BR" ]; then
  for p in "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "/Applications/Chromium.app/Contents/MacOS/Chromium" "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"; do
    [ -x "$p" ] && BR="$p" && break
  done
fi
if [ -n "$BR" ]; then echo "browser   ok ($BR)"; else echo "browser   FAIL: install Brave/Chrome or set HFT_BROWSER"; ok=0; fi
command -v afconvert >/dev/null && echo "afconvert ok" || echo "afconvert missing (audio mastering to AAC needs it)"
if command -v swiftc >/dev/null; then
  for src in "$DIR"/*.swift; do
    name="$(basename "$src" .swift)"; out="$BIN/$name"
    if [ -x "$out" ] && [ "$out" -nt "$src" ]; then echo "swift     up-to-date $name"; continue; fi
    if swiftc -O "$src" -o "$out" 2>"$BIN/$name.log"; then echo "swift     built $name"; rm -f "$BIN/$name.log"; else echo "swift     FAIL $name (see $BIN/$name.log)"; ok=0; fi
  done
  xattr -dr com.apple.quarantine "$BIN" 2>/dev/null || true
else
  echo "swiftc    missing: xcode-select --install. Fallback: the shipped arm64 binary scripts/encode (encode only)"
fi
echo "bin dir:  $BIN   (use as \$B)"
[ "$ok" = 1 ] && echo "setup OK" || { echo "setup finished with problems"; exit 1; }
