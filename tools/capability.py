#!/usr/bin/env python3
"""The "at command" loader for config/capability-index.yaml.

    tools/capability.py list [--type skill|tool|reference]
    tools/capability.py show <unit_id>
    tools/capability.py load <unit_id>     # activates it
    tools/capability.py unload <unit_id>   # deactivates it

`load` on a skill symlinks its directory into skills/<unit_id>/ so Claude
Code's own Skill tool picks it up immediately — live, not copied, so
re-syncing external/ updates it automatically. `load` on a tool prints (and
runs, with confirmation) its detected install command. A `reference` unit has
nothing to load; it's already readable at its `path`.

Every entry loads the same way regardless of trust tier (T1-T3) — Riyan's
explicit instruction, 2026-10-16: the flagged-stars caveat on a few entries
(see their capability-registry.yaml comments) is a documented risk, not a
load-time gate.
"""
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX = REPO_ROOT / "config" / "capability-index.yaml"
SKILLS_DIR = REPO_ROOT / "skills"


def load_units():
    if not INDEX.exists():
        sys.exit("config/capability-index.yaml missing — run tools/build_capability_index.py first")
    return {u["unit_id"]: u for u in yaml.safe_load(INDEX.read_text())["units"]}


def cmd_list(args):
    units = load_units()
    type_filter = None
    if "--type" in args:
        type_filter = args[args.index("--type") + 1]
    by_type = {}
    for u in units.values():
        if type_filter and u["type"] != type_filter:
            continue
        by_type.setdefault(u["type"], []).append(u)
    for t in ("skill", "tool", "reference"):
        if t not in by_type:
            continue
        print(f"\n=== {t} ({len(by_type[t])}) ===")
        for u in sorted(by_type[t], key=lambda x: x["unit_id"]):
            loaded = " [LOADED]" if t == "skill" and (SKILLS_DIR / u["unit_id"].replace(":", "__")).exists() else ""
            print(f"  {u['unit_id']:50s}{loaded}")


def cmd_search(args):
    if not args:
        sys.exit("usage: tools/capability.py search <keyword> [<keyword> ...]")
    units = load_units()
    terms = [a.lower() for a in args]
    hits = []
    for u in units.values():
        text = f"{u['unit_id']} {u.get('name','')} {u.get('description','')}".lower()
        if all(t in text for t in terms):
            hits.append(u)
    if not hits:
        print(f"No matches for: {' '.join(args)}")
        return
    for u in sorted(hits, key=lambda x: x["unit_id"]):
        desc = (u.get("description") or "")[:100].replace("\n", " ")
        print(f"  [{u['type']:9s}] {u['unit_id']:50s} {desc}")
    print(f"\n{len(hits)} match(es). `show <unit_id>` for detail, `load <unit_id>` to activate a skill.")


def cmd_show(args):
    units = load_units()
    u = units.get(args[0]) if args else None
    if not u:
        sys.exit(f"unknown unit_id: {args[0] if args else '(none given)'}")
    print(yaml.dump(u, sort_keys=False, allow_unicode=True))


def cmd_load(args):
    units = load_units()
    u = units.get(args[0]) if args else None
    if not u:
        sys.exit(f"unknown unit_id: {args[0] if args else '(none given)'}")

    if u["type"] == "reference":
        print(f"'{u['unit_id']}' is reference-only — already readable at {u['path']}, nothing to load.")
        return

    if u["type"] == "skill":
        src = (REPO_ROOT / u["path"]).resolve()
        link_name = u["unit_id"].replace(":", "__")
        dest = SKILLS_DIR / link_name
        if dest.is_symlink() or dest.exists():
            print(f"'{link_name}' already loaded at skills/{link_name}")
            return
        dest.symlink_to(src)
        print(f"loaded: skills/{link_name} -> {src}")
        if u.get("pairs_with"):
            print(f"pairs well with: {', '.join(u['pairs_with'])} (load those too if the task needs them)")
        return

    if u["type"] == "tool":
        cmd = u.get("load_cmd", "")
        print(f"'{u['unit_id']}' install command: {cmd}")
        print(f"  (cd external/{u['registry_id']} && {cmd.split(' (')[0]})")
        if u.get("pairs_with"):
            print(f"pairs well with: {', '.join(u['pairs_with'])}")


def cmd_unload(args):
    units = load_units()
    u = units.get(args[0]) if args else None
    if not u or u["type"] != "skill":
        sys.exit(f"'{args[0] if args else ''}' is not a loaded skill unit")
    link_name = u["unit_id"].replace(":", "__")
    dest = SKILLS_DIR / link_name
    if dest.is_symlink():
        dest.unlink()
        print(f"unloaded: skills/{link_name}")
    else:
        print(f"'{link_name}' was not loaded")


COMMANDS = {"list": cmd_list, "show": cmd_show, "load": cmd_load, "unload": cmd_unload}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: tools/capability.py <{'|'.join(COMMANDS)}> [args]")
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
