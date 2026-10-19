"""Staffing engine (D4). Determinism is the whole point of the table."""

import sys
import tempfile
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


class TestJoinExistingGateGroups(unittest.TestCase):
    """resolve-os, 2026-09-16/17: 18 tasks staffed across 6 separate `company
    plan` calls in ~29h produced 6 gate_groups (and PRs) — default_gate_group
    only ever sees its own batch. This is the cross-plan-call half."""

    def test_joins_a_still_open_group_sharing_owned_files(self):
        planned = [{"id": "NEW-1", "tier": 2, "project": "p",
                    "owned_globs": ["src/ticket/move-ticket.ts"]}]
        existing = [{"id": "OLD-1", "project": "p", "status": "IN_PROGRESS",
                     "gate_group": "wave-1-group",
                     "owned_globs": ["src/ticket/move-ticket.ts"]}]
        joins = staffing.join_existing_gate_groups(planned, existing)
        self.assertEqual(len(joins), 1)
        self.assertEqual(planned[0]["gate_group"], "wave-1-group")

    def test_does_not_join_a_group_that_already_reached_review(self):
        planned = [{"id": "NEW-1", "tier": 2, "project": "p",
                    "owned_globs": ["src/ticket/move-ticket.ts"]}]
        existing = [{"id": "OLD-1", "project": "p", "status": "REVIEW",
                     "gate_group": "wave-1-group",
                     "owned_globs": ["src/ticket/move-ticket.ts"]}]
        joins = staffing.join_existing_gate_groups(planned, existing)
        self.assertEqual(joins, [])
        self.assertNotIn("gate_group", planned[0])

    def test_does_not_join_across_projects(self):
        planned = [{"id": "NEW-1", "tier": 2, "project": "p2",
                    "owned_globs": ["src/ticket/move-ticket.ts"]}]
        existing = [{"id": "OLD-1", "project": "p1", "status": "IN_PROGRESS",
                     "gate_group": "wave-1-group",
                     "owned_globs": ["src/ticket/move-ticket.ts"]}]
        joins = staffing.join_existing_gate_groups(planned, existing)
        self.assertEqual(joins, [])

    def test_does_not_join_without_overlapping_files(self):
        planned = [{"id": "NEW-1", "tier": 2, "project": "p",
                    "owned_globs": ["src/unrelated.ts"]}]
        existing = [{"id": "OLD-1", "project": "p", "status": "IN_PROGRESS",
                     "gate_group": "wave-1-group",
                     "owned_globs": ["src/ticket/move-ticket.ts"]}]
        joins = staffing.join_existing_gate_groups(planned, existing)
        self.assertEqual(joins, [])

    def test_never_overrides_an_explicit_gate_group(self):
        planned = [{"id": "NEW-1", "tier": 2, "project": "p",
                    "gate_group": "manual-choice",
                    "owned_globs": ["src/ticket/move-ticket.ts"]}]
        existing = [{"id": "OLD-1", "project": "p", "status": "IN_PROGRESS",
                     "gate_group": "wave-1-group",
                     "owned_globs": ["src/ticket/move-ticket.ts"]}]
        joins = staffing.join_existing_gate_groups(planned, existing)
        self.assertEqual(joins, [])
        self.assertEqual(planned[0]["gate_group"], "manual-choice")

    def test_joining_makes_the_task_ineligible_for_a_fresh_batch_group(self):
        """The composition with default_gate_group(): a task that joins an
        existing group here is no longer eligible there, since it already
        carries a gate_group."""
        planned = [
            {"id": "NEW-1", "tier": 2, "project": "p", "gates": ["review"],
             "owned_globs": ["src/ticket/move-ticket.ts"]},
            {"id": "NEW-2", "tier": 2, "project": "p", "gates": ["review"]},
        ]
        existing = [{"id": "OLD-1", "project": "p", "status": "IN_PROGRESS",
                     "gate_group": "wave-1-group",
                     "owned_globs": ["src/ticket/move-ticket.ts"]}]
        staffing.join_existing_gate_groups(planned, existing)
        group_id, assigned = staffing.default_gate_group(planned, "p")
        self.assertEqual(planned[0]["gate_group"], "wave-1-group")
        # NEW-2 is the only one left eligible for a new batch group, and one
        # task alone can't form one.
        self.assertIsNone(group_id)
        self.assertEqual(assigned, [])


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


