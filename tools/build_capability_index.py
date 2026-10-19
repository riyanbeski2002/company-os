#!/usr/bin/env python3
"""Scan every `external/<id>/` with a local clone and build a curated,
loadable catalog at `config/capability-index.yaml`.

Classifies each repo:
  - skill   : has one or more SKILL.md files (possibly nested) -> one
              loadable unit per SKILL.md, extracted from its frontmatter.
  - tool    : has a detectable CLI entrypoint (pyproject.toml [project.scripts],
              package.json "bin", a top-level install.sh, or a Go main.go)
              -> one loadable unit, the repo itself.
  - reference: neither of the above -> read-only, no load step (local_path
              already makes it readable; nothing to "activate").

A single repo can produce multiple units (e.g. claudedesignskills' 22
SKILL.md files) or units of mixed type.

Each unit also gets `source_commit` (the clone's current HEAD) and
`content_shape` (donor review, 2026-10-19 — paperclip's skills-store derives
a bundle's trust-relevant shape from what it actually contains, not from a
self-declared tier; this is company-os's version of that check). Neither is
a hand-curated judgment like `pairs_with` — both are computed fresh every
run, so `source_commit` changing between two runs is drift since the last
registry review was done, and a `trust_tier` of T3/T4 ("manual use only"/
"unknown, reference only" — config/capability-registry.yaml) that turns out
to have `content_shape: scripts_executables` is a mismatch worth a human
glance, printed as a warning at the end of a build rather than silently
indexed.

Run after external/ is populated:
    tools/sync_external_capabilities.py && tools/build_capability_index.py
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "capability-registry.yaml"
INDEX_OUT = REPO_ROOT / "config" / "capability-index.yaml"
EXTERNAL_DIR = REPO_ROOT / "external"

EXECUTABLE_SUFFIXES = {".sh", ".py", ".js", ".ts", ".rb", ".pl", ".go", ".ps1"}

# Tiers where "manual use only"/"reference only" already implies lower trust
# (config/capability-registry.yaml's comment) — the tiers where a hidden
# script would be the biggest surprise.
LOWER_TRUST_TIERS = {"T3", "T4"}


def detect_content_shape(unit_dir: Path) -> str:
    """'scripts_executables' if anything under this unit's own directory
    runs; 'markdown_only' otherwise. Computed from what's actually there, not
    taken on faith from the registry's declared trust_tier."""
    if not unit_dir.is_dir():
        return "unknown"
    for p in unit_dir.rglob("*"):
        if ".git" in p.parts or not p.is_file():
            continue
        if p.suffix in EXECUTABLE_SUFFIXES or os.access(p, os.X_OK):
            return "scripts_executables"
    return "markdown_only"


def source_commit(repo_dir: Path) -> str | None:
    """The clone's current HEAD SHA — cheap drift detection: if this differs
    from what a previous index build recorded for the same unit, the
    upstream fork moved since it was last reviewed. `sync_external_
    capabilities.py` tracks each fork's default branch, not a pinned commit
    (a real gap, not yet closed — see that script's own module docstring and
    tasks/lessons.md, 2026-10-19), so this is the index's own after-the-fact
    visibility into that movement, not a guarantee nothing moved unreviewed."""
    if not (repo_dir / ".git").exists():
        return None
    r = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                        capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


