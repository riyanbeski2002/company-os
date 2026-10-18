"""`company escalate --list` (cost audit, 2026-09-14): finos-52 found 114
escalations as flat, ungrep-able .md files — "what's still waiting on Riyan?"
required reading all of them by hand. The underlying data already carries a
status (`escalations.all_escalations()`); this is the missing CLI query.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE.parent / "tools" / "company" / "cli.py"


class TestEscalateList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".company"
        self._run("init")

    def _run(self, *args):
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              capture_output=True, text=True)

    def _raise(self, need, kind="decision", non_blocking=False):
        args = ["escalate", "--kind", kind, "--need", need, "--project", "p"]
        if non_blocking:
            args.append("--non-blocking")
        r = self._run(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)["id"]

    def test_list_open_shows_a_freshly_raised_escalation(self):
        esc_id = self._raise("pick a database")
        r = self._run("escalate", "--list", "open")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["filter"], "open")
        self.assertIn(esc_id, [e["id"] for e in out["escalations"]])

    def test_resolved_escalation_drops_out_of_open_but_stays_in_all(self):
        esc_id = self._raise("pick a database")
        r = self._run("resolve", esc_id, "--resolution", "postgres", "--project", "p")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        open_out = json.loads(self._run("escalate", "--list", "open").stdout)
        self.assertNotIn(esc_id, [e["id"] for e in open_out["escalations"]])

        all_out = json.loads(self._run("escalate", "--list", "all").stdout)
        ids = {e["id"]: e for e in all_out["escalations"]}
        self.assertIn(esc_id, ids)
        self.assertEqual(ids[esc_id]["status"], "resolved")

        resolved_out = json.loads(self._run("escalate", "--list", "resolved").stdout)
        self.assertIn(esc_id, [e["id"] for e in resolved_out["escalations"]])

    def test_list_with_nothing_raised_yet_is_an_empty_list_not_an_error(self):
        r = self._run("escalate", "--list", "open")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["escalations"], [])
        self.assertEqual(out["count"], 0)

    def test_list_filters_by_project(self):
        self._raise("need A")
        r = self._run("escalate", "--kind", "decision", "--need", "need B", "--project", "other")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(self._run("escalate", "--list", "open", "--project", "p").stdout)
        needs = [e.get("need") for e in out["escalations"]]
        self.assertIn("need A", needs)
        self.assertNotIn("need B", needs)

    def test_raising_without_list_still_requires_kind_and_need(self):
        r = self._run("escalate", "--project", "p")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--kind", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
