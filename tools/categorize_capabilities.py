#!/usr/bin/env python3
"""One-time (then ongoing) pass that adds a `category:` field to every
`type: skill` entry in `config/capability-registry.yaml`, so skills can be
browsed by major/sub category (`config/capability-index.yaml`'s `by_category`
tree, built by `build_capability_index.py`) instead of only being
discoverable by cloning into `external/` and reading each repo separately.

Text-insertion only, same discipline as `tools/pin_external_commits.py`:
`config/capability-registry.yaml` is full of hand-written prose comments a
yaml.safe_load + yaml.dump round-trip would silently discard, so this finds
each entry's exact `type: skill` line by id and inserts a `category:` line
right after it, never touching anything else in the file.

Usage:
    tools/categorize_capabilities.py [--check]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "capability-registry.yaml"

# major.sub — hand-curated from each entry's own `purpose:` line, not
# inferred by keyword matching (a few ids share surface words but belong in
# different categories, e.g. "token-" ids are cost/finance here, not
# design, despite living next to design-token tooling elsewhere).
CATEGORIES: dict[str, str] = {
    # design.motion — animation/motion-graphics/video-render pipelines
    "motion-vocabulary": "design.motion",
    "scroll-animation": "design.motion",
    "greensock-gsap-skills": "design.motion",
    "juliangarnier-anime": "design.motion",
    "motiondivision-motion": "design.motion",
    "heygen-com-hyperframes": "design.motion",
    "remotion-dev-skills": "design.motion",
    "latent-spaces-brag": "design.motion",
    "sunwood-ai-labs-hyperframes-motion-reel-skill": "design.motion",
    "abubakrchan-product-launch-motion": "design.motion",
    "higgsfield-motion": "design.motion",
    "higgsfield-motion-saas": "design.motion",

    # design.taste-and-quality — anti-slop/anti-pattern/accessibility/taste
    "emilkowalski-skills": "design.taste-and-quality",
    "pbakaus-impeccable": "design.taste-and-quality",
    "leonxlnx-taste-skill": "design.taste-and-quality",
    "laith0003-ux-skill": "design.taste-and-quality",
    "community-access-accessibility-agents": "design.taste-and-quality",
    "content-designer-ux-writing-skill": "design.taste-and-quality",

    # design.components — component/registry libraries
    "nextlevelbuilder-ui-ux-pro-max-skill": "design.components",
    "davidhdev-react-bits": "design.components",
    "shadcn-ui-ui": "design.components",
    "assistant-ui-assistant-ui": "design.components",
    "tailark-blocks": "design.components",
    "watermeloncorp-watermellon-registry": "design.components",
    "serafimcloud-21st": "design.components",
    "bklit-bklit-ui": "design.components",
    "themesberg-neumorphism-ui-free": "design.components",
    "uiverse-io-galaxy": "design.components",

    # design.3d-and-visual-tech — 3D/WebGL/graphics engines
    "freshtechbro-claudedesignskills": "design.3d-and-visual-tech",

    # design.image — image/illustration generation
    "hassancs91-claude-image-generation": "design.image",

    # design.ux — flow/onboarding/diagramming
    "nilbuild-driverjs": "design.ux",
    "coleam00-excalidraw-diagram-skill": "design.ux",

    # engineering.fundamentals — generic coding discipline/reference
    "dietrichgebert-ponytail": "engineering.fundamentals",
    "multica-ai-andrej-karpathy-skills": "engineering.fundamentals",
    "leonardomso-33-js-concepts": "engineering.fundamentals",
    "khazp-vibe-coding-prompt-template": "engineering.fundamentals",
    "coleam00-context-engineering-intro": "engineering.fundamentals",

    # engineering.cloud-platform — official vendor agent-skill libraries
    "google-skills": "engineering.cloud-platform",
    "google-labs-code-stitch-skills": "engineering.cloud-platform",

    # engineering.codebase-tools — repo-analysis/generation tooling
    "graphify-labs-graphify": "engineering.codebase-tools",
    "jcodesmore-ai-website-cloner-template": "engineering.codebase-tools",

    # architecture.reference — system-design reference material
    "bytebytegohq-system-design-101": "architecture.reference",

    # security.training — educational reference, not an owned methodology
    "theartofhacking-h4cker": "security.training",

    # finance.cost-optimization — token/cost reduction technique
    "juliusbrussee-caveman": "finance.cost-optimization",

    # growth.content — copy/SEO/CRO, AI-tell removal
    "coreyhaines31-marketingskills": "growth.content",
    "blader-humanizer": "growth.content",
    "mvanhorn-last30days-skill": "growth.content",

    # governance.agent-harness — meta-skills about the harness/skill system itself
    "anthropics-skills": "governance.agent-harness",
    "obra-superpowers": "governance.agent-harness",

    # media.video-production — video-specific authoring beyond motion render
    "hypit-ai-hypit": "media.video-production",
}

# First-party skills (no `local_path`, living directly under skills/) that
# also need a category — same dict, kept separate only because they're
# matched by a different id convention (skill dir name, not registry id
# that happens to equal a repo slug).
FIRST_PARTY_CATEGORIES: dict[str, str] = {
    "capability-curator": "governance.agent-harness",
    "capture-and-tailor": "design.ux",
    # claude-image-generation and claudedesignskills are bundles (no SKILL.md
    # of their own, only per-sub-skill ones) -- already categorized via their
    # registry entries (hassancs91-claude-image-generation, freshtechbro-
    # claudedesignskills) instead.
    "component-customization": "design.components",
    "motion-graphics-video": "design.motion",
    "pen_test": "security.offensive",
    "ux-flow": "design.ux",
    "voice-commanded-editing": "media.video-production",
}


def insert_categories(text: str, categories: dict[str, str]) -> tuple[str, list[str]]:
    """Insert a `category:` line right after each matched entry's `type:`
    line. Returns (new_text, ids_not_found) — ids_not_found is how a stale
    mapping (an id renamed/removed since this script was written) surfaces
    instead of silently doing nothing."""
    not_found = []
    for skill_id, category in categories.items():
        pattern = re.compile(
            r'(  - id: ' + re.escape(skill_id) + r'\n    type: \w+\n)'
        )
        if not pattern.search(text):
            not_found.append(skill_id)
            continue
        if re.search(r'  - id: ' + re.escape(skill_id) + r'\n(?:.*\n)*?    category: ', text):
            continue  # already categorized, idempotent re-run
        text = pattern.sub(lambda m: m.group(1) + f'    category: "{category}"\n', text, count=1)
    return text, not_found


def categorize_first_party_skill_md(skills_dir: Path, categories: dict[str, str]) -> tuple[int, list[str]]:
    """First-party skills (no registry entry to patch) get `category:`
    inserted into their own SKILL.md frontmatter instead — same
    insert-only discipline, applied to the frontmatter block rather than
    the registry text."""
    changed = 0
    missing = []
    for skill_id, category in categories.items():
        skill_md = skills_dir / skill_id / "SKILL.md"
        if not skill_md.is_file():
            missing.append(skill_id)
            continue
        text = skill_md.read_text()
        if re.search(r'^category: ', text, re.MULTILINE):
            continue  # already categorized, idempotent re-run
        new_text = re.sub(
            r'^(description: .*\n)',
            lambda m: m.group(1) + f'category: "{category}"\n',
            text, count=1, flags=re.MULTILINE,
        )
        if new_text != text:
            skill_md.write_text(new_text)
            changed += 1
    return changed, missing


def main() -> int:
    check_only = "--check" in sys.argv
    text = REGISTRY.read_text()
    original = text
    text, missing_registry = insert_categories(text, CATEGORIES)

    if missing_registry:
        print(f"WARNING: {len(missing_registry)} id(s) in CATEGORIES not found "
              f"in the registry (renamed/removed?): {', '.join(missing_registry)}")

    if check_only:
        would_change = text != original
        skills_dir = REPO_ROOT / "skills"
        for skill_id, category in FIRST_PARTY_CATEGORIES.items():
            skill_md = skills_dir / skill_id / "SKILL.md"
            if skill_md.is_file() and not re.search(r'^category: ', skill_md.read_text(), re.MULTILINE):
                would_change = True
        if would_change:
            print("would add category fields -- not fully categorized")
            return 1
        print("fully categorized")
        return 0

    if text != original:
        REGISTRY.write_text(text)
        print(f"categorized {REGISTRY}")
    else:
        print("registry: nothing to do -- already categorized")

    changed, missing_first_party = categorize_first_party_skill_md(
        REPO_ROOT / "skills", FIRST_PARTY_CATEGORIES)
    print(f"categorized {changed} first-party SKILL.md frontmatter block(s)")
    if missing_first_party:
        print(f"WARNING: {len(missing_first_party)} first-party id(s) not found "
              f"under skills/: {', '.join(missing_first_party)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
