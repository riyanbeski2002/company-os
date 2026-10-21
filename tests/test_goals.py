"""ADR-006 — goals above projects, and outcomes distinct from "done".

What must hold: the four goal events validate exactly as §2 specifies; a
task's goal is resolved in one place (taskstate.fold) without touching its
clock or inventing tasks; delivery and outcome stay two independent axes
(no task event moves outcome, self-assessment and stale or contradicted
measurements are flagged, parents never inherit); only `company goal`
writes goal events, never from inside a worker; and a log that predates all
of this replays byte-identical.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

from eventlog import GOAL_EVENTS, EventLog, EvidenceError, canonical, make_event, validate  # noqa: E402
import goals  # noqa: E402
import taskstate  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"
REAL_COMPANY = HERE.parent / ".company"

KR_MEASURE = {"metric": "manual corrections per close", "unit": "count",
              "baseline": 14, "target": 0, "direction": "decrease"}


def goal_event(name, data, evidence=None, **kw):
    return make_event(event=name, actor=kw.pop("actor", "riyan"),
                      project=kw.pop("project", "_org"), data=data, evidence=evidence, **kw)


class GoalCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        self.log = EventLog(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def define(self, level, title="t", parent=None, measure=None, actor="riyan", **extra):
        data = {"level": level, "title": title, **extra}
        if parent:
            data["parent"] = parent
        if measure:
            data["measure"] = measure
        data.setdefault("id", goals.next_id(self.log.read()))
        goals.append(self.root, event="GOAL_DEFINED", actor=actor, data=data)
        return data["id"]

    def tree(self):
        """G-001 mission -> G-002 objective -> G-003 key result."""
        m = self.define("mission", "run the company")
        o = self.define("objective", "close the books cleanly", parent=m)
        kr = self.define("key_result", "no manual corrections", parent=o, measure=KR_MEASURE)
        return m, o, kr

    def task(self, tid, owner="be-1", **data):
        self.log.append(make_event(event="TASK_CREATED", actor="company-pm", project="p",
                                   task=tid, data={"title": tid, "owner": owner, **data}))

    def task_event(self, tid, name, evidence=None, **data):
        self.log.append(make_event(event=name, actor="integration", project="p", task=tid,
                                   data=data or None, evidence=evidence))

    def link(self, gid, tasks, reason=None, actor="company-pm"):
        data = {"goal": gid, "tasks": tasks}
        if reason:
            data["reason"] = reason
        return goals.append(self.root, event="GOAL_LINKED", actor=actor, data=data)

    def assess(self, gid, verdict, value=None, actor="riyan"):
        data = {"goal": gid, "verdict": verdict}
        if value is not None:
            data["measured"] = {"value": value}
        return goals.append(self.root, event="OUTCOME_ASSESSED", actor=actor, data=data,
                            evidence={"log": "reports/close.csv"})

    def views(self):
        events = self.log.read()
        return goals.fold(events, taskstate.fold(events))


# --- §2: event validation ---------------------------------------------------

class TestGoalDefinedValidation(unittest.TestCase):
    def ok(self, data, **kw):
        validate(goal_event("GOAL_DEFINED", data, **kw))

    def bad(self, data, **kw):
        with self.assertRaises(ValueError):
            validate(goal_event("GOAL_DEFINED", data, **kw))

    def test_valid_shapes(self):
        self.ok({"id": "G-001", "level": "mission", "title": "m"})
        self.ok({"id": "G-002", "level": "objective", "title": "o", "parent": "G-001"})
        self.ok({"id": "G-003", "level": "key_result", "title": "k", "parent": "G-002",
                 "measure": KR_MEASURE, "budget": {"output_tokens": 3000000}})

    def test_must_carry_the_org_sentinel_and_no_task(self):
        self.bad({"id": "G-001", "level": "mission", "title": "m"}, project="finos")
        self.bad({"id": "G-001", "level": "mission", "title": "m"}, task="T-1")

    def test_id_level_and_title(self):
        self.bad({"id": "ESC-1", "level": "mission", "title": "m"})
        self.bad({"id": "G-001", "level": "program", "title": "m"})
        self.bad({"id": "G-001", "level": "mission", "title": "  "})

    def test_parent_rules(self):
        self.bad({"id": "G-001", "level": "mission", "title": "m", "parent": "G-000"})
        self.bad({"id": "G-002", "level": "objective", "title": "o"})
        self.bad({"id": "G-003", "level": "key_result", "title": "k", "measure": KR_MEASURE})

    def test_key_result_needs_a_measure_with_a_target(self):
        self.bad({"id": "G-003", "level": "key_result", "title": "k", "parent": "G-002"})
        self.bad({"id": "G-003", "level": "key_result", "title": "k", "parent": "G-002",
                  "measure": {"metric": "x"}})
        self.bad({"id": "G-003", "level": "key_result", "title": "k", "parent": "G-002",
                  "measure": {**KR_MEASURE, "direction": "sideways"}})

    def test_budget_must_be_numbers(self):
        self.bad({"id": "G-001", "level": "mission", "title": "m", "budget": {"output_tokens": "lots"}})
        self.bad({"id": "G-001", "level": "mission", "title": "m", "budget": {"output_tokens": -1}})


class TestOtherGoalEventValidation(unittest.TestCase):
    def test_goal_linked(self):
        validate(goal_event("GOAL_LINKED", {"goal": "G-002", "tasks": ["T-1"]}))
        validate(goal_event("GOAL_LINKED", {"goal": None, "tasks": ["T-1"]}))
        for data in ({"tasks": ["T-1"]}, {"goal": "G-002", "tasks": []},
                     {"goal": "G-002", "tasks": "T-1"}):
            with self.assertRaises(ValueError):
                validate(goal_event("GOAL_LINKED", data))
        with self.assertRaises(ValueError):
            validate(goal_event("GOAL_LINKED", {"goal": "G-002", "tasks": ["T-1"]}, task="T-1"))

    def test_outcome_assessed_requires_evidence(self):
        with self.assertRaises(EvidenceError):
            validate(goal_event("OUTCOME_ASSESSED", {"goal": "G-003", "verdict": "achieved"}))

    def test_outcome_assessed_refuses_a_bare_commit(self):
        """A commit proves something shipped, not that it worked."""
        with self.assertRaises(EvidenceError):
            validate(goal_event("OUTCOME_ASSESSED", {"goal": "G-003", "verdict": "achieved"},
                                evidence={"commit": "a3e20be15408e7876b4d02811d5c86c63fa16e19"}))
        validate(goal_event("OUTCOME_ASSESSED", {"goal": "G-003", "verdict": "achieved"},
                            evidence={"commit": "a3e20be", "log": "reports/close.csv"}))

    def test_outcome_assessed_verdict_and_measured(self):
        for data in ({"goal": "G-003", "verdict": "probably"},
                     {"goal": "G-003", "verdict": "achieved", "measured": {"as_of": "x"}},
                     {"verdict": "achieved"}):
            with self.assertRaises(ValueError):
                validate(goal_event("OUTCOME_ASSESSED", data, evidence={"log": "x"}))

    def test_goal_closed(self):
        validate(goal_event("GOAL_CLOSED", {"goal": "G-3", "disposition": "abandoned", "reason": "r"}))
        validate(goal_event("GOAL_CLOSED", {"goal": "G-3", "disposition": "superseded",
                                            "superseded_by": "G-9", "reason": "r"}))
        for data in ({"goal": "G-3", "disposition": "done", "reason": "r"},
                     {"goal": "G-3", "disposition": "superseded", "reason": "r"},
                     {"goal": "G-3", "disposition": "abandoned"}):
            with self.assertRaises(ValueError):
                validate(goal_event("GOAL_CLOSED", data))


class TestHistoryRules(GoalCase):
    def test_ids_are_sequential_and_revisions_reuse_them(self):
        m, o, kr = self.tree()
        self.assertEqual((m, o, kr), ("G-001", "G-002", "G-003"))
        self.define("objective", "renamed", parent=m, id=o, reason="sharper wording")
        self.assertEqual(goals.next_id(self.log.read()), "G-004")
        view = self.views()[o]
        self.assertEqual(view["title"], "renamed")
        self.assertEqual([r["reason"] for r in view["revisions"]], ["sharper wording"])

    def test_revision_requires_a_reason_and_keeps_its_level(self):
        m, o, _ = self.tree()
        with self.assertRaises(ValueError):
            self.define("objective", "renamed", parent=m, id=o)
        with self.assertRaises(ValueError):
            self.define("mission", "promoted", id=o, reason="r")

    def test_parent_must_be_the_level_above(self):
        m, o, kr = self.tree()
        with self.assertRaises(ValueError):
            self.define("key_result", "k", parent=m, measure=KR_MEASURE)
        with self.assertRaises(ValueError):
            self.define("objective", "o", parent=o)
        with self.assertRaises(ValueError):
            self.define("objective", "o", parent="G-099")

    def test_at_most_one_open_mission(self):
        m = self.define("mission", "m")
        with self.assertRaises(ValueError):
            self.define("mission", "another")
        goals.append(self.root, event="GOAL_CLOSED", actor="riyan",
                     data={"goal": m, "disposition": "abandoned", "reason": "pivot"})
        self.define("mission", "another")

    def test_never_link_to_the_mission_or_a_closed_goal(self):
        m, o, _ = self.tree()
        self.task("T-1")
        with self.assertRaises(ValueError):
            self.link(m, ["T-1"])
        goals.append(self.root, event="GOAL_CLOSED", actor="riyan",
                     data={"goal": o, "disposition": "abandoned", "reason": "r"})
        with self.assertRaises(ValueError):
            self.link(o, ["T-1"])

    def test_retro_linking_a_terminal_task_needs_a_reason(self):
        _, o, _ = self.tree()
        self.task("T-1")
        self.task_event("T-1", "MERGED", evidence={"commit": "abcdef1"})
        with self.assertRaises(ValueError):
            self.link(o, ["T-1"])
        self.link(o, ["T-1"], reason="retro-link: predates ADR-006")

    def test_key_result_verdict_needs_a_measured_value(self):
        *_, kr = self.tree()
        with self.assertRaises(ValueError):
            self.assess(kr, "achieved")
        self.assess(kr, "inconclusive")
        self.assess(kr, "achieved", value=0)

    def test_assess_and_close_need_a_defined_goal(self):
        with self.assertRaises(ValueError):
            self.assess("G-404", "achieved")
        with self.assertRaises(ValueError):
            goals.append(self.root, event="GOAL_CLOSED", actor="riyan",
                         data={"goal": "G-404", "disposition": "abandoned", "reason": "r"})


# --- §3: task -> goal linking -----------------------------------------------

class TestTaskLinking(GoalCase):
    def test_goal_at_creation(self):
        self.task("T-1", goal="G-002")
        self.assertEqual(taskstate.fold(self.log.read())["T-1"]["goal"], "G-002")

    def test_absence_means_ungoaled_no_default_key(self):
        self.task("T-1")
        self.assertNotIn("goal", taskstate.fold(self.log.read())["T-1"])

    def test_later_link_wins_and_unlink_sets_null(self):
        _, o, kr = self.tree()
        self.task("T-1", goal=o)
        self.link(kr, ["T-1"])
        self.assertEqual(taskstate.fold(self.log.read())["T-1"]["goal"], kr)
        self.link(None, ["T-1"])
        self.assertIsNone(taskstate.fold(self.log.read())["T-1"]["goal"])
        self.assertEqual(self.views()[kr]["tasks"], [])

    def test_linking_never_touches_updated_at(self):
        """Relinking is classification, not work — bumping the clock would
        reset detect_stale_tasks/detect_resting_tasks."""
        events = [
            {"seq": 1, "ts": "2026-01-01T00:00:00Z", "event": "TASK_CREATED", "actor": "pm",
             "project": "p", "task": "T-1", "data": {"title": "x"}},
            {"seq": 2, "ts": "2026-06-01T00:00:00Z", "event": "GOAL_LINKED", "actor": "pm",
             "project": "_org", "data": {"goal": "G-002", "tasks": ["T-1"]}},
        ]
        task = taskstate.fold(events)["T-1"]
        self.assertEqual(task["goal"], "G-002")
        self.assertEqual(task["updated_at"], "2026-01-01T00:00:00Z")

    def test_unknown_ids_never_become_phantom_tasks(self):
        _, o, _ = self.tree()
        self.task("T-1")
        self.link(o, ["T-1", "T-TYPO"])
        tasks = taskstate.fold(self.log.read())
        self.assertNotIn("T-TYPO", tasks)
        view = self.views()[o]
        self.assertEqual(view["tasks"], ["T-1"])
        self.assertEqual(view["unknown_tasks"], ["T-TYPO"])
        self.assertIn("unknown_tasks", view["flags"])


# --- §4: delivery and outcome -----------------------------------------------

class TestOutcomeAxis(GoalCase):
    def test_no_goal_events_means_no_views(self):
        self.task("T-1")
        self.assertEqual(self.views(), {})

    def test_delivered_but_unassessed_is_awaiting_assessment(self):
        _, o, _ = self.tree()
        self.task("T-1", goal=o)
        self.task("T-2", goal=o)
        self.task_event("T-1", "MERGED", evidence={"commit": "abcdef1"})
        self.task_event("T-2", "TASK_COMPLETED")
        view = self.views()[o]
        self.assertEqual(view["delivery"]["state"], "delivered")
        self.assertEqual((view["delivery"]["done"], view["delivery"]["merged"]), (1, 1))
        self.assertEqual(view["outcome"]["state"], "unassessed")
        self.assertIn("awaiting_assessment", view["flags"])

    def test_shipped_and_not_achieved_is_first_class(self):
        _, o, _ = self.tree()
        self.task("T-1", goal=o)
        self.task_event("T-1", "MERGED", evidence={"commit": "abcdef1"})
        self.assess(o, "not_achieved")
        view = self.views()[o]
        self.assertEqual((view["delivery"]["state"], view["outcome"]["state"]),
                         ("delivered", "not_achieved"))
        self.assertEqual(view["flags"], [])

    def test_achieved_with_tasks_still_open(self):
        _, o, _ = self.tree()
        self.task("T-1", goal=o)
        self.task_event("T-1", "WORKER_STARTED")
        self.assess(o, "achieved")
        view = self.views()[o]
        self.assertEqual((view["delivery"]["state"], view["outcome"]["state"]),
                         ("in_progress", "achieved"))

    def test_self_assessment_is_flagged_and_never_counts(self):
        _, o, _ = self.tree()
        self.task("T-1", goal=o, owner="be-1")
        self.assess(o, "achieved", actor="be-1")
        view = self.views()[o]
        self.assertEqual(view["outcome"]["state"], "unassessed")
        self.assertTrue(view["assessments"][0]["self_assessed"])
        self.assertIn("self_assessed", view["flags"])
        self.assess(o, "not_achieved", actor="riyan")
        view = self.views()[o]
        self.assertEqual(view["outcome"]["state"], "not_achieved")
        self.assertNotIn("self_assessed", view["flags"])

    def test_staleness_is_by_seq(self):
        _, o, _ = self.tree()
        self.task("T-1", goal=o)
        self.task("T-2", goal=o)
        self.task_event("T-1", "MERGED", evidence={"commit": "abcdef1"})
        self.assess(o, "achieved")
        self.assertFalse(self.views()[o]["outcome"]["stale"])
        self.task_event("T-2", "MERGED", evidence={"commit": "abcdef2"})
        view = self.views()[o]
        self.assertTrue(view["outcome"]["stale"])
        self.assertIn("stale", view["flags"])
        self.assess(o, "achieved")
        self.assertFalse(self.views()[o]["outcome"]["stale"])

    def test_parents_never_inherit(self):
        _, o, kr = self.tree()
        self.assess(kr, "achieved", value=0)
        views = self.views()
        self.assertEqual(views[kr]["outcome"]["state"], "achieved")
        self.assertEqual(views[o]["children_achieved"], {"achieved": 1, "total": 1})
        self.assertEqual(views[o]["outcome"]["state"], "unassessed")

    def test_meets_target_is_computed(self):
        dec = {"metric": "m", "target": 0, "direction": "decrease"}
        inc = {"metric": "m", "target": 10, "direction": "increase"}
        self.assertTrue(goals.meets_target(dec, {"value": 0}))
        self.assertFalse(goals.meets_target(dec, {"value": 3}))
        self.assertTrue(goals.meets_target(inc, {"value": 12.5}))
        self.assertFalse(goals.meets_target(inc, {"value": 9}))
        self.assertIsNone(goals.meets_target({"metric": "m", "target": 0}, {"value": 3}))
        self.assertIsNone(goals.meets_target({**dec, "target": "zero"}, {"value": 3}))
        self.assertIsNone(goals.meets_target(dec, {"value": "about three"}))
        self.assertIsNone(goals.meets_target(dec, {"value": True}))

    def test_contradicted_verdict_is_assessment_inconsistent(self):
        """"achieved" at 3 against a target of 0, decreasing."""
        *_, kr = self.tree()
        self.assess(kr, "achieved", value=3)
        view = self.views()[kr]
        self.assertFalse(view["assessments"][0]["meets_target"])
        self.assertIn("assessment_inconsistent", view["flags"])
        self.assess(kr, "not_achieved", value=3)
        self.assertNotIn("assessment_inconsistent", self.views()[kr]["flags"])

    def test_closed_goals_drop_out_of_gaps_but_stay_readable(self):
        _, o, kr = self.tree()
        self.task("T-1", goal=kr)
        self.task_event("T-1", "MERGED", evidence={"commit": "abcdef1"})
        events = self.log.read()
        gap = goals.gaps(goals.fold(events, taskstate.fold(events)), taskstate.fold(events), {})
        self.assertEqual(gap["awaiting_assessment"], [kr])
        self.assertEqual(gap["key_results_unassessed"], [kr])
        goals.append(self.root, event="GOAL_CLOSED", actor="riyan",
                     data={"goal": kr, "disposition": "abandoned", "reason": "r"})
        events = self.log.read()
        views = goals.fold(events, taskstate.fold(events))
        gap = goals.gaps(views, taskstate.fold(events), {})
        self.assertEqual((gap["awaiting_assessment"], gap["key_results_unassessed"]), ([], []))
        self.assertEqual(views[kr]["status"], "closed")
        self.assertEqual(views[kr]["closed"]["disposition"], "abandoned")
        self.assertEqual(views[o]["children_achieved"], {"achieved": 0, "total": 0})

    def test_gaps_lists_ungoaled_tasks_per_project(self):
        _, o, _ = self.tree()
        self.task("T-1", goal=o)
        self.task("T-2")
        self.task("T-3", goal="G-404")
        events = self.log.read()
        tasks = taskstate.fold(events)
        gap = goals.gaps(goals.fold(events, tasks), tasks, {})
        self.assertEqual(gap["ungoaled_tasks"], {"p": ["T-2"]})
        self.assertEqual(gap["tasks_linked_to_undefined_goal"], {"G-404": ["T-3"]})

    def test_spend_is_by_task_summed_and_budget_is_report_only(self):
        _, o, _ = self.tree()
        self.define("objective", "close the books cleanly", parent="G-001", id=o,
                    budget={"output_tokens": 1000}, reason="add a budget")
        self.task("T-1", goal=o)
        self.task("T-2", goal=o)
        self.task("T-3")
        for tid, out in (("T-1", 500), ("T-2", 300), ("T-3", 9999)):
            self.log.append(make_event(event="WORKER_EXITED", actor="be", project="p", task=tid,
                                       data={"tokens": {"output": out}, "elapsed_s": 1}))
        view = self.views()[o]
        self.assertEqual(view["activity"]["output_tokens"], 800)
        self.assertEqual(view["activity"]["runs"], 2)
        policy = {"unit": "output_tokens", "warn_at_ratio": 0.8, "enforce": False}
        status = goals.budget_status(view, policy)
        self.assertEqual((status["spent"], status["ratio"], status["warn"]), (800, 0.8, True))
        self.assertFalse(goals.budget_status(view, {**policy, "warn_at_ratio": 0.9})["warn"])


# --- rebuild coverage --------------------------------------------------------

class TestRebuild(GoalCase):
    def test_no_goals_creates_no_directory(self):
        self.task("T-1")
        taskstate.rebuild(self.root)
        self.assertFalse((self.root / "goals").exists())
        self.assertEqual(taskstate.rebuild(self.root, verify=True)[1], [])

    def test_views_replay_byte_identical_and_strays_are_mismatches(self):
        _, o, _ = self.tree()
        self.task("T-1", goal=o)
        taskstate.rebuild(self.root)
        self.assertEqual(sorted(p.name for p in (self.root / "goals").glob("*.json")),
                         ["G-001.json", "G-002.json", "G-003.json"])
        self.assertEqual(taskstate.rebuild(self.root, verify=True)[1], [])

        (self.root / "goals" / "G-099.json").write_text("{}\n")
        (self.root / "goals" / "G-002.json").write_text("{}\n")
        mismatches = taskstate.rebuild(self.root, verify=True)[1]
        self.assertTrue(any("G-099.json: on disk but no events" in m for m in mismatches))
        self.assertTrue(any("G-002.json: differs from replay" in m for m in mismatches))


# --- §5: CLI and its guards -------------------------------------------------

class TestCli(GoalCase):
    def run_cli(self, *args, actor_env=None, stdin=None):
        env = dict(os.environ)
        env.pop("COMPANY_ACTOR", None)
        env.pop("COMPANY_PROJECT", None)
        if actor_env:
            env["COMPANY_ACTOR"] = actor_env
        return subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env, input=stdin)

    def test_raw_company_event_refuses_all_four(self):
        payloads = {
            "GOAL_DEFINED": {"id": "G-001", "level": "mission", "title": "m"},
            "GOAL_LINKED": {"goal": "G-002", "tasks": ["T-1"]},
            "OUTCOME_ASSESSED": {"goal": "G-002", "verdict": "achieved"},
            "GOAL_CLOSED": {"goal": "G-002", "disposition": "abandoned", "reason": "r"},
        }
        for name, data in payloads.items():
            r = self.run_cli("event", name, "--project", "_org", "--data", json.dumps(data),
                             "--evidence", "reports/x.csv")
            self.assertEqual(r.returncode, 2, name)
            self.assertIn("company goal", r.stderr)
        self.assertEqual(self.log.read(), [])

    def test_goal_mutations_refuse_inside_a_worker(self):
        m, o, kr = self.tree()
        self.task("T-1")
        before = self.log.read()
        for argv in (["define", "--level", "objective", "--title", "x", "--parent", m],
                     ["link", o, "--tasks", "T-1"],
                     ["assess", kr, "--verdict", "achieved", "--evidence", "x.csv",
                      "--measured-value", "0"],
                     ["close", kr, "--disposition", "abandoned", "--reason", "r"]):
            r = self.run_cli("goal", *argv, actor_env="backend-engineer-01")
            self.assertEqual(r.returncode, 2, argv)
            self.assertIn("inside a launched worker", r.stderr)
        self.assertEqual(self.log.read(), before)

    def test_reads_are_allowed_inside_a_worker(self):
        self.tree()
        for argv in (["tree"], ["show", "G-002"], ["gaps"]):
            self.assertEqual(self.run_cli("goal", *argv, actor_env="be-1").returncode, 0, argv)

    def test_define_link_assess_close_round_trip(self):
        r = self.run_cli("goal", "define", "--level", "mission", "--title", "m", "--actor", "riyan")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["goal"], "G-001")
        self.run_cli("goal", "define", "--level", "objective", "--title", "o", "--parent", "G-001")
        r = self.run_cli("goal", "define", "--level", "key_result", "--title", "k",
                         "--parent", "G-002", "--measure", json.dumps(KR_MEASURE))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_cli("goal", "define", "--id", "G-003", "--title", "k2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("requires a reason", r.stderr)
        r = self.run_cli("goal", "define", "--id", "G-003", "--title", "k2", "--reason", "rename")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.task("T-1")
        self.assertEqual(self.run_cli("goal", "link", "G-003", "--tasks", "T-1").returncode, 0)

        r = self.run_cli("goal", "assess", "G-003", "--verdict", "achieved",
                         "--evidence", "a3e20be15408e7876b4d02811d5c86c63fa16e19",
                         "--measured-value", "0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("bare commit", r.stderr)
        r = self.run_cli("goal", "assess", "G-003", "--verdict", "achieved",
                         "--evidence", "reports/close.csv", "--measured-value", "3")
        self.assertEqual(r.returncode, 0, r.stderr)

        show = json.loads(self.run_cli("goal", "show", "G-003").stdout)
        self.assertEqual(show["title"], "k2")
        self.assertEqual(show["measure"], KR_MEASURE)  # carried through the revision
        self.assertEqual(show["linked_tasks"][0]["id"], "T-1")
        self.assertIn("assessment_inconsistent", show["flags"])
        self.assertEqual(json.loads(self.run_cli("goal", "gaps").stdout)
                         ["assessment_inconsistent"], ["G-003"])
        tree = json.loads(self.run_cli("goal", "tree", "--json").stdout)["goals"]
        self.assertEqual(tree[0]["children"][0]["children"][0]["id"], "G-003")
        self.assertIn("G-003 key_result: k2", self.run_cli("goal", "tree").stdout)

        r = self.run_cli("goal", "close", "G-003", "--disposition", "abandoned", "--reason", "r")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((self.root / "goals" / "G-003.json").read_text())["status"],
                         "closed")
        self.assertEqual(self.run_cli("rebuild", "--verify").returncode, 0)

    def plan(self, spec):
        return self.run_cli("plan", "--allow-tier-escalation", stdin=json.dumps(spec))

    def test_plan_stamps_the_spec_goal_onto_tasks_lacking_one(self):
        _, o, kr = self.tree()
        r = self.plan({"project": "p", "request": "fix", "goal": o, "tasks": [
            {"id": "P-1", "title": "a", "tier": 0},
            {"id": "P-2", "title": "b", "tier": 0, "goal": kr}]})
        self.assertEqual(r.returncode, 0, r.stderr)
        planned = {t["id"]: t for t in json.loads(r.stdout)["tasks"]}
        self.assertEqual((planned["P-1"]["goal"], planned["P-2"]["goal"]), (o, kr))

    def test_plan_without_a_goal_adds_no_goal_key(self):
        r = self.plan({"project": "p", "request": "fix", "tasks": [{"id": "P-1", "title": "a"}]})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("goal", json.loads(r.stdout)["tasks"][0])

    def test_plan_refuses_an_undefined_or_mission_goal(self):
        m, _, _ = self.tree()
        for gid in ("G-404", m):
            r = self.plan({"project": "p", "goal": gid, "tasks": [{"id": "P-1", "title": "a"}]})
            self.assertEqual(r.returncode, 1, gid)

    def test_goal_text_never_reaches_the_risk_table(self):
        """§6: an objective about payments must not fire the payments
        trigger on every task under it."""
        m = self.define("mission", "m")
        o = self.define("objective", "grow payments revenue via stripe billing", parent=m)
        task = {"id": "P-1", "title": "fix a typo in the footer", "owned_globs": ["docs/**"]}
        without = json.loads(self.plan({"project": "p", "tasks": [task]}).stdout)["tasks"][0]
        with_goal = json.loads(self.plan({"project": "q", "goal": o, "tasks": [task]}).stdout)["tasks"][0]
        for k in ("gates", "triggers_fired", "fast_path"):
            self.assertEqual(without[k], with_goal[k], k)


# --- migration safety (ADR-006 Consequences) ---------------------------------

@unittest.skipUnless((REAL_COMPANY / "events" / "events.jsonl").exists(),
                     "no real event log in this checkout")
class TestRealLogReplaysUnchanged(unittest.TestCase):
    """Against a COPY of this repo's own log: never the live .company/."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        shutil.copy(REAL_COMPANY / "events" / "events.jsonl", self.root / "events")
        shutil.copytree(REAL_COMPANY / "tasks", self.root / "tasks")

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_task_view_replays_byte_identical(self):
        events = EventLog(self.root).read()
        tasks = taskstate.fold(events)
        on_disk = sorted(p.stem for p in (self.root / "tasks").glob("*.json"))
        self.assertEqual(sorted(tasks), on_disk)
        predates_goals = not any(e.get("event") in GOAL_EVENTS for e in events)
        for tid, task in tasks.items():
            if predates_goals:
                self.assertNotIn("goal", task, tid)
            self.assertEqual(canonical(task), (self.root / "tasks" / f"{tid}.json").read_text(
                encoding="utf-8"), tid)

    def test_no_goal_views_and_rebuild_verify_passes(self):
        events = EventLog(self.root).read()
        if any(e.get("event") in GOAL_EVENTS or "goal" in (e.get("data") or {})
               for e in events):
            self.skipTest("this log has started recording goals")
        self.assertEqual(goals.fold(events, taskstate.fold(events)), {})
        self.assertEqual(taskstate.rebuild(self.root, verify=True)[1], [])
        taskstate.rebuild(self.root)
        self.assertFalse((self.root / "goals").exists())


if __name__ == "__main__":
    unittest.main()
