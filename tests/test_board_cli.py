"""`company board note/read/check` end to end, the same way
test_route_outcome_cli.py pins ROUTE_OUTCOME's CLI surface."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLI = HERE.parent / "tools" / "company" / "cli.py"


class TestBoardCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".company"
        self._run("init")

    def _run(self, *args):
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              capture_output=True, text=True)

    def _note(self, type, content, subject="T-1", actor="w1", ttl=None):
        args = ["board", "note", "--subject", subject, "--type", type,
                "--content", content, "--actor", actor, "--project", "p"]
        if ttl is not None:
            args += ["--ttl", str(ttl)]
        return self._run(*args)

    def test_note_then_read_round_trips(self):
        r = self._note("FACT", "the bug is in parse()")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r2 = self._run("board", "read", "--subject", "T-1")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        out = json.loads(r2.stdout)
        self.assertEqual(len(out["facts"]), 1)
        self.assertEqual(out["facts"][0]["content"], "the bug is in parse()")

    def test_done_summary_with_weasel_words_is_rejected(self):
        r = self._note("DONE_SUMMARY", "should work now")
        self.assertNotEqual(r.returncode, 0)

    def test_done_summary_with_real_evidence_is_accepted(self):
        r = self._note("DONE_SUMMARY", "tests passed")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unknown_type_is_rejected_by_argparse(self):
        r = self._note("RUMOR", "something")
        self.assertNotEqual(r.returncode, 0)

    def test_fail_invalidates_the_actors_open_claim(self):
        self._note("CLAIM", "trying the regex approach", actor="w1")
        self._note("FAIL", "regex approach doesn't handle nesting", actor="w1")
        out = json.loads(self._run("board", "read", "--subject", "T-1").stdout)
        self.assertEqual(out["open_claims"], [])

    def test_check_is_false_before_any_follow_up_note(self):
        r1 = self._note("CLAIM", "taking it", actor="w1")
        seq = json.loads(r1.stdout)["seq"]
        r2 = self._run("board", "check", "--subject", "T-1", "--actor", "w1",
                       "--since", str(seq))
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertFalse(json.loads(r2.stdout)["published"])

    def test_check_is_true_after_a_follow_up_note(self):
        r1 = self._note("CLAIM", "taking it", actor="w1")
        seq = json.loads(r1.stdout)["seq"]
        self._note("DONE_SUMMARY", "fix applied, tests passed", actor="w1")
        r2 = self._run("board", "check", "--subject", "T-1", "--actor", "w1",
                       "--since", str(seq))
        self.assertTrue(json.loads(r2.stdout)["published"])

    def test_different_subjects_stay_isolated(self):
        self._note("FACT", "about T-1", subject="T-1")
        self._note("FACT", "about T-2", subject="T-2")
        out = json.loads(self._run("board", "read", "--subject", "T-1").stdout)
        self.assertEqual(len(out["facts"]), 1)
        self.assertEqual(out["facts"][0]["content"], "about T-1")


if __name__ == "__main__":
    unittest.main()
