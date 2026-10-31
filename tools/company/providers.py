"""Bring-your-own-key model providers (docs/HARNESS-AGNOSTIC-MIGRATION.md
§4.5, M4).

A harness (harness.yaml) is the CLI a worker runs in; a provider is whose
model endpoint and credentials that CLI talks to. `native` means the CLI's
own login (claude.ai subscription, ChatGPT account): nothing is injected and
nothing changes. Any other provider is declared in providers.yaml:

  auth                native | env | none
  key_ref             env auth only: the NAME of the env var holding the key.
                      The key itself is never stored, and any config value
                      shaped like a key is rejected outright.
  trust               first_party | third_party | local
  max_classification  the most sensitive project (project.yaml
                      `data_classification`) this provider may see. Required
                      for every non-native provider; native has no ceiling.
  base_url            optional endpoint override

Routing is `default` + `roles:`, the same shape as harness.yaml. The key is
read from the launching process's env at launch, handed to the worker only
through the env var its harness declares (`provider_env`), and scrubbed from
the worker's stdout/stderr before anything reads them (`redact`). A provider
the project's classification forbids is refused; there is no fallback to
another provider.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import staffing

NATIVE = "native"
LEVELS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET"]
DEFAULT_CLASSIFICATION = "INTERNAL"  # project.yaml's own default (cli.py onboard)
AUTH = {"native", "env", "none"}
TRUSTS = {"first_party", "third_party", "local"}

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
# Known credential prefixes, at the start of a word (`task-...` is not `sk-`).
_KEY_PREFIX = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:sk-|sk_|rk_|pk_|ghp_|gho_|github_pat_|xox[abpr]-|AIza|AKIA|ya29\.|glpat-)"
    r"[A-Za-z0-9_\-.]{8,}")
# Otherwise: a long unbroken token mixing upper, lower and digits, as random
# keys do. Names, paths and URLs don't (a '.' or ':' also rules a token out).
_KEY_TOKEN = re.compile(r"^[A-Za-z0-9_\-+/=]{32,}$")


def _looks_like_key(text: str) -> bool:
    if _KEY_PREFIX.search(text):
        return True
    return any(_KEY_TOKEN.match(tok) and re.search(r"[a-z]", tok)
               and re.search(r"[A-Z]", tok) and re.search(r"[0-9]", tok)
               for tok in text.split())


class ProviderError(RuntimeError):
    pass


class ProviderIneligible(ProviderError):
    """The project's data classification forbids this provider."""


def load_config(company_root: Path) -> dict:
    for path in (Path(company_root) / "config" / "providers.yaml",
                 staffing.PLUGIN_CONFIG / "providers.yaml"):
        if path.exists():
            text = path.read_text(encoding="utf-8")
            # The raw text too: a key pasted into a comment is still committed.
            if _looks_like_key(text):
                raise ProviderError(_PASTED_KEY.format(where=str(path)))
            break
    try:
        cfg = staffing.load_config(company_root, "providers.yaml")
    except FileNotFoundError:
        cfg = {}
    validate(cfg)
    return cfg


_PASTED_KEY = ("{where} contains something that looks like a credential. providers.yaml "
               "stores only the NAME of the env var that holds a key (key_ref), never the "
               "key. Remove it from the file (and from git history if it was committed) "
               "and rotate it.")


def _strings(value, path: str):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, f"{path}[{i}]")


def validate(cfg: dict) -> None:
    """Raise on anything that could leak a key or route somewhere unchecked.
    Errors name the field, never echo its value."""
    for where, text in _strings(cfg, "providers.yaml"):
        if _looks_like_key(text):
            raise ProviderError(_PASTED_KEY.format(where=where))
    provs = cfg.get("providers") or {}
    for name, spec in provs.items():
        if name == NATIVE:
            raise ProviderError("`native` is built in (the CLI's own login); don't redefine it")
        spec = spec or {}
        auth = spec.get("auth")
        if auth not in AUTH - {NATIVE}:
            raise ProviderError(f"provider {name!r}: auth must be env or none, not {auth!r}")
        if auth == "env":
            if not _ENV_NAME.match(str(spec.get("key_ref") or "")):
                raise ProviderError(
                    f"provider {name!r}: auth env needs key_ref, the NAME of an env var "
                    f"(e.g. OPENROUTER_API_KEY)")
        elif spec.get("key_ref"):
            raise ProviderError(f"provider {name!r}: key_ref is only meaningful with auth: env")
        if spec.get("trust") not in TRUSTS:
            raise ProviderError(f"provider {name!r}: trust must be one of {sorted(TRUSTS)}")
        if spec.get("max_classification") not in LEVELS:
            raise ProviderError(
                f"provider {name!r}: max_classification must be one of {LEVELS} — the most "
                f"sensitive project this endpoint may see")
        base = spec.get("base_url")
        if base is not None and not re.match(r"^https?://", str(base)):
            raise ProviderError(f"provider {name!r}: base_url must be an http(s) URL")
    for where, name in [("default", cfg.get("default"))] + [
            (f"roles.{r}", n) for r, n in (cfg.get("roles") or {}).items()]:
        if name not in (None, NATIVE) and name not in provs:
            raise ProviderError(f"providers.yaml {where} names undefined provider {name!r}")


