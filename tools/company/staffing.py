"""Staffing engine (D4): the risk table runs first, and it cannot be argued with.

Gate selection is a pure table lookup over the request text and the paths a
task touches. The PM may only ever ADD gates beyond what this produces, and
only with a recorded reason — never subtract one. That is what makes identical
requests produce identical mandatory staffing, and what means nobody has to
remember to ask for a security review.
"""

from __future__ import annotations

import re
from pathlib import Path

import pathrules

PLUGIN_CONFIG = Path(__file__).resolve().parents[2] / "config"


def load_config(company_root: Path, name: str) -> dict:
    """Repo config wins; the plugin default is the fallback."""
    import yaml
    for candidate in (Path(company_root) / "config" / name, PLUGIN_CONFIG / name):
        if candidate.exists():
            return yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    raise FileNotFoundError(f"no config {name!r} in repo or plugin defaults")


def _keyword_hit(text: str, keywords) -> str | None:
    lowered = text.lower()
    for kw in keywords or ():
        if re.search(rf"(?<![a-z0-9]){re.escape(kw.lower())}(?![a-z0-9])", lowered):
            return kw
    return None


def _path_hit(paths, patterns) -> str | None:
    for path in paths or ():
        # A task declares owned globs, not concrete files. Compare glob-to-glob
        # by testing the pattern against the glob with its wildcards stripped.
        probe = path.replace("**", "x").replace("*", "x")
        for pattern in patterns or ():
            if pathrules.matches(probe, pattern) or pathrules.matches(probe.rstrip("/x"), pattern):
                return path
    return None


def evaluate(config: dict, request: str = "", paths=None) -> dict:
    """Return the mandatory gates and which triggers produced them.

    Deterministic: same inputs, same output, every time.
    """
    fired = []
    gates: list[str] = []

    for trigger in config.get("triggers", []):
        kw = _keyword_hit(request, trigger.get("keywords"))
        ph = _path_hit(paths, trigger.get("paths"))
        if not (kw or ph):
            continue
        fired.append({
            "trigger": trigger["name"],
            "matched_keyword": kw,
            "matched_path": ph,
            "gates": trigger.get("gates", []),
        })
        for gate in trigger.get("gates", []):
            if gate not in gates:
                gates.append(gate)

    for gate in config.get("baseline_gates", []):
        if gate not in gates:
            gates.append(gate)

    return {"gates": gates, "triggers_fired": fired}


def order_gates(gates, quality_gates: dict) -> list[str]:
    order = quality_gates.get("order", [])
    return sorted(gates, key=lambda g: order.index(g) if g in order else len(order))


def reconcile(proposed_gates, mandatory_gates, reason: str | None = None) -> tuple[list[str], list[str]]:
    """Merge the PM's proposal with the table's mandate.

    Returns (final_gates, additions). Anything the table mandates is present in
    the result whether the PM asked for it or not. Anything the PM added beyond
    the table is kept only if a reason was recorded.
    """
    final = list(mandatory_gates)
    additions = []
    for gate in proposed_gates or ():
        if gate not in final:
            if not reason:
                continue  # an addition without a recorded reason is dropped
            final.append(gate)
            additions.append(gate)
    return final, additions


# --- overlap prediction -----------------------------------------------------

def predict_overlap(tasks: list[dict]) -> list[dict]:
    """Find pairs of tasks whose owned globs intersect.

    Computed before launching parallel work. Overlap means sequence the tasks or
    split ownership explicitly — never launch and hope.
    """
    collisions = []
    for i, a in enumerate(tasks):
        for b in tasks[i + 1:]:
            shared = _glob_intersections(a.get("owned_globs"), b.get("owned_globs"))
            if shared:
                collisions.append({
                    "tasks": [a["id"], b["id"]],
                    "overlapping_globs": shared,
                })
    return collisions


def _glob_intersections(a_globs, b_globs) -> list[str]:
    shared = []
    for a in a_globs or ():
        for b in b_globs or ():
            if a == b:
                shared.append(a)
                continue
            a_probe = a.replace("**", "x").replace("*", "x").rstrip("/x")
            b_probe = b.replace("**", "x").replace("*", "x").rstrip("/x")
            if pathrules.matches(a_probe, b) or pathrules.matches(b_probe, a):
                shared.append(f"{a} ∩ {b}")
    return sorted(set(shared))


# --- team sizing ------------------------------------------------------------

# (min_tier2_workers, name, concurrency cap, typical shape)
SIZE_BANDS = [
    (0, "trivial", 0, "PM inline — Tier 0"),
    (1, "small", 1, "one specialist, Tier-1 review"),
    (2, "medium", 4, "pod plus Tier-1 QA and review"),
    (5, "large", 7, "pod with contracts published first"),
    (8, "program", 7, "multiple pods, staged; leads only if they reduce coordination"),
]


def size_band(tier2_count: int) -> dict:
    name, cap, shape = SIZE_BANDS[0][1:]
    for threshold, band_name, band_cap, band_shape in SIZE_BANDS:
        if tier2_count >= threshold:
            name, cap, shape = band_name, band_cap, band_shape
    return {"size": name, "shape": shape, "tier2_cap": cap}
