#!/bin/zsh
# Compile the Swift helpers once (macOS, Xcode command-line tools): encode (frames → H.264), mux (video + audio), extract (video → frames).
HERE="${0:A:h}"; mkdir -p "$HERE/bin"
for t in encode mux extract; do
  if [ ! -x "$HERE/bin/$t" ] || [ "$HERE/$t.swift" -nt "$HERE/bin/$t" ]; then
    swiftc -O -suppress-warnings "$HERE/$t.swift" -o "$HERE/bin/$t" 2>&1 | tail -5
  fi
  [ -x "$HERE/bin/$t" ] && echo "ok  $HERE/bin/$t" || echo "FAILED $t"
done
