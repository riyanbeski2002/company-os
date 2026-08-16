#!/usr/bin/env bash
# Materialize the expense-demo fixture as a standalone git repo.
# Disposable and idempotent: re-running it gives a clean slate, which is what
# makes the V1 Definition of Done re-runnable rather than a one-time claim.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../fixtures/expense-demo" && pwd)"
DEST="${1:-$HOME/dev/expense-demo}"

if [[ -e "$DEST" ]]; then
  echo "removing existing $DEST" >&2
  rm -rf "$DEST"
fi

mkdir -p "$DEST"
cp -R "$SRC"/. "$DEST"/

cd "$DEST"
cat > .gitignore <<'EOF'
__pycache__/
*.pyc
EOF

cat > CLAUDE.md <<'EOF'
# expense-demo

Small dependency-free Python app used as the Company OS fixture.

- `services/auth/` — users and roles
- `api/approvals/` — expense submission and listing
- `web/` — client surface
- `tests/` — stdlib unittest

Run the suite: `python3 -m unittest discover -q tests`

Authoritative operational state for work in progress lives in `.company/`,
not in this file. Events in `.company/events/events.jsonl` are the source of
truth; `.company/tasks/*.json` are a derived view.
EOF

git init -q
git add -A
git -c user.email=company-os@local -c user.name="Company OS" \
    commit -q -m "expense-demo fixture: users, roles, expenses, tests"

echo "$DEST"
