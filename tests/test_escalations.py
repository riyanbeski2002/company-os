"""Escalations (§9) — the PM's channel to the CEO.

The CEO is an active participant who can do things the PM cannot: open tmux
sessions, supply credentials, decide between defensible options. Being blocked
in silence is the failure, so this path has to work and has to be visible.
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import escalations  # noqa: E402
import gallery  # noqa: E402
import render  # noqa: E402
from eventlog import EventLog  # noqa: E402


class TestEscalationLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _raise(self, **kw):
        kw.setdefault("project", "p")
        kw.setdefault("actor", "company-pm")
        kw.setdefault("kind", "human_action")
        kw.setdefault("need", "open 2 tmux panes")
        return escalations.raise_escalation(self.root, **kw)

    def test_ids_increment(self):
        self.assertEqual(self._raise()["id"], "ESC-001")
        self.assertEqual(self._raise()["id"], "ESC-002")

    def test_open_escalation_is_visible(self):
        self._raise(task="T-1")
        open_now = escalations.fold(EventLog(self.root).read())
        self.assertIn("ESC-001", open_now)
        self.assertEqual(open_now["ESC-001"]["task"], "T-1")

    def test_resolved_escalation_drops_out(self):
        self._raise()
        escalations.resolve(self.root, "ESC-001", actor="riyan", project="p",
                            resolution="done")
        self.assertEqual(escalations.fold(EventLog(self.root).read()), {})

    def test_resolution_is_preserved_for_audit(self):
        self._raise()
        escalations.resolve(self.root, "ESC-001", actor="riyan", project="p",
                            resolution="gallery is up")
        record = escalations.all_escalations(EventLog(self.root).read())["ESC-001"]
        self.assertEqual(record["status"], "resolved")
        self.assertEqual(record["resolution"], "gallery is up")
        self.assertEqual(record["resolved_by"], "riyan")

    def test_cannot_resolve_unknown(self):
        with self.assertRaises(KeyError):
            escalations.resolve(self.root, "ESC-999", actor="riyan", project="p",
                                resolution="x")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            self._raise(kind="vibes")

    def test_empty_need_rejected(self):
        with self.assertRaises(ValueError):
            self._raise(need="   ")

    def test_views_are_rebuilt_from_the_log(self):
        self._raise(commands=["company gallery --open"])
        escalations.write_views(self.root, EventLog(self.root).read())
        text = (self.root / "escalations" / "ESC-001.md").read_text()
        self.assertIn("blocking", text)
        self.assertIn("company gallery --open", text)


class TestEscalationsAreSurfaced(unittest.TestCase):
    """A blocking ask nobody notices is the same as being stuck."""

    BLOCKING = [{"id": "ESC-001", "kind": "human_action", "blocking": True,
                 "need": "open 2 tmux panes", "raised_by": "company-pm",
                 "commands": ["company gallery --open"]}]

    def test_blocking_ask_is_the_next_action(self):
        text = render.status("p", [], self.BLOCKING)
        self.assertIn("NEEDS YOU — BLOCKING", text)
        self.assertIn("Next     you — ESC-001", text)

    def test_command_is_shown_verbatim(self):
        self.assertIn("$ company gallery --open", render.status("p", [], self.BLOCKING))

    def test_non_blocking_is_separated(self):
        text = render.status("p", [], [{**self.BLOCKING[0], "blocking": False,
                                        "kind": "decision"}])
        self.assertIn("NEEDS YOU", text)
        self.assertNotIn("BLOCKING", text)

    def test_report_leads_with_what_you_owe(self):
        text = render.report("p", [], self.BLOCKING)
        self.assertIn("## Waiting on you", text)


class TestGalleryPlan(unittest.TestCase):
    """The PM cannot open windows, so it must be able to say how many it needs."""

    TASKS = [
        {"id": "T-1", "tier": 2, "owner": "be-1", "status": "IN_PROGRESS", "title": "a"},
        {"id": "T-2", "tier": 2, "owner": "fe-2", "status": "DONE", "title": "b"},
        {"id": "T-3", "tier": 1, "owner": "rv-3", "status": "REVIEW", "title": "c"},
    ]

    def test_one_pane_per_live_tier2_task_plus_status(self):
        panes = gallery.panes_needed(self.TASKS)
        self.assertEqual([p["name"] for p in panes], ["status", "T-1"])

    def test_finished_and_tier1_work_gets_no_pane(self):
        names = [p["name"] for p in gallery.panes_needed(self.TASKS)]
        self.assertNotIn("T-2", names)   # done
        self.assertNotIn("T-3", names)   # tier 1

    def test_plan_reports_a_count_the_ceo_can_act_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = gallery.plan(Path(tmp) / ".company", self.TASKS)
            self.assertEqual(plan["sessions"], 1)
            self.assertEqual(plan["panes"], 2)

    def test_script_only_tails_and_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = gallery.script(Path(tmp) / ".company", self.TASKS)
        self.assertIn("tail -f", text)
        for verb in ("company event", "company task", "company run", "git "):
            self.assertNotIn(verb, text)


if __name__ == "__main__":
    unittest.main()
