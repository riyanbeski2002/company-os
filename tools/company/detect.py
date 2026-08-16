"""Detect what a repo is and how to prove a change didn't break it.

Company OS is aimed at brownfield work: half-built and live repos being
upgraded, not greenfield scaffolds. So the question is never "does this project
have tests" but "what command produces a real exit code here, today".

Every strategy below must be able to FAIL. A verify command that cannot go red
is a rubber stamp, and the Evidence Rule built on it would be theatre.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

# Ordered: the first strategy whose marker is present wins. Real test suites
# beat syntax checks, because they prove behaviour rather than parseability.
STRATEGIES = [
    {
        "name": "node-test-script",
        "why": "package.json defines a test script",
        "verify": "npm test",
        "strength": "behaviour",
    },
    {
        "name": "pytest",
        "why": "pytest is installed and tests/ exists",
        "verify": "python3 -m pytest -q",
        "strength": "behaviour",
    },
    {
        "name": "python-unittest",
        "why": "tests/ exists with no pytest",
        "verify": "python3 -m unittest discover -q tests",
        "strength": "behaviour",
    },
    {
        "name": "go-test",
        "why": "go.mod present",
        "verify": "go test ./...",
        "strength": "behaviour",
    },
    {
        "name": "cargo-test",
        "why": "Cargo.toml present",
        "verify": "cargo test",
        "strength": "behaviour",
    },
    {
        "name": "make-test",
        "why": "Makefile defines a test target",
        "verify": "make test",
        "strength": "behaviour",
    },
    {
        "name": "apps-script-syntax",
        "why": "Google Apps Script project — no local runner exists, so every "
               "source file is parsed instead. Proves nothing is broken syntactically; "
               "proves nothing about behaviour.",
        "verify": r"""find . -name '*.js' -not -path './.git/*' -not -path './node_modules/*' """
                  r"""-not -path './.company/*' -print0 | xargs -0 -n1 node --check""",
        "strength": "syntax-only",
    },
    {
        "name": "node-syntax",
        "why": "JavaScript sources with no test script — parse them at least",
        "verify": r"""find . -name '*.js' -not -path './.git/*' -not -path './node_modules/*' """
                  r"""-not -path './.company/*' -print0 | xargs -0 -n1 node --check""",
        "strength": "syntax-only",
    },
    {
        "name": "python-syntax",
        "why": "Python sources with no tests — compile them at least",
        "verify": "python3 -m compileall -q .",
        "strength": "syntax-only",
    },
]


def detect(repo: Path) -> dict:
    """Identify the stack and the strongest verify command available."""
    repo = Path(repo)
    signals = _signals(repo)
    chosen = None
    for strategy in STRATEGIES:
        if _applies(strategy["name"], signals):
            chosen = strategy
            break

    result = {
        "stack": signals["stack"],
        "signals": {k: v for k, v in signals.items() if k != "stack"},
        "verify": chosen["verify"] if chosen else None,
        "verify_strategy": chosen["name"] if chosen else None,
        "verify_why": chosen["why"] if chosen else None,
        "verify_strength": chosen["strength"] if chosen else None,
        "default_branch": _default_branch(repo),
    }
    if not chosen:
        result["warning"] = (
            "No verify command could be detected. The Evidence Rule requires a "
            "command that produces a real exit code, so set one explicitly in "
            ".company/config/project.yaml before running any task."
        )
    elif chosen["strength"] == "syntax-only":
        result["warning"] = (
            f"The only available check is {chosen['name']}, which proves the code "
            f"parses and nothing more. A worker can satisfy it while breaking "
            f"behaviour completely. Treat 'green' here as weak evidence, and "
            f"consider adding real tests before trusting this on live code."
        )
    return result


def _signals(repo: Path) -> dict:
    pkg = repo / "package.json"
    pkg_test = False
    if pkg.exists():
        try:
            scripts = (json.loads(pkg.read_text(encoding="utf-8")) or {}).get("scripts") or {}
            test = scripts.get("test", "")
            # `npm init` leaves a placeholder that exits 1 and tests nothing.
            pkg_test = bool(test) and "no test specified" not in test
        except (json.JSONDecodeError, OSError):
            pass

    makefile = repo / "Makefile"
    make_test = False
    if makefile.exists():
        try:
            make_test = any(l.startswith("test:") for l in
                            makefile.read_text(encoding="utf-8").splitlines())
        except OSError:
            pass

    has_py = bool(list(repo.glob("*.py")) or list(repo.glob("**/*.py"))[:1])
    has_js = bool(list(repo.glob("*.js")) or list(repo.glob("src/**/*.js"))[:1])

    stack = []
    if pkg.exists():
        stack.append("node")
    if has_py:
        stack.append("python")
    if (repo / "go.mod").exists():
        stack.append("go")
    if (repo / "Cargo.toml").exists():
        stack.append("rust")
    if (repo / "appsscript.json").exists():
        stack.append("apps-script")

    return {
        "stack": stack or ["unknown"],
        "package_json": pkg.exists(),
        "package_test_script": pkg_test,
        "tests_dir": (repo / "tests").is_dir(),
        "pytest_available": _module_available("pytest"),
        "go_mod": (repo / "go.mod").exists(),
        "cargo_toml": (repo / "Cargo.toml").exists(),
        "makefile_test": make_test,
        "appsscript": (repo / "appsscript.json").exists(),
        "node_available": shutil.which("node") is not None,
        "has_python_sources": has_py,
        "has_js_sources": has_js,
    }


def _applies(name: str, s: dict) -> bool:
    return {
        "node-test-script": s["package_test_script"],
        "pytest": s["tests_dir"] and s["pytest_available"],
        "python-unittest": s["tests_dir"] and s["has_python_sources"],
        "go-test": s["go_mod"],
        "cargo-test": s["cargo_toml"],
        "make-test": s["makefile_test"],
        "apps-script-syntax": s["appsscript"] and s["node_available"],
        "node-syntax": s["has_js_sources"] and s["node_available"],
        "python-syntax": s["has_python_sources"],
    }.get(name, False)


def _module_available(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _default_branch(repo: Path) -> str:
    import subprocess
    for args in (["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                 ["rev-parse", "--abbrev-ref", "HEAD"]):
        r = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().replace("origin/", "")
    return "main"
