"""Locks the CLI JSON contract documented in doc/integrations/cli-json-contract.md.

A read-only consumer (cmd-center's GUI-01..05) shells out to `company ... `
and parses stdout. Nothing in the CLI itself would notice a refactor that
renames `stalled`, drops `by_task`, or turns `goals` into a dict, so each
test here asserts the EXACT top-level key set and the basic type of every
key. Adding, removing or renaming a key fails here first; update the
contract doc (and its changelog) in the same change that updates the test.

Values are deliberately not asserted — they depend on the clock and on
whatever the fixture log happens to contain.

Runs the real CLI as a subprocess against a tempdir `--root`, so argparse,
emit() and canonical() are all on the path a consumer actually takes.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

from eventlog import EventLog, canonical, make_event  # noqa: E402
import escalations  # noqa: E402
import goals  # noqa: E402

CLI = HERE.parent / "tools" / "company" / "cli.py"
NULL = type(None)

STATUS_KEYS = {"project": (str, NULL), "progress": str, "progress_pct": (int, NULL),
               "tasks": list, "escalations": list, "stalled": dict,
               "early_warning": dict}
TASK_ALWAYS = {"id", "project", "status", "evidence", "criteria_met",
               "created_at", "updated_at"}
ESCALATION_ALWAYS = {"id", "kind", "need", "blocking", "raised_by", "raised_at",
                     "task", "project"}
COSTS_KEYS = {"project": (str, NULL), "billed_to": str, "worker_runs": int,
              "tasks_delivered": int, "tokens": dict,
              "tokens_per_delivered_task": (dict, NULL),
              "wall_clock_minutes": (int, float), "api_equivalent_usd": (int, float),
              "by_actor": list, "by_task": list, "untasked": dict,
              "runs_with_unestimated_cost": int, "runs_with_backfilled_tokens": int,
              "notes": list}
TOKEN_KEYS = {"input", "output", "cache_read", "cache_creation"}
BY_ACTOR_ALWAYS = {"actor", "runs", "output_tokens", "cache_read_tokens", "seconds",
                   "usd_equivalent", "tasks", "turns", "runs_missing_turns",
                   "runs_with_unestimated_cost"}
BY_ACTOR_WITH_TURNS = {"avg_cache_read_per_turn", "avg_output_per_turn"}
BY_TASK_KEYS = {"task", "runs", "output_tokens", "cache_read_tokens", "seconds",
                "usd_equivalent", "actors", "split_across_tasks"}
UNTASKED_KEYS = {"runs", "output_tokens", "cache_read_tokens", "seconds", "usd_equivalent"}
TREE_NODE_KEYS = {"id": str, "level": str, "title": str, "status": str,
                  "delivery": dict, "outcome": dict, "flags": list,
                  "activity": dict, "children": list}
DELIVERY_KEYS = {"state", "total", "done", "merged", "abandoned", "open"}
OUTCOME_KEYS = {"state", "assessed_seq", "stale", "self_assessed", "inconsistent"}
ACTIVITY_KEYS = {"runs", "output_tokens", "cache_read_tokens", "seconds",
                 "usd_equivalent", "includes_split_estimate"}
GOAL_SHOW_DERIVED = {"id": str, "level": str, "title": str, "status": str,
                     "defined_by": str, "defined_at": str, "revisions": list,
                     "tasks": list, "projects": list, "unknown_tasks": list,
                     "delivery": dict, "activity": dict, "assessments": list,
                     "outcome": dict, "children": list, "children_achieved": dict,
                     "flags": list, "linked_tasks": list,
                     "budget_status": (dict, NULL)}
BUDGET_STATUS_KEYS = {"unit", "budget", "spent", "ratio", "warn", "enforced"}
GAPS_KEYS = {"ungoaled_tasks": dict, "awaiting_assessment": list, "stale": list,
             "self_assessed": list, "assessment_inconsistent": list,
             "key_results_unassessed": list, "unknown_tasks": dict,
             "tasks_linked_to_undefined_goal": dict, "budget_warnings": list}
ESCALATE_LIST_KEYS = {"ok": bool, "filter": str, "count": int, "escalations": list}
# Every documented JSON command accepts `--json`, so a consumer can pass it
# uniformly; on the always-JSON ones it is a no-op.
ALWAYS_JSON = (("costs",), ("goal", "gaps"), ("escalate", "--list", "all"))


class ContractCase(unittest.TestCase):
    """One small but non-trivial log: two projects, a delivered task, a
    blocked task, an ungoaled task, tasked + untasked worker runs, a goal
    tree with a budget and an independent assessment, and one open plus
    one resolved escalation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".company"
        (self.root / "events").mkdir(parents=True)
        log = EventLog(self.root)

        for tid, project, owner in (("T-1", "p", "backend-engineer"),
                                    ("T-2", "p", "backend-engineer"),
                                    ("T-3", "q", "frontend-engineer")):
            log.append(make_event(event="TASK_CREATED", actor="company-pm", project=project,
                                  task=tid, data={"title": f"task {tid}", "owner": owner}))
        log.append(make_event(event="MERGED", actor="integration", project="p", task="T-1",
                              evidence={"commit": "abc1234"}))
        log.append(make_event(
            event="WORKER_EXITED", actor="backend-engineer", project="p", task="T-1",
            data={"tokens": {"input": 10, "output": 200, "cache_read": 5000,
                             "cache_creation": 30},
                  "cost_usd_estimate": 0.12, "num_turns": 4, "elapsed_s": 90}))
        log.append(make_event(
            event="WORKER_EXITED", actor="cfo-advisor", project="p",
            data={"tokens": {"input": 1, "output": 50, "cache_read": 900,
                             "cache_creation": 0},
                  "cost_usd_estimate": 0.01, "elapsed_s": 12}))

        escalations.raise_escalation(self.root, project="p", actor="company-pm",
                                     kind="human_action", need="unblock T-2", task="T-2")
        resolved = escalations.raise_escalation(self.root, project="q", actor="company-pm",
                                                kind="information", need="which API?")
        log.append(make_event(event="ESCALATION_RESOLVED", actor="riyan", project="q",
                              data={"id": resolved["id"], "resolution": "the v2 one"}))

        def define(level, title, parent=None, **extra):
            data = {"id": goals.next_id(log.read()), "level": level, "title": title, **extra}
            if parent:
                data["parent"] = parent
            goals.append(self.root, event="GOAL_DEFINED", actor="riyan", data=data)
            return data["id"]

        self.mission = define("mission", "ship it")
        self.objective = define("objective", "reliable delivery", self.mission,
                                budget={"output_tokens": 100})
        define("key_result", "fewer reruns", self.objective,
               measure={"metric": "reruns", "unit": "count", "baseline": 5,
                        "target": 1, "direction": "decrease"})
        goals.append(self.root, event="GOAL_LINKED", actor="riyan",
                     data={"goal": self.objective, "tasks": ["T-1", "T-2"],
                           "reason": "T-1 merged before the goal existed"})
        goals.append(self.root, event="OUTCOME_ASSESSED", actor="riyan",
                     data={"goal": self.objective, "verdict": "achieved"},
                     evidence={"log": "reports/reruns.txt"})

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        env = {k: v for k, v in os.environ.items()
               if k not in ("COMPANY_ACTOR", "COMPANY_PROJECT", "COMPANY_ROOT")}
        r = subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def run_json(self, *args):
        stdout = self.run_cli(*args)
        out = json.loads(stdout)
        # Every documented command goes through emit(): sorted keys, indent 2.
        self.assertEqual(stdout, canonical(out))
        return out

    def assertShape(self, obj, spec):
        """Exact key set, and each value an instance of its declared type(s)."""
        self.assertEqual(set(obj), set(spec))
        for key, types in spec.items():
            self.assertIsInstance(obj[key], types, key)
            # bool is an int subclass; a count must never silently become one.
            if types is int or (isinstance(types, tuple) and int in types and bool not in types):
                self.assertNotIsInstance(obj[key], bool, key)


