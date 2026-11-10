"""`company run --detach` result file must stay valid JSON (2026-11-10: the
supervisor's stderr — e.g. an escalations.fold() warning — was interleaved
into detached.json, so nothing could json.load it)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "company"))

import cli  # noqa: E402


class TestSpawnDetached(unittest.TestCase):
    def test_stderr_never_lands_in_the_json_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state" / "workers" / "be-1"
            child = ("import json, sys; print('warning: noise', file=sys.stderr); "
                     "print(json.dumps({'ok': True}))")
            proc = cli._spawn_detached([sys.executable, "-c", child], state, "p")
            proc.wait(timeout=30)
            self.assertEqual(json.loads((state / "detached.json").read_text()), {"ok": True})
            self.assertIn("warning: noise", (state / "detached.err").read_text())


if __name__ == "__main__":
    unittest.main()
