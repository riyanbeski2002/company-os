"""events.jsonl durability: backups, integrity checks, torn tails, real crashes.

The log is the only authoritative state Company OS has, and before this it had
no copy anywhere and no way to say what was wrong with it: read() hard-fails on
one bad line, and a crash that left a partial last line made the next append()
fuse its event onto it — two bad lines, silently. This covers:

- `company backup`: a complete, byte-identical copy taken under the append
  lock, outside the repo, that doesn't pile up duplicates;
- check_integrity / `company doctor`: every line JSON, seq contiguous,
  trailing newline — reported, never raised;
- append() refusing a torn tail rather than guessing at it, with no false
  positive on a healthy log;
- a restore from backup that `company rebuild --verify` accepts;
- a writer genuinely SIGKILLed mid-append().

Every CLI call runs with HOME pointed into the tempdir, so a default-location
backup can never land in the operator's real ~/.company-backups.
"""

import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools" / "company"
sys.path.insert(0, str(TOOLS))

from eventlog import (EventLog, TornTailError, _flock_with_timeout,  # noqa: E402
                      check_integrity, compact, make_event)
import backup  # noqa: E402
import taskstate  # noqa: E402

CLI = TOOLS / "cli.py"


def heartbeat(i=0):
    return make_event(event="WORKER_HEARTBEAT", actor="w", project="p",
                      task="T-1", data={"i": i})


class DurabilityCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.root = base / "repo" / ".company"
        (self.root / "events").mkdir(parents=True)
        (self.root / "tasks").mkdir()
        self.log = EventLog(self.root)

    def _cli(self, *args):
        env = dict(os.environ, HOME=str(self.home), COMPANY_PROJECT="p")
        env.pop("COMPANY_ACTOR", None)
        env.pop("COMPANY_ROOT", None)
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env)

    def _write_lines(self, *events, tail=""):
        """A log written directly, so seqs and corruption are exactly as given."""
        body = "".join((e if isinstance(e, str) else compact(e)) + "\n" for e in events)
        self.log.path.write_text(body + tail, encoding="utf-8")

    def _seq(self, n):
        return {**heartbeat(n), "seq": n}


