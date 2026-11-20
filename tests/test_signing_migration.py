"""ESC-002: the signing mode comes from the key, never from the log.

Final review of 0ac8e0c (sr/legacy.py): a "legacy window" decided from the
log itself — no signed event yet means unsigned task state still counts —
is a window a worker controls, since it can write the log. Editing an
unsigned TASK_CREATED in place to `gates: []`, or zeroing every MAC on a
signed log, let `task advance --to DONE` close an unreviewed task.

Now: if .company/secrets/gate.key exists, only PM-signed task state counts.
The PM process that first creates the key carries the old log over as
signed TASK_SNAPSHOTs (gatesig.migrate) — the PM's first `company` command
after deploy does it.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import gatesig  # noqa: E402
import taskstate  # noqa: E402
from eventlog import EventLog, make_event  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"
GATE_ROLES = {"review": "code-reviewer"}


class SigningCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        for d in ("events", "tasks", "projects"):
            (self.root / d).mkdir(parents=True)
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _cli(self, *args, actor=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("COMPANY_")}
        env["COMPANY_PROJECT"] = "p"
        if actor:
            env["COMPANY_ACTOR"] = actor
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env)

    def _legacy_history(self):
        """An existing project's log from before signing: all unsigned."""
        for ev in (
            make_event(event="TASK_CREATED", actor="company-pm", project="p", task="T-1",
                       data={"title": "gated", "owner": "be-1", "gates": ["review"],
                             "owned_globs": ["api/**"], "branch": "task/1"}),
            make_event(event="IMPLEMENTATION_READY", actor="be-1", project="p", task="T-1",
                       evidence={"commit": "abc1234"}),
            make_event(event="TEST_RUN", actor="be-1", project="p", task="T-1",
                       data={"exit_code": 0}, evidence={"log": "t"}),
            make_event(event="TASK_CREATED", actor="company-pm", project="p", task="T-2",
                       data={"title": "shipped", "owner": "be-2", "gates": []}),
            make_event(event="MERGED", actor="integration", project="p", task="T-2",
                       evidence={"commit": "def5678"}),
            make_event(event="TASK_CREATED", actor="company-pm", project="p", task="T-3",
                       data={"title": "dropped", "owner": "be-3"}),
            make_event(event="STATUS_CHANGED", actor="company-pm", project="p", task="T-3",
                       data={"to": "ABANDONED"}),
            make_event(event="BASELINE_RECORDED", actor="company-cli", project="p",
                       data={"exit_code": 1, "failures": 2, "green": False},
                       evidence={"log": "baseline.log"}),
            make_event(event="ESCALATION_RAISED", actor="be-1", project="p", task="T-1",
                       data={"id": "ESC-1", "need": "a", "kind": "decision", "blocking": True}),
            make_event(event="ESCALATION_RAISED", actor="be-1", project="p", task="T-1",
                       data={"id": "ESC-2", "need": "b", "kind": "decision", "blocking": True}),
            make_event(event="ESCALATION_RESOLVED", actor="riyan", project="p", task="T-1",
                       data={"id": "ESC-1", "resolution": "yes"}),
        ):
            self.log.append(ev)

    def _edit_in_place(self, old, new):
        self.log.path.write_text(self.log.path.read_text().replace(old, new))

    def _advance_done(self, tid="T-1"):
        return self._cli("task", "advance", tid, "--to", "DONE")


class TestMigration(SigningCase):
    def test_the_first_pm_command_migrates_and_preserves_state(self):
        import escalations
        self._legacy_history()
        before = taskstate.fold(self.log.read())
        self.assertFalse(gatesig.key_path(self.root).exists())

        r = self._cli("status", "--json")  # any PM command
        self.assertEqual(r.returncode, 0, r.stderr)
        key = gatesig.load_key(self.root)
        self.assertIsNotNone(key)
        self.assertEqual(oct(gatesig.key_path(self.root).stat().st_mode & 0o777), "0o600")

        after = taskstate.load(self.root)
        for tid in ("T-1", "T-2", "T-3"):
            for field in ("status", "gates", "owner", "owned_globs", "branch"):
                self.assertEqual(after[tid].get(field), before[tid].get(field), (tid, field))
            self.assertTrue(after[tid]["created_signed"], tid)
        self.assertEqual(after["T-2"]["evidence"]["merged"], "def5678")
        self.assertEqual(after["T-3"]["status"], "ABANDONED")
        import cli
        self.assertEqual(cli._baseline(self.root, "p")["failures"], 2)
        self.assertEqual(set(escalations.open_escalations(self.root)), {"ESC-2"})

    def test_migration_is_idempotent(self):
        self._legacy_history()
        self._cli("status")
        n = len(self.log.read())
        for _ in range(2):
            self._cli("status")
            self.assertIsNotNone(gatesig.load_key(self.root, create=True))
        self.assertEqual(len(self.log.read()), n)
        snaps = [e for e in self.log.read() if e["event"] == "TASK_SNAPSHOT"]
        self.assertEqual(sorted(e["task"] for e in snaps), ["T-1", "T-2", "T-3"])

    def test_a_worker_never_migrates(self):
        self._legacy_history()
        self._cli("event", "T-1", "HANDOFF_WRITTEN", actor="be-1")
        self.assertFalse(gatesig.key_path(self.root).exists())

    def test_a_signed_log_whose_key_is_gone_is_not_resigned(self):
        self._legacy_history()
        self._cli("status")
        gatesig.key_path(self.root).unlink()
        with self.assertRaises(ValueError):
            gatesig.load_key(self.root, create=True)
        self.assertFalse(gatesig.key_path(self.root).exists())


