"""`company harnesses` — which agent CLIs this machine has, at which version,
what each was verified to support, and whether a role could launch on it now
(docs/HARNESS-AGNOSTIC-MIGRATION.md §2/§4.1, M3).

Each harness.yaml entry may carry:
  binary / binary_paths  how to find the CLI (PATH first, then the paths)
  verified_with          the CLI version its capabilities and invocation were
                         checked against (directive V2 §6: values must be
                         confirmed against the installed version)
  capabilities           {capability: state}, states from STATES only — no
                         optimistic defaults; what wasn't confirmed is UNKNOWN

Detection runs `<cli> --version` and nothing else: no model call, no login.
A version that differs from `verified_with` is drift — not a launch block
(the guards and adapters still apply), but `--check` fails on it for any
harness a role actually uses, because a CLI upgrade is exactly when a hook
contract or output shape silently changes.
"""

from __future__ import annotations

import re
import subprocess

import harness

STATES = {"SUPPORTED", "UNSUPPORTED", "UNKNOWN", "DISABLED", "REQUIRES_CONFIGURATION"}
_VERSION = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def validate_capabilities(name: str, caps: dict) -> None:
    bad = {k: v for k, v in (caps or {}).items() if v not in STATES}
    if bad:
        raise harness.HarnessError(
            f"harness {name!r} has capability states outside {sorted(STATES)}: {bad}")


def _version_of(text: str | None) -> str | None:
    m = _VERSION.search(text or "")
    return m.group(1) if m else None


def detect(spec: dict) -> dict:
    path = harness.find_binary(spec)
    version = None
    if path:
        try:
            r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=15)
            version = _version_of(r.stdout) or _version_of(r.stderr)
        except (OSError, subprocess.SubprocessError):
            version = None
    return {"path": path, "version": version}


def _row(name: str, spec: dict, harnesses_cfg: dict) -> dict:
    spec = {**spec, "_name": name}
    found = detect(spec) if spec.get("binary") else {"path": None, "version": None}
    verified = _version_of(spec.get("verified_with"))
    reasons = []
    if spec.get("binary") and not found["path"]:
        reasons.append(f"not installed (looked for {spec['binary']!r} on PATH"
                       + (f" and in {spec['binary_paths']}" if spec.get("binary_paths") else "")
                       + ")")
    try:
        validate_capabilities(name, spec.get("capabilities") or {})
    except harness.HarnessError as exc:
        reasons.append(str(exc))
    guards = None
    try:
        resolved = harness.resolve({"default": name, "harnesses": harnesses_cfg}, None)
        guards = harness.require_guards(resolved)
    except harness.HarnessError as exc:
        reasons.append(str(exc))
    return {
        "binary": found["path"],
        "version": found["version"],
        "verified_with": spec.get("verified_with"),
        "drift": bool(found["version"] and verified and found["version"] != verified),
        "guards": guards or harness.guard_mode(spec),
        "launchable": not reasons,
        "reasons": reasons,
        "capabilities": spec.get("capabilities") or {},
    }


def report(config: dict) -> dict:
    hs = config.get("harnesses") or {}
    rows = {name: _row(name, spec, hs) for name, spec in hs.items()}
    used = {config.get("default"), *((config.get("roles") or {}).values())} - {None}
    problems = []
    for name in sorted(used):
        row = rows.get(name)
        if row is None:
            problems.append(f"{name}: used by default/roles but not defined")
        elif not row["launchable"]:
            problems.append(f"{name}: in use but cannot launch — " + "; ".join(row["reasons"]))
        elif row["drift"]:
            problems.append(f"{name}: installed {row['version']} differs from verified "
                            f"{row['verified_with']!r} — re-verify (adapter + guard smoke test)")
    return {"default": config.get("default"), "roles": config.get("roles") or {},
            "harnesses": rows, "problems": problems}