class TestTornTailRefusal(DurabilityCase):
    def test_a_healthy_log_is_unaffected(self):
        self.log.path.touch()  # `company init` creates it empty
        for i in range(5):
            self.log.append(heartbeat(i))
        self.assertEqual([e["seq"] for e in self.log.read()], [1, 2, 3, 4, 5])
        self.assertTrue(self.log.path.read_bytes().endswith(b"\n"))

    def test_a_partial_last_line_is_refused_and_nothing_is_written(self):
        self.log.append(heartbeat())
        with open(self.log.path, "a") as fh:
            fh.write('{"event":"WORKER_HEAR')
        before = self.log.path.read_bytes()

        with self.assertRaises(TornTailError) as ctx:
            self.log.append(heartbeat(1))
        self.assertIn("company doctor", str(ctx.exception))
        self.assertEqual(self.log.path.read_bytes(), before)

    def test_complete_json_missing_only_its_newline_is_still_refused(self):
        # It parses, but there's no knowing the write that produced it finished.
        self._write_lines(self._seq(1), tail=compact(self._seq(2)))
        with self.assertRaises(TornTailError):
            self.log.append(heartbeat())

    def test_repairing_the_tail_by_hand_lets_appends_resume(self):
        self.log.append(heartbeat())
        good = self.log.path.read_bytes()
        with open(self.log.path, "ab") as fh:
            fh.write(b'{"partial')
        with self.assertRaises(TornTailError):
            self.log.append(heartbeat())
        self.log.path.write_bytes(good)  # the operator's own repair
        self.assertEqual(self.log.append(heartbeat())["seq"], 2)

    def test_company_event_reports_it_without_a_traceback(self):
        self.log.append(heartbeat())
        with open(self.log.path, "a") as fh:
            fh.write('{"half')
        r = self._cli("event", "T-1", "TASK_BLOCKED", "--actor", "pm", "--no-rebuild")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ends mid-line", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class TestCheckIntegrity(DurabilityCase):
    def test_a_healthy_log_has_no_problems(self):
        for i in range(3):
            self.log.append(heartbeat(i))
        report = check_integrity(self.log.path)
        self.assertEqual(report["problems"], [])
        self.assertEqual((report["events"], report["lines"]), (3, 3))

    def test_an_empty_log_is_healthy(self):
        self.log.path.touch()
        self.assertEqual(check_integrity(self.log.path)["problem_count"], 0)

    def test_one_bad_line_is_one_problem_not_a_cascade_of_gaps(self):
        self._write_lines(self._seq(1), "{not json", self._seq(3), self._seq(4))
        report = check_integrity(self.log.path)
        self.assertEqual(report["problem_count"], 1, report["problems"])
        self.assertIn("line 2 is not valid JSON", report["problems"][0])

    def test_a_seq_gap(self):
        self._write_lines(self._seq(1), self._seq(2), self._seq(4))
        [problem] = check_integrity(self.log.path)["problems"]
        self.assertIn("seq 4 follows 2 — a gap", problem)

    def test_a_repeated_seq(self):
        self._write_lines(self._seq(1), self._seq(2), self._seq(2))
        [problem] = check_integrity(self.log.path)["problems"]
        self.assertIn("repeated or out-of-order", problem)

    def test_a_log_not_starting_at_one(self):
        self._write_lines(self._seq(2), self._seq(3))
        [problem] = check_integrity(self.log.path)["problems"]
        self.assertIn("seq 2 follows 0", problem)

    def test_a_missing_seq(self):
        self._write_lines(self._seq(1), heartbeat())
        [problem] = check_integrity(self.log.path)["problems"]
        self.assertIn("line 2 has no integer seq", problem)

    def test_a_blank_line(self):
        self._write_lines(self._seq(1), "", self._seq(3))
        [problem] = check_integrity(self.log.path)["problems"]
        self.assertIn("line 2 is blank", problem)

    def test_no_trailing_newline(self):
        self._write_lines(self._seq(1), tail=compact(self._seq(2)))
        [problem] = check_integrity(self.log.path)["problems"]
        self.assertIn("line 2 has no trailing newline", problem)

    def test_the_listed_problems_are_capped_but_the_count_is_not(self):
        self._write_lines(*["{bad"] * 50)
        report = check_integrity(self.log.path)
        self.assertEqual(report["problem_count"], 50)
        self.assertEqual(len(report["problems"]), 20)


class TestDoctorIntegrity(DurabilityCase):
    def _doctor(self):
        r = self._cli("doctor")
        self.assertNotIn("Traceback", r.stderr)
        out = json.loads(r.stdout)
        return r, out, {c["check"]: c for c in out["checks"]}

    def test_a_corrupt_log_is_reported_and_blocks_without_crashing(self):
        self._write_lines(self._seq(1), self._seq(3), tail='{"torn')
        r, out, checks = self._doctor()
        self.assertEqual(r.returncode, 1)
        integrity = checks["event log integrity"]
        self.assertFalse(integrity["ok"])
        self.assertIn("seq 3 follows 1", integrity["detail"])
        self.assertIn("no trailing newline", integrity["detail"])
        self.assertTrue(any(b.startswith("event log integrity") for b in out["blocking"]))
        # The rest of doctor still ran instead of dying in read().
        self.assertIn("unreadable", checks["baseline recorded"]["detail"])

    def test_a_healthy_log_passes(self):
        self.log.append(heartbeat())
        _, out, checks = self._doctor()
        self.assertTrue(checks["event log integrity"]["ok"])
        self.assertFalse(any(b.startswith("event log integrity") for b in out["blocking"]))

    def test_a_missing_backup_is_flagged_but_not_blocking(self):
        self.log.append(heartbeat())
        _, out, checks = self._doctor()
        self.assertFalse(checks["event log backed up"]["ok"])
        self.assertIn("company backup", checks["event log backed up"]["detail"])
        self.assertFalse(any(b.startswith("event log backed up") for b in out["blocking"]))

    def test_an_existing_backup_reports_how_far_behind_it_is(self):
        self.log.append(heartbeat())
        self.assertEqual(self._cli("backup").returncode, 0)
        self.log.append(heartbeat(1))
        self.log.append(heartbeat(2))
        _, _, checks = self._doctor()
        self.assertTrue(checks["event log backed up"]["ok"])
        self.assertIn("2 event(s) appended since", checks["event log backed up"]["detail"])


