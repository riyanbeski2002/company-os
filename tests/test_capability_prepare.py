"""tools/capability.py prepare: rank catalog units against a project brief,
make their repos local, and load skills — without running install commands."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import capability as cap  # noqa: E402


def _unit(uid, name, desc, type_="skill", path="external/r/skill"):
    return {"unit_id": uid, "registry_id": uid.split(":")[0], "type": type_,
            "name": name, "description": desc, "path": path, "pairs_with": []}


class RankUnitsTest(unittest.TestCase):
    def test_needs_two_shared_terms_and_orders_by_hits(self):
        units = {u["unit_id"]: u for u in [
            _unit("a:rate", "rate-limiting", "rate limiting for redis-backed APIs"),
            _unit("a:redis", "redis-patterns", "redis caching patterns"),
            _unit("a:legal", "contract-review", "review vendor contracts"),
        ]}
        got = [u["unit_id"] for u in cap.rank_units("rate limiting an API with redis", units)]
        # "rate" + "limiting" hit; redis alone is one term, below the bar.
        self.assertEqual(got, ["a:rate"])

    def test_stopwords_alone_do_not_match(self):
        units = {"a:x": _unit("a:x", "make-the-thing", "use this for your new app")}
        self.assertEqual(cap.rank_units("make a new app for you", units), [])


class PrepareTest(unittest.TestCase):
    def test_native_skill_is_loaded_and_never_cloned(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            skills = tmp / "skills"
            skills.mkdir()
            native = tmp / "skills" / "native-thing"
            native.mkdir()
            index = {"n:native": _unit("n:native", "rate-limit-helper",
                                       "rate limit redis helper", path="skills/native-thing")}
            with mock.patch.object(cap, "load_units", return_value=index), \
                 mock.patch.object(cap, "_registry_tiers", return_value={"n": "T3"}), \
                 mock.patch.object(cap, "SKILLS_DIR", skills), \
                 mock.patch.object(cap, "REPO_ROOT", tmp), \
                 mock.patch.object(cap, "ensure_repo", wraps=cap.ensure_repo) as ens, \
                 mock.patch("sync_external_capabilities.sync_one") as sync:
                out = cap.prepare("rate limit with redis")
            self.assertEqual(out["loaded"], ["n:native"])
            self.assertEqual(out["cloned"], [])
            sync.assert_not_called()
            self.assertTrue((skills / "n__native").is_symlink())

    def test_tools_are_cloned_but_not_installed(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            index = {"t:tool": _unit("t:tool", "redis-cli-tool", "redis tool helper",
                                     type_="tool", path="external/t/tool")}
            with mock.patch.object(cap, "load_units", return_value=index), \
                 mock.patch.object(cap, "_registry_tiers", return_value={"t": "T3"}), \
                 mock.patch.object(cap, "REPO_ROOT", tmp), \
                 mock.patch("sync_external_capabilities.load_entries",
                            return_value=[{"id": "t", "local_path": "external/t"}]), \
                 mock.patch("sync_external_capabilities.sync_one", return_value=True) as sync, \
                 mock.patch("subprocess.run") as run:
                out = cap.prepare("redis tool helper")
            sync.assert_called_once()
            run.assert_not_called()
            self.assertEqual(out["cloned"], ["t:tool"])
            self.assertEqual(out["loaded"], [])
            self.assertEqual(out["available"][0]["unit_id"], "t:tool")


class TierGateTest(unittest.TestCase):
    def test_t4_units_are_never_auto_selected(self):
        index = {"t4:skill": _unit("t4:skill", "redis-helper", "redis rate limit helper")}
        with mock.patch.object(cap, "load_units", return_value=index), \
             mock.patch.object(cap, "_registry_tiers", return_value={"t4": "T4"}), \
             mock.patch.object(cap, "ensure_repo") as ens, \
             mock.patch.object(cap, "cmd_load") as load:
            out = cap.prepare("redis rate limit")
        self.assertEqual(out["selected"], [])
        ens.assert_not_called()
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
