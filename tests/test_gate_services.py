"""gate_services (finos ESC-239 A): a gate role's declared services come up
outside the sandbox before it launches, from the MAIN checkout, and always
come down afterwards. Driven through the real worker.launch()/launch_group()
with the stand-in harness from test_launch_regressions."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

from test_launch_regressions import FakeHarnessCase  # noqa: E402
import worker  # noqa: E402


class GateServicesCase(FakeHarnessCase):
    def setUp(self):
        super().setUp()
        # The MAIN repo holds the reviewed branch: services get a snapshot of
        # its commit, read through the main gitdir (never the worktree's).
        g = ["git", "-C", str(self.repo), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "supabase").mkdir()
        (self.repo / "supabase" / "001.sql").write_text("select 1;\n")
        (self.repo / "secret.txt").write_text("TOPSECRET\n")
        os.symlink(self.repo / "secret.txt", self.repo / "supabase" / "002.sql")
        subprocess.run(g + ["add", "supabase"], check=True)
        subprocess.run(g + ["commit", "-qm", "branch"], check=True)
        for b in ("review-branch", "_gate-group-iam-qa-engineer"):
            subprocess.run(g + ["branch", b], check=True)
        self.trace = self.repo / "trace.jsonl"
        # The harness records the env it actually received.
        self.seen = self.repo / "seen_env.json"

    def _services(self, up_body, down=True, extra=""):
        up = self.repo / "up.py"
        up.write_text(
            "import json, os, sys\n"
            f"open({str(self.trace)!r}, 'a').write(json.dumps({{'cmd': 'up', 'cwd': os.getcwd(),"
            " 'wt': os.environ.get('COMPANY_GATE_WORKTREE'), 'id': os.environ.get('VERIFY_ID')}) + '\\n')\n"
            + up_body)
        down_cmd = (f'    down: "{sys.executable} -c \\"import os; open({str(self.trace)!r}, \'a\')'
                    f'.write(\'down \' + os.environ[\'VERIFY_ID\'] + chr(10))\\""\n') if down else ""
        (self.root / "config" / "project.yaml").write_text(
            "verify: 'true'\ngate_services:\n"
            f"  - up: '{sys.executable} {up}'\n"
            "    env_from_output: {DB_URL: 'DB_URL=(\\S+)'}\n" + down_cmd + extra)

    def _record_env_harness(self):
        self._harness(extra="")
        script = Path(self.tmp.name) / "fake_harness.py"
        script.write_text(
            "import json, os, sys\nsys.stdin.read()\n"
            f"json.dump({{k: os.environ.get(k) for k in ('DB_URL', 'COMPANY_TASK')}}, open({str(self.seen)!r}, 'w'))\n"
            + script.read_text().split("sys.stdin.read()\n", 1)[1])

    def _task(self, tid="T-1"):
        return {**super()._task(tid), "branch": "review-branch"}

    def _trace(self):
        return self.trace.read_text().splitlines() if self.trace.exists() else []


class TestGateServices(GateServicesCase):
    def test_gate_gets_parsed_env_and_services_come_down(self):
        self._services("print('starting'); print('DB_URL=postgres://u:p@127.0.0.1:5999/db')\n")
        self._record_env_harness()
        worker.launch(self.repo, self.root, self._task("TASK-UX.S1"), "packet",
                      "qa-engineer", "qa-1")
        self.assertEqual(json.loads(self.seen.read_text())["DB_URL"],
                         "postgres://u:p@127.0.0.1:5999/db")
        up = json.loads(self._trace()[0])
        # trust boundary: run from the main checkout, the branch passed as a
        # data-only snapshot of its commit (cleaned up afterwards)
        self.assertEqual(Path(up["cwd"]).resolve(), self.repo.resolve())
        self.assertEqual(Path(up["wt"]), self.root / "state" / "gate-services" / "task-ux-s1")
        self.assertFalse(Path(up["wt"]).exists())
        self.assertEqual(up["id"], "task-ux-s1")
        self.assertEqual(self._trace()[-1], "down task-ux-s1")
        [ev_up] = self._events("GATE_SERVICES_UP")
        self.assertTrue(ev_up["data"]["ok"])
        self.assertEqual(ev_up["data"]["env_vars"], ["DB_URL"])
        self.assertNotIn("postgres://", json.dumps(ev_up))  # never the value
        [ev_down] = self._events("GATE_SERVICES_DOWN")
        self.assertTrue(ev_down["data"]["ok"])
        [started] = self._events("WORKER_STARTED")
        self.assertLess(ev_up["seq"], started["seq"])
        [exited] = self._events("WORKER_EXITED")
        # teardown finishes before the exit is visible to a relaunching PM
        self.assertLess(ev_down["seq"], exited["seq"])

    def test_failed_up_refuses_launch_and_still_runs_down(self):
        self._services("print('DB_URL=x'); sys.exit(3)\n")
        self._harness()
        with self.assertRaisesRegex(worker.WorkerError, "exited 3"):
            worker.launch(self.repo, self.root, self._task(), "packet",
                          "security-reviewer", "sec-1")
        self.assertEqual(self._events("WORKER_STARTED"), [])
        [ev] = self._events("GATE_SERVICES_UP")
        self.assertFalse(ev["data"]["ok"])
        self.assertEqual(self._trace()[-1], "down t-1")
        # the claim is freed: the task is launchable again
        self.assertTrue(worker.claim_task(self.root, "T-1", "probe"))

    def test_missing_env_value_refuses_launch(self):
        self._services("print('no url here')\n")
        self._harness()
        with self.assertRaisesRegex(worker.WorkerError, "DB_URL"):
            worker.launch(self.repo, self.root, self._task(), "packet",
                          "code-reviewer", "cr-1")
        self.assertEqual(self._events("WORKER_STARTED"), [])

    def test_up_timeout_refuses_launch(self):
        self._services("import time; time.sleep(5)\n", extra="    timeout_s: 1\n")
        self._harness()
        with self.assertRaisesRegex(worker.WorkerError, "timed out"):
            worker.launch(self.repo, self.root, self._task(), "packet",
                          "qa-engineer", "qa-1")

    def test_down_runs_when_the_gate_times_out(self):
        self._services("print('DB_URL=x')\n")
        self._harness(sleep=5)
        worker.launch(self.repo, self.root, self._task(), "packet",
                      "qa-engineer", "qa-1", timeout=1)
        self.assertEqual(self._trace()[-1], "down t-1")
        self.assertEqual(len(self._events("GATE_SERVICES_DOWN")), 1)

    def test_implementers_are_untouched(self):
        self._services("print('DB_URL=x')\n")
        self._record_env_harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "backend-engineer", "be-1")
        self.assertEqual(self._trace(), [])
        self.assertIsNone(json.loads(self.seen.read_text())["DB_URL"])
        self.assertEqual(self._events("GATE_SERVICES_UP"), [])

    def test_no_config_is_a_noop(self):
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        self.assertEqual(self._events("GATE_SERVICES_UP"), [])

    def test_group_worker_gets_the_env_and_is_told_about_it(self):
        """finos m5-phase1: services came up for a group gate, the worker
        never used them. It must both receive the var and be told of it."""
        self._services("print('DB_URL=postgres://g')\n")
        self._harness()
        script = Path(self.tmp.name) / "fake_harness.py"
        script.write_text(
            "import json, os, sys\npacket = sys.stdin.read()\n"
            f"json.dump({{'DB_URL': os.environ.get('DB_URL'), 'told': 'DB_URL' in packet"
            f" and 'GATE SERVICES' in packet}}, open({str(self.seen)!r}, 'w'))\n"
            + script.read_text().split("sys.stdin.read()\n", 1)[1])
        worker.launch_group(self.repo, self.root, "iam", [self._task()], self.wt,
                            "packet", "qa-engineer", "qa-g", "p")
        self.assertEqual(json.loads(self.seen.read_text()),
                         {"DB_URL": "postgres://g", "told": True})

    def test_solo_worker_is_told_too_and_implementers_are_not(self):
        self._services("print('DB_URL=x')\n")
        self._harness()
        script = Path(self.tmp.name) / "fake_harness.py"
        script.write_text(
            "import json, os, sys\npacket = sys.stdin.read()\n"
            f"open({str(self.seen)!r}, 'a').write(str('GATE SERVICES' in packet) + chr(10))\n"
            + script.read_text().split("sys.stdin.read()\n", 1)[1])
        worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        worker.launch(self.repo, self.root, self._task("T-2"), "packet", "backend-engineer", "be-1")
        self.assertEqual(self.seen.read_text().split(), ["True", "False"])

    def test_group_launch_uses_a_per_role_id(self):
        self._services("print('DB_URL=y')\n")
        self._harness()
        worker.launch_group(self.repo, self.root, "iam", [self._task()], self.wt,
                            "packet", "qa-engineer", "qa-g", "p")
        self.assertEqual(json.loads(self._trace()[0])["id"], "gg-iam-qa-engineer")
        self.assertEqual(self._trace()[-1], "down gg-iam-qa-engineer")


class TestReviewFindings(GateServicesCase):
    def test_config_in_the_worktree_is_ignored(self):
        """The branch under review can't declare what runs unsandboxed."""
        (self.wt / ".company" / "config").mkdir(parents=True)
        (self.wt / ".company" / "config" / "project.yaml").write_text(
            f"gate_services:\n  - up: 'touch {self.repo}/pwned'\n")
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        self.assertFalse((self.repo / "pwned").exists())
        self.assertEqual(self._events("GATE_SERVICES_UP"), [])

    def test_first_match_wins(self):
        self._services("print('DB_URL=trusted'); print('DB_URL=from-migrations')\n")
        self._record_env_harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        self.assertEqual(json.loads(self.seen.read_text())["DB_URL"], "trusted")

    def test_up_timeout_kills_the_whole_process_tree(self):
        marker = self.repo / "grandchild_survived"
        child = self.repo / "grandchild.py"
        child.write_text(f"import time\ntime.sleep(3)\nopen({str(marker)!r}, 'w')\n")
        self._services(
            "import subprocess\n"
            f"subprocess.Popen([sys.executable, {str(child)!r}], stdout=subprocess.DEVNULL)\n"
            "import time; time.sleep(30)\n", extra="    timeout_s: 1\n")
        self._harness()
        with self.assertRaisesRegex(worker.WorkerError, "timed out"):
            worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        import time
        time.sleep(4)
        self.assertFalse(marker.exists())

    def test_second_service_failing_tears_down_both_newest_first(self):
        down = lambda n: (f'    down: "{sys.executable} -c \\"open({str(self.trace)!r}, \'a\')'
                          f'.write(\'down{n}\' + chr(10))\\""\n')
        (self.root / "config" / "project.yaml").write_text(
            "gate_services:\n"
            f"  - up: '{sys.executable} -c pass'\n" + down(1) +
            f"  - up: '{sys.executable} -c \"import sys; sys.exit(2)\"'\n" + down(2))
        self._harness()
        with self.assertRaises(worker.WorkerError):
            worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        self.assertEqual(self._trace(), ["down2", "down1"])

    def test_exception_after_up_still_tears_down(self):
        self._services("print('DB_URL=x')\n")
        self._harness()
        orig = worker.build_env
        worker.build_env = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            with self.assertRaises(RuntimeError):
                worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        finally:
            worker.build_env = orig
        self.assertEqual(self._trace()[-1], "down t-1")

    def test_no_down_declared_reports_ok_none(self):
        self._services("print('DB_URL=x')\n", down=False)
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        [ev] = self._events("GATE_SERVICES_DOWN")
        self.assertIsNone(ev["data"]["ok"])


