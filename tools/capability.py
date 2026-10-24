#!/usr/bin/env python3
"""The "at command" loader for config/capability-index.yaml.

    tools/capability.py list [--type skill|tool|reference]
    tools/capability.py search <keyword> [<keyword> ...]
    tools/capability.py show <unit_id>
    tools/capability.py load <unit_id>     # activates it
    tools/capability.py unload <unit_id>   # deactivates it
    tools/capability.py prepare <brief...> # auto: rank, clone, load for a project

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
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX = REPO_ROOT / "config" / "capability-index.yaml"
SKILLS_DIR = REPO_ROOT / "skills"
sys.path.insert(0, str(REPO_ROOT / "tools"))


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


STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "our", "are",
    "use", "using", "make", "build", "create", "new", "need", "want", "should",
    "can", "will", "not", "all", "any", "how", "what", "when", "your", "you",
    "its", "has", "have", "more", "also", "such", "like", "over", "about",
}
PREPARE_LIMIT = 3
PREPARE_MIN_HITS = 2
# Auto-selection never clones or loads a T4 (unknown provenance / no usable
# license) unit: capability-curator's legend says "reference only". T0-T3 are
# auto-eligible, per Riyan 2026-10-24. Reference-only units stay browsable.
AUTO_TIERS = {"T0", "T1", "T2", "T3"}
REGISTRY = REPO_ROOT / "config" / "capability-registry.yaml"


def _registry_tiers():
    data = yaml.safe_load(REGISTRY.read_text())
    return {e["id"]: e.get("trust_tier") for e in data.get("entries", [])}


def _terms(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}


def rank_units(brief, units, limit=PREPARE_LIMIT, min_hits=PREPARE_MIN_HITS):
    """Units whose id/name/description share at least `min_hits` meaningful
    terms with the brief, best first. Deterministic: ties break on unit_id."""
    wanted = _terms(brief)
    scored = []
    for u in units.values():
        text = f"{u['unit_id']} {u.get('name', '')} {u.get('description', '')}"
        hits = len(wanted & _terms(text))
        if hits >= min_hits:
            scored.append((-hits, u["unit_id"], u))
    return [u for _, _, u in sorted(scored)[:limit]]


def ensure_repo(unit, registry_path=None):
    """Clone the unit's registry repo if it isn't present yet. Never pulls an
    existing clone (that stays an explicit `sync_external_capabilities.py`
    run). Native units (path under skills/) need nothing. Returns True if a
    clone was made."""
    if not unit["path"].startswith("external/"):
        return False
    repo_dir = REPO_ROOT / "external" / unit["registry_id"]
    if (repo_dir / ".git").is_dir():
        return False
    import sync_external_capabilities as sec
    entries = {e["id"]: e for e in sec.load_entries()}
    entry = entries.get(unit["registry_id"])
    if entry is None:
        raise RuntimeError(f"no registry entry for {unit['registry_id']}")
    if not sec.sync_one(entry, check_only=False):
        raise RuntimeError(f"clone failed for {unit['registry_id']}")
    return True


def prepare(brief, limit=PREPARE_LIMIT):
    """Pick the catalog units a project needs, make their repos local, and
    load the skills. Tools are cloned but their install commands are NOT run
    (running an install is code execution — that stays a deliberate act).
    Returns a dict the caller can record or print."""
    import contextlib
    import io
    units = load_units()
    tiers = _registry_tiers()
    eligible = {uid: u for uid, u in units.items()
                if tiers.get(u["registry_id"]) in AUTO_TIERS}
    picked = rank_units(brief, eligible, limit=limit)
    result = {"selected": [], "cloned": [], "loaded": [], "available": []}
    for u in picked:
        result["selected"].append(u["unit_id"])
        if ensure_repo(u):
            result["cloned"].append(u["unit_id"])
        if u["type"] == "skill":
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_load([u["unit_id"]])
            result["loaded"].append(u["unit_id"])
        else:
            result["available"].append({"unit_id": u["unit_id"], "type": u["type"], "path": u["path"]})
    return result


def prepare_unit(unit_id):
    """Clone+load ONE named catalog unit (the router already chose it, so no
    ranking here). T4 is still refused — the no-T4 rule holds whoever asks.
    Returns the same shape as prepare()."""
    import contextlib
    import io
    units = load_units()
    u = units.get(unit_id)
    if not u:
        raise RuntimeError(f"unknown unit_id: {unit_id}")
    if _registry_tiers().get(u["registry_id"]) not in AUTO_TIERS:
        raise RuntimeError(f"{unit_id} is T4 (reference only) — not auto-loadable")
    result = {"selected": [unit_id], "cloned": [], "loaded": [], "available": []}
    if ensure_repo(u):
        result["cloned"].append(unit_id)
    if u["type"] == "skill":
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_load([unit_id])
        result["loaded"].append(unit_id)
    else:
        result["available"].append({"unit_id": unit_id, "type": u["type"], "path": u["path"]})
    return result


def cmd_prepare(args):
    if not args:
        sys.exit("usage: tools/capability.py prepare <brief words...>")
    print(json.dumps(prepare(" ".join(args)), indent=2))


COMMANDS = {"list": cmd_list, "search": cmd_search, "show": cmd_show,
            "load": cmd_load, "unload": cmd_unload, "prepare": cmd_prepare}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: tools/capability.py <{'|'.join(COMMANDS)}> [args]")
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
