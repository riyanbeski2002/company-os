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
    def test_untriggered_change_gets_a_baseline_review(self):
        """D10 (2026-08-24) made baseline_gates empty; REVERSED 2026-09-14 on
        real evidence — finos shipped tasks with a real correctness surface
        (a context-duplication bug across 4 modules) with zero independent
        review because nothing triggered and nobody remembered to add one.
        Every untriggered-but-substantive task now gets `review` as a floor;
        qa/security stay risk-triggered only, not baseline."""
        r = staffing.evaluate(CFG, "Fix the typo on the settings screen", ["docs/**"])
        self.assertEqual(r["gates"], ["review"])
        self.assertEqual(r["triggers_fired"], [])

    def test_baseline_review_is_still_only_a_floor_not_a_ceiling(self):
        """A triggered task's gates are still whatever the table says, with
        review folded in same as any other task — no double-counting, no
        triggered task ending up UNDER its category's mandate."""
        r = staffing.evaluate(CFG, "Add role-based expense approvals", ["api/approvals/**"])
        self.assertEqual(sorted(r["gates"]), ["qa", "review", "security"])

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
        fast_path behavior change from D9."""
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


class TestDefaultGateGroup(unittest.TestCase):
    def test_groups_two_or_more_eligible_tier2_gated_tasks(self):
        planned = [
            {"id": "T1", "tier": 2, "gates": ["review"]},
            {"id": "T2", "tier": 2, "gates": ["review", "qa"]},
        ]
        group_id, assigned = staffing.default_gate_group(planned, "proj")
        self.assertIsNotNone(group_id)
        self.assertEqual(sorted(assigned), ["T1", "T2"])
        self.assertEqual(planned[0]["gate_group"], group_id)
        self.assertEqual(planned[1]["gate_group"], group_id)
        self.assertTrue(group_id.startswith("proj-plan-"))

    def test_single_eligible_task_stays_solo(self):
        planned = [{"id": "T1", "tier": 2, "gates": ["review"]}]
        group_id, assigned = staffing.default_gate_group(planned, "proj")
        self.assertIsNone(group_id)
        self.assertEqual(assigned, [])
        self.assertNotIn("gate_group", planned[0])

    def test_ungated_tasks_are_not_eligible(self):
        planned = [
            {"id": "T1", "tier": 2, "gates": []},
            {"id": "T2", "tier": 2, "gates": ["review"]},
        ]
        group_id, assigned = staffing.default_gate_group(planned, "proj")
        self.assertIsNone(group_id)  # only 1 gated task, still solo

    def test_tier1_tasks_are_not_eligible(self):
        planned = [
            {"id": "T1", "tier": 1, "gates": ["review"]},
            {"id": "T2", "tier": 2, "gates": ["review"]},
        ]
        group_id, assigned = staffing.default_gate_group(planned, "proj")
        self.assertIsNone(group_id)

    def test_explicit_gate_group_is_never_overridden(self):
        planned = [
            {"id": "T1", "tier": 2, "gates": ["review"], "gate_group": "manual-choice"},
            {"id": "T2", "tier": 2, "gates": ["review"]},
        ]
        group_id, assigned = staffing.default_gate_group(planned, "proj")
        # T1 already had its own choice, so only T2 was ever eligible — 1
        # eligible task stays solo, and T1's explicit group is untouched.
        self.assertIsNone(group_id)
        self.assertEqual(planned[0]["gate_group"], "manual-choice")
        self.assertNotIn("gate_group", planned[1])

    def test_solo_gate_opt_out_needs_a_reason(self):
        planned = [
            {"id": "T1", "tier": 2, "gates": ["review"], "solo_gate": True},
            {"id": "T2", "tier": 2, "gates": ["review"]},
            {"id": "T3", "tier": 2, "gates": ["review"]},
        ]
        # T1 opted out with no reason recorded -> the opt-out is ignored,
        # same as reconcile() ignoring an ungated addition with no reason.
        group_id, assigned = staffing.default_gate_group(planned, "proj")
        self.assertIsNotNone(group_id)
        self.assertEqual(sorted(assigned), ["T1", "T2", "T3"])

    def test_solo_gate_opt_out_with_reason_is_honored(self):
        planned = [
            {"id": "T1", "tier": 2, "gates": ["review"],
             "solo_gate": True, "solo_gate_reason": "touches a different subsystem"},
            {"id": "T2", "tier": 2, "gates": ["review"]},
            {"id": "T3", "tier": 2, "gates": ["review"]},
        ]
        group_id, assigned = staffing.default_gate_group(planned, "proj")
        self.assertEqual(sorted(assigned), ["T2", "T3"])
        self.assertNotIn("gate_group", planned[0])

    def test_deterministic_across_reruns(self):
        planned_a = [
            {"id": "T1", "tier": 2, "gates": ["review"]},
            {"id": "T2", "tier": 2, "gates": ["review"]},
        ]
        planned_b = [
            {"id": "T1", "tier": 2, "gates": ["review"]},
            {"id": "T2", "tier": 2, "gates": ["review"]},
        ]
        group_a, _ = staffing.default_gate_group(planned_a, "proj")
        group_b, _ = staffing.default_gate_group(planned_b, "proj")
        self.assertEqual(group_a, group_b)


class TestFindDuplicateStaffing(unittest.TestCase):
    """finos-5a, 2026-09-14: the same admin-self-attach fix was staffed
    three times across three waves under three different task ids — two of
    the three produced nothing. This is the cross-wave check that was
    missing."""

    def test_flags_a_near_identical_title_against_a_live_task(self):
        planned = [{"id": "TASK-NEW", "title": "Fix the admin self-attach bug"}]
        existing = [{"id": "TASK-OLD", "title": "Admin self attach bug fix",
                     "status": "IMPLEMENTATION_READY"}]
        hits = staffing.find_duplicate_staffing(planned, existing)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["existing_task"], "TASK-OLD")

    def test_does_not_flag_unrelated_titles(self):
        planned = [{"id": "TASK-NEW", "title": "Add dark mode to the dashboard"}]
        existing = [{"id": "TASK-OLD", "title": "Fix the admin self-attach bug",
                     "status": "IN_PROGRESS"}]
        self.assertEqual(staffing.find_duplicate_staffing(planned, existing), [])

    def test_does_not_flag_a_resolved_existing_task(self):
        """A DONE/MERGED/ABANDONED/FAILED task isn't live work someone could
        collide with — restaffing the same title after it shipped or was
        abandoned is a legitimate new task, not a duplicate."""
        planned = [{"id": "TASK-NEW", "title": "Fix the admin self-attach bug"}]
        for status in ("DONE", "MERGED", "ABANDONED", "FAILED"):
            existing = [{"id": "TASK-OLD", "title": "Fix the admin self-attach bug",
                         "status": status}]
            self.assertEqual(staffing.find_duplicate_staffing(planned, existing), [],
                             f"should not flag against a {status} task")

    def test_replanning_the_same_task_id_is_not_a_duplicate(self):
        planned = [{"id": "TASK-1", "title": "Fix the admin self-attach bug"}]
        existing = [{"id": "TASK-1", "title": "Fix the admin self-attach bug",
                     "status": "IN_PROGRESS"}]
        self.assertEqual(staffing.find_duplicate_staffing(planned, existing), [])

    def test_deterministic(self):
        planned = [{"id": "TASK-NEW", "title": "Fix the admin self-attach bug"}]
        existing = [{"id": "TASK-OLD", "title": "Admin self attach fix",
                     "status": "READY"}]
        a = staffing.find_duplicate_staffing(planned, existing)
        b = staffing.find_duplicate_staffing(planned, existing)
        self.assertEqual(a, b)


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