class TestSecurityReviewFindings(GateServicesCase):
    def test_snapshot_has_committed_files_and_no_symlinks(self):
        listing = self.repo / "listing.json"
        self._services(
            "files = sorted(os.path.relpath(os.path.join(d, f), os.environ['COMPANY_GATE_WORKTREE'])"
            " for d, _, fs in os.walk(os.environ['COMPANY_GATE_WORKTREE']) for f in fs)\n"
            "links = [p for p in files if os.path.islink(os.path.join(os.environ['COMPANY_GATE_WORKTREE'], p))]\n"
            f"json.dump({{'files': files, 'links': links}}, open({str(listing)!r}, 'w'))\n"
            "print('DB_URL=x')\n")
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        seen = json.loads(listing.read_text())
        self.assertEqual(seen["files"], ["supabase/001.sql"])  # the planted link is gone
        self.assertEqual(seen["links"], [])

    def test_output_is_logged_where_sandboxed_workers_cannot_read(self):
        self._services("print('DB_URL=postgres://u:hunter2@h/db')\n")
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        [ev] = self._events("GATE_SERVICES_UP")
        log = Path(ev["data"]["log"])
        self.assertEqual(log.parent, self.root / "secrets" / "gate_services")
        self.assertIn("hunter2", log.read_text())
        self.assertNotIn("hunter2", json.dumps(self.log.read()))

    def test_stderr_is_not_parsed(self):
        self._services("sys.stderr.write('DB_URL=from-stderr\\n'); print('DB_URL=trusted')\n")
        self._record_env_harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        self.assertEqual(json.loads(self.seen.read_text())["DB_URL"], "trusted")


