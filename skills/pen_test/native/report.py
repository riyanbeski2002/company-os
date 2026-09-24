#!/usr/bin/env python3
"""report.py — the mandatory engagement deliverable generator.

Every native probe, when run with `--evidence-dir DIR`, appends structured
Finding records to `DIR/findings.jsonl` and saves raw proof artifacts under
`DIR/artifacts/`. This tool aggregates that directory into the deliverable:

  * report.md   — severity-first, human-readable, every finding tied to its
                  real, benign proof + the exact command to reproduce it
  * report.json — the same, machine-readable

**Evidence is mandatory.** A finding whose `proof` is empty (no real,
source-extracted evidence) is NOT reportable — it is quarantined into a
separate "Unsubstantiated" section and excluded from the headline counts. This
operationalizes knowledge/exploitation_depth.md: a benign PoC or a bare signal
is a *candidate*; only demonstrated impact with real data is a finding.

Usage:
    # after a run that used --evidence-dir ./ev :
    python3 report.py ./ev
    python3 report.py ./ev --out ./ev/report.md --title "ACME webapp — 2026-09"
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _httpcore as core  # noqa: E402

SEV_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}


def load_findings(evidence_dir: str) -> list[dict]:
    path = os.path.join(evidence_dir, "findings.jsonl")
    if not os.path.exists(path):
        raise SystemExit(f"No findings.jsonl in {evidence_dir!r} — run a probe with "
                         f"--evidence-dir {evidence_dir} first.")
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def is_reportable(f: dict) -> bool:
    """A finding counts only with real, captured proof (or an explicit confirm)."""
    return bool(f.get("proof")) or f.get("status") == "confirmed"


def _sev_key(f: dict) -> int:
    return core._SEV_ORDER.get(f.get("severity", "info"), 99)


def dedup(findings: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in findings:
        key = (f.get("vuln_class"), f.get("target"), f.get("param"),
               f.get("location"), f.get("title"))
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def render_md(reportable: list[dict], quarantined: list[dict], title: str) -> str:
    L: list[str] = []
    L.append(f"# {title}")
    L.append("")
    counts = {s: 0 for s in core.SEVERITIES}
    for f in reportable:
        counts[f.get("severity", "info")] = counts.get(f.get("severity", "info"), 0) + 1
    summary = "  ".join(f"{SEV_EMOJI[s]} {s} {counts[s]}" for s in core.SEVERITIES if counts[s])
    L.append(f"**{len(reportable)} reportable finding(s).** {summary or '_none_'}")
    if quarantined:
        L.append(f"\n> ⚠️ {len(quarantined)} candidate(s) had no captured proof and are "
                 f"quarantined below — not counted as findings until evidence is attached "
                 f"(see knowledge/exploitation_depth.md).")
    L.append("\n---\n")

    if not reportable:
        L.append("_No evidence-backed findings. Absence of proof is not proof of absence — "
                 "review the quarantine and the per-probe output before concluding._\n")
    for i, f in enumerate(sorted(reportable, key=_sev_key), 1):
        sev = f.get("severity", "info")
        L.append(f"## {i}. {SEV_EMOJI.get(sev,'')} [{sev.upper()}] {f.get('title','(untitled)')}")
        L.append("")
        L.append(f"- **Class:** {f.get('vuln_class','?')}  |  **Status:** {f.get('status','candidate')}"
                 f"  |  **Tool:** {f.get('tool','?')}")
        L.append(f"- **Target:** `{f.get('target','')}`")
        if f.get("param") or f.get("location"):
            L.append(f"- **Injection point:** `{f.get('param','')}` in `{f.get('location','')}`")
        L.append("")
        L.append("**Proof (real, benign evidence):**")
        L.append("```")
        L.append(str(f.get("proof", "")).strip() or "(none)")
        L.append("```")
        if f.get("response_excerpt"):
            L.append("**Response excerpt (bounded/redacted):**")
            L.append("```")
            L.append(str(f["response_excerpt"]).strip())
            L.append("```")
        if f.get("request"):
            L.append(f"**Request:** `{f['request']}`")
        if f.get("reproduce"):
            L.append(f"\n**Reproduce:**\n```bash\n{f['reproduce']}\n```")
        if f.get("artifacts"):
            L.append("**Artifacts:** " + ", ".join(f"`{p}`" for p in f["artifacts"].values()))
        if f.get("notes"):
            L.append(f"\n> {f['notes']}")
        if f.get("ts"):
            L.append(f"\n_captured {f['ts']}_")
        L.append("\n---\n")

    if quarantined:
        L.append("## Unsubstantiated candidates (NOT reportable — no captured proof)\n")
        L.append("Each fired a signal but has no real evidence attached. Reproduce and capture "
                 "demonstrated impact (real extracted data) before treating any as a finding.\n")
        for f in sorted(quarantined, key=_sev_key):
            L.append(f"- **[{f.get('severity','?')}]** {f.get('title','?')} — "
                     f"`{f.get('param','')}`@`{f.get('location','')}` on `{f.get('target','')}`"
                     + (f"  → reproduce: `{f['reproduce']}`" if f.get("reproduce") else ""))
        L.append("")
    return "\n".join(L)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("evidence_dir", help="the --evidence-dir a run wrote to")
    p.add_argument("--out", help="markdown path (default: <evidence_dir>/report.md)")
    p.add_argument("--json-out", help="json path (default: <evidence_dir>/report.json)")
    p.add_argument("--title", default="Penetration test — findings report")
    args = p.parse_args()

    findings = dedup(load_findings(args.evidence_dir))
    reportable = [f for f in findings if is_reportable(f)]
    quarantined = [f for f in findings if not is_reportable(f)]

    md = render_md(reportable, quarantined, args.title)
    md_path = args.out or os.path.join(args.evidence_dir, "report.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md)

    json_path = args.json_out or os.path.join(args.evidence_dir, "report.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"title": args.title,
                   "reportable": sorted(reportable, key=_sev_key),
                   "quarantined": sorted(quarantined, key=_sev_key)}, fh, indent=2)

    print(f"[report] {len(reportable)} reportable, {len(quarantined)} quarantined "
          f"(no proof) out of {len(findings)} record(s)")
    print(f"[report] wrote {md_path}")
    print(f"[report] wrote {json_path}")
    if quarantined:
        print(f"[report] ⚠️  {len(quarantined)} candidate(s) lack captured proof and are NOT "
              f"counted — attach real evidence per exploitation_depth.md before reporting them.")


if __name__ == "__main__":
    main()