class TestStatusContract(ContractCase):
    def test_top_level_keys_and_types(self):
        for args in ((), ("--project", "p")):
            with self.subTest(args=args):
                self.assertShape(self.run_json("status", "--json", *args), STATUS_KEYS)

    def test_task_and_escalation_entries(self):
        out = self.run_json("status", "--json")
        self.assertEqual(len(out["tasks"]), 3)
        for task in out["tasks"]:
            self.assertLessEqual(TASK_ALWAYS, set(task))
        self.assertEqual(len(out["escalations"]), 1)  # resolved ones drop out
        self.assertLessEqual(ESCALATION_ALWAYS, set(out["escalations"][0]))
        self.assertIsInstance(out["escalations"][0]["blocking"], bool)
        for reason in (*out["stalled"].values(), *out["early_warning"].values()):
            self.assertIsInstance(reason, str)

    def test_progress_pct_is_null_when_progress_is_unknown(self):
        # No fixture task has acceptance criteria, so progress can't be computed.
        out = self.run_json("status", "--json")
        self.assertEqual(out["progress"], "unknown")
        self.assertIsNone(out["progress_pct"])

    def test_progress_pct_is_the_number_behind_progress(self):
        EventLog(self.root).append(make_event(
            event="TASK_CREATED", actor="company-pm", project="r", task="T-4",
            data={"title": "task T-4", "acceptance_criteria": ["a", "b"],
                  "criteria_met": ["a"]}))
        out = self.run_json("status", "--json", "--project", "r")
        self.assertEqual(out["progress"], "50%")  # unchanged, still a string
        self.assertEqual(out["progress_pct"], 50)
        self.assertNotIsInstance(out["progress_pct"], bool)


