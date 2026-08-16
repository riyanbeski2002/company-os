"""Brownfield verification (V2).

V1 required exit 0 to close a task. On a half-built or live repo — which is the
actual target for this system — the suite is often already red on arrival. Under
V1 every task would be refused forever for damage the worker did not do, and the
only ways out were to fix unrelated code or to lie about the exit code.

The rule is now "no worse than the baseline", where the baseline is measured
before any work and recorded as an event so it cannot be quietly adjusted later.
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import baseline  # noqa: E402
import detect  # noqa: E402
import taskstate  # noqa: E402

GREEN = {"green": True, "exit_code": 0, "failures": 0, "ref": "abc1234"}
RED_3 = {"green": False, "exit_code": 1, "failures": 3, "ref": "abc1234"}
RED_UNCOUNTED = {"green": False, "exit_code": 1, "failures": None, "ref": "abc1234"}


class TestCompare(unittest.TestCase):
    def test_green_run_always_passes(self):
        for base in (None, GREEN, RED_3):
            ok, _ = baseline.compare(base, {"exit_code": 0})
            self.assertTrue(ok)

    def test_red_run_against_green_baseline_is_a_regression(self):
        ok, why = baseline.compare(GREEN, {"exit_code": 1, "failures": 1})
        self.assertFalse(ok)
        self.assertIn("broke something that worked", why)

    def test_red_run_with_no_baseline_is_refused(self):
        ok, why = baseline.compare(None, {"exit_code": 1, "failures": 1})
        self.assertFalse(ok)
        self.assertIn("no baseline was recorded", why)

    def test_same_failures_as_baseline_is_accepted(self):
        ok, why = baseline.compare(RED_3, {"exit_code": 1, "failures": 3})
        self.assertTrue(ok)
        self.assertIn("no worse", why)

    def test_fewer_failures_than_baseline_is_accepted(self):
        ok, _ = baseline.compare(RED_3, {"exit_code": 1, "failures": 1})
        self.assertTrue(ok)

    def test_one_extra_failure_is_refused(self):
        ok, why = baseline.compare(RED_3, {"exit_code": 1, "failures": 4})
        self.assertFalse(ok)
        self.assertIn("added 1", why)

    def test_uncountable_failures_refuse_rather_than_assume(self):
        """Unparseable counts must never be read as 'probably fine'."""
        ok, why = baseline.compare(RED_UNCOUNTED, {"exit_code": 1, "failures": None})
        self.assertFalse(ok)
        self.assertIn("cannot be proven", why)


class TestFailureCounting(unittest.TestCase):
    def test_pytest(self):
        self.assertEqual(baseline._count_failures("2 failed, 8 passed in 0.5s"), 2)

    def test_unittest(self):
        self.assertEqual(baseline._count_failures("FAILED (failures=3)"), 3)

    def test_jest(self):
        self.assertEqual(baseline._count_failures("Tests:  1 failed, 4 passed"), 1)

    def test_clean_output_has_no_count(self):
        self.assertIsNone(baseline._count_failures("OK\nRan 10 tests"))


class TestEvidenceRuleWithBaseline(unittest.TestCase):
    """The end-to-end consequence for closing a task."""

    def _task(self, exit_code, failures):
        return {
            "id": "T-1", "owner": "be-1", "gates": [],
            "evidence": {"diff": "abc1234"},
            "last_test_run": {"exit_code": exit_code, "failures": failures,
                              "actor": "be-1"},
        }

    def test_red_repo_no_new_failures_can_close(self):
        reasons = taskstate.check_done(self._task(1, 3), RED_3)
        self.assertEqual(reasons, [])

    def test_red_repo_with_a_new_failure_cannot_close(self):
        reasons = taskstate.check_done(self._task(1, 4), RED_3)
        self.assertTrue(any("added 1" in r for r in reasons))

    def test_green_repo_still_demands_green(self):
        reasons = taskstate.check_done(self._task(1, 1), GREEN)
        self.assertTrue(any("broke something that worked" in r for r in reasons))

    def test_no_test_run_at_all_is_still_refused(self):
        task = {"id": "T-1", "owner": "be-1", "gates": [],
                "evidence": {"diff": "abc1234"}}
        reasons = taskstate.check_done(task, RED_3)
        self.assertTrue(any("no TEST_RUN event at all" in r for r in reasons))

    def test_accepted_red_run_is_labelled_honestly(self):
        task = self._task(1, 3)
        taskstate.check_done(task, RED_3)
        self.assertIn("no regression", task["evidence"]["tests"])


class TestDetection(unittest.TestCase):
    """A verify command that cannot fail is a rubber stamp."""

    def _repo(self, files: dict):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, body in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        return root

    def test_node_test_script_wins(self):
        r = self._repo({"package.json": '{"scripts":{"test":"jest"}}'})
        self.assertEqual(detect.detect(r)["verify_strategy"], "node-test-script")

    def test_npm_placeholder_test_is_not_a_test(self):
        """`npm init` writes a test script that exits 1 and tests nothing."""
        r = self._repo({"package.json":
                        '{"scripts":{"test":"echo \\"Error: no test specified\\" && exit 1"}}'})
        self.assertNotEqual(detect.detect(r)["verify_strategy"], "node-test-script")

    def test_apps_script_falls_back_to_syntax_checking(self):
        r = self._repo({"appsscript.json": "{}", "Code.js": "function f(){}"})
        d = detect.detect(r)
        self.assertEqual(d["verify_strategy"], "apps-script-syntax")
        self.assertEqual(d["verify_strength"], "syntax-only")
        self.assertIn("parses and nothing more", d["warning"])

    def test_behavioural_checks_beat_syntax_checks(self):
        r = self._repo({"appsscript.json": "{}", "Code.js": "function f(){}",
                        "package.json": '{"scripts":{"test":"jest"}}'})
        self.assertEqual(detect.detect(r)["verify_strength"], "behaviour")

    def test_unknown_repo_warns_rather_than_inventing_a_command(self):
        r = self._repo({"README.md": "# nothing here"})
        d = detect.detect(r)
        self.assertIsNone(d["verify"])
        self.assertIn("Evidence Rule requires", d["warning"])


if __name__ == "__main__":
    unittest.main()
