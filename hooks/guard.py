#!/usr/bin/env python3
"""company-os's guards for a harness other than Claude Code (M2).

usage: guard.py <codex|agy>   — the harness's PreToolUse payload on stdin.

Translates the harness's own pre-tool hook payload into hooks/policy.py's
three checks (write / read / shell) and the result into that harness's own
deny shape. Contracts as read from each CLI's installed schema/docs on
2026-10-30 (tests/test_guard_shim.py's docstring has the sources):

  codex  stdin {tool_name, tool_input, cwd, ...}; deny = the same
         hookSpecificOutput/permissionDecision JSON Claude uses.
  agy    stdin {toolCall: {name, args}, workspacePaths, ...};
         deny = {"decision": "deny", "reason": ...}.

Unlike the Claude shims (written when only Claude existed, against a
payload known exactly), this one FAILS CLOSED: an unparseable payload, a
tool name it doesn't recognize, or a write whose target it can't find is
denied, naming what it saw. Which tool names actually reach each hook could
not be confirmed offline; a denial that names an unknown tool on the first
live run is the safe way to learn it — silently allowing it is not.

Also enforces the role's tool restriction ($COMPANY_ALLOWED_TOOLS, set by
worker.build_env from worker.ROLE_TOOLS): Claude Code enforces an agent
file's `tools:` natively; every other harness gets the persona inlined with
its frontmatter stripped, so without this a read-only reviewer could write.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import policy  # noqa: E402

# "Bash" is what codex 0.163.0 actually sends for a shell call (live run,
# 2026-10-31); the others are its internal tool names, kept in case a
# version reports those instead.
CODEX_SHELL = {"Bash", "exec_command", "shell_command", "shell", "local_shell", "unified_exec"}
CODEX_PATCH = {"apply_patch"}

AGY_SHELL = {"run_command"}
AGY_READ = {"view_file", "view_file_outline", "view_code_item"}
AGY_WRITE = {"write_to_file", "replace_file_content", "multi_replace_file_content",
             "edit_file"}
AGY_PATH_KEYS = ("TargetFile", "AbsolutePath", "File", "FilePath", "Path")

# Codex's apply_patch envelope: every file a patch touches is named on one of
# these header lines (Move to: is a rename's destination — also a write).
_PATCH_TARGET = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$",
                           re.MULTILINE)


def _deny_codex(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def _deny_agy(reason: str) -> None:
    print(json.dumps({"decision": "deny", "reason": reason}))
    sys.exit(0)


def _may(capability: str) -> bool:
    """The role's own tool restriction. Unset = no role restriction applies
    (only the policy checks do) — the variable is always set for a worker."""
    allowed = os.environ.get("COMPANY_ALLOWED_TOOLS")
    if allowed is None:
        return True
    tools = {t.strip() for t in allowed.split(",")}
    return {"write": bool(tools & {"Edit", "Write", "MultiEdit", "NotebookEdit"}),
            "shell": "Bash" in tools,
            "read": bool(tools & {"Read", "Grep", "Glob"})}[capability]


def _read_only(tool: str) -> str:
    return (f"Company OS: this role is read-only — `{tool}` would write. Its allowed "
            f"tools are {os.environ.get('COMPANY_ALLOWED_TOOLS')}.")


def _unknown(tool: str) -> str:
    return (f"Company OS guard: unrecognized tool `{tool}`. This guard denies what it "
            f"can't classify rather than letting an unchecked write or read through. "
            f"If this tool is legitimate, it needs a mapping in hooks/guard.py.")


def _first(reasons) -> str | None:
    for r in reasons:
        if r:
            return r
    return None


def codex(payload: dict) -> str | None:
    tool = payload.get("tool_name") or ""
    tin = payload.get("tool_input") or {}
    if tool in CODEX_SHELL:
        if not _may("shell"):
            return f"Company OS: this role may not run shell commands (`{tool}`)."
        cmd = tin.get("command") if isinstance(tin, dict) else None
        if cmd is None and isinstance(tin, dict):
            cmd = tin.get("cmd")
        if isinstance(cmd, list):
            cmd = shlex.join(str(c) for c in cmd)
        if not isinstance(cmd, str):
            return f"Company OS guard: could not determine the command `{tool}` would run."
        return policy.check_command(cmd)
    if tool in CODEX_PATCH:
        if not _may("write"):
            return _read_only(tool)
        text = "\n".join(v for v in (tin.values() if isinstance(tin, dict) else [tin])
                         if isinstance(v, str))
        targets = [t.strip() for t in _PATCH_TARGET.findall(text)]
        if not targets:
            return f"Company OS guard: could not determine which files `{tool}` writes."
        cwd = payload.get("cwd") or os.environ.get("COMPANY_REPO") or os.getcwd()
        return _first(policy.check_write(str(Path(cwd) / t)) for t in targets)
    return _unknown(tool)


def agy(payload: dict) -> str | None:
    call = payload.get("toolCall") or {}
    tool = call.get("name") or ""
    args = call.get("args") or {}
    target = next((args[k] for k in AGY_PATH_KEYS if isinstance(args.get(k), str)), None)
    if tool in AGY_SHELL:
        if not _may("shell"):
            return f"Company OS: this role may not run shell commands (`{tool}`)."
        cmd = args.get("CommandLine")
        if not isinstance(cmd, str):
            return f"Company OS guard: could not determine the command `{tool}` would run."
        return policy.check_command(cmd)
    if tool in AGY_WRITE:
        if not _may("write"):
            return _read_only(tool)
        if target is None:
            return f"Company OS guard: could not determine which file `{tool}` writes."
        return policy.check_write(target)
    if tool in AGY_READ:
        if target is None:
            return f"Company OS guard: could not determine which file `{tool}` reads."
        return policy.check_read(target)
    return _unknown(tool)


HARNESSES = {"codex": (codex, _deny_codex), "agy": (agy, _deny_agy)}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in HARNESSES:
        sys.exit(f"usage: guard.py <{'|'.join(HARNESSES)}>")
    check, deny = HARNESSES[sys.argv[1]]
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload is not a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        deny(f"Company OS guard: unreadable hook payload ({exc}); denying rather than guessing.")
    try:
        reason = check(payload)
    except Exception as exc:  # noqa: BLE001 — a crashing guard must not allow
        reason = f"Company OS guard: internal error ({type(exc).__name__}: {exc}); denying."
    if reason:
        deny(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