class TestLegacyWindowIsGone(SigningCase):
    """sr/legacy.py, each case."""

    def test_in_place_edit_on_a_new_projects_log_fails_closed(self):
        """Key first (a project started after deploy), then a definition a
        worker wrote or edited: unsigned, so it never counts."""
        gatesig.load_key(self.root, create=True)
        self._legacy_history()  # all unsigned, after the key
        self._edit_in_place('"gates":["review"]', '"gates":[]')
        self.assertNotIn("created_signed", taskstate.load(self.root)["T-1"])
        r = self._advance_done()
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("not signed by the PM", r.stdout)

    def test_in_place_edit_after_migration_fails_closed(self):
        self._legacy_history()
        self._cli("status")  # migrates
        lines = self.log.path.read_text().splitlines()
        lines[0] = lines[0].replace('"gates":["review"]', '"gates":[]')  # the legacy definition
        self.log.path.write_text("\n".join(lines) + "\n")
        task = taskstate.load(self.root)["T-1"]
        self.assertEqual(task["gates"], ["review"])  # from the signed snapshot
        self.assertEqual(self._advance_done().returncode, 3)
        # Editing the snapshot itself breaks its MAC: the task is undefined.
        self._edit_in_place('"gates":["review"]', '"gates":[]')
        self.assertNotIn("created_signed", taskstate.load(self.root)["T-1"])
        self.assertEqual(self._advance_done().returncode, 3)
        self.assertNotEqual(taskstate.load(self.root)["T-1"]["status"], "DONE")

    def test_stripping_every_mac_fails_closed(self):
        self._legacy_history()
        self._cli("status")
        text = re.sub(r'"(pm_mac|launch_mac|verdict_mac)":"[0-9a-f]+"', r'"\1":"00"',
                      self.log.path.read_text())
        self.log.path.write_text(text.replace('"gates":["review"]', '"gates":[]'))
        tasks = taskstate.load(self.root)
        self.assertFalse(any(t.get("created_signed") for t in tasks.values()))
        self.assertNotIn("merged", tasks.get("T-2", {"evidence": {}})["evidence"])
        self.assertEqual(self._advance_done().returncode, 3)
        import escalations
        self.assertIn("ESC-1", escalations.open_escalations(self.root))  # unresolved again

    def test_unsigned_status_merge_baseline_and_resolution_do_not_count(self):
        import cli
        import escalations
        self._legacy_history()
        self._cli("status")
        for ev in (
            make_event(event="STATUS_CHANGED", actor="be-1", project="p", task="T-1",
                       data={"to": "DONE"}),
            make_event(event="MERGED", actor="be-1", project="p", task="T-1",
                       evidence={"commit": "abc1234"}),
            make_event(event="BASELINE_RECORDED", actor="be-1", project="p",
                       data={"exit_code": 1, "failures": 999, "green": False},
                       evidence={"log": "x"}),
            make_event(event="ESCALATION_RESOLVED", actor="be-1", project="p", task="T-1",
                       data={"id": "ESC-2", "resolution": "self-approved"}),
        ):
            self.log.append(ev)
        task = taskstate.load(self.root)["T-1"]
        self.assertNotEqual(task["status"], "DONE")
        self.assertNotIn("merged", task["evidence"])
        self.assertEqual(cli._baseline(self.root, "p")["failures"], 2)
        self.assertIn("ESC-2", escalations.open_escalations(self.root))


class TestDoneNeedsASignedDefinition(SigningCase):
    def test_done_without_a_signed_task_created_or_snapshot_is_refused(self):
        gatesig.load_key(self.root, create=True)
        self.log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                                   task="T-9", data={"title": "ungated", "owner": "be-1"}))
        self.log.append(make_event(event="IMPLEMENTATION_READY", actor="be-1", project="p",
                                   task="T-9", evidence={"commit": "abc1234"}))
        self.log.append(make_event(event="TEST_RUN", actor="be-1", project="p", task="T-9",
                                   data={"exit_code": 0}, evidence={"log": "t"}))
        r = self._advance_done("T-9")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("not signed by the PM", r.stdout)

    def test_a_signed_ungated_task_reaches_done(self):
        self.log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                                   task="T-9", data={"title": "ungated", "owner": "be-1"}),
                        finalize=gatesig.pm_signer(self.root))
        self.log.append(make_event(event="IMPLEMENTATION_READY", actor="be-1", project="p",
                                   task="T-9", evidence={"commit": "abc1234"}))
        self.log.append(make_event(event="TEST_RUN", actor="be-1", project="p", task="T-9",
                                   data={"exit_code": 0}, evidence={"log": "t"}))
        r = self._advance_done("T-9")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(taskstate.load(self.root)["T-9"]["status"], "DONE")


if __name__ == "__main__":
    unittest.main()


class RefusedKeyCreateAppendsNothing(unittest.TestCase):
    def test_unwritable_secrets_fails_before_migrating(self):
        import gatesig
        from eventlog import EventLog, make_event
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / ".company"
            (root / "events").mkdir(parents=True)
            EventLog(root).append(make_event(event="TASK_CREATED", actor="company-pm",
                                             project="p", task="T-1",
                                             data={"title": "t", "gates": ["review"]}))
            before = len(EventLog(root).read())
            sec = root / "secrets"
            sec.mkdir(mode=0o500)
            try:
                self.assertIsNone(gatesig.pm_signer(root))
                self.assertEqual(len(EventLog(root).read()), before)
            finally:
                sec.chmod(0o700)
            self.assertIsNotNone(gatesig.pm_signer(root))  # PM can still sign afterwards
