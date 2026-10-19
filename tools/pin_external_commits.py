#!/usr/bin/env python3
"""Pin every capability-registry.yaml entry with a local clone to its
current commit SHA — closing (for already-cloned entries) the gap
`sync_external_capabilities.py`'s own module docstring documents: that
script tracks each fork's default branch, not a pinned commit, so a fork
owner pushing new commits silently changes what the next sync pulls in with
no re-review required.

Like `promote_skill.py`, this inserts text rather than parsing and
rewriting the whole YAML document: `capability-registry.yaml` is full of
hand-written prose comments a yaml.safe_load/yaml.dump round-trip would
silently discard. Each insertion is scoped to one entry's own text span (via
`_entry_spans`), so an id that happens to be a substring of another id's
`local_path` value can never cause a cross-entry mistake, and the whole
resulting file is re-parsed and entry-counted before anything touches disk.

Usage:
    tools/pin_external_commits.py --check          # report only, change nothing
    tools/pin_external_commits.py                  # pin every unpinned, cloned entry
    tools/pin_external_commits.py <id> [<id> ...]  # pin only these
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "capability-registry.yaml"
EXTERNAL_DIR = REPO_ROOT / "external"

ENTRY_RE = re.compile(r"(?m)^  - id: (\S+)\n")


def current_sha(repo_dir: Path) -> str | None:
    if not (repo_dir / ".git").exists():
        return None
    r = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                        capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _entry_spans(text: str) -> list[tuple[str, int, int]]:
    """[(id, start, end)] for each `  - id: ...` entry block, end exclusive."""
    matches = list(ENTRY_RE.finditer(text))
    spans = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spans.append((m.group(1), start, end))
    return spans


def plan(text: str, ids_with_local_path: set[str],
         only_ids: set[str] | None = None,
         external_dir: Path = EXTERNAL_DIR) -> dict[str, str]:
    """{id: sha} for every entry that: has a `local_path` (an external
    clone, not an Anthropic-native or reference-only entry), is actually
    cloned on disk, has no `pinned_commit` yet, and — if `only_ids` is
    given — is in it."""
    out = {}
    for id_, start, end in _entry_spans(text):
        if id_ not in ids_with_local_path:
            continue
        if only_ids and id_ not in only_ids:
            continue
        if "pinned_commit:" in text[start:end]:
            continue
        sha = current_sha(external_dir / id_)
        if sha:
            out[id_] = sha
    return out


def apply(text: str, shas: dict[str, str]) -> str:
    """The new registry text with `pinned_commit: "<sha>"` inserted right
    after each pinned entry's `local_path:` line — not yet written."""
    out = []
    cursor = 0
    for id_, start, end in _entry_spans(text):
        out.append(text[cursor:start])
        block = text[start:end]
        if id_ in shas:
            block = re.sub(
                r"(?m)^(\s*local_path:.*)$",
                lambda m, sha=shas[id_]: f'{m.group(1)}\n    pinned_commit: "{sha}"',
                block, count=1,
            )
        out.append(block)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    only_ids = {a for a in args if not a.startswith("--")} or None

    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    before_count = len(data.get("entries", []))
    ids_with_local_path = {e["id"] for e in data.get("entries", []) if e.get("local_path")}

    text = REGISTRY.read_text(encoding="utf-8")
    shas = plan(text, ids_with_local_path, only_ids)

    if not shas:
        print("Nothing to pin (every cloned, local_path-bearing entry already "
              "has a pinned_commit, or no id matched).")
        return

    for id_, sha in sorted(shas.items()):
        print(f"  {id_:45s} -> {sha}")

    if check_only:
        noun = "entry" if len(shas) == 1 else "entries"
        print(f"\n{len(shas)} {noun} would be pinned. Run without --check to apply.")
        return

    new_text = apply(text, shas)

    reparsed = yaml.safe_load(new_text)
    after_entries = reparsed.get("entries", [])
    if len(after_entries) != before_count:
        sys.exit(f"Internal error: entry count changed ({before_count} -> "
                  f"{len(after_entries)}) — nothing written.")
    pinned_ids = {e["id"] for e in after_entries if e.get("pinned_commit")}
    missing = set(shas) - pinned_ids
    if missing:
        sys.exit(f"Internal error: {sorted(missing)} did not round-trip a "
                  f"pinned_commit field — nothing written.")

    REGISTRY.write_text(new_text, encoding="utf-8")
    print(f"\nPinned {len(shas)} entries.")


if __name__ == "__main__":
    main()