# Known complementary relationships, hand-curated from what's already
# documented in agents/*.md and config/capability-registry.yaml purpose
# lines — not auto-derived, since "these two genuinely work together" is a
# judgment call, not a structural fact graphify or any scanner can detect.
PAIRS = {
    # pen_test native probes <-> cloned engines (CATALOG.md)
    "sqlmapproject-sqlmap": ["pen_test-native"],
    # frontend motion/taste/anti-pattern stack
    "emilkowalski-skills": ["leonxlnx-taste-skill", "pbakaus-impeccable", "motion-vocabulary"],
    "leonxlnx-taste-skill": ["emilkowalski-skills", "pbakaus-impeccable"],
    "pbakaus-impeccable": ["emilkowalski-skills", "leonxlnx-taste-skill"],
    "greensock-gsap-skills": ["juliangarnier-anime", "motiondivision-motion"],
    "nextlevelbuilder-ui-ux-pro-max-skill": ["shadcn-ui-ui"],
    # claudedesignskills sub-skills <-> existing frontend taste/impl stack
    "freshtechbro-claudedesignskills:threejs-webgl": ["freshtechbro-claudedesignskills:react-three-fiber", "greensock-gsap-skills"],
    "freshtechbro-claudedesignskills:gsap-scrolltrigger": ["scroll-animation", "greensock-gsap-skills"],
    "freshtechbro-claudedesignskills:motion-framer": ["motiondivision-motion", "emilkowalski-skills"],
    "freshtechbro-claudedesignskills:react-three-fiber": ["freshtechbro-claudedesignskills:threejs-webgl"],
    "freshtechbro-claudedesignskills:modern-web-design": ["emilkowalski-skills", "leonxlnx-taste-skill"],
    # video pipeline
    "heygen-com-hyperframes": ["latent-spaces-brag", "remotion-dev-skills"],
    "remotion-dev-skills": ["heygen-com-hyperframes"],
    "latent-spaces-brag": ["heygen-com-hyperframes"],
    # LLM cost/routing
    "berriai-litellm": ["tashfeenahmed-freellmapi"],
    "tashfeenahmed-freellmapi": ["berriai-litellm"],
    # code-quality standards that reinforce each other
    "dietrichgebert-ponytail": ["multica-ai-andrej-karpathy-skills"],
    "multica-ai-andrej-karpathy-skills": ["dietrichgebert-ponytail"],
    # review-dimension tools
    "affaan-m-ecc": ["pbakaus-impeccable"],
    # codebase mapping
    "graphify-labs-graphify": [],
}


def load_registry():
    data = yaml.safe_load(REGISTRY.read_text())
    return {e["id"]: e for e in data.get("entries", []) if e.get("local_path")}


def find_skill_files(repo_dir):
    """Find real SKILL.md files, deduped by skill slug (a repo that ships the
    same skill content under multiple per-tool dot-dirs — .cursor/skills/,
    .kiro/skills/, docs/, etc., as affaan-m/ecc does — should produce one
    loadable unit per skill, not one per copy)."""
    candidates = [p for p in repo_dir.rglob("SKILL.md") if ".git" not in p.parts and p.is_file()]
    # Preference order when a repo ships the same skill under several roots
    # (freshtechbro/claudedesignskills has it under .claude/, .factory/,
    # plugins/bundles/..., plugins/individual/...; affaan-m/ecc under
    # .cursor/, .kiro/, .agents/, docs/, skills/, ...). `.claude/skills/` is
    # the live Claude-Code-loadable root and wins; plain `skills/` next;
    # anything else is a per-tool duplicate.
    PRIORITY = [".claude/skills/", "skills/"]

    def rank(p):
        rel = str(p.relative_to(repo_dir))
        for i, prefix in enumerate(PRIORITY):
            if prefix in rel:
                return i
        return len(PRIORITY)

    by_slug = {}
    for p in sorted(candidates, key=rank):
        slug = p.parent.name
        by_slug.setdefault(slug, p)
    skipped = len(candidates) - len(by_slug)
    if skipped:
        print(f"    (deduped {skipped} per-tool copies, {len(by_slug)} unique skills)")
    return list(by_slug.values())


def parse_frontmatter(skill_md_path):
    text = skill_md_path.read_text(errors="replace")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def detect_tool_entrypoint(repo_dir):
    pj = repo_dir / "package.json"
    if pj.exists():
        try:
            data = json.loads(pj.read_text())
            if data.get("bin"):
                return f"npm install (bin: {list(data['bin'].keys()) if isinstance(data['bin'], dict) else data.get('name')})"
        except (json.JSONDecodeError, OSError):
            pass
    pp = repo_dir / "pyproject.toml"
    if pp.exists():
        text = pp.read_text(errors="replace")
        m = re.search(r"\[project\.scripts\]\s*\n((?:.+\n?)*?)(?:\n\[|\Z)", text)
        if m:
            scripts = re.findall(r"^(\S+)\s*=", m.group(1), re.MULTILINE)
            if scripts:
                return f"pip install -e . (scripts: {', '.join(scripts)})"
    if (repo_dir / "install.sh").exists():
        return "./install.sh"
    for go_main in repo_dir.glob("*/main.go"):
        return f"go build ./{go_main.parent.name}"
    if (repo_dir / "main.go").exists():
        return "go build ."
    return None


