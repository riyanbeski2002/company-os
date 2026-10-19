"""Pluggable agent-runtime backends (BYO-model).

Every Tier-1/Tier-2 worker used to be a hardcoded `claude -p ...` subprocess
(worker.py, pre-harness). That made every role, every gate, and this system's
whole evidence trail depend on one vendor's CLI existing and behaving one
specific way — the thing paperclip (github.com/paperclipai/paperclip) gets
right with its "any model, any agent, one org chart" adapter model. This
module is the seam that makes company-os the same kind of BYO system: a
harness is a declarative command template plus a small amount of env policy,
resolved per role from config/harness.yaml. The default ships exactly the
old hardcoded Claude Code behavior, byte-for-byte — swapping or adding a
backend means writing a new config entry and pointing roles at it, never
touching worker.py again.

Contract an alternate harness must meet (see doc/BYO-MODEL.md for the worked
example):
  1. Accept the packet on stdin and exit 0 on a clean run.
  2. Print a JSON object somewhere in stdout shaped like worker.py's
     RESULT_SCHEMA, with `usage.*` and `total_cost_usd` keys present (zero or
     estimated values are fine) — worker.py's event-logging code reads that
     shape unconditionally and is not itself harness-aware.
  3. If the backend has no equivalent of `claude --agent <role>` (no native
     way to load agents/<role>.md as the running persona), set
     `native_agent_loading: false` in its harness.yaml entry — worker.py then
     prepends that file's body to the packet itself before launch.
A CLI that can't natively satisfy (1)/(2) gets wrapped in a thin adapter
script; the `command` template points at that script instead of the raw CLI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import staffing  # reuses the repo-config-wins-over-plugin-default loader

_PLACEHOLDER_RE = re.compile(r"^\{(\w+)\}$")


class HarnessError(RuntimeError):
    pass


def load_config(company_root: Path) -> dict:
    return staffing.load_config(company_root, "harness.yaml")


def resolve(config: dict, role: str | None) -> dict:
    """The harness spec a role should launch with: its own override, else
    the configured default. Raises rather than silently falling back to an
    undefined harness — a typo in `roles:` should fail loudly, not launch
    whatever happens to be first in the dict."""
    name = (config.get("roles") or {}).get(role) or config.get("default")
    if not name:
        raise HarnessError("harness.yaml has no `default` harness configured")
    spec = (config.get("harnesses") or {}).get(name)
    if spec is None:
        raise HarnessError(f"harness {name!r} (role {role!r}) not defined under `harnesses:`")
    return {**spec, "_name": name}


def build_command(spec: dict, *, role: str, plugin_root: Path, allowed_tools: str,
                   schema: dict | None = None, model: str | None = None,
                   effort: str | None = None, skip_permissions: bool = False) -> list[str]:
    """Fill the harness's command template.

    A template token that is exactly a `{placeholder}` and resolves to None
    (e.g. `{schema_json}` when no schema was requested) is dropped along with
    the literal flag token immediately before it — this is what lets one
    `claude` entry serve both the schema-bearing Tier-2 launch and the
    schema-less readonly advisor launch without two near-duplicate templates.
    """
    subs = {
        "role": role,
        "plugin_root": str(plugin_root),
        "allowed_tools": allowed_tools,
        "schema_json": json.dumps(schema) if schema is not None else None,
    }
    cmd: list[str] = []
    for tok in spec.get("command") or []:
        m = _PLACEHOLDER_RE.match(tok)
        if not m:
            cmd.append(tok)
            continue
        key = m.group(1)
        if key not in subs:
            raise HarnessError(f"unknown placeholder {{{key}}} in harness {spec.get('_name')!r}")
        val = subs[key]
        if val is None:
            if cmd:
                cmd.pop()  # drop the flag that introduced this now-absent value
            continue
        cmd.append(val)

    if model and spec.get("model_flag"):
        cmd += [spec["model_flag"], translate_model(spec, model)]
    if effort and spec.get("effort_flag"):
        cmd += [spec["effort_flag"], translate_effort(spec, effort)]
    if skip_permissions and spec.get("skip_permissions_flag"):
        cmd.append(spec["skip_permissions_flag"])
    return cmd


def translate_model(spec: dict, model: str) -> str:
    """staffing.yaml names tiers by Claude model family (sonnet/opus/haiku).
    A non-Claude harness maps those abstract names onto its own model ids via
    `model_map`; an unmapped name passes through unchanged so the default
    `claude` harness needs no map at all."""
    return (spec.get("model_map") or {}).get(model, model)


def translate_effort(spec: dict, effort: str) -> str:
    return (spec.get("effort_map") or {}).get(effort, effort)


def apply_env(spec: dict, env: dict) -> dict:
    env = dict(env)
    for var in spec.get("strip_env") or []:
        env.pop(var, None)
    for k, v in (spec.get("extra_env") or {}).items():
        env[k] = v
    return env


def load_persona(plugin_root: Path, role: str) -> str:
    """agents/<role>.md's body, frontmatter stripped — what a harness without
    native `--agent` loading needs folded into the packet instead."""
    path = Path(plugin_root) / "agents" / f"{role}.md"
    if not path.exists():
        raise HarnessError(f"no agents/{role}.md to use as its persona")
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.strip()
