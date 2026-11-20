"""DB guard matches commands, not quoted text (finos); the signing key never
reaches git (growfin)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "tools" / "company"))

import gatesig  # noqa: E402
import policy  # noqa: E402

DB = "drop" + "db"  # keep the literal out of any shell command line


class DbGuardMatchesCommandsNotText(unittest.TestCase):
    def test_quoted_mentions_are_allowed(self):
        for cmd in (f'grep -n "down -v\\|{DB}\\|DROP DATABASE" scripts/verify-db-up.sh',
                    "rg -n 'supabase db reset' docs/",
                    f'git commit -m "docs: never run {DB} in CI"',
                    "bash scripts/verify-db-up.sh --stop"):
            self.assertIsNone(policy.check_command(cmd), cmd)

    def test_real_operations_still_blocked(self):
        for cmd in (f"{DB} finos", "supabase db reset", "echo 'TRUNCATE t' | psql",
                    "psql -c 'DROP TABLE x'", 'psql -c "drop schema public cascade"',
                    "docker compose down -v"):
            self.assertIsNotNone(policy.check_command(cmd), cmd)


class SigningKeyNeverReachesGit(unittest.TestCase):
    def test_key_is_ignored_even_when_company_dir_is_tracked(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            root = repo / ".company"
            (root / "events").mkdir(parents=True)
            (root / "events" / "events.jsonl").write_text("")
            gatesig.load_key(root, create=True)
            self.assertTrue((root / "secrets" / "gate.key").exists())
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
            staged = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--name-only"],
                                    capture_output=True, text=True, check=True).stdout
            self.assertNotIn("gate.key", staged)


if __name__ == "__main__":
    unittest.main()
