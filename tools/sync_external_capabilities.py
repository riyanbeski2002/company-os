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

CLOSED (donor review, 2026-10-19, tasks/lessons.md): `sync_one` used to
track each fork's default branch (`git clone --depth 1`, `git pull
--ff-only`) rather than a pinned commit, so a fork owner pushing new commits
silently changed what the next `--check`-less run pulled in — paperclip's
own skills-store requires a pinned 40-character commit SHA before import for
exactly this reason. `tools/pin_external_commits.py` pinned all 76
already-cloned entries to their then-current HEAD the same day; `sync_one`
now checks out an entry's `pinned_commit` exactly (fetch, then checkout —
never `pull`) when one is present, and only falls back to tracking the
branch HEAD for an entry that genuinely has none yet (a brand-new adoption,
before someone runs `pin_external_commits.py` on it — printed as
"UNPINNED" by `--check` so that state stays visible, not silently normal).
Updating a pin after a deliberate, reviewed upstream change is
`pin_external_commits.py <id>` again, by hand — there is no automatic
re-pin, the same way there is no automatic adoption.
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
    pinned = entry.get("pinned_commit")
    dest = EXTERNAL_DIR / id_

    if (dest / ".git").is_dir():
        if check_only:
            trust_note = f"pinned @ {pinned[:12]}" if pinned else "UNPINNED (tracks branch HEAD)"
            print(f"  {id_:45s} present ({src_note}, {trust_note})   {dest}")
            return True
        if pinned:
            # A pin means "this exact commit was reviewed" — fetch new
            # history without moving the working tree, then land on exactly
            # that commit. No `git pull`: that would move past the review
            # the pin represents (tools/pin_external_commits.py, the gap
            # this closes for the ~76 entries pinned 2026-10-19).
            run(["git", "-C", str(dest), "fetch", "--quiet", "origin"])
            r = run(["git", "-C", str(dest), "checkout", "--quiet", pinned])
            status = (f"checked out pinned {pinned[:12]}" if r.returncode == 0
                      else f"PIN CHECKOUT FAILED: {r.stderr.strip()[:150]}")
        else:
            r = run(["git", "-C", str(dest), "pull", "--ff-only"])
            status = "pulled (UNPINNED)" if r.returncode == 0 else f"PULL FAILED: {r.stderr.strip()[:150]}"
        print(f"  {id_:45s} {status} ({src_note})")
        return r.returncode == 0

    if check_only:
        print(f"  {id_:45s} MISSING   run without --check to clone from {url}")
        return False

    EXTERNAL_DIR.mkdir(exist_ok=True)
    # A pinned entry needs enough history to reach that commit — depth 1
    # only ever has the branch tip, which the pin may no longer be. An
    # unpinned entry keeps the original shallow, fast clone.
    clone_cmd = ["git", "clone", url, str(dest)] if pinned else \
        ["git", "clone", "--depth", "1", url, str(dest)]
    r = run(clone_cmd, timeout=180 if pinned else 90)
    if r.returncode == 0 and pinned:
        r = run(["git", "-C", str(dest), "checkout", "--quiet", pinned])
        status = (f"cloned, checked out pinned {pinned[:12]}" if r.returncode == 0
                  else f"CHECKOUT OF PIN FAILED: {r.stderr.strip()[:150]}")
    else:
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
