"""Wave-1 safety fixes (FIRST-PRINCIPLES-REVIEW Part 4 #3 and #1's prerequisite).

1. pen_test authorization is enforced in code, not only in agents/pen_test.md
   (verification batch-2, T-040): unlisted targets are refused before traffic.
2. The branch guard blocks remote deletion via `push --delete` / `-d` (T-160).
3. A blocking escalation must name the task it blocks or be --project-wide, so
   lead time can be attributed (tools/lead_time.py).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools" / "company"))
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "skills" / "pen_test" / "native"))
sys.path.insert(0, str(ROOT / "tools"))

import _httpcore as core  # noqa: E402
import escalations  # noqa: E402
import lead_time  # noqa: E402
import policy  # noqa: E402
from eventlog import EventLog  # noqa: E402

TARGETS = """
- target: "*.example-authorized.test"
  subdomain_wildcard: true
- target: "Some App / production"
  hosts:
    - "app.listed.test"     # dashboard
    - "api.listed.test"
"""


class PenTestAuthorization(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = Path(self.tmp.name) / "authorized-targets.yaml"
        self.file.write_text(TARGETS)
        self._old = os.environ.get("PEN_TEST_AUTHORIZED_TARGETS")
        os.environ["PEN_TEST_AUTHORIZED_TARGETS"] = str(self.file)
        os.environ["PEN_TEST_UNDER_UNITTEST"] = "1"

    def tearDown(self):
        os.environ.pop("PEN_TEST_UNDER_UNITTEST", None)
        if self._old is None:
            os.environ.pop("PEN_TEST_AUTHORIZED_TARGETS", None)
        else:
            os.environ["PEN_TEST_AUTHORIZED_TARGETS"] = self._old
        self.tmp.cleanup()

    def test_listed_hosts_and_wildcards_are_allowed(self):
        for t in ("https://app.listed.test/login", "api.listed.test:443",
                  "https://x.example-authorized.test/", "example-authorized.test"):
            self.assertTrue(core.is_authorized(t), t)

    def test_unlisted_hosts_and_labels_are_refused(self):
        for t in ("https://evil.test/", "app.listed.test.evil.test", "notexample-authorized.test",
                  "Some App / production"):
            self.assertFalse(core.is_authorized(t), t)

    def test_loopback_is_always_allowed(self):
        for t in ("http://127.0.0.1:8080/", "localhost", "http://[::1]:9/"):
            self.assertTrue(core.is_authorized(t), t)

    def test_missing_file_fails_closed(self):
        self.file.unlink()
        self.assertFalse(core.is_authorized("https://app.listed.test/"))
        self.assertTrue(core.is_authorized("http://127.0.0.1/"))

    def test_require_scheme_refuses_an_unlisted_target(self):
        with self.assertRaises(SystemExit) as cm:
            core.require_scheme("https://evil.test/")
        self.assertIn("REFUSED", str(cm.exception))

    def test_client_request_refuses_before_any_traffic(self):
        with self.assertRaises(core.UnauthorizedTarget):
            core.Client().request("GET", "https://evil.test/")

    def test_socket_probe_entrypoint_refuses(self):
        script = ROOT / "skills" / "pen_test" / "native" / "port_scan.py"
        r = subprocess.run([sys.executable, str(script), "evil.test"],
                           capture_output=True, text=True, timeout=60,
                           env={**os.environ, "PEN_TEST_AUTHORIZED_TARGETS": str(self.file)})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REFUSED", r.stdout + r.stderr)

    def test_env_override_is_ignored_outside_tests(self):
        os.environ.pop("PEN_TEST_UNDER_UNITTEST")
        self.assertNotEqual(core._targets_file(), self.file)

    def _redirector(self):
        import http.server, threading
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302); self.send_header("Location", "http://evil.test/x")
                self.end_headers()
            def log_message(self, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return f"http://127.0.0.1:{srv.server_port}/"

    def test_an_unfollowed_redirect_is_returned_not_refused(self):
        r = core.Client().request("GET", self._redirector(), allow_redirects=False)
        self.assertEqual(r.status, 302)

    def test_redirect_to_an_unlisted_host_is_refused(self):
        import http.server, threading
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302); self.send_header("Location", "http://evil.test/x")
                self.end_headers()
            def log_message(self, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(core.UnauthorizedTarget):
                core.Client().request("GET", f"http://127.0.0.1:{srv.server_port}/",
                                      allow_redirects=True)
        finally:
            srv.shutdown(); srv.server_close()

    def test_workflow_refuses_before_any_step(self):
        script = ROOT / "skills" / "pen_test" / "scripts" / "workflow.sh"
        r = subprocess.run(["bash", str(script), "recon", "https://evil.test/"],
                           capture_output=True, text=True, timeout=60,
                           env={**os.environ, "PEN_TEST_AUTHORIZED_TARGETS": str(self.file)})
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSED", r.stderr)
        self.assertNotIn("=== workflow", r.stdout)


class PushDeleteIsBlocked(unittest.TestCase):
    def test_flag_spellings_are_blocked(self):
        for cmd in ("git push origin --delete feature", "git push -d origin feature",
                    "git push origin --delete v1.0"):
            self.assertIsNotNone(policy.check_command(cmd), cmd)

    def test_ordinary_push_is_not_blocked_by_this_rule(self):
        for cmd in ("git push origin feature-branch", "git push origin feat/x-d",
                    "git push --dry-run origin x", "git fetch --prune"):
            self.assertIsNone(policy.check_command(cmd), cmd)

    def test_mirror_and_prune_pushes_are_blocked(self):
        for cmd in ("git push --mirror origin", "git push --prune origin refs/heads/*"):
            self.assertIsNotNone(policy.check_command(cmd), cmd)

    def test_authorization_list_cannot_be_rewritten_or_overridden(self):
        for cmd in ("echo '- target: evil.test' >> config/authorized-targets.yaml",
                    "sed -i '' 's/a/b/' config/authorized-targets.yaml",
                    "PEN_TEST_AUTHORIZED_TARGETS=/tmp/x.yaml python3 sqli_probe.py",
                    "export PEN_TEST_UNDER_UNITTEST=1"):
            self.assertIsNotNone(policy.check_command(cmd), cmd)
        for cmd in ("cat config/authorized-targets.yaml", "grep -ln x config/authorized-targets.yaml",
                    "git push origin x && git fetch --prune"):
            self.assertIsNone(policy.check_command(cmd), cmd)


class EscalationsNameWhatTheyBlock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def raise_(self, **kw):
        base = dict(project="p", actor="company-pm", kind="decision", need="pick one")
        return escalations.raise_escalation(self.root, **{**base, **kw})

    def test_blocking_without_task_or_project_wide_is_refused(self):
        with self.assertRaisesRegex(ValueError, "--task"):
            self.raise_()

    def test_task_project_wide_and_non_blocking_are_accepted(self):
        self.raise_(task="T-1")
        self.raise_(project_wide=True)
        self.raise_(blocking=False)
        data = [e["data"] for e in EventLog(self.root).read() if e["event"] == "ESCALATION_RAISED"]
        self.assertEqual([d.get("project_wide") for d in data], [None, True, None])

    def test_task_and_project_wide_together_are_refused(self):
        with self.assertRaises(ValueError):
            self.raise_(task="T-1", project_wide=True)


class LeadTimeCountsProjectWideEscalations(unittest.TestCase):
    def test_project_wide_counts_in_the_default_bound(self):
        ev = [
            {"seq": 1, "ts": "2026-11-01T00:00:00Z", "event": "TASK_CREATED", "task": "T-1", "actor": "pm"},
            {"seq": 2, "ts": "2026-11-01T00:00:00Z", "event": "ESCALATION_RAISED", "actor": "pm",
             "data": {"id": "ESC-1", "blocking": True, "project_wide": True}},
            {"seq": 3, "ts": "2026-11-01T06:00:00Z", "event": "ESCALATION_RESOLVED", "actor": "riyan",
             "data": {"id": "ESC-1"}},
            {"seq": 4, "ts": "2026-11-01T10:00:00Z", "event": "MERGED", "task": "T-1", "actor": "pm"},
        ]
        rep = lead_time.analyse(ev)["2026-11"]
        self.assertEqual(rep["share_riyan_pct"], 60.0)
        self.assertEqual(rep["share_nobody_pct"], 40.0)

    def test_overlapping_minus_intervals_are_subtracted_once(self):
        self.assertEqual(lead_time.covered([(0, 10)], 0, 10, minus=[(0, 4), (2, 4)]), 6.0)


if __name__ == "__main__":
    unittest.main()
