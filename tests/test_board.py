"""board.py — the coordination board (KNOWN_GAPS.md #7): typed, peer-visible
notes for concurrently running subagents sharing one exploratory subject.
Mined from microsoft/Agensh's board-service, reimplemented natively on this
repo's own event log (no adoption, no reference, no dependency)."""

import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "company"))

import board  # noqa: E402
from eventlog import make_event  # noqa: E402


class TestValidateNote(unittest.TestCase):
    def _data(self, **over):
        base = {"subject": "T-1", "type": "FACT", "content": "the bug is in parse()"}
        base.update(over)
        return base

    def test_valid_fact_passes(self):
        board.validate_note(self._data())

    def test_unknown_type_rejected(self):
        with self.assertRaises(board.BoardError):
            board.validate_note(self._data(type="RUMOR"))

    def test_empty_subject_rejected(self):
        with self.assertRaises(board.BoardError):
            board.validate_note(self._data(subject="  "))

    def test_empty_content_rejected(self):
        with self.assertRaises(board.BoardError):
            board.validate_note(self._data(content=""))

    def test_content_over_cap_rejected(self):
        with self.assertRaises(board.BoardError):
            board.validate_note(self._data(content="x" * (board.CONTENT_CAP + 1)))

    def test_done_summary_gets_the_wider_cap(self):
        content = "x" * (board.CONTENT_CAP + 1) + " passed"
        self.assertLessEqual(len(content), board.DONE_SUMMARY_CAP)
        board.validate_note(self._data(type="DONE_SUMMARY", content=content))

    def test_done_summary_with_weasel_words_rejected(self):
        for weak in ("should work now", "looks right to me", "pending review", "TBD"):
            with self.assertRaises(board.BoardError):
                board.validate_note(self._data(type="DONE_SUMMARY", content=weak))

    def test_done_summary_with_real_evidence_accepted(self):
        for solid in ("tests passed", "confirmed against main",
                     "no longer throws", "now returns the right value"):
            board.validate_note(self._data(type="DONE_SUMMARY", content=solid))

    def test_claim_ttl_must_be_a_non_negative_number(self):
        board.validate_note(self._data(type="CLAIM", content="taking the parser", ttl_seconds=60))
        with self.assertRaises(board.BoardError):
            board.validate_note(self._data(type="CLAIM", content="taking the parser", ttl_seconds=-1))
        with self.assertRaises(board.BoardError):
            board.validate_note(self._data(type="CLAIM", content="taking the parser", ttl_seconds="soon"))


def _ev(seq, actor, subject, type, content, ttl_seconds=None, ts=None):
    data = {"subject": subject, "type": type, "content": content}
    if ttl_seconds is not None:
        data["ttl_seconds"] = ttl_seconds
    ev = make_event(event="BOARD_NOTE", actor=actor, project="p", data=data)
    ev["seq"] = seq
    if ts:
        ev["ts"] = ts
    return ev


class TestReadBoard(unittest.TestCase):
    def test_durable_facts_are_deduped_with_a_count(self):
        events = [
            _ev(1, "w1", "T-1", "FACT", "config.py has no default"),
            _ev(2, "w2", "T-1", "FACT", "config.py  has no default"),  # whitespace-only diff
        ]
        view = board.read_board(events, "T-1")
        self.assertEqual(len(view["facts"]), 1)
        self.assertEqual(view["facts"][0]["count"], 2)

    def test_fail_invalidates_the_same_actors_later_claim(self):
        events = [
            _ev(1, "w1", "T-1", "CLAIM", "trying the regex approach"),
            _ev(2, "w1", "T-1", "FAIL", "regex approach doesn't handle nesting"),
        ]
        view = board.read_board(events, "T-1")
        self.assertEqual(view["open_claims"], [])

    def test_fail_does_not_invalidate_a_different_actors_claim(self):
        events = [
            _ev(1, "w1", "T-1", "CLAIM", "trying the regex approach"),
            _ev(2, "w2", "T-1", "FAIL", "unrelated finding"),
        ]
        view = board.read_board(events, "T-1")
        self.assertEqual(len(view["open_claims"]), 1)

    def test_expired_claim_is_excluded_from_open_claims(self):
        old_ts = "2020-01-01T00:00:00Z"
        events = [_ev(1, "w1", "T-1", "CLAIM", "taking the parser", ttl_seconds=60, ts=old_ts)]
        view = board.read_board(events, "T-1", now=time.time())
        self.assertEqual(view["open_claims"], [])

    def test_unexpired_claim_is_open(self):
        events = [_ev(1, "w1", "T-1", "CLAIM", "taking the parser", ttl_seconds=3600)]
        view = board.read_board(events, "T-1", now=board._ts_epoch(events[0]["ts"]) + 10)
        self.assertEqual(len(view["open_claims"]), 1)

    def test_done_summary_invalidated_by_a_later_fail_from_the_same_actor(self):
        events = [
            _ev(1, "w1", "T-1", "DONE_SUMMARY", "fix applied, tests passed"),
            _ev(2, "w1", "T-1", "FAIL", "the fix regressed a different test"),
        ]
        view = board.read_board(events, "T-1")
        self.assertTrue(view["done_summaries"][0]["invalidated_by_fail"])

    def test_latest_directive_wins(self):
        events = [
            _ev(1, "pm", "T-1", "DIRECTIVE", "explore broadly"),
            _ev(2, "pm", "T-1", "DIRECTIVE", "converge, time is short"),
        ]
        view = board.read_board(events, "T-1")
        self.assertEqual(view["latest_directive"]["content"], "converge, time is short")

    def test_a_different_subject_never_leaks_in(self):
        events = [_ev(1, "w1", "T-2", "FACT", "irrelevant to T-1")]
        view = board.read_board(events, "T-1")
        self.assertEqual(view["facts"], [])


class TestPublishedSince(unittest.TestCase):
    def test_true_when_the_actor_published_after_the_seq(self):
        events = [_ev(5, "w1", "T-1", "FACT", "found it")]
        self.assertTrue(board.published_since(events, "T-1", "w1", 1))

    def test_false_when_nothing_follows_the_seq(self):
        events = [_ev(1, "w1", "T-1", "CLAIM", "taking it")]
        self.assertFalse(board.published_since(events, "T-1", "w1", 1))

    def test_false_for_a_different_actor(self):
        events = [_ev(5, "w2", "T-1", "FACT", "found it")]
        self.assertFalse(board.published_since(events, "T-1", "w1", 1))


if __name__ == "__main__":
    unittest.main()
