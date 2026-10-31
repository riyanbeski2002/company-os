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
  2. Declare its stdout format as `output:` (default `claude-json`). An
     adapter in adapters/ turns that into the normalized result worker.py
     reads; worker.py itself is not harness-aware. A format with no adapter
     yet means writing one (adapters/__init__.py) — not wrapping the CLI to
     impersonate Claude's JSON, which is what the old contract required.
  3. If the backend has no equivalent of `claude --agent <role>` (no native
     way to load agents/<role>.md as the running persona), set
     `native_agent_loading: false` in its harness.yaml entry — worker.py then
     prepends that file's body to the packet itself before launch.
A CLI that can't natively satisfy (1) gets wrapped in a thin adapter script;
the `command` template points at that script instead of the raw CLI.
`trailing_args` are appended after every flag build_command adds (codex's
`-`, which reads the prompt from stdin).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import adapters
import staffing  # reuses the repo-config-wins-over-plugin-default loader

_PLACEHOLDER_RE = re.compile(r"^\{(\w+)\}$")
_EMBEDDED_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


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
    if not spec.get("command"):
        # Catalogued (M3): the CLI's verified capabilities are recorded so
        # `company harnesses` can report on it, but no invocation has been
        # observed working yet — so there is nothing honest to launch.
        raise HarnessError(
            f"harness {name!r} is catalogued only: its capabilities are recorded, but "
            f"no invocation (command + output adapter) has been verified against a "
            f"live run yet. See `company harnesses`.")
    # Checked here, before launch, not when the output is read: an unknown
    # format discovered after the run has already spent the run's tokens.
    fmt = adapters.output_format(spec)
    if fmt not in adapters.PARSERS:
        raise HarnessError(f"harness {name!r} declares output {fmt!r}; known formats: "
                           f"{', '.join(sorted(adapters.PARSERS))}")
    if spec.get("guards") is not None and spec["guards"] not in GUARD_MODES:
        raise HarnessError(f"harness {name!r} declares guards {spec['guards']!r}; known "
                           f"modes: {', '.join(sorted(GUARD_MODES))}")
    return {**spec, "_name": name}


# How company-os's guards (hooks/policy.py: ownership, secret reads, shell
# rules) reach a harness's workers (migration §4.6, H3):
#   claude-plugin  hooks/hooks.json, loaded by Claude Code via --plugin-dir
#   shim           company-os installs hooks/guard.py into the harness's own
#                  blocking pre-tool hook for each launch
#   external       the operator asserts this harness enforces equivalent
#                  policy by its own means — explicit, reviewable in config,
#                  and recorded in every WORKER_STARTED
GUARD_MODES = {"claude-plugin", "shim", "external"}


def guard_mode(spec: dict) -> str | None:
    """The harness's guard mode, or None if it has none — and a harness with
    none gets no workers (require_guards). A spec with no `guards:` field
    that passes `--plugin-dir {plugin_root}` is claude-plugin: that flag IS
    the mechanism that loads hooks/hooks.json, and every harness.yaml written
    before this field existed carries it."""
    if spec.get("guards"):
        return spec["guards"]
    cmd = spec.get("command") or []
    for i, tok in enumerate(cmd[:-1]):
        if tok == "--plugin-dir" and cmd[i + 1] == "{plugin_root}":
            return "claude-plugin"
    return None


def require_guards(spec: dict) -> str:
    mode = guard_mode(spec)
    if mode is None:
        raise HarnessError(
            f"harness {spec.get('_name')!r} has no guards: nothing would stop its "
            f"worker writing outside its owned files, reading secrets, or "
            f"force-pushing. Declare how hooks/policy.py reaches it — `guards: shim` "
            f"(company-os installs its hook) or `guards: external` (you vouch for "
            f"equivalent enforcement) — in its harness.yaml entry. See "
            f"docs/HARNESS-AGNOSTIC-MIGRATION.md §4.6.")
    if mode == "shim" and not spec.get("guards_verified"):
        # Codex skips an untrusted hook silently, and a skipped hook is
        # indistinguishable from one that allowed everything. A shim counts
        # only once a live run has shown it firing — recorded by a human as
        # `guards_verified: "<date> <cli version>"`, never assumed.
        raise HarnessError(
            f"harness {spec.get('_name')!r} has the guard shim wired in but not yet "
            f"verified live: until a real run shows hooks/guard.py actually firing "
            f"(and denying) under this CLI version, it can't be told apart from a "
            f"hook the CLI silently skipped. Run the smoke test in "
            f"docs/HARNESS-AGNOSTIC-MIGRATION.md §4.6, then set `guards_verified`.")
    return mode


def check_workdir(spec: dict, project_root: Path) -> None:
    """Refuse a launch whose project ships config the harness would run
    unreviewed. codex needs --dangerously-bypass-hook-trust for its guard
    hook to run headless, and that flag waives review for every hook in the
    run, the project's own `.codex/` ones included — so a repo that ships
    one could run arbitrary commands the moment a worker starts. Declared
    per harness as `refuse_project_paths` (relative to the project root,
    which is the worktree, or the repo for an advisor)."""
    found = [p for p in spec.get("refuse_project_paths") or []
             if (Path(project_root) / p).exists()]
    if found:
        raise HarnessError(
            f"harness {spec.get('_name')!r} refuses to launch in {project_root}: it contains "
            f"{found}, project config this harness would run without review. Remove it "
            f"or review it, then launch; or staff a different harness.")


