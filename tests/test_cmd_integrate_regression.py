"""Commit 6cdd62d (2026-10-21, "4 ECC/paperclip orchestration-reliability
mechanisms...") rewrote cmd_integrate's gate check to be fail-closed on any
check_done() reason, but deleted the line that assigns `reasons` while
keeping the line that reads it — every `company integrate` call raised
`NameError: reasons`, unconditionally. No existing test caught this because
test_integrate.py only exercises the `integrate` module's helper functions,
never `cli.cmd_integrate` itself.

This runs cmd_integrate end to end (real EventLog, real taskstate.fold) and
would fail with the NameError if the assignment regressed again.
"""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import cli  # noqa: E402
from eventlog import EventLog, make_event  # noqa: E402


class Args:
    def __init__(self, **kw):
        self.root = None
        self.task = None
        self.test_command = "true"
        self.force = False
        self.actor = "pm"
        self.json = True
        self.__dict__.update(kw)


class TestCmdIntegrateDoesNotCrash(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.root = self.repo / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gates_not_satisfied_path_does_not_raise_nameerror(self):
        # TASK_CREATED + IMPLEMENTATION_READY gives evidence.diff, so the
        # task qualifies as an integrate target, but no TEST_RUN event means
        # check_done() returns a non-empty `reasons` list — the exact branch
        # that read `reasons` without it ever being assigned.
        self.log.append(make_event(event="TASK_CREATED", actor="pm", project="p", task="T-1"))
        self.log.append(make_event(
            event="IMPLEMENTATION_READY", actor="backend-engineer", project="p", task="T-1",
            evidence={"commit": "abc123"}))

        args = Args(root=str(self.root), task="T-1")
        with self.assertRaises(SystemExit) as ctx:
            cli.cmd_integrate(args)

        # A regression of the deleted assignment raises NameError instead,
        # which would surface as an uncaught exception, not SystemExit.
        self.assertIn(ctx.exception.code, (0, 3))


if __name__ == "__main__":
    unittest.main()
