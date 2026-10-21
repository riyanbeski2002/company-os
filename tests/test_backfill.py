"""`company backfill-tokens` — KNOWN_ISSUES #1's outstanding half.

Pre-capture WORKER_EXITED events carry no `tokens`; their stdout.json still
has the usage block. The backfill must append (never edit), be idempotent,
leave already-captured runs alone, and name every run it could not
reconstruct instead of zero-filling it — and costs.aggregate must actually
read what it appended.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

from eventlog import EventLog, make_event  # noqa: E402
import backfill  # noqa: E402
import costs  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"

# The shape `claude -p --output-format json` actually writes (trimmed).
RESULT = {
    "type": "result", "subtype": "success", "is_error": False, "num_turns": 11,
    "stop_reason": "end_turn", "session_id": "sess-1", "total_cost_usd": 0.42,
    "usage": {"input_tokens": 54, "output_tokens": 9241,
              "cache_read_input_tokens": 793971, "cache_creation_input_tokens": 39230,
              "output_tokens_details": {"thinking_tokens": 3093}},
}
TOKENS = {"output": 9241, "input": 54, "cache_read": 793971, "cache_creation": 39230}


class BackfillCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _exited(self, actor, session_id="sess-1", tokens=None, task="T-1"):
        """A WORKER_EXITED as the pre-fix worker.py wrote it (no `tokens`),
        or as today's does when `tokens` is given."""
        data = {"exit_code": 0, "elapsed_s": 60.0, "cost_usd": 0.42,
                "session_id": session_id}
        if tokens is not None:
            data["tokens"] = tokens
        return self.log.append(make_event(event="WORKER_EXITED", actor=actor,
                                          project="p", task=task, data=data))

    def _stdout(self, actor, content):
        d = self.root / "state" / "workers" / actor
        d.mkdir(parents=True, exist_ok=True)
        (d / "stdout.json").write_text(
            content if isinstance(content, str) else json.dumps(content))

    def _backfills(self):
        return [e for e in self.log.read() if e["event"] == "TOKENS_BACKFILLED"]


class TestReconstructable(BackfillCase):
    def test_missing_tokens_with_a_matching_stdout_is_backfilled(self):
        original = self._exited("security-reviewer-201")
        self._stdout("security-reviewer-201", RESULT)
        before = self.log.path.read_text()

        out = backfill.run(self.root)

        self.assertEqual(len(out["appended"]), 1)
        self.assertEqual(out["unreconstructable"], [])
        [ev] = self._backfills()
        self.assertEqual(ev["data"]["backfills_seq"], original["seq"])
        self.assertEqual(ev["data"]["actor"], "security-reviewer-201")
        self.assertEqual(ev["data"]["session_id"], "sess-1")
        self.assertEqual(ev["data"]["tokens"], TOKENS)
        self.assertEqual(ev["data"]["task"], "T-1")
        self.assertNotIn("task", ev, "a task field would bump the task's updated_at on fold")
        self.assertTrue(ev["evidence"]["log"].endswith("security-reviewer-201/stdout.json"))
        # Append-only: every original line is byte-for-byte where it was.
        self.assertTrue(self.log.path.read_text().startswith(before))

    def test_costs_folds_the_backfilled_tokens_in(self):
        self._exited("security-reviewer-201")
        self._stdout("security-reviewer-201", RESULT)
        self.assertEqual(costs.aggregate(self.log.read())["tokens"]["cache_read"], 0)

        backfill.run(self.root)
        result = costs.aggregate(self.log.read())

        self.assertEqual(result["tokens"], TOKENS)
        self.assertEqual(result["runs_with_backfilled_tokens"], 1)
        self.assertEqual(result["worker_runs"], 1, "the backfill event is not a second run")
        self.assertEqual(result["by_actor"]["security-reviewer-201"]["cache_read_tokens"], 793971)
        self.assertEqual(result["by_task"]["T-1"]["output_tokens"], 9241)

    def test_dry_run_appends_nothing(self):
        self._exited("be-1")
        self._stdout("be-1", RESULT)
        out = backfill.run(self.root, dry_run=True)
        self.assertEqual(len(out["would_append"]), 1)
        self.assertEqual(out["appended"], [])
        self.assertEqual(self._backfills(), [])


