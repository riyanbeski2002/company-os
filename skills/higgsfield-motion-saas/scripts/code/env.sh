# Source this: finds node (22+), a Chromium browser and python deps for the code pipeline.  source scripts/code/env.sh
for n in "$NODE" "$(command -v node)" "/Users/$USER/Library/Application Support/Logi/LogiPluginService/PluginHosts/node22/node/bin/node" /opt/homebrew/bin/node /usr/local/bin/node; do
  [ -n "$n" ] && [ -x "$n" ] && "$n" -e 'process.exit(+process.versions.node.split(".")[0] >= 21 ? 0 : 1)' 2>/dev/null && { export NODE="$n"; break; }
done
if [ -z "$HFT_BROWSER" ]; then
  for b in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
           "/Applications/Chromium.app/Contents/MacOS/Chromium" "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
           "/Applications/Yandex.app/Contents/MacOS/Yandex"; do [ -x "$b" ] && { export HFT_BROWSER="$b"; break; }; done
fi
echo "NODE=${NODE:-MISSING (need Node >= 21 with global fetch/WebSocket)}"
echo "HFT_BROWSER=${HFT_BROWSER:-MISSING (any Chromium-based browser)}"
python3 -c "import numpy, PIL" 2>/dev/null && echo "python: numpy+PIL ok" || echo "python: need numpy + Pillow (no scipy needed)"
