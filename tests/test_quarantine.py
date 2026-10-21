"""`company quarantine-lessons` — disregard leaked test-fixture lessons.

tests/test_lessons.py and test_onboard.py recorded LESSON_RECORDED events
under project "p" into the real log when the suite ran inside a worker session.
The correction must append (never edit), be idempotent, be forgeable only by
the trusted launcher, and leave every genuine lesson's fold() output untouched.
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
import lessons  # noqa: E402
import quarantine  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"


class QuarantineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _leaked(self, pattern="x", project="p"):
        """A LESSON_RECORDED exactly as the fixtures leaked it."""
        return self.log.append(make_event(
            event="LESSON_RECORDED", actor="company-pm", project=project,
            data={"pattern": pattern, "fix": "f"}, evidence={"log": "e"}))

    def _real(self, pattern, project="company-os", skill=None):
        """A genuine lesson that must survive the quarantine untouched."""
        data = {"pattern": pattern, "fix": "the real fix"}
        if skill:
            data["skill"] = skill
        return self.log.append(make_event(
            event="LESSON_RECORDED", actor="company-pm", project=project,
            data=data, evidence={"log": "a real incident"}))

    def _quarantines(self):
        return [e for e in self.log.read() if e["event"] == "LESSONS_QUARANTINED"]


class TestQuarantineApplied(QuarantineCase):
    def test_one_event_covers_every_leaked_seq_and_fold_skips_them(self):
        leaked = [self._leaked()["seq"] for _ in range(3)]
        real = self._real("a genuine cross-project pattern")["seq"]
        before = self.log.path.read_text()

        out = quarantine.run(self.root)

        self.assertEqual(out["appended"]["data"]["seqs"], leaked)
        self.assertEqual(out["appended"]["data"]["count"], 3)
        # Append-only: every original line is byte-for-byte where it was.
        self.assertTrue(self.log.path.read_text().startswith(before))

        folded = lessons.fold(self.log.read())
        ids = {l["id"] for l in folded}
        self.assertEqual(ids, {f"LESSON-{real}"},
                         "the unfiltered fold must drop the quarantined seqs and keep the real one")

    def test_requires_evidence(self):
        self._leaked()
        with self.assertRaises(Exception):
            # make_event with no evidence can't even be appended for this type.
            self.log.append(make_event(
                event="LESSONS_QUARANTINED", actor=quarantine.QUARANTINE_ACTOR,
                project="p", data={"seqs": [1], "count": 1}))

    def test_expect_mismatch_refuses(self):
        self._leaked()
        self._leaked()
        with self.assertRaises(ValueError):
            quarantine.run(self.root, expect=99)
        self.assertEqual(self._quarantines(), [], "nothing appended when the count disagrees")

    def test_dry_run_appends_nothing(self):
        self._leaked()
        out = quarantine.run(self.root, dry_run=True)
        self.assertEqual(len(out["would_quarantine"]), 1)
        self.assertIsNone(out["appended"])
        self.assertEqual(self._quarantines(), [])


class TestIdempotent(QuarantineCase):
    def test_a_second_run_appends_nothing(self):
        self._leaked()
        self._leaked()
        quarantine.run(self.root)
        lines = self.log.path.read_text()

        out = quarantine.run(self.root)

        self.assertIsNone(out["appended"])
        self.assertEqual(len(out["already_quarantined"]), 2)
        self.assertEqual(self.log.path.read_text(), lines)
        self.assertEqual(len(self._quarantines()), 1, "no duplicate correction event")

    def test_a_later_leak_is_quarantined_without_re_listing_the_old_ones(self):
        self._leaked()
        quarantine.run(self.root)
        fresh = self._leaked()["seq"]

        out = quarantine.run(self.root)

        self.assertEqual(out["appended"]["data"]["seqs"], [fresh])
        self.assertEqual(len(self._quarantines()), 2)
        self.assertEqual(lessons.fold(self.log.read()), [])


class TestUnaffectedLessons(QuarantineCase):
    def test_non_quarantined_fold_is_completely_unaffected(self):
        a = self._real("pattern A", skill="deploy")
        b = self._real("pattern B", skill="deploy")
        c = self._real("pattern C", project="other")
        self._leaked()  # noise that will be quarantined

        before = lessons.fold(self.log.read())
        quarantine.run(self.root)
        after = lessons.fold(self.log.read())

        # The genuine lessons fold identically before and after, minus only the leak.
        real_ids = {f"LESSON-{a['seq']}", f"LESSON-{b['seq']}", f"LESSON-{c['seq']}"}
        self.assertEqual({l["id"] for l in after}, real_ids)
        self.assertEqual([l for l in before if l["id"] in real_ids], after)
        # Repeat-detection on real skills still fires, untouched by the quarantine.
        self.assertEqual(lessons.skills_with_repeated_lessons(self.log.read()), {"deploy": 2})

    def test_a_project_filter_still_works_after_quarantine(self):
        c = self._real("pattern C", project="other")
        self._leaked()
        quarantine.run(self.root)
        self.assertEqual([l["id"] for l in lessons.fold(self.log.read(), project="other")],
                         [f"LESSON-{c['seq']}"])


class TestCli(QuarantineCase):
    def _run(self, *args, actor_env=None):
        env = dict(os.environ)
        env.pop("COMPANY_ACTOR", None)
        if actor_env:
            env["COMPANY_ACTOR"] = actor_env
        return subprocess.run(
            [sys.executable, str(CLI), "--root", str(self.root), *args],
            capture_output=True, text=True, env=env)

    def test_a_worker_cannot_forge_a_quarantine(self):
        """LESSONS_QUARANTINED disregards recorded lessons, so it gets the same
        launcher-only protection as WORKER_STARTED/TOKENS_BACKFILLED — a worker
        must not be able to hide its own real lessons."""
        real = self._real("a worker's genuine lesson")["seq"]
        r = self._run("event", "LESSONS_QUARANTINED", "--evidence", "x",
                      "--data", json.dumps({"seqs": [real], "count": 1}),
                      actor_env="backend-engineer-1")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self._quarantines(), [])

    def test_cli_quarantines_and_is_idempotent(self):
        self._leaked()
        self._leaked()
        r = self._run("quarantine-lessons", "--expect", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["appended"]["data"]["count"], 2)

        r2 = self._run("quarantine-lessons")
        self.assertIsNone(json.loads(r2.stdout)["appended"])
        self.assertEqual(len(self._quarantines()), 1)


if __name__ == "__main__":
    unittest.main()