class TestIdempotent(BackfillCase):
    def test_a_second_run_appends_nothing(self):
        original = self._exited("be-1")
        self._stdout("be-1", RESULT)
        backfill.run(self.root)
        lines = self.log.path.read_text()

        out = backfill.run(self.root)

        self.assertEqual(out["appended"], [])
        self.assertEqual(out["already_backfilled"], [original["seq"]])
        self.assertEqual(self.log.path.read_text(), lines)
        self.assertEqual(costs.aggregate(self.log.read())["tokens"], TOKENS)

    def test_costs_never_counts_a_duplicated_backfill_twice(self):
        """Two concurrent backfills could both pass the existence check
        before either appends; the reader must still count the run once."""
        original = self._exited("be-1")
        for _ in range(2):
            self.log.append(make_event(
                event="TOKENS_BACKFILLED", actor=backfill.BACKFILL_ACTOR, project="p",
                data={"backfills_seq": original["seq"], "actor": "be-1",
                      "session_id": "sess-1", "tokens": TOKENS},
                evidence={"log": "stdout.json"}))
        self.assertEqual(costs.aggregate(self.log.read())["tokens"], TOKENS)


class TestAlreadyCaptured(BackfillCase):
    def test_an_event_that_has_tokens_is_left_alone(self):
        captured = {"output": 5, "input": 1, "cache_read": 50, "cache_creation": 2}
        self._exited("be-1", tokens=captured)
        self._stdout("be-1", RESULT)  # disagrees on purpose: must not win

        out = backfill.run(self.root)

        self.assertEqual(out["appended"], [])
        self.assertEqual(out["already_had_tokens"], 1)
        self.assertEqual(out["unreconstructable"], [])
        self.assertEqual(self._backfills(), [])
        self.assertEqual(costs.aggregate(self.log.read())["tokens"], captured)

    def test_an_all_zero_captured_tokens_field_is_still_captured(self):
        """A post-fix run that really consumed nothing (e.g. api_error) has
        `tokens` present and zero — that's a recorded fact, not a gap."""
        zero = {"output": 0, "input": 0, "cache_read": 0, "cache_creation": 0}
        self._exited("be-1", tokens=zero)
        self._stdout("be-1", RESULT)
        self.assertEqual(backfill.run(self.root)["appended"], [])

    def test_costs_ignores_a_backfill_aimed_at_a_captured_run(self):
        captured = {"output": 5, "input": 1, "cache_read": 50, "cache_creation": 2}
        original = self._exited("be-1", tokens=captured)
        self.log.append(make_event(
            event="TOKENS_BACKFILLED", actor=backfill.BACKFILL_ACTOR, project="p",
            data={"backfills_seq": original["seq"], "actor": "be-1",
                  "session_id": "sess-1", "tokens": TOKENS},
            evidence={"log": "stdout.json"}))
        self.assertEqual(costs.aggregate(self.log.read())["tokens"], captured)


