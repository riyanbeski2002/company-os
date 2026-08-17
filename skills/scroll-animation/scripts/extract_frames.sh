#!/usr/bin/env bash
# Deterministic frame extraction for the frame-sequenced-video pipeline.
#
# This exists because a skill that just TELLS an agent "run ffmpeg with these
# flags" is a prompt wearing a skill's name — the agent retypes the command
# from memory every time, with every chance to get the flags subtly wrong.
# A script the skill actually ships is the thing itself: same output, no
# re-derivation, every time.
#
# Usage: extract_frames.sh <input-video> <output-dir> [fps]
set -euo pipefail

INPUT="${1:?usage: extract_frames.sh <input-video> <output-dir> [fps]}"
OUTDIR="${2:?usage: extract_frames.sh <input-video> <output-dir> [fps]}"
FPS="${3:-30}"

if [[ ! -f "$INPUT" ]]; then
  echo "error: input video not found: $INPUT" >&2
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "error: ffmpeg not found on PATH — install it before running this pipeline" >&2
  exit 1
fi

mkdir -p "$OUTDIR"
ffmpeg -y -loglevel error -i "$INPUT" -vf "fps=${FPS}" "${OUTDIR}/frame-%04d.png"

count=$(find "$OUTDIR" -name 'frame-*.png' | wc -l | tr -d ' ')
echo "extracted ${count} frames at ${FPS}fps into ${OUTDIR}"
