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


class TestSkillTaggingAndRepeatDetection(unittest.TestCase):
    """The actual self-improving loop: a lesson tagged to a skill is
    queryable, and 2+ lessons on the same skill is the concrete signal that
    skill needs a real patch — not a hope someone remembers to reread the
    event log. Researched from how real self-improving skill setups work:
    capture the pattern, persist it, and let repetition (not vibes) trigger
    the update. https://github.com/Kulaxyz/self-learning-skills"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)

    def test_a_lesson_can_be_tagged_to_a_skill(self):
        lessons.record(self.root, project="p", pattern="x", evidence="e", fix="f",
                       skill="scroll-animation")
        found = lessons.fold(EventLog(self.root).read(), skill="scroll-animation")
        self.assertEqual(len(found), 1)

    def test_fold_by_skill_excludes_untagged_and_other_skills(self):
        lessons.record(self.root, project="p", pattern="a", evidence="e", fix="f",
                       skill="scroll-animation")
        lessons.record(self.root, project="p", pattern="b", evidence="e", fix="f",
                       skill="motion-vocabulary")
        lessons.record(self.root, project="p", pattern="c", evidence="e", fix="f")
        found = lessons.fold(EventLog(self.root).read(), skill="scroll-animation")
        self.assertEqual([l["pattern"] for l in found], ["a"])

    def test_one_lesson_on_a_skill_is_not_yet_a_signal(self):
        lessons.record(self.root, project="p", pattern="x", evidence="e", fix="f",
                       skill="scroll-animation")
        signals = lessons.skills_with_repeated_lessons(EventLog(self.root).read())
        self.assertEqual(signals, {})

    def test_two_lessons_on_the_same_skill_is_the_signal(self):
        lessons.record(self.root, project="p", pattern="x", evidence="e", fix="f",
                       skill="scroll-animation")
        lessons.record(self.root, project="p", pattern="y", evidence="e", fix="f",
                       skill="scroll-animation")
        signals = lessons.skills_with_repeated_lessons(EventLog(self.root).read())
        self.assertEqual(signals, {"scroll-animation": 2})

    def test_lessons_on_different_skills_do_not_combine(self):
        lessons.record(self.root, project="p", pattern="x", evidence="e", fix="f",
                       skill="scroll-animation")
        lessons.record(self.root, project="p", pattern="y", evidence="e", fix="f",
                       skill="motion-vocabulary")
        signals = lessons.skills_with_repeated_lessons(EventLog(self.root).read())
        self.assertEqual(signals, {})


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


class TestReadOnlyRolesCannotRecord(unittest.TestCase):
    """COO's audit finding, live: cto-advisor called `company lesson` 47
    times with placeholder junk while exploring the CLI, permanently
    polluting the append-only log. Recording is refused for every read-only
    role; listing (no --pattern) is still allowed — that's genuinely read-only."""

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

    def _run(self, *args, actor=None):
        import os
        import subprocess
        env = dict(os.environ)
        if actor:
            env["COMPANY_ACTOR"] = actor
        else:
            env.pop("COMPANY_ACTOR", None)
        return subprocess.run(
            [sys.executable, str(HERE.parent / "tools" / "company" / "cli.py"), *args],
            cwd=self.repo, capture_output=True, text=True, env=env)

    def test_a_pure_advisor_cannot_record(self):
        result = self._run("lesson", "--pattern", "x", "--evidence", "e", "--fix", "f",
                           "--project", "p", actor="cto-advisor")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(EventLog(self.repo / ".company").read(), [])

    def test_a_task_scoped_reviewer_cannot_record(self):
        """Actor ids for reviewers carry a task suffix (code-reviewer-201),
        not an exact role-name match — the check must handle that."""
        result = self._run("lesson", "--pattern", "x", "--evidence", "e", "--fix", "f",
                           "--project", "p", actor="code-reviewer-201")
        self.assertNotEqual(result.returncode, 0)

    def test_company_pm_can_still_record(self):
        result = self._run("lesson", "--pattern", "x", "--evidence", "e", "--fix", "f",
                           "--project", "p", actor="company-pm")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_an_implementer_can_still_record(self):
        result = self._run("lesson", "--pattern", "x", "--evidence", "e", "--fix", "f",
                           "--project", "p", actor="backend-engineer-101")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_read_only_role_can_still_list(self):
        self._run("lesson", "--pattern", "x", "--evidence", "e", "--fix", "f",
                 "--project", "p", actor="company-pm")
        result = self._run("lesson", "--project", "p", actor="cto-advisor")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