class TestUnreconstructable(BackfillCase):
    def _assert_reported_not_fabricated(self, actor, reason_fragment):
        out = backfill.run(self.root)
        self.assertEqual(out["appended"], [])
        self.assertEqual(self._backfills(), [])
        [miss] = out["unreconstructable"]
        self.assertEqual(miss["actor"], actor)
        self.assertIn(reason_fragment, miss["reason"])
        self.assertEqual(costs.aggregate(self.log.read())["tokens"]["cache_read"], 0)
        return miss

    def test_no_stdout_json_at_all(self):
        original = self._exited("be-1")
        miss = self._assert_reported_not_fabricated("be-1", "no ")
        self.assertEqual(miss["seq"], original["seq"])

    def test_corrupt_stdout_json(self):
        self._exited("be-1")
        self._stdout("be-1", '{"session_id": "sess-1", "usage": {')
        self._assert_reported_not_fabricated("be-1", "not parseable")

    def test_stdout_json_with_no_usage_block_is_not_zero_filled(self):
        """worker._usage() zero-fills a missing usage block; the backfill
        must not, or a fabricated zero looks identical to a real one."""
        self._exited("be-1")
        self._stdout("be-1", {"session_id": "sess-1", "is_error": True})
        self._assert_reported_not_fabricated("be-1", "no usable usage block")

    def test_stdout_overwritten_by_a_later_launch_of_the_same_actor(self):
        """state/workers/<actor>/ is reused on relaunch, so the file on disk
        may be a different run's. Only a session_id match proves it isn't."""
        self._exited("be-1", session_id="sess-old")
        self._stdout("be-1", RESULT)  # sess-1, a later run
        self._assert_reported_not_fabricated("be-1", "different run")

    def test_event_with_no_session_id(self):
        self._exited("be-1", session_id=None)
        self._stdout("be-1", RESULT)
        self._assert_reported_not_fabricated("be-1", "no session_id")

    def test_two_tokenless_exits_sharing_a_session_are_both_refused(self):
        self._exited("be-1")
        self._exited("be-1")
        self._stdout("be-1", RESULT)
        out = backfill.run(self.root)
        self.assertEqual(out["appended"], [])
        self.assertEqual(len(out["unreconstructable"]), 2)

    def test_actor_that_is_not_a_plain_directory_name_is_not_followed(self):
        self._exited("../../escape")
        self._assert_reported_not_fabricated("../../escape", "not a plain")

    def test_one_gap_does_not_block_the_rest(self):
        self._exited("be-1")
        self._stdout("be-1", RESULT)
        self._exited("be-2", session_id="sess-2")  # no stdout.json
        out = backfill.run(self.root)
        self.assertEqual([a["actor"] for a in out["appended"]], ["be-1"])
        self.assertEqual([m["actor"] for m in out["unreconstructable"]], ["be-2"])


class TestCli(BackfillCase):
    def _run(self, *args, actor_env=None):
        env = dict(os.environ)
        env["COMPANY_PROJECT"] = "p"
        env.pop("COMPANY_ACTOR", None)
        if actor_env:
            env["COMPANY_ACTOR"] = actor_env
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), *args],
            capture_output=True, text=True, env=env)

    def test_unreconstructable_runs_are_warned_about_on_stderr_and_listed(self):
        self._exited("be-1")
        self._stdout("be-1", RESULT)
        self._exited("be-2", session_id="sess-2")
        r = self._run("backfill-tokens")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(len(out["appended"]), 1)
        self.assertEqual([m["actor"] for m in out["unreconstructable"]], ["be-2"])
        self.assertIn("cannot reconstruct tokens", r.stderr)
        self.assertIn("be-2", r.stderr)

    def test_costs_reports_the_backfilled_runs(self):
        self._exited("be-1")
        self._stdout("be-1", RESULT)
        self._run("backfill-tokens")
        out = json.loads(self._run("costs").stdout)
        self.assertEqual(out["tokens"], TOKENS)
        self.assertEqual(out["runs_with_backfilled_tokens"], 1)

    def test_a_worker_cannot_forge_a_backfill(self):
        """TOKENS_BACKFILLED supplies a WORKER_EXITED's tokens, so it gets
        WORKER_EXITED's launcher-only protection."""
        original = self._exited("be-1")
        r = self._run("event", "TOKENS_BACKFILLED", "--evidence", "x.json",
                      "--data", json.dumps({"backfills_seq": original["seq"], "actor": "be-1",
                                            "session_id": "sess-1", "tokens": TOKENS}),
                      actor_env="be-1")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self._backfills(), [])


if __name__ == "__main__":
    unittest.main()
