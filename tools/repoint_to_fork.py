#!/usr/bin/env python3
"""Point an already-cloned external/<id>/ working copy at its fork's remote,
once config/capability-registry.yaml has a forked_to: for it (the fork may
have been created after the local clone, e.g. due to GitHub's fork-creation
throttle delaying it — see external/README.md).

Usage:
    tools/repoint_to_fork.py <id> [<id> ...]
    tools/repoint_to_fork.py --all    # repoint everything that has both
                                       # local_path and forked_to
"""
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "capability-registry.yaml"
EXTERNAL_DIR = REPO_ROOT / "external"


def main():
    args = sys.argv[1:]
    data = yaml.safe_load(REGISTRY.read_text())
    entries = {e["id"]: e for e in data.get("entries", [])}

    if args == ["--all"]:
        ids = [i for i, e in entries.items() if e.get("local_path") and e.get("forked_to")]
    else:
        ids = args

    for id_ in ids:
        e = entries.get(id_)
        if not e or not e.get("forked_to"):
            print(f"  {id_:45s} SKIP (no forked_to in registry)")
            continue
        dest = EXTERNAL_DIR / id_
        if not (dest / ".git").is_dir():
            print(f"  {id_:45s} SKIP (not cloned yet — run sync_external_capabilities.py first)")
            continue
        r = subprocess.run(
            ["git", "-C", str(dest), "remote", "set-url", "origin", e["forked_to"]],
            capture_output=True, text=True,
        )
        status = "repointed" if r.returncode == 0 else f"FAILED: {r.stderr.strip()[:150]}"
        print(f"  {id_:45s} {status} -> {e['forked_to']}")


if __name__ == "__main__":
    main()