class TestBackup(DurabilityCase):
    def _backup(self, *extra):
        r = self._cli("backup", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_backup_is_a_complete_byte_identical_copy_outside_the_repo(self):
        for i in range(10):
            self.log.append(heartbeat(i))
        out = self._backup()
        copy = Path(out["backup"])
        self.assertEqual(copy.read_bytes(), self.log.path.read_bytes())
        self.assertEqual(out["events"], 10)
        self.assertTrue(out["intact"] and out["written"])
        # Named from the CLI's own resolution; this process has the real HOME.
        self.assertEqual(copy.parent.name, backup.default_dir(self.root).name)
        self.assertTrue(copy.is_relative_to(self.home / ".company-backups"))
        self.assertFalse(copy.is_relative_to(self.root.parent))
        self.assertEqual(EventLog(self.root).read(), [json.loads(l) for l in copy.read_text().splitlines()])

    def test_rerunning_on_an_unchanged_log_writes_nothing_new(self):
        self.log.append(heartbeat())
        first = self._backup()
        second = self._backup()
        self.assertFalse(second["written"])
        self.assertEqual(second["backup"], first["backup"])
        self.assertEqual(len(list(Path(first["dest"]).glob("events-*.jsonl"))), 1)

    def test_a_changed_log_gets_a_new_backup_and_the_old_one_is_kept(self):
        self.log.append(heartbeat())
        first = self._backup()
        old = Path(first["backup"]).read_bytes()
        self.log.append(heartbeat(1))
        second = self._backup()
        self.assertTrue(second["written"])
        self.assertEqual(Path(second["backup"]).read_bytes(), self.log.path.read_bytes())
        self.assertEqual(Path(first["backup"]).read_bytes(), old)
        self.assertEqual(backup.latest(Path(first["dest"])), Path(second["backup"]))

    def test_dest_override(self):
        self.log.append(heartbeat())
        dest = Path(self.tmp.name) / "elsewhere"
        out = self._backup("--dest", str(dest))
        self.assertEqual(Path(out["backup"]).parent, dest)

    def test_same_named_repos_in_different_places_never_share_a_folder(self):
        a = backup.default_dir(Path("/x/one/app/.company"))
        b = backup.default_dir(Path("/x/two/app/.company"))
        self.assertNotEqual(a, b)
        self.assertTrue(a.name.startswith("app-") and b.name.startswith("app-"))

    def test_a_damaged_log_is_still_backed_up_but_flagged(self):
        self._write_lines(self._seq(1), tail='{"torn')
        r = self._cli("backup")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertFalse(out["intact"])
        self.assertEqual(Path(out["backup"]).read_bytes(), self.log.path.read_bytes())
        self.assertIn("not intact", r.stderr)

    def test_no_log_is_an_error_not_an_empty_backup(self):
        r = self._cli("backup")
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing to back up", r.stderr)
        self.assertFalse((self.home / ".company-backups").exists())

    def test_snapshot_waits_for_the_append_lock(self):
        self.log.append(heartbeat())
        target = Path(self.tmp.name) / "snap.jsonl"
        with open(self.log.lockpath, "r+") as lock:
            _flock_with_timeout(lock)
            t = threading.Thread(target=self.log.snapshot, args=(target,))
            t.start()
            time.sleep(0.3)
            self.assertFalse(target.exists(), "snapshot ran while a writer held the lock")
            fcntl.flock(lock, fcntl.LOCK_UN)
        t.join(5)
        self.assertEqual(target.read_bytes(), self.log.path.read_bytes())


class TestRestoreFromBackup(DurabilityCase):
    def setUp(self):
        super().setUp()
        self.log.append(make_event(
            event="TASK_CREATED", actor="pm", project="p", task="TASK-7",
            data={"title": "Thing", "owner": "b1", "gates": ["review"], "tier": 2}))
        self.log.append(make_event(
            event="TASK_ASSIGNED", actor="pm", project="p", task="TASK-7",
            data={"owner": "b1"}))
        taskstate.rebuild(self.root)
        r = self._cli("backup")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.saved = Path(json.loads(r.stdout)["backup"])

    def _verify(self):
        return self._cli("rebuild", "--verify")

    def test_restore_after_corruption(self):
        with open(self.log.path, "a") as fh:
            fh.write("{garbage\n")
        self.assertNotEqual(self._verify().returncode, 0)

        shutil.copyfile(self.saved, self.log.path)
        r = self._verify()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"] and out["verified"])
        self.assertEqual(out["tasks"], 1)

    def test_restore_after_deletion(self):
        self.log.path.unlink()
        self.assertEqual(self._verify().returncode, 4)  # TASK-7.json now has no events

        shutil.copyfile(self.saved, self.log.path)
        r = self._verify()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(check_integrity(self.log.path)["problem_count"], 0)


# A real writer process, killed with SIGKILL while inside append() with the
# lock held. The child stalls at a chosen point by shadowing names inside the
# eventlog module only — the lock, seq assignment and file handling are the
# real code — then signals readiness so the kill lands exactly there.
CHILD = r"""
import os, sys, time
sys.path.insert(0, {tools!r})
import eventlog
from eventlog import EventLog, make_event

mode, root, ready = sys.argv[1:4]
log = EventLog(root)
ev = lambda i: make_event(event="WORKER_HEARTBEAT", actor="w", project="p",
                          task="T-1", data={{"i": i}})
for i in range(5):
    log.append(ev(i))

def stall():
    open(ready, "w").close()
    time.sleep(60)

if mode == "torn":
    # The write dies halfway through its line.
    real_open = open
    class HalfWrite:
        def __init__(self, fh): self.fh = fh
        def __enter__(self): return self
        def __exit__(self, *exc): return self.fh.__exit__(*exc)
        def __getattr__(self, name): return getattr(self.fh, name)
        def write(self, s):
            self.fh.write(s[: len(s) // 2])
            self.fh.flush()
            os.fsync(self.fh.fileno())
            stall()
    eventlog.open = lambda path, m="r", *a, **kw: (
        HalfWrite(real_open(path, m, *a, **kw)) if m == "a" else real_open(path, m, *a, **kw))
else:
    # The whole line reached the OS; the kill lands before fsync returns.
    eventlog.os.fsync = lambda fd: stall()
log.append(ev("killed"))
"""


class TestKilledMidAppend(DurabilityCase):
    def _kill_mid_append(self, mode):
        ready = Path(self.tmp.name) / "ready"
        script = CHILD.format(tools=str(TOOLS))
        proc = subprocess.Popen([sys.executable, "-c", script, mode, str(self.root), str(ready)])
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.monotonic() + 15
        while not ready.exists():
            self.assertIsNone(proc.poll(), "writer exited before reaching the kill point")
            self.assertLess(time.monotonic(), deadline, "writer never reached the kill point")
            time.sleep(0.01)
        os.kill(proc.pid, signal.SIGKILL)
        self.assertEqual(proc.wait(10), -signal.SIGKILL)

    def _durable_prefix(self, count):
        lines = self.log.path.read_bytes().split(b"\n")
        return [json.loads(l) for l in lines[:count]]

    def test_a_torn_write_loses_nothing_fsynced_and_is_detected_not_compounded(self):
        self._kill_mid_append("torn")

        # (b) every event fsync'd before the kill is intact, in order.
        before_kill = self._durable_prefix(5)
        self.assertEqual([e["seq"] for e in before_kill], [1, 2, 3, 4, 5])
        self.assertEqual([e["data"]["i"] for e in before_kill], [0, 1, 2, 3, 4])

        # (a) the torn tail is reported by doctor's check...
        report = check_integrity(self.log.path)
        self.assertEqual(report["events"], 5)
        self.assertTrue(any("no trailing newline" in p for p in report["problems"]))
        # ...and the next append refuses rather than fusing onto it. The dead
        # writer's lock was released by the kernel, so this is a refusal, not
        # a lock timeout.
        torn = self.log.path.read_bytes()
        with self.assertRaises(TornTailError):
            self.log.append(heartbeat(99))
        self.assertEqual(self.log.path.read_bytes(), torn)

    def test_a_writer_killed_holding_the_lock_does_not_wedge_the_log(self):
        self._kill_mid_append("unsynced")

        events = self.log.read()
        self.assertEqual([e["seq"] for e in events], [1, 2, 3, 4, 5, 6])
        self.assertEqual(check_integrity(self.log.path)["problem_count"], 0)
        self.assertEqual(self.log.append(heartbeat(7))["seq"], 7)


if __name__ == "__main__":
    unittest.main()
