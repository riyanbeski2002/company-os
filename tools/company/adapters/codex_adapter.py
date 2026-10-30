#!/usr/bin/env python3
"""Compatibility shim for harness.yaml copies written before 2026-10-30.

The shipped `codex` harness now runs `codex exec` directly and declares
`output: codex-jsonl`, so worker.py parses the JSONL itself via
adapters/codex.py. A repo whose own .company/config/harness.yaml still points
its `command` at this script (and has no `output:`, so it's read as
claude-json) keeps working unchanged: this runs codex the same way it always
did, parses with the same adapter, and prints the single Claude-shaped object
that config expects — the model's structured reply spread at top level,
`total_cost_usd` null, exactly the pre-shim output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import codex  # noqa: E402


def main() -> int:
    packet = sys.stdin.read()
    proc = subprocess.run(["codex", "exec", "--json", *sys.argv[1:], "-"],
                          input=packet, capture_output=True, text=True)
    r = codex.parse(proc.stdout, proc.returncode)
    print(json.dumps({
        **(r["structured_output"] or {}),
        "session_id": r["session_id"],
        "is_error": r["is_error"],
        "terminal_reason": r["terminal_reason"],
        "total_cost_usd": None,
        "usage": r["usage"],
    }))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