def find_binary(spec: dict) -> str | None:
    """The CLI's executable: on PATH first, then each declared install path
    (`binary_paths`, ~ expanded) — agy installs to ~/.gemini/bin, which is
    not on PATH by default, and its PATH-facing symlink can dangle."""
    import os
    import shutil
    name = spec.get("binary")
    if not name:
        return None
    found = shutil.which(name)
    if found:
        return found
    for candidate in spec.get("binary_paths") or []:
        path = os.path.expanduser(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def read_result(spec: dict, raw: str, exit_code: int | None) -> dict:
    """The run's normalized result (adapters/__init__.py has the fields)."""
    return adapters.parse(spec, raw, exit_code)


def build_command(spec: dict, *, role: str, plugin_root: Path, allowed_tools: str,
                   schema: dict | None = None, model: str | None = None,
                   effort: str | None = None, skip_permissions: bool = False,
                   settings: dict | None = None) -> list[str]:
    """Fill the harness's command template.

    A template token that is EXACTLY a `{placeholder}` (nothing else in the
    token) and resolves to None (e.g. `{schema_json}` when no schema was
    requested) is dropped along with the literal flag token immediately
    before it — this is what lets one `claude` entry serve both the
    schema-bearing Tier-2 launch and the schema-less readonly advisor launch
    without two near-duplicate templates.

    `settings` (worker.sandbox_settings()'s per-launch OS sandbox policy) is
    passed inline via the harness's `settings_flag`. A harness with no such
    flag must declare `self_sandboxed: true` (its command template applies
    its own containment, e.g. codex's `sandbox_mode`) — otherwise this
    raises rather than launching unsandboxed. Fail-closed on purpose: a repo
    whose .company/config/harness.yaml predates settings_flag would
    otherwise silently drop the sandbox.

    A placeholder embedded inside a larger token (e.g. `"{plugin_root}/
    tools/foo.py"`, needed the first time a harness pointed at an adapter
    script under the plugin root rather than passing `--plugin-dir
    {plugin_root}` as Claude's own template does) is substituted the same
    way but can't be "dropped" if unset — there's no flag pair to drop a
    fragment of a larger string from. A real bug, caught live
    (2026-10-19): the `codex` harness's first command template used
    `"{plugin_root}/tools/company/adapters/codex_adapter.py"` as one token
    assuming substring replacement, but this function originally only
    matched a token that was a placeholder and nothing else — the literal
    string `{plugin_root}` reached the shell unexpanded and the launch
    failed with a file-not-found. Fixed here, not by rewriting the template
    to avoid embedding — a harness author reaching for this is reasonable
    and the function should support it.
    """
    subs = {
        "role": role,
        "plugin_root": str(plugin_root),
        "allowed_tools": allowed_tools,
        "schema_json": json.dumps(schema) if schema is not None else None,
    }

    def _fill(match: re.Match, tok: str) -> str:
        key = match.group(1)
        if key not in subs:
            raise HarnessError(f"unknown placeholder {{{key}}} in harness {spec.get('_name')!r}")
        val = subs[key]
        if val is None:
            raise HarnessError(
                f"{{{key}}} has no value for this launch and can't be dropped "
                f"from inside a larger token ({tok!r}) the way a whole-token "
                f"placeholder can — give {{{key}}} its own command-list entry "
                f"instead if it needs to be optional")
        return val

    cmd: list[str] = []
    command = list(spec.get("command") or [])
    if command and spec.get("binary") and command[0] == spec["binary"]:
        # Only for a CLI that isn't on PATH (agy): one that is keeps its bare
        # name, so the launched argv stays byte-identical to what's pinned.
        import shutil
        if not shutil.which(command[0]):
            command[0] = find_binary(spec) or command[0]
    for tok in command:
        m = _PLACEHOLDER_RE.match(tok)
        if m:
            key = m.group(1)
            if key not in subs:
                raise HarnessError(f"unknown placeholder {{{key}}} in harness {spec.get('_name')!r}")
            val = subs[key]
            if val is None:
                if cmd:
                    cmd.pop()  # drop the flag that introduced this now-absent value
                continue
            cmd.append(val)
            continue
        cmd.append(_EMBEDDED_PLACEHOLDER_RE.sub(lambda m, t=tok: _fill(m, t), tok))

    if model and spec.get("model_flag"):
        cmd += [spec["model_flag"], translate_model(spec, model)]
    if effort and spec.get("effort_flag"):
        cmd += [spec["effort_flag"], translate_effort(spec, effort)]
    if skip_permissions and spec.get("skip_permissions_flag"):
        cmd.append(spec["skip_permissions_flag"])
    if settings is not None:
        if spec.get("settings_flag"):
            cmd += [spec["settings_flag"],
                    json.dumps({**(spec.get("settings_defaults") or {}), **settings})]
        elif not spec.get("self_sandboxed"):
            raise HarnessError(
                f"harness {spec.get('_name')!r} has no `settings_flag` to carry the "
                f"launch sandbox and does not declare `self_sandboxed: true` — "
                f"refusing to launch unsandboxed. Add `settings_flag: --settings` "
                f"to its entry in config/harness.yaml (and any .company/config "
                f"copy of it).")
    # Last of all, after every appended flag: e.g. codex's `-` (read the
    # prompt from stdin), which must follow the options it terminates.
    cmd += list(spec.get("trailing_args") or [])
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
