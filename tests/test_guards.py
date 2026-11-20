"""Bash guardrails (§9, §12).

Both classes here exist because a real worker run tripped them:
- a reviewer's mutation-testing scratch dir (`rm -rf /tmp/rev101`) was wrongly
  blocked as a root delete;
- and the ownership hook, which only watches Write/Edit/NotebookEdit, could be
  bypassed entirely by a shell redirect.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

spec = importlib.util.spec_from_file_location(
    "protect_branches", HERE.parent / "hooks" / "protect_branches.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

WT = "/repo/.company/worktrees/TASK-1"
CROOT = "/repo/.company"


def blocked_by_rule(command: str) -> str | None:
    for pattern, label in guard.RULES:
        if pattern.search(command):
            return label
    return None


class TestDangerousCommands(unittest.TestCase):
    def test_blocks_force_push(self):
        self.assertIsNotNone(blocked_by_rule("git push --force origin task/1"))

    def test_blocks_protected_checkout(self):
        self.assertIsNotNone(blocked_by_rule("git checkout main"))

    def test_blocks_secret_commit(self):
        self.assertIsNotNone(blocked_by_rule("git add .env && git commit -m x"))

    def test_blocks_reading_secret_via_shell(self):
        """guard_secrets.py only covers the Read/Grep tools; `cat .env` is the
        same information exposure via Bash instead."""
        for cmd in ("cat .env", "head -20 secrets.yaml", "less config/secrets.json",
                    "tail -f .env.production"):
            self.assertIsNotNone(blocked_by_rule(cmd), cmd)

    def test_allows_ordinary_reads(self):
        for cmd in ("cat README.md", "head -5 CHANGELOG.md", "cat src/api/keys.py"):
            self.assertIsNone(blocked_by_rule(cmd), cmd)

    def test_blocks_worktree_removal(self):
        self.assertIsNotNone(blocked_by_rule("git worktree remove foo"))

    def test_allows_ordinary_work(self):
        for cmd in ("git add api/x.py && git commit -m 'work'",
                    "python3 -m unittest discover -q tests",
                    "git push origin task/101-expense-approval",
                    "git diff main..HEAD"):
            self.assertIsNone(blocked_by_rule(cmd), cmd)


class TestDestructiveDatabaseCommands(unittest.TestCase):
    """D-9: destroying a database is always refused, in every session."""

    def test_blocks(self):
        for cmd in ("supabase db reset",
                    "npx supabase db reset --linked",
                    "supabase stop --no-backup",
                    "dropdb myapp_dev",
                    "PGPASSWORD=x dropdb -h localhost app",
                    'psql "$DATABASE_URL" -c "DROP TABLE users;"',
                    "psql -c 'drop schema public cascade'",
                    'psql -d app -c "DROP DATABASE app"',
                    "psql app -c 'TRUNCATE users'",
                    "echo 'TRUNCATE TABLE orders' | psql app",
                    "psql app <<'SQL'\nBEGIN;\nDROP TABLE accounts;\nSQL",
                    'docker exec db psql -U postgres -c "drop database app"',
                    'mysql -e "DROP DATABASE shop"',
                    "npx prisma migrate reset --force",
                    "bin/rails db:drop",
                    "bundle exec rake db:reset",
                    "docker volume rm myapp_postgres_data",
                    "psql app -f schema.sql", "psql --file=reset.sql app",
                    "psql app < dump.sql", "mysql shop < reset.sql",
                    "npx prisma db push --force-reset", "prisma db push --accept-data-loss",
                    "docker compose down -v", "docker-compose down --volumes",
                    "docker volume prune -f",
                    "bin/rails db:schema:load", "bundle exec rake db:truncate_all",
                    "python manage.py flush --noinput",
                    "mongosh app --eval 'db.dropDatabase()'",
                    "redis-cli FLUSHALL", "redis-cli -n 2 flushdb", "echo FLUSHALL | redis-cli",
                    "cd app && psql -c 'drop table t'",
                    "true; psql <<EOF\nDROP TABLE x;\nEOF"):
            label = blocked_by_rule(cmd)
            self.assertIsNotNone(label, cmd)
            self.assertIn("destructive database", label, cmd)

    def test_allows(self):
        for cmd in ("supabase start", "supabase stop", "supabase db push",
                    "psql app -c 'select count(*) from users'",
                    "grep -rn 'DROP TABLE' migrations/",
                    "truncate -s 0 app.log",
                    "npx prisma migrate dev", "bin/rails db:migrate",
                    "docker volume rm scratch_cache",
                    # client and statement in different commands (D-9 scoping)
                    "rg 'drop schema' && psql -l",
                    "mysql -e 'select 1' && grep TRUNCATE log",
                    "psql -l; echo 'drop table'",
                    "cat <<EOF > notes.md\nDROP TABLE x\nEOF\npsql -l",
                    "docker volume rm pgadmin_cache", "docker compose down",
                    "grep -rn dropDatabase src/", "prisma db push"):
            self.assertIsNone(blocked_by_rule(cmd), cmd)

    def test_no_project_config_or_env_can_relax_them(self):
        """Nothing in the policy reads config, so a repo's own .company/
        cannot opt out; this plants the overrides a repo might try and runs
        both shims for real."""
        import json
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".company"
            (root / "config").mkdir(parents=True)
            (root / "projects").mkdir()
            override = ("autonomy: full\nallow_destructive_db: true\n"
                        "allow_commands: ['supabase db reset', 'dropdb']\n"
                        "rules: []\nask: []\n")
            for name in ("policy.yaml", "guards.yaml", "autonomy.yaml",
                         "quality-gates.yaml", "harness.yaml"):
                (root / "config" / name).write_text(override)
            (root / "projects" / "p.json").write_text(json.dumps(
                {"id": "p", "autonomy": "full", "allow_destructive_db": True}))
            env = {**os.environ, "COMPANY_ROOT": str(root), "COMPANY_PROJECT": "p",
                   "COMPANY_AUTONOMY": "full", "COMPANY_ALLOW_DESTRUCTIVE_DB": "1"}
            env.pop("COMPANY_TASK", None)
            for cmd in ("supabase db reset", "dropdb app",
                        'psql -c "DROP TABLE users"', "npx prisma migrate reset"):
                claude = subprocess.run(
                    [sys.executable, str(HERE.parent / "hooks" / "protect_branches.py")],
                    input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
                    capture_output=True, text=True, cwd=tmp, env=env)
                out = json.loads(claude.stdout)
                self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny", cmd)
                codex = subprocess.run(
                    [sys.executable, str(HERE.parent / "hooks" / "guard.py"), "codex"],
                    input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                                      "cwd": tmp}),
                    capture_output=True, text=True, cwd=tmp, env=env)
                out = json.loads(codex.stdout)
                self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny", cmd)


class TestRmRule(unittest.TestCase):
    """Regression: `rm -rf /tmp/rev101` is ordinary scratch work, not a root wipe."""

    def test_blocks_root_ish_targets(self):
        for cmd in ("rm -rf /", "rm -rf ~", "rm -rf .", "rm -rf /tmp",
                    "rm -rf $HOME", "rm -fr /usr"):
            self.assertIsNotNone(blocked_by_rule(cmd), cmd)

    def test_allows_scoped_deletes(self):
        for cmd in ("rm -rf /tmp/rev101", "rm -rf ./build", "rm -rf node_modules",
                    "rm -rf $HOME/projects/scratch"):
            self.assertIsNone(blocked_by_rule(cmd), cmd)


class TestWorktreeEscape(unittest.TestCase):
    """The ownership hook does not see Bash. Without this, a redirect bypasses it."""

    def esc(self, cmd):
        return guard.find_escape(cmd, WT, CROOT)

    def test_blocks_redirect_into_main_checkout(self):
        self.assertEqual(self.esc("echo pwned > /repo/api/x.py"), "/repo/api/x.py")

    def test_blocks_append_outside(self):
        self.assertEqual(self.esc("echo x >> /etc/hosts"), "/etc/hosts")

    def test_blocks_cd_outside(self):
        self.assertEqual(self.esc("cd /repo && git log"), "/repo")

    def test_blocks_tee_outside(self):
        self.assertEqual(self.esc("cat a | tee /Users/x/notes.txt"), "/Users/x/notes.txt")

    def test_allows_tmp_scratch(self):
        self.assertIsNone(self.esc("mkdir -p /tmp/rev101 && cd /tmp/rev101"))


MAIN_REPO = "/Users/User/dev/company-os"


class TestMainRepoReadAccess(unittest.TestCase):
    """Regression (2026-10-17): a Tier-2 worker was blocked from reading
    external/<id>/ and skills/<id>/ in the main checkout -- `cd` into
    COMPANY_MAIN_REPO was treated identically to a write escape, even for
    pure reads (`ls`, `find`, `which`). The whole capability-registry/
    external/ workflow depends on every worker being able to cd there and
    read; this is load-bearing, not optional."""

    def esc(self, cmd):
        return guard.find_escape(cmd, WT, CROOT, MAIN_REPO)

    def test_allows_reading_main_repo(self):
        for cmd in (
            "cd /Users/User/dev/company-os; ls; ls external 2>/dev/null | head -80",
            "cd /Users/User/dev/company-os && cat skills/motion-graphics-video/SKILL.md",
            "cd /Users/User/dev/company-os && find external -maxdepth 2 -type d",
        ):
            self.assertIsNone(self.esc(cmd), cmd)

    def test_still_blocks_writing_into_main_repo(self):
        """cd being allowed must never imply writes into the main repo are --
        the ownership hook only sees Write/Edit/NotebookEdit, so a shell
        redirect is still the escape hatch this guard exists to close."""
        self.assertEqual(
            self.esc("cd /Users/User/dev/company-os && echo pwned > /Users/User/dev/company-os/README.md"),
            "/Users/User/dev/company-os/README.md")
        self.assertEqual(
            self.esc("cat a | tee /Users/User/dev/company-os/notes.txt"),
            "/Users/User/dev/company-os/notes.txt")

    def test_still_blocks_cd_into_unrelated_absolute_paths(self):
        self.assertEqual(self.esc("cd /etc && cat hosts"), "/etc")

    def test_worktree_and_company_root_unaffected(self):
        self.assertIsNone(self.esc(f"cd {WT} && git log"))
        self.assertIsNone(self.esc(f"cd {CROOT} && cat events/events.jsonl"))

    def test_allows_dev_null(self):
        self.assertIsNone(self.esc("python3 -m unittest discover -q tests > /dev/null"))

    def test_allows_inside_worktree(self):
        self.assertIsNone(self.esc(f"echo x > {WT}/api/new.py"))

    def test_allows_company_root(self):
        self.assertIsNone(self.esc(f"echo x > {CROOT}/state/workers/w1/log.txt"))

    def test_allows_relative_paths(self):
        self.assertIsNone(self.esc("python3 -m unittest discover -q tests > out.txt 2>&1"))


if __name__ == "__main__":
    unittest.main()