class TestSnapshotFailure(GateServicesCase):
    def test_unsnapshottable_branch_refuses_launch_before_any_up(self):
        self._services("print('DB_URL=x')\n")
        self._harness()
        task = {**self._task(), "branch": "no-such-branch"}
        with self.assertRaisesRegex(worker.WorkerError, "snapshot"):
            worker.launch(self.repo, self.root, task, "packet", "qa-engineer", "qa-1")
        self.assertEqual(self._trace(), [])
        self.assertEqual(self._events("WORKER_STARTED"), [])


class TestWorktreeGitConfigIsNeverUsed(GateServicesCase):
    def test_smudge_filter_in_a_repointed_worktree_gitdir_never_runs(self):
        """Security re-review PoC: the implementer repoints the worktree's
        .git at a gitdir whose config defines a smudge filter, and commits a
        .gitattributes using it. Nothing company-os runs unsandboxed may
        consult that gitdir."""
        marker = self.repo / "SMUDGE_EXECUTED"
        evil = self.repo / "evil"
        subprocess.run(["git", "init", "-q", str(evil)], check=True)
        eg = ["git", "-C", str(evil), "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(eg + ["config", "filter.p.smudge", f"touch {marker}; cat"], check=True)
        (evil / ".gitattributes").write_text("* filter=p\n")
        (evil / "x.sql").write_text("select 1;\n")
        subprocess.run(eg + ["add", "-A"], check=True)
        subprocess.run(eg + ["commit", "-qm", "evil"], check=True)
        (self.wt / ".git").write_text(f"gitdir: {evil / '.git'}\n")
        self._services("print('DB_URL=x')\n")
        self._harness()
        worker.launch(self.repo, self.root, self._task(), "packet", "qa-engineer", "qa-1")
        self.assertEqual(len(self._events("GATE_SERVICES_UP")), 1)
        self.assertFalse(marker.exists())


class TestConfigValidation(GateServicesCase):
    def _cfg(self, body):
        (self.root / "config" / "project.yaml").write_text(body)
        return worker.load_gate_services(self.root)

    def test_rejects_reserved_and_bad_names(self):
        for var in ("COMPANY_REPO", "PATH", "lower", "ANTHROPIC_API_KEY", "DYLD_INSERT_LIBRARIES",
                    "NODE_OPTIONS", "BASH_ENV", "HOME", "PYTHONPATH", "VERIFY_ID"):
            with self.assertRaises(worker.WorkerError):
                self._cfg(f"gate_services:\n  - up: x\n    env_from_output: {{{var}: '(x)'}}\n")

    def test_rejects_regex_without_one_group(self):
        with self.assertRaisesRegex(worker.WorkerError, "capture group"):
            self._cfg("gate_services:\n  - up: x\n    env_from_output: {A: 'x'}\n")

    def test_rejects_missing_up(self):
        with self.assertRaisesRegex(worker.WorkerError, "up"):
            self._cfg("gate_services:\n  - down: x\n")


if __name__ == "__main__":
    unittest.main()