def main():
    registry = load_registry()
    units = []

    for id_, entry in sorted(registry.items()):
        repo_dir = EXTERNAL_DIR / id_
        if not (repo_dir / ".git").is_dir():
            print(f"  {id_:45s} SKIP (not cloned yet)")
            continue

        commit = source_commit(repo_dir)
        tier = entry.get("trust_tier")

        skill_files = find_skill_files(repo_dir)
        if skill_files:
            for sm in skill_files:
                fm = parse_frontmatter(sm)
                rel = sm.relative_to(repo_dir)
                # Namespace sub-skills as parent:slug when nested (e.g.
                # claudedesignskills has 23), plain id when it IS the skill.
                sub = rel.parent.name if rel.parent != Path(".") else None
                unit_id = f"{id_}:{sub}" if sub and sub != id_ else id_
                units.append({
                    "unit_id": unit_id,
                    "registry_id": id_,
                    "type": "skill",
                    "path": f"external/{id_}/{rel.parent}".rstrip("/."),
                    "name": fm.get("name", sub or id_),
                    "description": fm.get("description", entry.get("purpose", "")[:200]),
                    "pairs_with": PAIRS.get(unit_id, PAIRS.get(id_, [])),
                    "source_commit": commit,
                    "content_shape": detect_content_shape(repo_dir / rel.parent),
                })
            print(f"  {id_:45s} skill   ({len(skill_files)} SKILL.md)")
            continue

        tool_cmd = detect_tool_entrypoint(repo_dir)
        if tool_cmd:
            units.append({
                "unit_id": id_,
                "registry_id": id_,
                "type": "tool",
                "path": f"external/{id_}",
                "name": id_,
                "description": entry.get("purpose", "")[:200],
                "load_cmd": tool_cmd,
                "pairs_with": PAIRS.get(id_, []),
                "source_commit": commit,
                "content_shape": detect_content_shape(repo_dir),
            })
            print(f"  {id_:45s} tool    ({tool_cmd})")
            continue

        units.append({
            "unit_id": id_,
            "registry_id": id_,
            "type": "reference",
            "path": f"external/{id_}",
            "name": id_,
            "description": entry.get("purpose", "")[:200],
            "pairs_with": PAIRS.get(id_, []),
            "source_commit": commit,
            "content_shape": detect_content_shape(repo_dir),
        })
        print(f"  {id_:45s} reference")

    INDEX_OUT.write_text(
        "# Auto-generated by tools/build_capability_index.py — do not hand-edit.\n"
        "# Re-run after tools/sync_external_capabilities.py to refresh.\n"
        "# `pairs_with` is hand-curated in the script itself, not auto-derived.\n"
        "# `source_commit`/`content_shape` are computed fresh every run — see\n"
        "# this script's module docstring for what a change in either means.\n\n"
        + yaml.dump({"units": units}, sort_keys=False, allow_unicode=True, width=100)
    )
    print(f"\n{len(units)} loadable units -> {INDEX_OUT}")

    mismatches = [u for u in units
                  if registry.get(u["registry_id"], {}).get("trust_tier") in LOWER_TRUST_TIERS
                  and u["content_shape"] == "scripts_executables"]
    if mismatches:
        print(f"\n{len(mismatches)} unit(s) at trust_tier T3/T4 (\"manual use only\"/"
              f"\"reference only\") actually carry executable content — worth a look:")
        for u in mismatches:
            print(f"  {u['unit_id']:45s} trust_tier={registry[u['registry_id']]['trust_tier']}  {u['path']}")


if __name__ == "__main__":
    main()
