"""Step 1 verification: the event log is concurrency-safe and replay is exact."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

from eventlog import EventLog, EvidenceError, make_event  # noqa: E402
import taskstate  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"


class TestAppend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_seq_is_contiguous(self):
        for i in range(20):
            self.log.append(make_event(
                event="WORKER_HEARTBEAT", actor="w1", project="p", task="TASK-1",
                data={"i": i}))
        seqs = [e["seq"] for e in self.log.read()]
        self.assertEqual(seqs, list(range(1, 21)))

    def test_one_line_per_event(self):
        self.log.append(make_event(
            event="TASK_CREATED", actor="pm", project="p", task="TASK-1",
            data={"title": "multi\nline\ttitle with \"quotes\""}))
        raw = self.log.path.read_text(encoding="utf-8")
        self.assertEqual(raw.count("\n"), 1)

    def test_evidence_required_for_assertions(self):
        with self.assertRaises(EvidenceError):
            self.log.append(make_event(
                event="REVIEW_PASSED", actor="r1", project="p", task="TASK-1"))

    def test_test_run_requires_exit_code(self):
        with self.assertRaises(EvidenceError):
            self.log.append(make_event(
                event="TEST_RUN", actor="w1", project="p", task="TASK-1",
                data={"cmd": "pytest"}, evidence={"log": "x.log"}))

    def test_implementation_ready_requires_commit(self):
        with self.assertRaises(EvidenceError):
            self.log.append(make_event(
                event="IMPLEMENTATION_READY", actor="w1", project="p", task="TASK-1",
                evidence={"log": "not-a-sha"}))

    def test_unknown_event_rejected(self):
        with self.assertRaises(ValueError):
            self.log.append(make_event(
                event="LOOKS_PRODUCTIVE", actor="w1", project="p", task="TASK-1"))


class TestConcurrency(unittest.TestCase):
    """8 processes x 25 events. Any lost update or duplicated seq fails here."""

    def test_parallel_writers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".company"
            (root / "events").mkdir(parents=True)
            (root / "tasks").mkdir(parents=True)

            script = (
                "import sys;sys.path.insert(0,%r)\n"
                "from eventlog import EventLog, make_event\n"
                "log=EventLog(%r)\n"
                "for i in range(25):\n"
                "    log.append(make_event(event='WORKER_HEARTBEAT',"
                "actor=sys.argv[1],project='p',task='TASK-1',data={'i':i}))\n"
                % (str(HERE.parent / "tools" / "company"), str(root))
            )
            procs = [
                subprocess.Popen([sys.executable, "-c", script, f"w{n}"])
                for n in range(8)
            ]
            for p in procs:
                self.assertEqual(p.wait(), 0)

            events = EventLog(root).read()
            self.assertEqual(len(events), 200)
            self.assertEqual(sorted(e["seq"] for e in events), list(range(1, 201)))
            actors = {e["actor"] for e in events}
            self.assertEqual(len(actors), 8)


class TestReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        (self.root / "tasks").mkdir(parents=True)
        self.log = EventLog(self.root)
        self.log.append(make_event(
            event="TASK_CREATED", actor="pm", project="p", task="TASK-7",
            data={"title": "Thing", "owner": "b1", "gates": ["review"], "tier": 2}))
        self.log.append(make_event(
            event="TASK_ASSIGNED", actor="pm", project="p", task="TASK-7",
            data={"owner": "b1"}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_rebuild_then_verify_is_clean(self):
        taskstate.rebuild(self.root)
        count, mismatches = taskstate.rebuild(self.root, verify=True)
        self.assertEqual(count, 1)
        self.assertEqual(mismatches, [])

    def test_verify_detects_hand_edit(self):
        taskstate.rebuild(self.root)
        p = taskstate.task_path(self.root, "TASK-7")
        doc = json.loads(p.read_text())
        doc["status"] = "DONE"          # a lie, told directly to the view
        p.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n")
        _, mismatches = taskstate.rebuild(self.root, verify=True)
        self.assertTrue(any("differs from replay" in m for m in mismatches))

    def test_verify_detects_stray_task_file(self):
        taskstate.rebuild(self.root)
        (self.root / "tasks" / "TASK-999.json").write_text("{}\n")
        _, mismatches = taskstate.rebuild(self.root, verify=True)
        self.assertTrue(any("no events produce it" in m for m in mismatches))

    def test_replay_is_deterministic_across_runs(self):
        a = taskstate.fold(self.log.read())
        b = taskstate.fold(self.log.read())
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
