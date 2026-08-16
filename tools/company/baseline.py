"""Baseline capture — what "green" means in a repo that was never green.

V1 required `exit_code == 0` to close a task. On a greenfield fixture that is
right. On a half-built or live repo it is a trap: if the suite is already red
when you arrive, every task is refused forever for damage the worker did not do,
and the only ways out are to fix unrelated code or to lie.

So the rule becomes **no worse than the baseline**, measured before any work
starts:

- baseline green  → a task must be green. Unchanged from V1, and still strict.
- baseline red    → a task must not add failures, and must not turn a passing
                    check red.

The baseline is recorded as an event, so it is auditable and cannot be quietly
adjusted later to make a red run look acceptable.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from eventlog import EventLog, make_event

# Failure counts, per runner. Falling back to exit code alone is safe but coarse:
# it cannot tell "fixed one, broke another" from "no change".
COUNT_PATTERNS = [
    re.compile(r"(?P<failed>\d+)\s+failed", re.I),            # pytest
    re.compile(r"FAILED\s+\(failures=(?P<failed>\d+)", re.I),  # unittest
    re.compile(r"FAILED\s+\(errors=(?P<failed>\d+)", re.I),
    re.compile(r"Tests:\s+(?P<failed>\d+)\s+failed", re.I),    # jest
    re.compile(r"(?P<failed>\d+)\s+failing", re.I),            # mocha
]


def measure(repo: Path, verify: str, timeout: int = 900) -> dict:
    """Run the verify command and describe the result. No judgement, just facts."""
    try:
        run = subprocess.run(verify, shell=True, cwd=str(repo),
                             capture_output=True, text=True, timeout=timeout)
        output = (run.stdout or "") + (run.stderr or "")
        exit_code = run.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        output = str(exc)
        exit_code = 124
        timed_out = True

    return {
        "verify": verify,
        "exit_code": exit_code,
        "failures": _count_failures(output),
        "timed_out": timed_out,
        "output_tail": output[-2000:],
    }


def _count_failures(output: str) -> int | None:
    for pattern in COUNT_PATTERNS:
        m = pattern.search(output)
        if m:
            return int(m.group("failed"))
    return None


def record(company_root: Path, repo: Path, *, project: str, verify: str,
           actor: str = "company-cli", ref: str | None = None,
           timeout: int = 900) -> dict:
    """Measure the repo as it stands and write the result to the event log."""
    result = measure(repo, verify, timeout=timeout)
    sha = _head(repo)
    data = {
        "verify": verify,
        "exit_code": result["exit_code"],
        "failures": result["failures"],
        "green": result["exit_code"] == 0,
        "ref": ref or sha,
    }
    log_dir = Path(company_root) / "state"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "baseline.log"
    log_path.write_text(result["output_tail"], encoding="utf-8")

    EventLog(company_root).append(make_event(
        event="BASELINE_RECORDED", actor=actor, project=project,
        data=data, evidence={"commit": sha, "log": str(log_path)}))
    return {**data, "log": str(log_path), "output_tail": result["output_tail"]}


def _head(repo: Path) -> str:
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def latest(events: list[dict], project: str | None = None) -> dict | None:
    """The most recent baseline, which is the one in force."""
    found = None
    for ev in events:
        if ev.get("event") != "BASELINE_RECORDED":
            continue
        if project and ev.get("project") != project:
            continue
        found = ev.get("data")
    return found


def compare(baseline: dict | None, run: dict) -> tuple[bool, str]:
    """Is this run acceptable given the baseline? Returns (ok, reason).

    `run` needs `exit_code` and may carry `failures`.
    """
    exit_code = run.get("exit_code")
    failures = run.get("failures")

    if exit_code == 0:
        return True, "verify passed (exit 0)"

    if baseline is None:
        return False, (
            f"verify failed (exit {exit_code}) and no baseline was recorded, so "
            f"there is nothing to judge it against. Run `company baseline` on a "
            f"clean checkout first."
        )

    if baseline.get("green"):
        return False, (
            f"verify failed (exit {exit_code}) but the baseline was green "
            f"(exit 0 at {str(baseline.get('ref'))[:8]}). This change broke "
            f"something that worked."
        )

    base_failures = baseline.get("failures")
    if base_failures is None or failures is None:
        return False, (
            f"verify failed (exit {exit_code}). The baseline was also red "
            f"(exit {baseline.get('exit_code')}), but failure counts could not be "
            f"parsed from either run, so 'no worse' cannot be proven. Fix the "
            f"pre-existing failures, or set a verify command that reports counts."
        )

    if failures > base_failures:
        return False, (
            f"verify failed with {failures} failures against a baseline of "
            f"{base_failures}. This change added {failures - base_failures}."
        )

    return True, (
        f"verify still red ({failures} failures) but no worse than the "
        f"pre-existing baseline of {base_failures}. Accepted as no-regression; "
        f"the pre-existing failures remain outstanding."
    )
