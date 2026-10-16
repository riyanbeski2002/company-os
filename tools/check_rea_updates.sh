#!/bin/bash
# Weekly upstream-update check for morluto/rea — Riyan's "most important one,"
# explicitly requires at-least-weekly checking (see its capability-registry
# entry). Checks only; never auto-merges, since rea is still trust-tier T3
# (real flagged-stars caveat — see the registry entry's comment).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$REPO_ROOT/external/morluto-rea"
LOG="$REPO_ROOT/.company/handoffs/rea-update-checks.log"

if [ ! -d "$DEST/.git" ]; then
  echo "morluto-rea not cloned at $DEST — run tools/sync_external_capabilities.py morluto-rea first"
  exit 1
fi

cd "$DEST"
LOCAL=$(git rev-parse HEAD)
git fetch origin --quiet
REMOTE=$(git rev-parse origin/HEAD 2>/dev/null || git rev-parse origin/main 2>/dev/null || git rev-parse origin/master 2>/dev/null)

mkdir -p "$(dirname "$LOG")"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "[$TS] up to date ($LOCAL)" | tee -a "$LOG"
else
  echo "[$TS] UPDATE AVAILABLE: local=$LOCAL remote=$REMOTE — review before pulling (shallow clone, re-run tools/sync_external_capabilities.py morluto-rea to update, or git -C $DEST log HEAD..origin/HEAD to see what changed first)" | tee -a "$LOG"
fi
