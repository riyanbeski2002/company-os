#!/usr/bin/env bash
# Install Company OS so it is available in every project, not just this one.
#
# There is NO settings.json key that auto-loads a local plugin directory —
# `--plugin-dir` is the only CLI mechanism, and it does not help a session you
# started by hand. So discoverability is assembled from the three user-scope
# surfaces that ARE loaded everywhere:
#
#   ~/.claude/agents/    symlinked role definitions  -> `claude --agent company-pm`
#   ~/.claude/settings.json hooks (absolute paths)   -> ownership + branch guards
#   ~/.claude/CLAUDE.md  a short pointer             -> Claude knows it exists
#
# Idempotent, backs up what it edits, and prints every change.
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

# --- 2. agents, so --agent works in any directory ----------------------------
mkdir -p "$CLAUDE_DIR/agents"
linked=0
for src in "$ROOT"/agents/*.md; do
  dst="$CLAUDE_DIR/agents/$(basename "$src")"
  if [[ -L "$dst" && "$(readlink "$dst")" == "$src" ]]; then continue; fi
  if [[ -e "$dst" && ! -L "$dst" ]]; then
    echo "  agents    SKIPPED $(basename "$dst") — a real file is already there"
    continue
  fi
  ln -sfn "$src" "$dst"
  linked=$((linked + 1))
done
echo "  agents    $(ls "$ROOT"/agents/*.md | wc -l | tr -d ' ') linked into $CLAUDE_DIR/agents ($linked new)"

# --- 3. hooks + CLAUDE.md pointer -------------------------------------------
python3 - "$SETTINGS" "$ROOT" "$CLAUDE_DIR/CLAUDE.md" <<'PY'
import json, shutil, sys
from pathlib import Path

settings_path, root, claude_md = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
settings_path.parent.mkdir(parents=True, exist_ok=True)

data = {}
if settings_path.exists():
    shutil.copy(settings_path, str(settings_path) + ".bak-company-os")
    data = json.loads(settings_path.read_text(encoding="utf-8") or "{}")

# `pluginDirectories` is not a real setting. An earlier version of this script
# wrote it and it silently did nothing — agents were not discoverable at all.
if data.pop("pluginDirectories", None) is not None:
    print("  settings  removed bogus 'pluginDirectories' key (never did anything)")

def hook(event, matcher, script):
    return (event, {
        **({"matcher": matcher} if matcher else {}),
        "hooks": [{"type": "command",
                   "command": f'python3 "{root}/hooks/{script}"'}],
    })

wanted = [
    hook("PreToolUse", "Write|Edit|NotebookEdit|MultiEdit", "guard_paths.py"),
    hook("PreToolUse", "Bash", "protect_branches.py"),
    hook("PreToolUse", "Read|Grep", "guard_secrets.py"),
    hook("SessionEnd", None, "emit_exit.py"),
]

hooks = data.setdefault("hooks", {})
added = 0
for event, entry in wanted:
    bucket = hooks.setdefault(event, [])
    cmd = entry["hooks"][0]["command"]
    if any(cmd == h.get("command")
           for existing in bucket for h in existing.get("hooks", [])):
        continue
    bucket.append(entry)
    added += 1

settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
print(f"  hooks     {added} registered in {settings_path.name} "
      f"(guards are inert unless $COMPANY_TASK is set)")

# A short pointer in the global CLAUDE.md is what makes a session in ANY repo
# aware Company OS exists. Kept deliberately small: this file is re-read on
# every turn of every session.
POINTER_START = "<!-- company-os:start -->"
POINTER_END = "<!-- company-os:end -->"
POINTER = f"""{POINTER_START}
# Company OS

An organisational layer for delivering work with evidence. Installed at
`{root}`. The `company` CLI is on PATH.

**Use it when** a task is big enough to need more than one worker, needs an
independent review, or touches something risky (auth, permissions, payments,
migrations, secrets). For a one-file change, just do the work.

- Is this repo onboarded? `.company/` exists at the repo root.
- To onboard one: `company onboard` (init + detect + baseline + doctor, stops at the first real failure)
- To run the loop: `claude --agent company-pm`, then give it one outcome.
- Read `{root}/README.md` before the first run on a live repo.

`.company/events/events.jsonl` is the authoritative state; `.company/tasks/*.json`
are a derived view. Never hand-edit either.
{POINTER_END}"""

existing = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
if POINTER_START in existing:
    head, _, rest = existing.partition(POINTER_START)
    _, _, tail = rest.partition(POINTER_END)
    claude_md.write_text(head + POINTER + tail, encoding="utf-8")
    print("  CLAUDE.md pointer updated")
else:
    claude_md.write_text((existing.rstrip() + "\n\n" if existing else "") + POINTER + "\n",
                         encoding="utf-8")
    print("  CLAUDE.md pointer added (every session now knows Company OS exists)")
PY

# --- 4. sanity check ---------------------------------------------------------
echo
echo "Checking the install..."
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

Done. Verify agent discovery from any directory with:

  claude --agent company-pm -p "say ok" </dev/null

To onboard a repo:

  cd /path/to/your/repo
  company onboard

Then give the PM one outcome:

  claude --agent company-pm
EOF
