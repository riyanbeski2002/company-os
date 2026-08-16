"""The executive panel — expertise the CEO does not have and should not need.

A CEO is not all-knowing; that is why a company has a CTO, a CISO, a CFO. The
implementer roles answer "did we build it correctly". These four answer the
questions nobody else in the system is asking:

  cto   — is this the right approach at all?
  ciso  — what is our standing exposure, beyond any single diff?
  cfo   — what is this consuming per unit delivered, and where is the waste?
  coo   — is the delivery machine itself working, or just producing motion?

They are advisors, not deciders. They produce findings backed by evidence and
escalate anything that is genuinely the CEO's call. They are read-only by
construction: none of them can write a file.

The justification is concrete. A Company OS build burned 2.49M cache-read
tokens, 83% of it tool definitions no worker ever called, and nothing in the
system noticed — a human found it by hand. That is precisely the gap this
closes.
"""

from __future__ import annotations

from pathlib import Path

from eventlog import EventLog, make_event

OFFICERS = {
    "cto": {
        "agent": "cto-advisor",
        "question": "Is this the right approach at all?",
        "brief": ("Review this repository's architecture and approach. Judge whether "
                  "the work being done is the right work, whether debt is accumulating, "
                  "and whether anything here should not be built at all. Read the code "
                  "and the event log; do not take documentation at face value."),
    },
    "ciso": {
        "agent": "ciso-advisor",
        "question": "What is our standing exposure?",
        "brief": ("Assess this repository's standing security exposure — secrets, the "
                  "authorization surface as a whole, dependency risk, and gaps in the "
                  "risk-trigger table relative to what this codebase actually handles. "
                  "This is not a diff review; look at what no single task would reveal."),
    },
    "cfo": {
        "agent": "cfo-advisor",
        "question": "What does this cost per unit delivered?",
        "brief": ("Audit what this project consumes against what it delivered. Start "
                  "with `company costs` and `company status --json`. Check every agent "
                  "file for a missing `tools:` list, which is the most expensive "
                  "mistake available. Report per delivered outcome, never as a raw "
                  "total, and never propose saving money by checking less."),
    },
    "coo": {
        "agent": "coo-advisor",
        "question": "Is the delivery machine working?",
        "brief": ("Audit the delivery process itself from the event log: tier "
                  "discipline, gate effectiveness, rework, stalls, contract discipline, "
                  "and whether escalations were genuinely the CEO's call. Identify "
                  "causes, not symptoms. Do not propose additional process."),
    },
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "finding": {"type": "string"},
                    "evidence": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "verified": {"type": "boolean"},
                    "needs_ceo_decision": {"type": "boolean"},
                },
                "required": ["severity", "finding", "evidence", "recommendation",
                             "verified", "needs_ceo_decision"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["findings", "summary"],
}


def record_finding(company_root: Path, *, project: str, officer: str, severity: str,
                   finding: str, evidence: str, recommendation: str,
                   verified: bool = True, actor: str | None = None) -> dict:
    if officer not in OFFICERS:
        raise ValueError(f"unknown officer {officer!r}; expected one of {sorted(OFFICERS)}")
    if severity not in SEVERITY_ORDER:
        raise ValueError(f"severity must be high, medium or low, not {severity!r}")
    if not evidence.strip():
        raise ValueError(
            "an advisory finding requires evidence. An officer's opinion without "
            "evidence is exactly the kind of noise this system exists to remove."
        )

    data = {"officer": officer, "severity": severity, "finding": finding,
            "recommendation": recommendation, "verified": verified}
    EventLog(company_root).append(make_event(
        event="ADVISORY_FINDING", actor=actor or f"{officer}-advisor",
        project=project, data=data, evidence={"log": evidence}))
    return data


def fold(events: list[dict], project: str | None = None) -> list[dict]:
    """Open advisory findings, most severe first."""
    findings = []
    resolved = {
        (e.get("data") or {}).get("finding")
        for e in events if e.get("event") == "ADVISORY_RESOLVED"
    }
    for ev in events:
        if ev.get("event") != "ADVISORY_FINDING":
            continue
        if project and ev.get("project") != project:
            continue
        data = dict(ev.get("data") or {})
        if data.get("finding") in resolved:
            continue
        data["raised_at"] = ev["ts"]
        data["evidence"] = (ev.get("evidence") or {}).get("log")
        findings.append(data)
    return sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f["severity"], 3),
                                           f.get("officer", "")))


def render(findings: list[dict]) -> str:
    if not findings:
        return "No open advisory findings."
    lines = []
    by_officer: dict[str, list] = {}
    for f in findings:
        by_officer.setdefault(f.get("officer", "?"), []).append(f)

    for officer, items in by_officer.items():
        lines.append(f"\n{officer.upper()} — {OFFICERS.get(officer, {}).get('question', '')}")
        for f in items:
            mark = {"high": "!!", "medium": " !", "low": "  "}.get(f["severity"], "  ")
            unverified = "" if f.get("verified", True) else "  [UNVERIFIED]"
            lines.append(f"  {mark} {f['finding']}{unverified}")
            lines.append(f"       evidence: {f.get('evidence')}")
            lines.append(f"       → {f.get('recommendation')}")
    return "\n".join(lines)
