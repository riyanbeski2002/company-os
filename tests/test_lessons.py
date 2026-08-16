"""The retrospective loop (V2): corrections become durable, not personal.

Before this, a correction only became durable via personal habit — hand-
written to `tasks/lessons.md` in whatever repo happened to be open, invisible
to Company OS itself and to any other project. `company lesson` makes it an
event, queryable by any future session on this repo.
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import lessons  # noqa: E402
from eventlog import EventLog  # noqa: E402


class TestRecord(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)

    def test_requires_a_pattern(self):
        with self.assertRaises(ValueError):
            lessons.record(self.root, project="p", pattern="", evidence="e", fix="f")

    def test_requires_a_fix(self):
        """An observation with no fix applied is a complaint, not a lesson."""
        with self.assertRaises(ValueError):
            lessons.record(self.root, project="p", pattern="something happened",
                           evidence="e", fix="")

    def test_requires_evidence(self):
        with self.assertRaises(ValueError):
            lessons.record(self.root, project="p", pattern="x", evidence="", fix="y")

    def test_records_a_real_lesson(self):
        data = lessons.record(self.root, project="p", pattern="PM polled instead of waiting",
                              evidence="66 sleep-poll shells observed", fix="documented the fix")
        self.assertEqual(data["pattern"], "PM polled instead of waiting")
        events = EventLog(self.root).read()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "LESSON_RECORDED")

    def test_default_actor_is_company_pm(self):
        lessons.record(self.root, project="p", pattern="x", evidence="e", fix="f")
        events = EventLog(self.root).read()
        self.assertEqual(events[0]["actor"], "company-pm")


class TestFold(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)

    def test_lessons_only_ever_accumulate(self):
        """Unlike an escalation, a lesson is never resolved — the fix already
        happened by the time it's recorded."""
        lessons.record(self.root, project="p", pattern="a", evidence="e", fix="f")
        lessons.record(self.root, project="p", pattern="b", evidence="e", fix="f")
        out = lessons.fold(EventLog(self.root).read())
        self.assertEqual(len(out), 2)
        self.assertEqual([l["pattern"] for l in out], ["a", "b"])

    def test_filters_by_project(self):
        lessons.record(self.root, project="p1", pattern="a", evidence="e", fix="f")
        lessons.record(self.root, project="p2", pattern="b", evidence="e", fix="f")
        out = lessons.fold(EventLog(self.root).read(), project="p1")
        self.assertEqual([l["pattern"] for l in out], ["a"])

    def test_no_lessons_is_an_empty_list_not_an_error(self):
        self.assertEqual(lessons.fold(EventLog(self.root).read()), [])


class TestCLI(unittest.TestCase):
    """`company lesson` end to end, as a real subprocess — the surface the PM
    and every other role actually calls."""

    def setUp(self):
        import subprocess
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@t.co"],
                   ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.repo, check=True, capture_output=True)
        (self.repo / "a.txt").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=self.repo, check=True, capture_output=True)
        self._run("init")

    def _run(self, *args):
        import subprocess
        return subprocess.run(
            [sys.executable, str(HERE.parent / "tools" / "company" / "cli.py"), *args],
            cwd=self.repo, capture_output=True, text=True)

    def test_record_then_list(self):
        rec = self._run("lesson", "--pattern", "a repeated pattern", "--evidence", "e",
                        "--fix", "f", "--project", "p")
        self.assertEqual(rec.returncode, 0, rec.stderr)

        listed = self._run("lesson", "--project", "p")
        self.assertEqual(listed.returncode, 0)
        import json
        out = json.loads(listed.stdout)
        self.assertEqual(len(out["lessons"]), 1)
        self.assertEqual(out["lessons"][0]["pattern"], "a repeated pattern")

    def test_missing_fix_is_refused(self):
        result = self._run("lesson", "--pattern", "x", "--evidence", "e", "--project", "p")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
