"""Brownfield verification (V2).

V1 required exit 0 to close a task. On a half-built or live repo — which is the
actual target for this system — the suite is often already red on arrival. Under
V1 every task would be refused forever for damage the worker did not do, and the
only ways out were to fix unrelated code or to lie about the exit code.

The rule is now "no worse than the baseline", where the baseline is measured
before any work and recorded as an event so it cannot be quietly adjusted later.
"""

import os
import subprocess
import sys
import tempfile
import time
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


class TestRunawayProcessFix(unittest.TestCase):
    """CTO reproduced this live against `company baseline`'s own documented
    verify command: `subprocess.run(..., shell=True, timeout=...)` only kills
    the shell on timeout, not any children it spawned. 51 identical
    `unittest discover` processes were still alive and growing after 120s in
    the real incident — nothing took a lock, and nothing killed the tree.
    """

    def test_a_hung_child_process_is_actually_killed_on_timeout(self):
        marker = f"company_os_test_marker_{os.getpid()}"
        # The shell backgrounds a long sleep tagged with a unique marker, then
        # itself hangs — reproducing "shell times out, child survives" if the
        # fix is wrong.
        result = baseline.measure(
            Path("."), f"sh -c 'sleep 30 {marker} & sleep 30'", timeout=1)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["exit_code"], 124)
        time.sleep(0.3)  # give the OS a moment to actually reap the killed group
        survivors = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True)
        self.assertEqual(survivors.stdout.strip(), "",
                         f"child process tagged {marker!r} survived the timeout kill")

    def test_a_fast_command_is_unaffected(self):
        result = baseline.measure(Path("."), "echo hello", timeout=5)
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("hello", result["output_tail"])


class TestBaselineSingleFlight(unittest.TestCase):
    """The other half of the same incident: 50 identical BASELINE_RECORDED
    events fired at the same second — nothing refused a second concurrent
    run for the same project."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)

    def test_a_concurrent_run_is_refused_not_stacked(self):
        with baseline._single_flight(self.root, "p"):
            with self.assertRaises(baseline.BaselineInProgress):
                with baseline._single_flight(self.root, "p"):
                    pass

    def test_a_different_project_is_not_blocked(self):
        with baseline._single_flight(self.root, "p1"):
            with baseline._single_flight(self.root, "p2"):
                pass  # must not raise

    def test_the_lock_releases_after_the_run_completes(self):
        with baseline._single_flight(self.root, "p"):
            pass
        with baseline._single_flight(self.root, "p"):
            pass  # must not raise — the first one already released


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
