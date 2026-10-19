#!/usr/bin/env python3
"""Self-service staging for a NEW first-party skill — authored here, not
adopted from an external source (that flow is skills/capability-curator's
discover-then-propose path, for vetting something that already exists
elsewhere). Donor review, 2026-10-19: paperclip lets any agent author/version
a skill mid-task via a tool call; company-os's version keeps the same "a
proposal that could silently become an adoption is not a proposal" rule
capability-curator already states for external resources — staging a draft
here changes nothing live. `tools/promote_skill.py` is the separate, human-
approval-gated step that actually makes a skill loadable.

Usage:
    tools/propose_skill.py <slug> <path-to-draft-SKILL.md>
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROPOSED_DIR = REPO_ROOT / ".company" / "proposed_skills"


class ProposalError(ValueError):
    pass


def validate_draft(draft_path: Path) -> dict:
    """The minimum a real skill needs — frontmatter with name + description,
    and a body substantial enough to be a procedure rather than a stub.
    Raises a specific reason rather than silently staging something
    half-written."""
    if not draft_path.is_file() or draft_path.name != "SKILL.md":
        raise ProposalError("draft must be a file named SKILL.md")
    text = draft_path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        raise ProposalError("SKILL.md must start with YAML frontmatter (---)")
    end = text.find("\n---", 3)
    if end == -1:
        raise ProposalError("frontmatter is never closed (no second ---)")
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as e:
        raise ProposalError(f"frontmatter is not valid YAML: {e}")
    missing = [f for f in ("name", "description") if not fm.get(f)]
    if missing:
        raise ProposalError(f"frontmatter missing required field(s): {', '.join(missing)}")
    body = text[end + 4:].strip()
    if len(body) < 50:
        raise ProposalError("SKILL.md body is too short to be a real procedure, not just a stub")
    return fm


def stage(slug: str, draft_path: Path, proposed_dir: Path = PROPOSED_DIR) -> tuple[Path, dict]:
    fm = validate_draft(draft_path)
    dest_dir = proposed_dir / slug
    if dest_dir.exists():
        raise ProposalError(
            f"{dest_dir} already exists — pick a new slug or remove the stale draft first")
    dest_dir.mkdir(parents=True)
    dest = dest_dir / "SKILL.md"
    shutil.copy(draft_path, dest)
    return dest, fm


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    slug, draft = sys.argv[1], Path(sys.argv[2])
    try:
        dest, fm = stage(slug, draft)
    except ProposalError as e:
        sys.exit(f"Not staged: {e}")

    rel = dest.relative_to(REPO_ROOT)
    need = f"new first-party skill: {slug} ({fm.get('name')}) -- draft at {rel}"
    print(f"Staged at {dest}")
    print()
    print("File the proposal (never write capability-registry.yaml or skills/ yourself):")
    print(f'  company escalate --kind approval --need "{need}"')
    print()
    print("Once approved (company resolve), promotion is a separate, PM-only step:")
    print(f"  tools/promote_skill.py {slug} --approved-by <name>")


if __name__ == "__main__":
    main()