class TestPresentationalPathDowngrade(unittest.TestCase):
    """Riyan, 2026-10-19: "a UI landing page with 'auth' written... should
    not trigger security, waste of effort." Keyword-only hits on purely
    presentational content are downgraded instead of forced — still fully
    deterministic, still conservative in every direction that matters."""

    SYN_CFG = {
        "presentational_paths": ["**/content/**", "**/*.copy.tsx"],
        "triggers": [
            {"name": "authentication", "keywords": ["login", "auth"],
             "paths": ["**/auth/**", "**/session/**"], "gates": ["review", "qa", "security"]},
        ],
        "baseline_gates": ["review"],
    }

    def test_keyword_only_hit_on_presentational_paths_is_downgraded(self):
        r = staffing.evaluate(self.SYN_CFG, "Add a Login button to the landing page",
                              ["ui/content/landing.md"])
        self.assertEqual(r["gates"], ["review"])
        self.assertEqual(r["triggers_fired"], [])
        self.assertEqual([d["trigger"] for d in r["downgraded_triggers"]], ["authentication"])

    def test_a_real_path_hit_is_never_downgraded_regardless_of_keyword(self):
        r = staffing.evaluate(self.SYN_CFG, "Add a Login button",
                              ["api/auth/session.ts"])
        self.assertIn("security", r["gates"])
        self.assertEqual(r["downgraded_triggers"], [])

    def test_a_non_presentational_path_is_never_downgraded(self):
        """A form component isn't pure copy — conservative by design."""
        r = staffing.evaluate(self.SYN_CFG, "Add a Login button",
                              ["ui/components/LoginForm.tsx"])
        self.assertIn("security", r["gates"])
        self.assertEqual(r["downgraded_triggers"], [])

    def test_no_declared_paths_at_all_is_never_downgraded(self):
        """Nothing to judge presentational from — can't be less conservative
        than today's behavior just because owned_globs wasn't filled in yet."""
        r = staffing.evaluate(self.SYN_CFG, "Add a Login button", [])
        self.assertIn("security", r["gates"])
        self.assertEqual(r["downgraded_triggers"], [])

    def test_mixed_paths_where_only_some_are_presentational_is_not_downgraded(self):
        """Every owned path must be presentational, not just some of them."""
        r = staffing.evaluate(self.SYN_CFG, "Add a Login button",
                              ["ui/content/landing.md", "api/handlers.ts"])
        self.assertIn("security", r["gates"])
        self.assertEqual(r["downgraded_triggers"], [])

    def test_no_presentational_paths_configured_never_downgrades_anything(self):
        cfg = {**self.SYN_CFG, "presentational_paths": []}
        r = staffing.evaluate(cfg, "Add a Login button", ["ui/content/landing.md"])
        self.assertIn("security", r["gates"])

    def test_downgrade_is_visible_with_its_evidence_not_silent(self):
        r = staffing.evaluate(self.SYN_CFG, "Add a Login button",
                              ["ui/content/landing.md"])
        entry = r["downgraded_triggers"][0]
        self.assertEqual(entry["matched_keyword"], "login")
        self.assertEqual(entry["owned_paths"], ["ui/content/landing.md"])
        self.assertIn("reason", entry)

    def test_real_config_downgrades_the_exact_reported_false_positive(self):
        """Integration check against the actual shipped config/
        risk-triggers.yaml, not just a synthetic fixture."""
        r = staffing.evaluate(
            CFG, "Update the landing page copy to say Login or Sign up for free",
            ["ui/content/landing.copy.tsx"])
        self.assertNotIn("security", r["gates"])
        self.assertIn("authentication", [d["trigger"] for d in r["downgraded_triggers"]])

    def test_real_config_still_gates_real_auth_implementation(self):
        r = staffing.evaluate(
            CFG, "Implement session token verification for the login endpoint",
            ["api/auth/session.ts"])
        self.assertIn("security", r["gates"])
        self.assertEqual(r["downgraded_triggers"], [])


class TestConfigDrift(unittest.TestCase):
    """`company doctor`'s self-hosted-only drift check — real incident,
    2026-10-19: a plugin policy fix (restoring the baseline review gate)
    never reached `.company/config/risk-triggers.yaml`, so company-os's own
    repo ran without it for ~5 weeks while believing it was fixed."""

    def _tree(self, tmp: Path, repo_files: dict, company_files: dict) -> tuple[Path, Path]:
        repo = tmp / "repo"
        (repo / "config").mkdir(parents=True)
        for name, text in repo_files.items():
            (repo / "config" / name).write_text(text)
        root = tmp / "repo" / ".company"
        (root / "config").mkdir(parents=True)
        for name, text in company_files.items():
            (root / "config" / name).write_text(text)
        return repo, root

    def test_identical_files_are_not_drifted(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, root = self._tree(
                Path(tmp),
                {"staffing.yaml": "policy: a\n"},
                {"staffing.yaml": "policy: a\n"})
            self.assertEqual(staffing.config_drift(repo, root), [])

    def test_a_diverged_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, root = self._tree(
                Path(tmp),
                {"risk-triggers.yaml": "baseline_gates: [review]\n"},
                {"risk-triggers.yaml": "baseline_gates: []\n"})
            self.assertEqual(staffing.config_drift(repo, root), ["risk-triggers.yaml"])

    def test_a_file_with_no_repo_copy_is_not_flagged(self):
        """Nothing to compare against -- not the same failure mode as a
        stale copy that silently shadows a fix."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, root = self._tree(Path(tmp), {"new.yaml": "x: 1\n"}, {})
            self.assertEqual(staffing.config_drift(repo, root), [])

    def test_multiple_drifted_files_all_reported_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, root = self._tree(
                Path(tmp),
                {"staffing.yaml": "a: 1\n", "risk-triggers.yaml": "b: 1\n"},
                {"staffing.yaml": "a: 2\n", "risk-triggers.yaml": "b: 2\n"})
            self.assertEqual(staffing.config_drift(repo, root),
                              ["risk-triggers.yaml", "staffing.yaml"])


if __name__ == "__main__":
    unittest.main()
