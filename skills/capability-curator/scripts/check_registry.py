#!/usr/bin/env python3
"""Deterministic staleness check for the capability registry.

"Check the registry, and re-check if it's been a while" as a prose
instruction relies on an agent remembering to do arithmetic on a date every
time. A script that computes it is the actual mechanism — same answer,
every time, no re-derivation.

Usage: check_registry.py <path-to-capability-registry.yaml> [--stale-after-days N]
Exit code 0 always (this reports, it doesn't gate); JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def check(registry_path: Path, stale_after_days: int, today: date | None = None) -> dict:
    import yaml
    today = today or date.today()
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    entries = data.get("entries") or []

    fresh, stale, unparseable = [], [], []
    for entry in entries:
        checked_at = entry.get("checked_at")
        eid = entry.get("id", "<no id>")
        if not checked_at:
            unparseable.append(eid)
            continue
        try:
            age_days = (today - _parse_date(checked_at)).days
        except ValueError:
            unparseable.append(eid)
            continue
        (stale if age_days > stale_after_days else fresh).append(
            {"id": eid, "age_days": age_days})

    return {
        "total": len(entries),
        "fresh": fresh,
        "stale": stale,
        "unparseable_checked_at": unparseable,
        "stale_after_days": stale_after_days,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("registry_path", type=Path)
    p.add_argument("--stale-after-days", type=int, default=90)
    args = p.parse_args()

    if not args.registry_path.exists():
        print(json.dumps({"error": f"no registry at {args.registry_path}"}))
        sys.exit(1)

    print(json.dumps(check(args.registry_path, args.stale_after_days), indent=2))


if __name__ == "__main__":
    main()
