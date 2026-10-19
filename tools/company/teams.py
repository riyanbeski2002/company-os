"""Team bundles (`company team show <name>`, teams/README.md) — a starter
pack of roles/skills/seed-tasks for a kind of project, read-only and
advisory. Never creates a task, loads a skill, or writes to the event log;
see teams/README.md for why that's deliberate.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
TEAMS_DIR = PLUGIN_ROOT / "teams"
AGENTS_DIR = PLUGIN_ROOT / "agents"
REGISTRY = PLUGIN_ROOT / "config" / "capability-registry.yaml"


class TeamError(ValueError):
    pass


def load_team(name: str, teams_dir: Path = TEAMS_DIR) -> dict:
    path = teams_dir / f"{name}.yaml"
    if not path.is_file():
        raise TeamError(f"no teams/{name}.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "name" not in data:
        raise TeamError(f"teams/{name}.yaml has no `name` field")
    return data


def _registry_ids(registry_path: Path) -> set[str]:
    if not registry_path.is_file():
        return set()
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return {e["id"] for e in data.get("entries", []) if e.get("id")}


def validate(team: dict, agents_dir: Path = AGENTS_DIR,
             registry_path: Path = REGISTRY) -> dict:
    """What's real vs. stale in a bundle — roles that no longer have an
    agents/*.md, suggested skills that no longer have a registry entry.
    Pure given the two directories/files it's handed, so it's testable
    without touching the real checkout."""
    known_roles = {p.stem for p in agents_dir.glob("*.md")} if agents_dir.is_dir() else set()
    known_skills = _registry_ids(registry_path)

    missing_roles = [r for r in team.get("roles", []) if r not in known_roles]
    missing_skills = [s["id"] for s in team.get("suggested_skills", [])
                       if s.get("id") and s["id"] not in known_skills]
    return {"missing_roles": missing_roles, "missing_skills": missing_skills}


def render(team: dict, problems: dict) -> str:
    lines = [f"# {team.get('name', '?')}", team.get("description", ""), ""]

    lines.append("## Roles")
    for r in team.get("roles", []):
        flag = "  [!! no agents/*.md found]" if r in problems["missing_roles"] else ""
        lines.append(f"  - {r}{flag}")

    lines.append("")
    lines.append("## Suggested skills (already-approved, check `company capability show <id>`)")
    for s in team.get("suggested_skills", []):
        flag = "  [!! no registry entry found]" if s.get("id") in problems["missing_skills"] else ""
        lines.append(f"  - {s.get('id')}{flag}: {s.get('why', '')}")

    lines.append("")
    lines.append("## Seed tasks (staffing judgment is still yours — these are a starting list, not an auto-plan)")
    for t in team.get("seed_tasks", []):
        lines.append(f"  - {t.get('title', '(untitled)')}")
        if t.get("notes"):
            lines.append(f"      {t['notes']}")

    if problems["missing_roles"] or problems["missing_skills"]:
        lines.append("")
        lines.append("## Stale references in this bundle")
        for r in problems["missing_roles"]:
            lines.append(f"  - role {r!r}: no agents/{r}.md in this checkout")
        for s in problems["missing_skills"]:
            lines.append(f"  - skill {s!r}: no entry in config/capability-registry.yaml")

    return "\n".join(lines)
