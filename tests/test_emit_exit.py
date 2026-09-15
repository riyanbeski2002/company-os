"""SessionEnd fallback hook (cost audit, 2026-09-14): must write a terminal
record when the launcher never got the chance to, and must NOT write a
second one when it already did (or when it fires more than once for the
same session) — that duplication was measured tripling every real worker
exit in the ledger.
"""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

spec = importlib.util.spec_from_file_location(
    "emit_exit", HERE.parent / "hooks" / "emit_exit.py")
emit_exit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emit_exit)

from eventlog import EventLog, make_event  # noqa: E402


def _run(company_root: Path, task_id: str, actor: str, payload: dict):
    env = {"COMPANY_TASK": task_id, "COMPANY_ROOT": str(company_root),
           "COMPANY_ACTOR": actor}
    with mock.patch.dict("os.environ", env, clear=False), \
         mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), \
         mock.patch("sys.exit"):
        emit_exit.main()


class TestEmitExitDedup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "tasks").mkdir(parents=True)
        (self.root / "events").mkdir(parents=True)
        self.task_id = "TASK-1"
        (self.root / "tasks" / f"{self.task_id}.json").write_text(
            json.dumps({"id": self.task_id, "project": "proj", "owner": "pm"}))

    def tearDown(self):
        self.tmp.cleanup()

    def _events(self):
        return [e for e in EventLog(self.root).read() if e.get("event") == "WORKER_EXITED"]

    def test_writes_a_fallback_when_nothing_recorded_the_exit_yet(self):
        _run(self.root, self.task_id, "backend-engineer-1", {"session_id": "sid-1", "reason": "other"})
        self.assertEqual(len(self._events()), 1)

    def test_second_firing_for_the_same_session_is_a_no_op(self):
        payload = {"session_id": "sid-1", "reason": "other"}
        _run(self.root, self.task_id, "backend-engineer-1", payload)
        _run(self.root, self.task_id, "backend-engineer-1", payload)
        self.assertEqual(len(self._events()), 1)

    def test_no_op_when_the_launcher_already_recorded_the_real_exit(self):
        # Simulate worker.py's own authoritative write landing first.
        EventLog(self.root).append(make_event(
            event="WORKER_EXITED", actor="backend-engineer-1", project="proj",
            task=self.task_id,
            data={"exit_code": 0, "timed_out": False, "session_id": "sid-1",
                  "tokens": {"cache_creation": 10, "cache_read": 0, "input": 1, "output": 5}},
        ))
        _run(self.root, self.task_id, "backend-engineer-1", {"session_id": "sid-1", "reason": "other"})
        events = self._events()
        self.assertEqual(len(events), 1)
        self.assertIn("tokens", events[0]["data"])  # the real one, not a stub

    def test_different_sessions_each_still_get_their_own_fallback(self):
        # A genuine relaunch (a new session_id) must not be swallowed by the
        # dedup — that's real signal, not duplication.
        _run(self.root, self.task_id, "backend-engineer-1", {"session_id": "sid-1", "reason": "other"})
        _run(self.root, self.task_id, "backend-engineer-1", {"session_id": "sid-2", "reason": "other"})
        self.assertEqual(len(self._events()), 2)

    def test_missing_session_id_still_writes_but_never_matches_itself(self):
        # No session_id to dedup on: falls back to always writing rather than
        # risking silently dropping a real crash record.
        _run(self.root, self.task_id, "backend-engineer-1", {"reason": "other"})
        _run(self.root, self.task_id, "backend-engineer-1", {"reason": "other"})
        self.assertEqual(len(self._events()), 2)


if __name__ == "__main__":
    unittest.main()
