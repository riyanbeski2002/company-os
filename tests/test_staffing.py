"""Staffing engine (D4). Determinism is the whole point of the table."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import staffing  # noqa: E402

CFG = staffing.load_config(Path("/nonexistent"), "risk-triggers.yaml")
QG = staffing.load_config(Path("/nonexistent"), "quality-gates.yaml")
SP = staffing.load_config(Path("/nonexistent"), "staffing.yaml")


class TestRiskTable(unittest.TestCase):
    def test_untriggered_change_gets_no_mandatory_gate(self):
        """D10, efficiency addendum v1: baseline_gates is empty now — review
        is risk-based like qa/security, not universal. Adding it back on an
        untriggered task needs a recorded reason, same as any other gate
        addition (see TestReconcile.test_pm_addition_needs_a_reason)."""
        r = staffing.evaluate(CFG, "Fix the typo on the settings screen", ["docs/**"])
        self.assertEqual(r["gates"], [])
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

    def test_editing_the_staffing_engine_itself_forces_security_unasked(self):
        """CTO audit, 2026-08-24: the efficiency addendum (D9-D11) put the
        fast_path/reconcile/model_policy logic in staffing.py without adding
        it to this table — an edit there decided every other task's gates
        while being invisible to the table itself."""
        r = staffing.evaluate(CFG, "tune the fast path bounds", ["tools/company/staffing.py"])
        self.assertIn("security", r["gates"])
        self.assertIn("governance-mechanism", [t["trigger"] for t in r["triggers_fired"]])

    def test_editing_the_tier_policy_itself_forces_security_unasked(self):
        r = staffing.evaluate(CFG, "swap the tier2 model", ["config/staffing.yaml"])
        self.assertIn("security", r["gates"])

    def test_editing_the_cli_wiring_forces_security_unasked(self):
        r = staffing.evaluate(CFG, "add a flag to gates", ["tools/company/cli.py"])
        self.assertIn("security", r["gates"])

    def test_dependency_manifest_edit_forces_security_unasked(self):
        """CTO audit, 2026-08-24: a version bump in a lockfile is the
        dominant small-diff supply-chain attack shape and previously matched
        no trigger — it would sail through fast_path with zero gates."""
        r = staffing.evaluate(CFG, "bump a dependency", ["requirements.txt"])
        self.assertIn("security", r["gates"])
        self.assertIn("dependency-manifest", [t["trigger"] for t in r["triggers_fired"]])

    def test_dependency_manifest_edit_is_never_fast_pathed(self):
        r = staffing.evaluate(CFG, "bump lodash", ["package-lock.json"],
                              files_touched=1, diff_lines=2)
        self.assertFalse(r["fast_path"])

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

    def test_review_on_an_untriggered_task_needs_a_reason_too(self):
        """D10: review lost its special unconditional status. Adding it back
        on a task the risk table cleared is a scope addition like any other."""
        final, added = staffing.reconcile(["review"], [])
        self.assertNotIn("review", final)
        self.assertEqual(added, [])

        final, added = staffing.reconcile(["review"], [], reason="new to this codebase")
        self.assertIn("review", final)
        self.assertEqual(added, ["review"])


class TestFastPath(unittest.TestCase):
    def test_recommends_tier_0_within_bounds(self):
        r = staffing.evaluate(CFG, "Fix the typo on the settings screen", ["docs/**"],
                              files_touched=1, diff_lines=10)
        self.assertTrue(r["fast_path"])
        self.assertEqual(r["recommended_tier"], 0)

    def test_does_not_apply_over_bounds(self):
        r = staffing.evaluate(CFG, "Fix the typo on the settings screen", ["docs/**"],
                              files_touched=3, diff_lines=200)
        self.assertFalse(r["fast_path"])
        self.assertIsNone(r["recommended_tier"])

    def test_does_not_apply_when_a_trigger_fires(self):
        r = staffing.evaluate(CFG, "Add role-based expense approvals", ["api/approvals/**"],
                              files_touched=1, diff_lines=5)
        self.assertFalse(r["fast_path"])
        self.assertIsNone(r["recommended_tier"])

    def test_unset_without_diff_stats(self):
        """Omitting files_touched/diff_lines leaves tier recommendation
        unset — existing callers (`company gates` with no counts) see no
        behavior change from D9 beyond baseline_gates now being empty."""
        r = staffing.evaluate(CFG, "Fix the typo on the settings screen", ["docs/**"])
        self.assertFalse(r["fast_path"])
        self.assertIsNone(r["recommended_tier"])


class TestModelPolicy(unittest.TestCase):
    def test_tier2_gated_gets_the_high_effort_row(self):
        """Model here is whatever staffing.yaml currently says (Riyan
        downgraded tier2_gated opus->sonnet 2026-08-24 for cost + an Opus
        outage — see the ADR and the comment in that file) — assert the
        structural property (highest effort, distinct from ungated), not a
        specific model name that's a live policy knob, not a code contract."""
        gated = staffing.model_policy(SP, tier=2, gated=True)
        ungated = staffing.model_policy(SP, tier=2, gated=False)
        self.assertEqual(gated["effort"], "high")
        self.assertNotEqual(gated["effort"], ungated["effort"])

    def test_tier2_ungated_stays_cheap(self):
        p = staffing.model_policy(SP, tier=2, gated=False)
        self.assertEqual(p["model"], "sonnet")
        self.assertEqual(p["effort"], "medium")

    def test_tier1_row(self):
        p = staffing.model_policy(SP, tier=1, gated=False)
        self.assertEqual(p["model"], "sonnet")
        self.assertEqual(p["effort"], "medium")

    def test_unknown_tier_falls_back_to_tier1_not_the_expensive_row(self):
        p = staffing.model_policy(SP, tier=99, gated=True)
        self.assertEqual(p, staffing.model_policy(SP, tier=1, gated=False))

    def test_role_override_cuts_effort_without_touching_the_role_that_wasnt_named(self):
        """Cost audit, 2026-08-25: code-reviewer and qa-engineer were the two
        largest gate-cost lines, both riding the same tier2_gated row
        security-reviewer uses. The override should touch only the roles
        named — security-reviewer's cost wasn't the complaint."""
        base = staffing.model_policy(SP, tier=2, gated=True)
        reviewer = staffing.model_policy(SP, tier=2, gated=True, role="code-reviewer")
        qa = staffing.model_policy(SP, tier=2, gated=True, role="qa-engineer")
        security = staffing.model_policy(SP, tier=2, gated=True, role="security-reviewer")

        self.assertEqual(reviewer["effort"], "medium")
        self.assertEqual(qa["effort"], "medium")
        self.assertEqual(security["effort"], base["effort"])
        self.assertEqual(security, base)

    def test_role_override_only_changes_the_fields_it_names(self):
        """An override naming only `effort` must not silently also change
        model or thinking — those still come from the base tier/gated row."""
        base = staffing.model_policy(SP, tier=2, gated=True)
        overridden = staffing.model_policy(SP, tier=2, gated=True, role="code-reviewer")
        self.assertEqual(overridden["model"], base["model"])
        self.assertEqual(overridden.get("thinking"), base.get("thinking"))

    def test_no_role_given_is_unaffected_by_overrides(self):
        p = staffing.model_policy(SP, tier=2, gated=True, role=None)
        self.assertEqual(p, staffing.model_policy(SP, tier=2, gated=True))

    def test_unknown_role_is_unaffected_by_overrides(self):
        p = staffing.model_policy(SP, tier=2, gated=True, role="some-role-not-in-the-table")
        self.assertEqual(p, staffing.model_policy(SP, tier=2, gated=True))


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
