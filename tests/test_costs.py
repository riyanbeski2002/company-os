"""Consumption reporting.

Workers run on a Claude subscription, so nothing is charged in dollars for
them. Claude Code still reports `total_cost_usd`, which is a client-side
estimate of the equivalent API spend — reporting that as if it were a bill is
simply wrong, and it hides the number that actually constrains a subscription:
tokens, dominated by cache reads.
"""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import worker  # noqa: E402

# Shape of a real `claude -p --output-format json` result.
REAL_RESULT = {
    "total_cost_usd": 0.361738,
    "usage": {
        "output_tokens": 5332,
        "input_tokens": 30,
        "cache_read_input_tokens": 195456,
        "cache_creation_input_tokens": 13056,
    },
    "modelUsage": {"claude-opus-5[1m]": {"provider": "firstParty"}},
}


class TestUsageExtraction(unittest.TestCase):
    def test_extracts_every_token_class(self):
        u = worker._usage(REAL_RESULT)
        self.assertEqual(u["output"], 5332)
        self.assertEqual(u["input"], 30)
        self.assertEqual(u["cache_read"], 195456)
        self.assertEqual(u["cache_creation"], 13056)

    def test_cache_reads_dominate(self):
        """The point of reporting tokens: cache reads are ~37x output here."""
        u = worker._usage(REAL_RESULT)
        self.assertGreater(u["cache_read"], u["output"] * 10)

    def test_missing_usage_is_zeroed_not_crashed(self):
        self.assertEqual(worker._usage({}),
                         {"output": 0, "input": 0, "cache_read": 0,
                          "cache_creation": 0})

    def test_partial_usage_is_tolerated(self):
        u = worker._usage({"usage": {"output_tokens": 10}})
        self.assertEqual(u["output"], 10)
        self.assertEqual(u["cache_read"], 0)


class TestSubscriptionAuth(unittest.TestCase):
    """Workers must reach the subscription, not fall through to API billing."""

    def test_api_key_never_reaches_a_worker(self):
        import os
        import tempfile
        os.environ["ANTHROPIC_API_KEY"] = "sk-would-bill-separately"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                env = worker.build_env(root, root / ".company",
                                       {"id": "T-1", "project": "p"}, "be-1",
                                       root / "wt")
            self.assertNotIn("ANTHROPIC_API_KEY", env)
            self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
