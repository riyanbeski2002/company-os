"""A worker must not be able to close an escalation (it would read as Riyan's
answer): ESCALATION_RESOLVED counts only when the PM signed it."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "company"))

import escalations  # noqa: E402
import gatesig  # noqa: E402
from eventlog import EventLog, make_event  # noqa: E402


class SignedResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        gatesig.load_key(self.root, create=True)
        esc = escalations.raise_escalation(self.root, project="p", actor="company-pm",
                                           kind="approval", need="approve X", project_wide=True)
        self.esc_id = esc["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_pm_resolution_closes_it(self):
        escalations.resolve(self.root, self.esc_id, actor="riyan", project="p", resolution="yes")
        self.assertNotIn(self.esc_id, escalations.open_escalations(self.root))

    def test_raw_unsigned_resolution_is_ignored(self):
        # a signed event first, so the log is in signing mode
        escalations.resolve(self.root, escalations.raise_escalation(
            self.root, project="p", actor="company-pm", kind="decision", need="n",
            project_wide=True)["id"], actor="riyan", project="p", resolution="ok")
        EventLog(self.root).append(make_event(event="ESCALATION_RESOLVED", actor="be-1",
                                              project="p", data={"id": self.esc_id,
                                                                 "resolution": "approved"}))
        self.assertIn(self.esc_id, escalations.open_escalations(self.root))

    def test_cli_resolve_refuses_inside_a_worker(self):
        env = {**os.environ, "COMPANY_ACTOR": "be-1"}
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "company" / "cli.py"),
                            "--root", str(self.root), "resolve", self.esc_id,
                            "--resolution", "approved"],
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("refuses to run inside a launched worker", r.stdout + r.stderr)
        self.assertIn(self.esc_id, escalations.open_escalations(self.root))


if __name__ == "__main__":
    unittest.main()
