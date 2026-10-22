"""Worker packets actually carry what the PM hands them (ESC-026).

`company handoff` always succeeded and wrote a file — but nothing ever read
it back into a worker's packet, so a PM's rescoping brief for a relaunched
task went nowhere. Caught on resolve-os: three relaunches exited 0 with
byte-identical diffs to their first attempt, because the "fix" existed only
in a handoff file the second worker never opened.
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import packet  # noqa: E402


class TestFindHandoff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "handoffs").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name: str, body: str = "x"):
        (self.root / "handoffs" / name).write_text(body, encoding="utf-8")

    def test_finds_a_handoff_addressed_to_the_exact_actor(self):
        self._write("TASK-1-company-pm-to-backend-engineer-1.md", "do X, not Y")
        found = packet.find_handoff(self.root, "TASK-1", "backend-engineer-1", "backend-engineer")
        self.assertIsNotNone(found)
        self.assertEqual(found.read_text(), "do X, not Y")

    def test_finds_a_handoff_addressed_to_the_bare_role(self):
        # A PM may write the handoff before an actor name is assigned.
        self._write("TASK-1-company-pm-to-backend-engineer.md", "role-addressed")
        found = packet.find_handoff(self.root, "TASK-1", "backend-engineer-7", "backend-engineer")
        self.assertIsNotNone(found)
        self.assertEqual(found.read_text(), "role-addressed")

    def test_ignores_a_handoff_for_a_different_task(self):
        self._write("TASK-2-company-pm-to-backend-engineer-1.md", "not this task")
        found = packet.find_handoff(self.root, "TASK-1", "backend-engineer-1", "backend-engineer")
        self.assertIsNone(found)

    def test_ignores_a_handoff_addressed_to_someone_else(self):
        self._write("TASK-1-company-pm-to-qa-engineer-1.md", "for qa, not backend")
        found = packet.find_handoff(self.root, "TASK-1", "backend-engineer-1", "backend-engineer")
        self.assertIsNone(found)

    def test_no_handoffs_dir_is_a_clean_miss(self):
        empty = Path(self.tmp.name) / "no-such-dir"
        self.assertIsNone(packet.find_handoff(empty, "TASK-1", "a", "r"))

    def test_newest_of_several_matches_wins(self):
        import time
        self._write("TASK-1-company-pm-to-backend-engineer-1.md", "first")
        time.sleep(0.01)
        self._write("TASK-1-company-pm-to-backend-engineer.md", "second, newer")
        found = packet.find_handoff(self.root, "TASK-1", "backend-engineer-1", "backend-engineer")
        self.assertEqual(found.read_text(), "second, newer")


class TestRenderCarriesTheHandoff(unittest.TestCase):
    def _task(self):
        return {"id": "TASK-1", "title": "t", "tier": 2, "branch": "b"}

    def test_handoff_text_appears_in_the_packet(self):
        body = packet.render(self._task(), why="w", verify="true",
                              handoff_text="REWRITE using the new column, not meta.ownerUserId")
        self.assertIn("HANDOFF FROM THE PM", body)
        self.assertIn("REWRITE using the new column", body)

    def test_no_handoff_text_means_no_section(self):
        body = packet.render(self._task(), why="w", verify="true", handoff_text=None)
        self.assertNotIn("HANDOFF FROM THE PM", body)

    def test_oversized_handoff_still_trips_the_budget(self):
        # A handoff big enough to blow the packet budget should fail loudly,
        # same as an oversized brief already does — not silently truncate.
        huge = "x" * (packet.TOKEN_BUDGET * packet.CHARS_PER_TOKEN * 2)
        with self.assertRaises(packet.PacketTooLarge):
            packet.render(self._task(), why="w", verify="true", handoff_text=huge)


class TestRenderCarriesMatchingLessons(unittest.TestCase):
    def _task(self):
        return {"id": "TASK-1", "title": "t", "tier": 2, "branch": "b"}

    def test_lessons_appear_with_a_citation_only_when_one_exists(self):
        body = packet.render(self._task(), why="w", verify="true", lessons=[
            {"pattern": "exit code swallowed", "fix": "propagate it",
             "source_ref": {"type": "commit", "ref": "6f2fea7"}},
            {"pattern": "PM polled", "fix": "wait for notices", "source_ref": None},
        ])
        self.assertIn("LESSONS THAT APPLY TO THIS TASK", body)
        self.assertIn("  - exit code swallowed → propagate it [source: commit 6f2fea7]\n", body)
        self.assertIn("  - PM polled → wait for notices\n", body)

    def test_no_lessons_means_no_section(self):
        for none in (None, []):
            body = packet.render(self._task(), why="w", verify="true", lessons=none)
            self.assertNotIn("LESSONS THAT APPLY", body)
        self.assertEqual(packet.render(self._task(), why="w", verify="true"),
                         packet.render(self._task(), why="w", verify="true", lessons=None))

    def test_lessons_are_bounded_and_clipped(self):
        many = [{"pattern": f"pattern-{i} " + "y" * 1000, "fix": "f"} for i in range(10)]
        body = packet.render(self._task(), why="w", verify="true", lessons=many)
        self.assertIn("pattern-0", body)
        self.assertNotIn(f"pattern-{packet.LESSONS_IN_PACKET}", body)
        self.assertNotIn("y" * packet.LESSON_CHARS, body)


if __name__ == "__main__":
    unittest.main()
