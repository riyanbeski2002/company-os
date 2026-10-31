"""Per-harness output adapters (docs/HARNESS-AGNOSTIC-MIGRATION.md §4.1).

Every worker run ends in one normalized result, whatever produced it:

  session_id         str | None   the harness's own id, for resume/attribution
  is_error           bool | None  None = the harness reported nothing (a killed
                                  run prints no result; unknown is not False)
  terminal_reason    str | None
  structured_output  dict | None  the RESULT_SCHEMA-shaped reply, if any
  cost_usd           float | None the harness's OWN estimate; None when it
                                  reports none — never computed here
  num_turns          int | None
  usage              {input_tokens, output_tokens, cache_read_input_tokens,
                      cache_creation_input_tokens} — ints, input disjoint
                      from cache reads (Claude's accounting, the one every
                      historical WORKER_EXITED already uses)

A harness names its stdout format in harness.yaml (`output:`); absent means
`claude-json`, because every harness.yaml written before the field existed
is a Claude one. Adding a harness is a new module with one `parse(raw,
exit_code)` function and one entry in PARSERS — worker.py never learns its
shape.
"""

from __future__ import annotations

from . import agy, claude, codex

DEFAULT_OUTPUT = "claude-json"
PARSERS = {
    "claude-json": claude.parse,
    "codex-jsonl": codex.parse,
    "agy-json": agy.parse,
}


def output_format(spec: dict) -> str:
    return spec.get("output") or DEFAULT_OUTPUT


def parse(spec: dict, raw: str, exit_code: int | None) -> dict:
    return PARSERS[output_format(spec)](raw, exit_code)
