"""Staffing engine (D4). Determinism is the whole point of the table."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import staffing  # noqa: E402

CFG = staffing.load_config(Path("/nonexistent"), "risk-triggers.yaml")
QG = staffing.load_config(Path("/nonexistent"), "quality-gates.yaml")


class TestRiskTable(unittest.TestCase):
    def test_docs_change_gets_review_only(self):
        r = staffing.evaluate(CFG, "Fix the typo on the settings screen", ["docs/**"])
        self.assertEqual(r["gates"], ["review"])
        self.assertEqual(r["triggers_fired"], [])

    def test_authorization_forces_security_unasked(self):
        r = staffing.evaluate(CFG, "Add role-based expense approvals", ["api/approvals/**"])
        self.assertIn("security", r["gates"])
        self.assertIn("authorization", [t["trigger"] for t in r["triggers_fired"]])

    def test_path_alone_is_enough(self):
        r = staffing.evaluate(CFG, "tidy up some helpers", ["services/auth/**"])
        self.assertIn("security", r["gates"])

    def test_keyword_alone_is_enough(self):
        r = staffing.evaluate(CFG, "store the stripe payment token", ["lib/**"])
        self.assertIn("security", r["gates"])

    def test_is_deterministic(self):
        a = staffing.evaluate(CFG, "Add RBAC to approvals", ["api/approvals/**"])
        b = staffing.evaluate(CFG, "Add RBAC to approvals", ["api/approvals/**"])
        self.assertEqual(a, b)

    def test_editing_a_guard_hook_forces_security_unasked(self):
        """CISO's whole-repo finding: a task editing hooks/ previously matched
        none of the application-domain triggers and shipped with review only,
        despite touching the code that decides who else gets reviewed."""
        r = staffing.evaluate(CFG, "simplify the error message in a hook", ["hooks/guard_secrets.py"])
        self.assertIn("security", r["gates"])
        self.assertIn("governance-mechanism", [t["trigger"] for t in r["triggers_fired"]])

    def test_editing_the_risk_table_itself_forces_security_unasked(self):
        r = staffing.evaluate(CFG, "tune gate ordering", ["config/risk-triggers.yaml"])
        self.assertIn("security", r["gates"])

    def test_editing_worker_launch_wiring_forces_security_unasked(self):
        r = staffing.evaluate(CFG, "tidy up the launcher", ["tools/company/worker.py"])
        self.assertIn("security", r["gates"])

    def test_fetching_untrusted_content_forces_security_unasked(self):
        r = staffing.evaluate(CFG, "fetch and summarize this vendor's API docs", ["docs/**"])
        self.assertIn("security", r["gates"])
        self.assertIn("untrusted-content", [t["trigger"] for t in r["triggers_fired"]])

    def test_no_substring_false_positives(self):
        # "role" must not fire on "payroll" or "console"
        r = staffing.evaluate(CFG, "tidy the console output in payroll exports", ["lib/**"])
        self.assertNotIn("authorization", [t["trigger"] for t in r["triggers_fired"]])


class TestReconcile(unittest.TestCase):
    def test_mandatory_gates_survive_a_pm_that_omits_them(self):
        final, _ = staffing.reconcile(["review"], ["review", "qa", "security"])
        self.assertEqual(sorted(final), ["qa", "review", "security"])

    def test_pm_cannot_subtract(self):
        final, _ = staffing.reconcile([], ["security"])
        self.assertIn("security", final)

    def test_pm_addition_needs_a_reason(self):
        final, added = staffing.reconcile(["qa"], ["review"])
        self.assertNotIn("qa", final)
        self.assertEqual(added, [])

    def test_pm_addition_with_a_reason_is_kept(self):
        final, added = staffing.reconcile(["qa"], ["review"], reason="touches billing exports")
        self.assertIn("qa", final)
        self.assertEqual(added, ["qa"])


class TestOverlap(unittest.TestCase):
    def test_detects_shared_ownership(self):
        c = staffing.predict_overlap([
            {"id": "T1", "owned_globs": ["api/**"]},
            {"id": "T2", "owned_globs": ["api/approvals/**"]},
        ])
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["tasks"], ["T1", "T2"])

    def test_identical_globs_collide(self):
        c = staffing.predict_overlap([
            {"id": "T1", "owned_globs": ["web/**"]},
            {"id": "T2", "owned_globs": ["web/**"]},
        ])
        self.assertEqual(len(c), 1)

    def test_disjoint_globs_do_not_collide(self):
        c = staffing.predict_overlap([
            {"id": "T1", "owned_globs": ["api/approvals/**", "tests/test_expenses.py"]},
            {"id": "T2", "owned_globs": ["web/**", "tests/test_web.py"]},
        ])
        self.assertEqual(c, [])


class TestSizeBands(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(staffing.size_band(0)["size"], "trivial")
        self.assertEqual(staffing.size_band(1)["size"], "small")
        self.assertEqual(staffing.size_band(2)["size"], "medium")
        self.assertEqual(staffing.size_band(4)["size"], "medium")
        self.assertEqual(staffing.size_band(5)["size"], "large")
        self.assertEqual(staffing.size_band(9)["size"], "program")

    def test_trivial_has_no_tier2_budget(self):
        self.assertEqual(staffing.size_band(0)["tier2_cap"], 0)


if __name__ == "__main__":
    unittest.main()
