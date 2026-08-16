"""Concurrency budget (D7). Exceeding the cap must queue, not spawn."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import slots  # noqa: E402


class TestSlots(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_acquire_under_cap_is_immediate(self):
        slot, queued = slots.acquire(self.root, "w1", cap=2, timeout=1)
        self.assertTrue(slot.exists())
        self.assertEqual(queued, 0)

    def test_cap_is_enforced(self):
        held = [subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
                for _ in range(2)]
        try:
            d = self.root / "state" / "slots"
            d.mkdir(parents=True)
            for i, p in enumerate(held):
                (d / f"held{i}.pid").write_text(str(p.pid))

            self.assertEqual(slots.live_count(self.root), 2)
            with self.assertRaises(slots.SlotTimeout):
                slots.acquire(self.root, "w3", cap=2, timeout=1.5, poll=0.2)
        finally:
            for p in held:
                p.kill()
                p.wait()

    def test_zombie_does_not_hold_a_slot(self):
        """A child that exited but was never reaped still answers kill(pid, 0).

        Counting it as live would queue every later worker behind a corpse.
        """
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        time.sleep(0.5)                      # exited, deliberately not reaped
        d = self.root / "state" / "slots"
        d.mkdir(parents=True)
        (d / "zombie.pid").write_text(str(proc.pid))
        try:
            self.assertEqual(slots.live_count(self.root), 0)
        finally:
            proc.wait()

    def test_dead_worker_slot_is_reclaimed(self):
        """A kill -9'd worker must not leak its slot forever."""
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        d = self.root / "state" / "slots"
        d.mkdir(parents=True)
        (d / "dead.pid").write_text(str(proc.pid))

        self.assertEqual(slots.live_count(self.root), 0)
        self.assertFalse((d / "dead.pid").exists())

    def test_queued_worker_proceeds_when_a_slot_frees(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(1.5)"])
        d = self.root / "state" / "slots"
        d.mkdir(parents=True)
        (d / "busy.pid").write_text(str(proc.pid))

        import threading
        threading.Thread(target=proc.wait, daemon=True).start()  # reap on exit

        start = time.monotonic()
        slot, queued = slots.acquire(self.root, "w2", cap=1, timeout=10, poll=0.2)
        elapsed = time.monotonic() - start

        self.assertTrue(slot.exists())
        self.assertGreater(elapsed, 1.0)   # it genuinely waited
        self.assertGreater(queued, 0)

    def test_release_frees_the_slot(self):
        slot, _ = slots.acquire(self.root, "w1", cap=1, timeout=1)
        slots.release(slot)
        self.assertFalse(slot.exists())
        self.assertEqual(slots.live_count(self.root), 0)

    def test_garbage_slot_file_is_discarded(self):
        d = self.root / "state" / "slots"
        d.mkdir(parents=True)
        (d / "junk.pid").write_text("not-a-pid")
        self.assertEqual(slots.live_count(self.root), 0)


if __name__ == "__main__":
    unittest.main()
