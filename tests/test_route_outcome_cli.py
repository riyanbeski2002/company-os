"""`company capability outcome`/`outcomes` (KNOWN_GAPS.md #3's standing fix):
a `confirm: true` capability-map entry can only ever be asked about forever
without a record of whether using it actually went well. ROUTE_OUTCOME
closes that; this pins the CLI surface down end to end, the same way
test_escalate_list.py pins `escalate --list`.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE.parent / "tools" / "company" / "cli.py"


class TestRouteOutcomeCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".company"
        self._run("init")

    def _run(self, *args):
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              capture_output=True, text=True)

    def _record(self, capabilities, verdict, why="it worked", evidence="T-1", task=None):
        args = ["capability", "outcome", "--capabilities", *capabilities,
                "--verdict", verdict, "--why", why, "--evidence", evidence,
                "--project", "p"]
        if task:
            args += ["--task", task]
        return self._run(*args)

    def test_record_a_good_outcome(self):
        r = self._record(["video-editor"], "good")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["verdict"], "good")
        self.assertEqual(out["capabilities"], ["video-editor"])

    def test_bad_verdict_is_rejected(self):
        r = self._record(["video-editor"], "mediocre")
        self.assertNotEqual(r.returncode, 0)

    def test_missing_why_is_rejected(self):
        r = self._run("capability", "outcome", "--capabilities", "video-editor",
                      "--verdict", "good", "--evidence", "T-1", "--project", "p")
        self.assertNotEqual(r.returncode, 0)

    def test_outcomes_tallies_across_multiple_records(self):
        self._record(["video-editor"], "good")
        self._record(["video-editor"], "good")
        self._record(["video-editor"], "bad", why="render came out wrong")
        r = self._run("capability", "outcomes", "video-editor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["total"], 3)
        self.assertEqual(out["tally"], {"good": 2, "bad": 1, "abandoned": 0})

    def test_outcomes_ignores_records_for_a_different_capability(self):
        self._record(["video-editor"], "good")
        self._record(["morluto-rea"], "bad", why="wrong tool for the job")
        r = self._run("capability", "outcomes", "morluto-rea")
        out = json.loads(r.stdout)
        self.assertEqual(out["total"], 1)
        self.assertEqual(out["tally"]["bad"], 1)

    def test_outcomes_on_a_never_recorded_id_is_honestly_empty(self):
        r = self._run("capability", "outcomes", "never-used-anything")
        out = json.loads(r.stdout)
        self.assertEqual(out["total"], 0)
        self.assertEqual(out["tally"], {"good": 0, "bad": 0, "abandoned": 0})

    def test_record_naming_multiple_capabilities_counts_for_each(self):
        self._record(["video-editor", "buildwithdarius-reel-editor"], "good")
        r1 = self._run("capability", "outcomes", "video-editor")
        r2 = self._run("capability", "outcomes", "buildwithdarius-reel-editor")
        self.assertEqual(json.loads(r1.stdout)["total"], 1)
        self.assertEqual(json.loads(r2.stdout)["total"], 1)


if __name__ == "__main__":
    unittest.main()