def resolve(cfg: dict, role: str | None) -> dict:
    name = (cfg.get("roles") or {}).get(role) or cfg.get("default") or NATIVE
    if name == NATIVE:
        return {"_name": NATIVE, "auth": NATIVE}
    return {**cfg["providers"][name], "_name": name}


def project_classification(company_root: Path) -> str:
    try:
        level = staffing.load_config(company_root, "project.yaml").get("data_classification")
    except FileNotFoundError:
        level = None
    level = level or DEFAULT_CLASSIFICATION
    if level not in LEVELS:
        # Unknown is treated as the most sensitive, not the least.
        raise ProviderError(f"project.yaml data_classification {level!r} is not one of {LEVELS}")
    return level


def check_classification(spec: dict, classification: str) -> None:
    if spec["_name"] == NATIVE:
        return
    ceiling = spec["max_classification"]
    if LEVELS.index(classification) > LEVELS.index(ceiling):
        raise ProviderIneligible(
            f"provider {spec['_name']!r} ({spec.get('trust')}) may see at most {ceiling} "
            f"data; this project is {classification}. Not launching, and not falling back "
            f"to another provider: route this role to an eligible provider in "
            f"providers.yaml, or reclassify the project if {classification} is wrong.")


def worker_env(spec: dict, harness_spec: dict, environ=None) -> tuple[dict, list[str]]:
    """(vars to set in the worker's env, vars to remove from it). Raises if
    the harness can't carry this provider or the key isn't set — before
    anything is claimed or launched."""
    if spec["_name"] == NATIVE:
        return {}, []
    environ = os.environ if environ is None else environ
    carry = harness_spec.get("provider_env") or {}
    hname = harness_spec.get("_name")
    if not carry:
        raise ProviderError(
            f"harness {hname!r} has no provider_env, so it can't be pointed at provider "
            f"{spec['_name']!r}: only its native login is wired in.")
    out = {}
    if spec.get("base_url"):
        if not carry.get("base_url"):
            raise ProviderError(f"harness {hname!r} has no env var for a provider base_url")
        out[carry["base_url"]] = spec["base_url"]
    remove = []
    if spec["auth"] == "env":
        ref = spec["key_ref"]
        if not environ.get(ref):
            raise ProviderError(
                f"provider {spec['_name']!r} reads its key from ${ref}, which is not set "
                f"in this shell. Export it, then launch.")
        if not carry.get("key"):
            raise ProviderError(f"harness {hname!r} has no env var to carry a provider key")
        out[carry["key"]] = environ[ref]
        # Only the harness's own variable carries the key into the worker.
        remove.append(ref)
    return out, remove


def secrets(spec: dict | None, environ=None) -> dict[str, str]:
    """{key_ref: value} for redaction; empty for native or an unset key."""
    if not spec or spec.get("auth") != "env":
        return {}
    environ = os.environ if environ is None else environ
    value = environ.get(spec["key_ref"])
    return {spec["key_ref"]: value} if value else {}


def redact(text: str, values: dict[str, str]) -> str:
    for ref, value in values.items():
        if len(value) >= 8:  # a shorter "key" would scrub ordinary words
            text = text.replace(value, f"[REDACTED:{ref}]")
    return text


def report(cfg: dict, environ=None) -> dict:
    """Each provider and whether its key is set (yes/no only), and the routing."""
    environ = os.environ if environ is None else environ
    rows = {}
    for name, spec in (cfg.get("providers") or {}).items():
        rows[name] = {k: spec.get(k) for k in ("auth", "trust", "max_classification",
                                                 "base_url", "key_ref")}
        if spec.get("auth") == "env":
            rows[name]["key_set"] = bool(environ.get(spec["key_ref"]))
    return {"default": cfg.get("default") or NATIVE, "roles": cfg.get("roles") or {},
            "providers": rows}
