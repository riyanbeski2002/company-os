#!/usr/bin/env bash
# Install Company OS for everyday use.
#
# Idempotent and conservative: it backs up settings.json before touching it,
# never removes anything it did not add, and prints what it changed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CLAUDE_DIR/settings.json"

echo "Company OS → $ROOT"

# --- 1. the CLI on PATH ------------------------------------------------------
SHELL_RC=""
case "${SHELL:-}" in
  *zsh)  SHELL_RC="$HOME/.zshrc" ;;
  *bash) SHELL_RC="$HOME/.bashrc" ;;
esac

LINE="export PATH=\"$ROOT/bin:\$PATH\"  # company-os"
if [[ -n "$SHELL_RC" ]]; then
  if grep -qF "# company-os" "$SHELL_RC" 2>/dev/null; then
    echo "  PATH      already configured in $SHELL_RC"
  else
    printf '\n%s\n' "$LINE" >> "$SHELL_RC"
    echo "  PATH      added to $SHELL_RC (open a new shell, or: source $SHELL_RC)"
  fi
else
  echo "  PATH      unknown shell — add manually: $LINE"
fi

# --- 2. register the plugin so hooks load without --plugin-dir ---------------
python3 - "$SETTINGS" "$ROOT" <<'PY'
import json, shutil, sys
from pathlib import Path

settings_path, root = Path(sys.argv[1]), sys.argv[2]
settings_path.parent.mkdir(parents=True, exist_ok=True)

if settings_path.exists():
    shutil.copy(settings_path, str(settings_path) + ".bak-company-os")
    data = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
else:
    data = {}

dirs = data.setdefault("pluginDirectories", [])
if root in dirs:
    print("  plugin    already registered")
else:
    dirs.append(root)
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    print(f"  plugin    registered in {settings_path}")
    print(f"            (backup at {settings_path}.bak-company-os)")
PY

# --- 3. sanity check ---------------------------------------------------------
echo
echo "Checking the install..."
# Failure output is shown, not swallowed. Hiding it once already cost a
# debugging round: the suite reported FAILED with no way to see why, then
# passed on the next run.
if TEST_OUT="$(cd "$ROOT" && python3 -m unittest discover tests 2>&1)"; then
  echo "  tests     pass ($(echo "$TEST_OUT" | grep -o 'Ran [0-9]* tests' || echo 'ran'))"
else
  echo "  tests     FAILED — do not use this until they pass:"
  echo "$TEST_OUT" | grep -E "FAIL:|ERROR:|Ran |OK|FAILED" | sed 's/^/            /'
  exit 1
fi

"$ROOT/bin/company" --help >/dev/null 2>&1 \
  && echo "  cli       responds" \
  || { echo "  cli       broken"; exit 1; }

cat <<'EOF'

Done. To onboard a repo:

  cd /path/to/your/repo
  company init            # scaffold .company/
  company detect --write  # find the stack and a verify command
  company baseline        # record how it behaves BEFORE any work
  company doctor          # preflight — fix anything it flags

Then give the PM one outcome:

  claude --agent company-pm

Read README.md first if this is a live repo. In particular: Company OS never
touches your working tree, but it does create branches and worktrees.
EOF
