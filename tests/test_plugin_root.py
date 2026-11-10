"""Self-hosted workers must be launched with a plugin dir outside the repo.

Claude Code refuses Write/Edit under the loaded --plugin-dir; when company-os
works on itself its task worktrees live inside that dir (bisected live on
claude 2.1.322, 2026-11-10 — see worker.launch_plugin_root).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "company"))

import worker  # noqa: E402
from test_launch_regressions import FakeHarnessCase  # noqa: E402


class TestLaunchPluginRoot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_other_repos_keep_the_real_plugin_root(self):
        self.assertEqual(worker.launch_plugin_root(Path(self.tmp.name)), worker.PLUGIN_ROOT)

    def test_self_hosted_gets_a_committed_snapshot_outside_the_repo(self):
        root = worker.launch_plugin_root(worker.PLUGIN_ROOT)
        self.assertNotEqual(root, worker.PLUGIN_ROOT)
        self.assertFalse(str(root.resolve()).startswith(str(worker.PLUGIN_ROOT) + os.sep))
        self.assertTrue(str(root).startswith(self.tmp.name))
        for needed in ("hooks/hooks.json", "agents/backend-engineer.md", ".complete"):
            self.assertTrue((root / needed).exists(), needed)
        self.assertEqual((root / "external").resolve(), (worker.PLUGIN_ROOT / "external").resolve())
        # a task worktree is never inside it, so its files aren't "sensitive"
        wt = worker.PLUGIN_ROOT / ".company" / "worktrees" / "T-1" / "x.py"
        self.assertFalse(str(wt).startswith(str(root) + os.sep))

    def test_snapshot_is_reused_not_re_exported(self):
        first = worker.launch_plugin_root(worker.PLUGIN_ROOT)
        marker = first / ".complete"
        before = marker.stat().st_mtime_ns
        with mock.patch.object(worker.subprocess, "run", wraps=worker.subprocess.run) as run:
            again = worker.launch_plugin_root(worker.PLUGIN_ROOT)
        self.assertEqual(again, first)
        self.assertEqual(marker.stat().st_mtime_ns, before)
        self.assertFalse(any("archive" in c.args[0] for c in run.call_args_list))

    def test_command_carries_the_launch_plugin_root(self):
        snap = Path(self.tmp.name) / "snap"
        spec = worker.harness.resolve(worker.harness.load_config(worker.PLUGIN_ROOT),
                                      "backend-engineer")
        cmd = worker.build_command({"id": "T-1"}, "backend-engineer",
                                   harness_spec=spec, plugin_root=snap)
        self.assertEqual(cmd[cmd.index("--plugin-dir") + 1], str(snap))

    def test_snapshot_is_read_only(self):
        root = worker.launch_plugin_root(worker.PLUGIN_ROOT)
        self.assertFalse(os.access(root / "hooks" / "hooks.json", os.W_OK))
        self.assertFalse(os.access(root / "hooks", os.W_OK))

    def test_prune_drops_old_snapshots_and_crashed_exports_only(self):
        parent = Path(self.tmp.name) / "plugin"
        parent.mkdir()
        made = []
        for i in range(7):
            d = parent / f"sha{i}"
            d.mkdir()
            (d / ".complete").write_text("x")
            os.utime(d, (1000 + i, 1000 + i))
            made.append(d)
        stale = parent / "shaX.tmp-old"
        stale.mkdir()
        os.utime(stale, (1, 1))
        fresh = parent / "shaY.tmp-new"
        fresh.mkdir()  # an export in progress right now: must survive
        worker._prune_plugin_snapshots(parent, keep="sha0")
        left = sorted(p.name for p in parent.iterdir())
        # keep + the newest SNAPSHOTS_KEPT-1 others, and the in-progress export
        self.assertEqual(left, sorted(["sha0", "sha3", "sha4", "sha5", "sha6", "shaY.tmp-new"]))

    def test_build_env_names_the_launch_plugin_root(self):
        snap = Path(self.tmp.name) / "snap"
        env = worker.build_env(Path(self.tmp.name), Path(self.tmp.name) / ".company",
                               {"id": "T-1", "project": "p"}, "be-1",
                               Path(self.tmp.name) / "wt", plugin_root=snap)
        self.assertEqual(env["COMPANY_PLUGIN_ROOT"], str(snap))


class TestCdGuard(unittest.TestCase):
    """Workers are told to read $CLAUDE_PLUGIN_ROOT/external; once expanded,
    that path is the snapshot, so cd into it must not read as an escape."""

    def setUp(self):
        sys.path.insert(0, str(worker.PLUGIN_ROOT / "hooks"))
        import policy
        self.policy = policy

    def test_cd_into_the_launch_plugin_root_is_allowed(self):
        f = self.policy.find_escape
        snap = "/Users/x/.cache/company-os/plugin/abc"
        self.assertIsNone(f(f"cd {snap}/external/foo && ls", "/r/.company/worktrees/T-1",
                            "/r/.company", "/r", snap))
        self.assertEqual(f(f"cd {snap}/external/foo", "/r/.company/worktrees/T-1",
                           "/r/.company", "/r", ""), f"{snap}/external/foo")

    def test_writes_into_it_are_still_escapes(self):
        snap = "/Users/x/.cache/company-os/plugin/abc"
        self.assertEqual(self.policy.find_escape(f"echo x > {snap}/hooks/guard.py",
                                                 "/r/wt", "/r/.company", "/r", snap),
                         f"{snap}/hooks/guard.py")


class TestLaunchUsesIt(FakeHarnessCase):
    """The wiring: a real worker.launch() builds its command with
    launch_plugin_root(repo), not the module constant."""

    def test_launch_passes_the_launch_plugin_root(self):
        self._harness()
        snap = Path(self.tmp.name) / "snap"
        with mock.patch.object(worker, "launch_plugin_root", return_value=snap) as lpr, \
             mock.patch.object(worker, "build_command", wraps=worker.build_command) as bc:
            worker.launch(self.repo, self.root, self._task(), "packet",
                          "backend-engineer", "be-1", timeout=30)
        lpr.assert_called_with(self.repo)
        self.assertEqual(bc.call_args.kwargs["plugin_root"], snap)
        started = self._events("WORKER_STARTED")
        self.assertEqual(len(started), 1)

    def test_a_failed_export_never_starts_a_worker(self):
        self._harness()
        boom = worker.subprocess.CalledProcessError(128, ["git", "archive"])
        with mock.patch.object(worker, "launch_plugin_root", side_effect=boom):
            with self.assertRaises(worker.subprocess.CalledProcessError):
                worker.launch(self.repo, self.root, self._task(), "packet",
                              "backend-engineer", "be-1", timeout=30)
        self.assertEqual(self._events("WORKER_STARTED"), [])
        # the claim is released, so a retry can launch
        worker.launch(self.repo, self.root, self._task(), "packet",
                      "backend-engineer", "be-2", timeout=30)


if __name__ == "__main__":
    unittest.main()
