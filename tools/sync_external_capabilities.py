#!/usr/bin/env python3
"""Clone/refresh local working copies of forked capability-registry entries.

Every `config/capability-registry.yaml` entry that carries a `forked_to:`
field gets a shallow local clone at `external/<id>/`, so any agent or skill
can read, run, or build on it directly — no `npx skills add` or ad hoc
`git clone` first. See `external/README.md`.

Usage:
    tools/sync_external_capabilities.py            # clone missing, pull present
    tools/sync_external_capabilities.py --check    # report only, change nothing
    tools/sync_external_capabilities.py <id> [...] # sync only these entries

KNOWN GAP (donor review, 2026-10-19, tasks/lessons.md): `sync_one` below
tracks each fork's default branch (`git clone --depth 1`, `git pull
--ff-only`), not a pinned commit. A fork's owner pushing new commits changes
what the next `--check`-less run pulls in, with no re-review required —
paperclip's own skills-store requires a pinned 40-character commit SHA
before import for exactly this reason. Not fixed here: pinning ~76 existing
entries retroactively needs inspecting each fork's current HEAD, a real
audit pass, not a mechanical edit. `tools/build_capability_index.py`'s
`source_commit` field is the partial mitigation that *is* shipped — it makes
a moved fork visible (compare two builds' `source_commit` for the same unit)
even though nothing yet stops the move from happening unreviewed.
"""
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "capability-registry.yaml"
EXTERNAL_DIR = REPO_ROOT / "external"


def load_entries():
    data = yaml.safe_load(REGISTRY.read_text())
    return [e for e in data.get("entries", []) if e.get("local_path")]


def clone_url(entry):
    """Prefer the fork (ours to push to); fall back to upstream `source` if
    the fork hasn't gone through yet (e.g. GitHub's fork-creation throttle).
    A later re-run after the fork lands will switch the remote (see
    tools/repoint_to_fork.py)."""
    if entry.get("forked_to"):
        return entry["forked_to"], True
    src = entry["source"].split("/tree/")[0].rstrip("/")  # drop any /tree/branch/subdir suffix
    return src, False


def run(cmd, **kw):
    kw.setdefault("timeout", 90)
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kw)
    except subprocess.TimeoutExpired:
        class _Timeout:
            returncode = 1
            stderr = f"timed out after {kw['timeout']}s"
        return _Timeout()


def sync_one(entry, check_only):
    id_ = entry["id"]
    url, is_fork = clone_url(entry)
    src_note = "fork" if is_fork else "UPSTREAM (fork pending)"
    dest = EXTERNAL_DIR / id_

    if (dest / ".git").is_dir():
        if check_only:
            print(f"  {id_:45s} present ({src_note})   {dest}")
            return True
        r = run(["git", "-C", str(dest), "pull", "--ff-only"])
        status = "pulled" if r.returncode == 0 else f"PULL FAILED: {r.stderr.strip()[:150]}"
        print(f"  {id_:45s} {status} ({src_note})")
        return r.returncode == 0

    if check_only:
        print(f"  {id_:45s} MISSING   run without --check to clone from {url}")
        return False

    EXTERNAL_DIR.mkdir(exist_ok=True)
    r = run(["git", "clone", "--depth", "1", url, str(dest)])
    status = "cloned" if r.returncode == 0 else f"CLONE FAILED: {r.stderr.strip()[:150]}"
    print(f"  {id_:45s} {status} ({src_note})")
    return r.returncode == 0


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    ids = [a for a in args if not a.startswith("--")]

    entries = load_entries()
    if ids:
        wanted = set(ids)
        entries = [e for e in entries if e["id"] in wanted]
        missing = wanted - {e["id"] for e in entries}
        if missing:
            print(f"Unknown id(s), no forked_to entry: {', '.join(sorted(missing))}")

    print(f"=== syncing {len(entries)} forked capability-registry entries into external/ ===")
    ok = sum(sync_one(e, check_only) for e in entries)
    print(f"\n{ok}/{len(entries)} OK.")
    sys.exit(0 if ok == len(entries) else 1)


if __name__ == "__main__":
    main()