class TestCostsContract(ContractCase):
    def test_top_level_keys_and_types(self):
        out = self.run_json("costs")
        self.assertShape(out, COSTS_KEYS)
        self.assertEqual(set(out["tokens"]), TOKEN_KEYS)
        self.assertEqual(set(out["tokens_per_delivered_task"]), TOKEN_KEYS)
        self.assertEqual(set(out["untasked"]), UNTASKED_KEYS)
        self.assertTrue(all(isinstance(n, str) for n in out["notes"]))

    def test_no_delivered_task_means_null_per_task_tokens(self):
        self.assertIsNone(self.run_json("costs", "--project", "q")["tokens_per_delivered_task"])

    def test_breakdown_entries(self):
        out = self.run_json("costs")
        by_actor = {e["actor"]: e for e in out["by_actor"]}
        self.assertEqual(len(by_actor), len(out["by_actor"]))  # one entry per actor
        self.assertEqual(set(by_actor["backend-engineer"]),
                         BY_ACTOR_ALWAYS | BY_ACTOR_WITH_TURNS)
        # The per-turn averages appear only once a run reported num_turns.
        self.assertEqual(set(by_actor["cfo-advisor"]), BY_ACTOR_ALWAYS)
        self.assertEqual([e["task"] for e in out["by_task"]], ["T-1"])
        self.assertEqual(set(out["by_task"][0]), BY_TASK_KEYS)

    def test_breakdowns_keep_their_cost_rank(self):
        """by_actor is ranked by output tokens, by_task by cache-read tokens,
        both descending. The extra run is picked so that rank and
        alphabetical order disagree for both lists: as dicts, sort_keys
        put `aaa-reviewer` and `T-1` first and the ranking was lost."""
        EventLog(self.root).append(make_event(
            event="WORKER_EXITED", actor="aaa-reviewer", project="p", task="T-2",
            data={"tokens": {"input": 1, "output": 10, "cache_read": 9000,
                             "cache_creation": 0},
                  "cost_usd_estimate": 0.02, "elapsed_s": 5}))
        out = self.run_json("costs")
        self.assertEqual([e["actor"] for e in out["by_actor"]],
                         ["backend-engineer", "cfo-advisor", "aaa-reviewer"])
        self.assertEqual([e["task"] for e in out["by_task"]], ["T-2", "T-1"])
        outputs = [e["output_tokens"] for e in out["by_actor"]]
        self.assertEqual(outputs, sorted(outputs, reverse=True))
        cache_reads = [e["cache_read_tokens"] for e in out["by_task"]]
        self.assertEqual(cache_reads, sorted(cache_reads, reverse=True))


