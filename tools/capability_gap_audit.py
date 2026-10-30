#!/usr/bin/env python3
"""Find onboarded-but-unwired capabilities before they cost a week of real
work, not after.

The gap this closes (`KNOWN_GAPS.md`, 2026-10-29): `morluto-rea` sat in
`config/capability-registry.yaml` as Riyan's explicit priority pick, fully
indexed, for two weeks before anyone noticed `config/capability-map.yaml`
never wired it — company-pm had no way to route a goal to it. That was found
by hand: list every registry id, diff it against every map `ref`, then read
each unwired entry's `purpose:` text to judge whether it was long-tail by
design or a real miss. This script is that same procedure, deterministic,
so it doesn't have to be redone by hand (and several Bash/awk calls) the next
time someone asks "what's unwired."

It does NOT judge every unwired entry a gap — `capability-map.yaml`'s own
header says most of the registry is correctly left unrouted, browsable via
`company capability search`. It flags a narrower, higher-signal set:
unwired entries whose own `purpose:` text names an existing agent file or
an existing playbook kind as the intended consumer (the exact shape of the
video-editor and morluto-rea misses) — "this was built for something that
already exists, and still can't be reached."

Usage:
    tools/capability_gap_audit.py              # human-readable report
    tools/capability_gap_audit.py --json        # same data, machine-readable
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "capability-registry.yaml"
MAP = REPO_ROOT / "config" / "capability-map.yaml"
PLAYBOOKS = REPO_ROOT / "config" / "playbooks.yaml"
AGENTS_DIR = REPO_ROOT / "agents"


def _load_registry() -> dict:
    return {e["id"]: e for e in yaml.safe_load(REGISTRY.read_text())["entries"]}


def _load_map() -> list:
    return yaml.safe_load(MAP.read_text())["entries"]


def _load_playbook_kinds() -> list:
    return [pb["kind"] for pb in yaml.safe_load(PLAYBOOKS.read_text())["playbooks"]]


def _names_agent(agent: str, purpose_lower: str) -> bool:
    """Does `purpose_lower` name this agent, written with a space or a hyphen
    ("video-editor" or "video editor")? Escape each hyphen-split piece BEFORE
    joining with the [ -] class — escaping the joined string instead (the
    original bug here) turns the class's own brackets into literal \\[ \\],
    so it never matches either spelling."""
    parts = [re.escape(p) for p in agent.split("-")]
    return re.search(r"\b" + r"[ -]".join(parts) + r"\b", purpose_lower) is not None


def _wired_ids(cmap: list) -> set:
    """A map entry's `ref` names the registry/agent/skill id it resolves to.
    `catalog_unit` refs are `registry_id:unit_name`, so take the registry_id
    half; everything else (agent/native_skill/repo/tool/external_tool) is
    already a bare id."""
    out = set()
    for e in cmap:
        ref = e["ref"]
        out.add(ref.split(":")[0] if e["kind"] == "catalog_unit" else ref)
    return out


def audit() -> dict:
    registry = _load_registry()
    wired = _wired_ids(_load_map())
    agent_names = {p.stem for p in AGENTS_DIR.glob("*.md")} if AGENTS_DIR.exists() else set()
    kind_words = set(_load_playbook_kinds())

    unwired = sorted(rid for rid in registry if rid not in wired)

    # A single common dictionary word ("research") as a playbook kind name
    # fires on "a research framework", "research-heavy", etc. — noise, not
    # evidence. Only match kind words specific enough that hitting them in
    # prose is itself meaningful (a compound phrase, or a rare word).
    _TOO_GENERIC_KIND_WORDS = {"research"}

    # A "likely gap" is an unwired entry whose own purpose text names a real
    # consumer that already exists — an agent file, or a playbook kind word
    # (e.g. "reverse engineer", "trading app", "vapt") — strong enough
    # evidence that this was built FOR something reachable, not just
    # interesting. This only catches the "named an existing consumer"
    # shape of gap (video-editor, morluto-rea); it does NOT catch a gap
    # where no tag exists for the job at all (e.g. leonxlnx-earshot's
    # missing audio_quality_check, found by reading purposes by hand in
    # KNOWN_GAPS.md) — that shape still needs a human read, this is a net
    # for the cheaper, recurring half of the problem, not a replacement
    # for the full manual audit.
    likely = []
    for rid in unwired:
        purpose = (registry[rid].get("purpose") or "").lower()
        hits = sorted(a for a in agent_names if _names_agent(a, purpose))
        kind_hits = sorted(k for k in kind_words if k not in _TOO_GENERIC_KIND_WORDS
                           and k.replace("_", " ") in purpose)
        if hits or kind_hits:
            likely.append({"id": rid, "names_agent": hits, "names_kind": kind_hits,
                           "trust_tier": registry[rid].get("trust_tier")})

    return {"total_registered": len(registry), "total_wired": len(wired),
            "total_unwired": len(unwired), "unwired": unwired, "likely_gaps": likely}


def _print_human(report: dict) -> None:
    print(f"{report['total_registered']} registered, {report['total_wired']} wired, "
          f"{report['total_unwired']} unwired.\n")
    if report["likely_gaps"]:
        print("LIKELY GAPS (purpose text names an existing agent/playbook kind, "
              "still unreachable):")
        for g in report["likely_gaps"]:
            named = ", ".join(g["names_agent"] + [f"kind:{k}" for k in g["names_kind"]])
            print(f"  ! {g['id']}  (trust={g['trust_tier']})  names: {named}")
        print()
    else:
        print("No likely gaps found by this heuristic — re-read KNOWN_GAPS.md's "
              "method if something still feels missing; this check is a net, not "
              "a guarantee.\n")
    print(f"({len(report['unwired']) - len(report['likely_gaps'])} other unwired "
          f"entries are long-tail by design — see them with "
          f"`company capability search`.)")


def main(argv=None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    report = audit()
    if "--json" in argv:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)


if __name__ == "__main__":
    main()
