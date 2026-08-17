"""check_registry.py: a real script, not a prose reminder to 'check the
registry occasionally.' Deterministic staleness by date arithmetic — same
answer every time, no agent has to remember to do it right."""

import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "capability-curator" / "scripts"))

import check_registry  # noqa: E402


class TestCheckRegistry(unittest.TestCase):
    def _write(self, entries):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        import yaml
        yaml.safe_dump({"entries": entries}, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_recent_entry_is_fresh(self):
        today = date(2026, 8, 17)
        recent = (today - timedelta(days=5)).isoformat()
        path = self._write([{"id": "x", "checked_at": recent}])
        result = check_registry.check(path, stale_after_days=90, today=today)
        self.assertEqual(len(result["fresh"]), 1)
        self.assertEqual(len(result["stale"]), 0)

    def test_old_entry_is_stale(self):
        today = date(2026, 8, 17)
        old = (today - timedelta(days=200)).isoformat()
        path = self._write([{"id": "x", "checked_at": old}])
        result = check_registry.check(path, stale_after_days=90, today=today)
        self.assertEqual(len(result["stale"]), 1)
        self.assertEqual(result["stale"][0]["id"], "x")
        self.assertEqual(result["stale"][0]["age_days"], 200)

    def test_boundary_is_exact_not_approximate(self):
        """Deterministic means the boundary is exact — this is the whole
        point of a script over a vague 'check occasionally' instruction."""
        today = date(2026, 8, 17)
        exactly_90 = (today - timedelta(days=90)).isoformat()
        path = self._write([{"id": "x", "checked_at": exactly_90}])
        result = check_registry.check(path, stale_after_days=90, today=today)
        self.assertEqual(len(result["stale"]), 0)  # 90 is not > 90

        one_more = (today - timedelta(days=91)).isoformat()
        path2 = self._write([{"id": "y", "checked_at": one_more}])
        result2 = check_registry.check(path2, stale_after_days=90, today=today)
        self.assertEqual(len(result2["stale"]), 1)

    def test_missing_checked_at_is_reported_not_silently_skipped(self):
        path = self._write([{"id": "no-date"}])
        result = check_registry.check(path, stale_after_days=90)
        self.assertIn("no-date", result["unparseable_checked_at"])

    def test_empty_registry_is_not_an_error(self):
        path = self._write([])
        result = check_registry.check(path, stale_after_days=90)
        self.assertEqual(result["total"], 0)


if __name__ == "__main__":
    unittest.main()
