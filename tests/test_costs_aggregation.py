"""costs.aggregate() — task-level and turn-level cost attribution (donor
review, 2026-10-19: cfo-advisor's own finding that a raw cache-read total
and one aggregate ratio can't tell a thorough run from a wasteful one, or
say what any single task actually cost)."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import costs  # noqa: E402


def _exited(actor, *, task=None, tasks=None, output=0, cache_read=0,
            num_turns=None, cost=0.0, elapsed=0.0, project="p"):
    data = {
        "tokens": {"output": output, "cache_read": cache_read,
                   "input": 0, "cache_creation": 0},
        "cost_usd_estimate": cost, "elapsed_s": elapsed,
    }
    if num_turns is not None:
        data["num_turns"] = num_turns
    if tasks is not None:
        data["tasks"] = tasks
    ev = {"event": "WORKER_EXITED", "actor": actor, "project": project, "data": data}
    if task is not None:
        ev["task"] = task
    return ev


class TestByTaskAttribution(unittest.TestCase):
    def test_a_normal_single_task_run_is_attributed_in_full(self):
        events = [_exited("be-1", task="T-1", output=100, cache_read=1000)]
        result = costs.aggregate(events)
        self.assertEqual(result["by_task"]["T-1"]["output_tokens"], 100)
        self.assertEqual(result["by_task"]["T-1"]["cache_read_tokens"], 1000)
        self.assertEqual(result["by_task"]["T-1"]["split_across_tasks"], 1)

    def test_a_gate_group_run_splits_evenly_across_its_tasks(self):
        events = [_exited("code-reviewer-1", tasks=["T-1", "T-2"],
                          output=100, cache_read=1000)]
        result = costs.aggregate(events)
        self.assertEqual(result["by_task"]["T-1"]["output_tokens"], 50)
        self.assertEqual(result["by_task"]["T-2"]["output_tokens"], 50)
        self.assertEqual(result["by_task"]["T-1"]["split_across_tasks"], 2)
        self.assertEqual(result["by_task"]["T-2"]["split_across_tasks"], 2)

    def test_multiple_runs_on_the_same_task_accumulate(self):
        events = [
            _exited("be-1", task="T-1", output=100, cache_read=1000),
            _exited("code-reviewer-1", task="T-1", output=50, cache_read=500),
        ]
        result = costs.aggregate(events)
        self.assertEqual(result["by_task"]["T-1"]["output_tokens"], 150)
        self.assertEqual(result["by_task"]["T-1"]["runs"], 2)
        self.assertEqual(set(result["by_task"]["T-1"]["actors"]), {"be-1", "code-reviewer-1"})

    def test_an_untasked_advisor_run_never_enters_by_task(self):
        events = [_exited("cfo-advisor", output=100, cache_read=1000)]
        result = costs.aggregate(events)
        self.assertEqual(result["by_task"], {})
        self.assertEqual(result["untasked"]["runs"], 1)
        self.assertEqual(result["untasked"]["output_tokens"], 100)

    def test_task_totals_sum_correctly_against_the_project_total(self):
        events = [
            _exited("be-1", task="T-1", output=100, cache_read=1000),
            _exited("cfo-advisor", output=50, cache_read=500),
        ]
        result = costs.aggregate(events)
        self.assertEqual(result["tokens"]["output"], 150)
        self.assertEqual(
            result["by_task"]["T-1"]["output_tokens"] + result["untasked"]["output_tokens"],
            result["tokens"]["output"])


class TestTurnLevelAttribution(unittest.TestCase):
    def test_a_run_with_num_turns_gets_a_per_turn_average(self):
        events = [_exited("cfo-advisor", output=200, cache_read=2000, num_turns=10)]
        result = costs.aggregate(events)
        entry = result["by_actor"]["cfo-advisor"]
        self.assertEqual(entry["avg_output_per_turn"], 20)
        self.assertEqual(entry["avg_cache_read_per_turn"], 200)

    def test_a_run_without_num_turns_is_excluded_from_the_average_not_faked(self):
        events = [_exited("cfo-advisor", output=200, cache_read=2000)]
        result = costs.aggregate(events)
        entry = result["by_actor"]["cfo-advisor"]
        self.assertNotIn("avg_output_per_turn", entry)
        self.assertEqual(entry["runs_missing_turns"], 1)

    def test_mixing_pre_capture_and_post_capture_runs_only_averages_the_captured_ones(self):
        events = [
            _exited("cfo-advisor", output=1000, cache_read=10000),  # old, no num_turns
            _exited("cfo-advisor", output=200, cache_read=2000, num_turns=10),
        ]
        result = costs.aggregate(events)
        entry = result["by_actor"]["cfo-advisor"]
        self.assertEqual(entry["turns"], 10)
        self.assertEqual(entry["runs_missing_turns"], 1)
        # Averaged over the 10 captured turns only, not diluted by the
        # pre-capture run's tokens landing on a turns=0 denominator.
        self.assertEqual(entry["avg_output_per_turn"], 20)

    def test_multiple_captured_runs_accumulate_turns_before_averaging(self):
        events = [
            _exited("cfo-advisor", output=100, cache_read=1000, num_turns=5),
            _exited("cfo-advisor", output=100, cache_read=1000, num_turns=5),
        ]
        result = costs.aggregate(events)
        entry = result["by_actor"]["cfo-advisor"]
        self.assertEqual(entry["turns"], 10)
        self.assertEqual(entry["avg_output_per_turn"], 20)


class TestProjectFiltering(unittest.TestCase):
    def test_a_run_from_a_different_project_is_excluded(self):
        events = [
            _exited("be-1", task="T-1", output=100, cache_read=1000, project="p1"),
            _exited("be-2", task="T-2", output=999, cache_read=9999, project="p2"),
        ]
        result = costs.aggregate(events, project="p1")
        self.assertIn("T-1", result["by_task"])
        self.assertNotIn("T-2", result["by_task"])

    def test_no_project_filter_includes_everything(self):
        events = [
            _exited("be-1", task="T-1", output=100, cache_read=1000, project="p1"),
            _exited("be-2", task="T-2", output=50, cache_read=500, project="p2"),
        ]
        result = costs.aggregate(events, project=None)
        self.assertEqual(set(result["by_task"]), {"T-1", "T-2"})


class TestIgnoresNonExitEvents(unittest.TestCase):
    def test_other_event_types_are_skipped(self):
        events = [
            {"event": "WORKER_STARTED", "actor": "be-1", "project": "p", "task": "T-1", "data": {}},
            _exited("be-1", task="T-1", output=100, cache_read=1000),
        ]
        result = costs.aggregate(events)
        self.assertEqual(result["worker_runs"], 1)

    def test_a_run_with_no_cost_and_no_tokens_is_skipped(self):
        events = [{"event": "WORKER_EXITED", "actor": "be-1", "project": "p",
                   "task": "T-1", "data": {}}]
        result = costs.aggregate(events)
        self.assertEqual(result["worker_runs"], 0)


if __name__ == "__main__":
    unittest.main()