class TestGoalContract(ContractCase):
    def test_tree(self):
        out = self.run_json("goal", "tree", "--json")
        self.assertEqual(set(out), {"goals"})
        self.assertIsInstance(out["goals"], list)
        self.assertEqual(len(out["goals"]), 1)

        def walk(node):
            self.assertShape(node, TREE_NODE_KEYS)
            self.assertEqual(set(node["delivery"]), DELIVERY_KEYS)
            self.assertEqual(set(node["outcome"]), OUTCOME_KEYS)
            self.assertEqual(set(node["activity"]), ACTIVITY_KEYS)
            return 1 + sum(walk(c) for c in node["children"])

        self.assertEqual(walk(out["goals"][0]), 3)

    def test_show(self):
        out = self.run_json("goal", "show", self.objective)
        # Definition keys (`parent`, `budget`, `measure`, `closed`) are present
        # only when the goal has them; everything else is always derived.
        self.assertShape(out, {**GOAL_SHOW_DERIVED, "parent": str, "budget": dict})
        self.assertEqual(set(out["budget_status"]), BUDGET_STATUS_KEYS)
        self.assertEqual(set(out["children_achieved"]), {"achieved", "total"})
        for linked in out["linked_tasks"]:
            self.assertEqual(set(linked), {"id", "status", "project", "title"})
        self.assertLessEqual({"seq", "by", "at", "verdict", "measured", "method",
                              "evidence", "self_assessed", "meets_target", "inconsistent"},
                             set(out["assessments"][0]))

    def test_show_mission_without_budget(self):
        out = self.run_json("goal", "show", self.mission)
        self.assertShape(out, GOAL_SHOW_DERIVED)
        self.assertIsNone(out["budget_status"])

    def test_gaps(self):
        out = self.run_json("goal", "gaps")
        self.assertShape(out, GAPS_KEYS)
        self.assertEqual(set(out["budget_warnings"][0]), {"goal"} | BUDGET_STATUS_KEYS)


class TestEscalateListContract(ContractCase):
    def test_list(self):
        for flt, count in (("open", 1), ("resolved", 1), ("all", 2)):
            with self.subTest(filter=flt):
                out = self.run_json("escalate", "--list", flt)
                self.assertShape(out, ESCALATE_LIST_KEYS)
                self.assertEqual(out["count"], count)
                for esc in out["escalations"]:
                    self.assertLessEqual(ESCALATION_ALWAYS | {"status"}, set(esc))

    def test_resolved_entry_carries_resolution(self):
        esc = self.run_json("escalate", "--list", "resolved")["escalations"][0]
        self.assertLessEqual({"resolution", "resolved_by", "resolved_at"}, set(esc))


class TestJsonFlagIsAcceptedEverywhere(ContractCase):
    def test_always_json_commands_accept_json_as_a_no_op(self):
        for args in (*ALWAYS_JSON, ("goal", "show", self.objective)):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args, "--json"), self.run_cli(*args))


class TestReportIsTextOnly(ContractCase):
    """`company report` has no JSON mode. If one is added, document it."""

    def test_report_prints_markdown_not_json(self):
        r = subprocess.run([sys.executable, str(CLI), "--root", str(self.root),
                            "report", "--project", "p"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("# p"))
        with self.assertRaises(json.JSONDecodeError):
            json.loads(r.stdout)


if __name__ == "__main__":
    unittest.main()
