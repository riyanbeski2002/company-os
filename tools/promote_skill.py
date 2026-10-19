#!/usr/bin/env python3
"""PM-only promotion of a staged skill proposal (tools/propose_skill.py)
into a live, loadable skill. The only step that writes `skills/` or
`capability-registry.yaml` — mirroring capability-curator's own "only
company-pm writes the registry entry, after approval" rule for external
adoptions (skills/capability-curator/SKILL.md).

Appends the new entry as TEXT rather than parsing and rewriting
capability-registry.yaml as a whole YAML document on purpose:
`config/capability-registry.yaml` is full of hand-written prose comments
documenting individual decisions, and `yaml.safe_load` + `yaml.dump` would
silently discard every one of them on a round-trip. The appended block is
built via `yaml.dump` (so its own syntax is correct) and the WHOLE resulting
file is re-parsed before anything touches disk, so a malformed append is
caught before it corrupts the registry rather than after.

Usage:
    tools/promote_skill.py <slug> --approved-by <name> [--trust-tier T0] [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROPOSED_DIR = REPO_ROOT / ".company" / "proposed_skills"
SKILLS_DIR = REPO_ROOT / "skills"
REGISTRY = REPO_ROOT / "config" / "capability-registry.yaml"


class PromotionError(ValueError):
    pass


def _read_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    end = text.find("\n---", 3)
    return yaml.safe_load(text[3:end]) or {}


def build_entry(slug: str, fm: dict, approved_by: str, trust_tier: str, today: str) -> dict:
    return {
        "id": slug,
        "type": "skill",
        "purpose": (fm.get("description") or "")[:300],
        "trust_tier": trust_tier,
        "source": "authored in this repo",
        "license": "original",
        "approved_by": approved_by,
        "approved_at": today,
        "checked_at": today,
    }


def append_entry_text(registry_path: Path, entry: dict) -> str:
    """The new registry text, with `entry` appended — not yet written."""
    # One entry, rendered the same way the file's existing entries are
    # shaped, then re-indented under `  - ` the way a list item needs.
    block = yaml.dump([entry], sort_keys=False, allow_unicode=True, width=100)
    indented = "\n".join(
        ("  " + line if line.strip() else line) for line in block.splitlines()
    )
    original = registry_path.read_text(encoding="utf-8")
    sep = "" if original.endswith("\n") else "\n"
    return original + sep + indented + "\n"


def promote(slug: str, approved_by: str, trust_tier: str = "T0",
            today: str | None = None, proposed_dir: Path = PROPOSED_DIR,
            skills_dir: Path = SKILLS_DIR, registry_path: Path = REGISTRY) -> Path:
    draft_dir = proposed_dir / slug
    draft = draft_dir / "SKILL.md"
    if not draft.is_file():
        raise PromotionError(f"no staged draft at {draft}")

    dest_dir = skills_dir / slug
    if dest_dir.exists():
        raise PromotionError(
            f"{dest_dir} already exists — pick a different slug or review the collision first")

    existing = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    if any(e.get("id") == slug for e in existing.get("entries", [])):
        raise PromotionError(f"capability-registry.yaml already has an entry {slug!r}")

    fm = _read_frontmatter(draft)
    entry = build_entry(slug, fm, approved_by, trust_tier, today or date.today().isoformat())
    new_text = append_entry_text(registry_path, entry)

    # Validate before touching disk at all: a malformed append must fail
    # here, not leave the registry half-written. An `entries: []` registry
    # (never true for the real file today, which always has entries already,
    # but a real possibility for a from-scratch one) can't take a block-style
    # append after a flow-style empty list — that's a real YAML syntax error,
    # not a corruption, so it's caught the same way any other malformed
    # append would be.
    try:
        reparsed = yaml.safe_load(new_text)
    except yaml.YAMLError as e:
        raise PromotionError(
            f"appending would produce invalid YAML, nothing written: {e}") from e
    if not any(e.get("id") == slug for e in reparsed.get("entries", [])):
        raise PromotionError("internal error: appended entry did not round-trip, nothing written")

    shutil.copytree(draft_dir, dest_dir)
    registry_path.write_text(new_text, encoding="utf-8")
    shutil.rmtree(draft_dir)
    return dest_dir


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("slug")
    p.add_argument("--approved-by", required=True)
    p.add_argument("--trust-tier", default="T0")
    p.add_argument("--today")
    args = p.parse_args()
    try:
        dest = promote(args.slug, args.approved_by, args.trust_tier, args.today)
    except PromotionError as e:
        sys.exit(f"Not promoted: {e}")
    print(f"Promoted to {dest} and registered in capability-registry.yaml")


if __name__ == "__main__":
    main()
