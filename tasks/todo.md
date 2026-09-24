# pen_test: close the native-probe blind spots + mandatory evidence

## Goal
Native probes for ALL five uncovered classes, a mandatory evidence deliverable,
a test harness, and content-discovery wired into the workflow. (Scope-guard skipped
— allowlist already exists per Riyan.)

## Plan
- [x] R. Research (Sonnet + web search) current methodology for each class before building
  - [x] SSTI  - [x] Command injection  - [x] Path traversal/LFI  - [x] File upload  - [x] XXE/XML
- [x] 1. Evidence layer: `Finding` + JSONL sink in `_httpcore.py`; `report.py` aggregator (md+json)
- [x] 2. New probes on the shared engine:
  - [x] ssti cmdi traversal xxe upload — all built + tested

- [x] 3. Make evidence deliverable MANDATORY (agents/pen_test.md + SKILL.md report sections)
- [x] 4. Tests: `tests/` mock-server harness + unit tests for engine + new probes
- [x] 5. Wire ffuf/katana content discovery into `workflow.sh`
- [x] 6. Update SKILL.md decision matrix, workflow.sh targeted steps, knowledge cross-refs
- [x] 7. Verify: run each probe against a local mock target; run test suite
- [ ] 8. Review section

## Review
(to be filled in on completion)

## Review (2026-09-24)
Closed the native-probe blind spots the audit found. All work verified.

**Built (native/):** ssti_probe, cmdi_probe, traversal_probe, xxe_probe, upload_probe
— each researched first via a Sonnet web-search agent (PortSwigger/HackTricks/
PayloadsAllTheThings + 2024-2026 CVEs), then built as differential DETECTORS on the
shared _httpcore engine with benign-proof discipline and false-positive guards.

**Evidence made mandatory:** _httpcore now has Finding + EvidenceLog; every probe
takes --evidence-dir; new native/report.py aggregates findings.jsonl into
report.md/report.json and QUARANTINES proof-less candidates (a signal/PoC is a
candidate, only real captured evidence counts). Agent + SKILL doctrine updated to
require the tool-produced report as the deliverable.

**Other blind spots solved:** tests/ harness (mock_target.py + test_probes.py,
16/16 passing end-to-end); ffuf/katana content-discovery wired into workflow.sh
(deep depth) with auto report.py footer; new probes added to webapp/api/owasp
targeted steps and the SKILL decision matrix. Engine gained multipart (files=) support.

**Scope-guard:** skipped per Riyan (allowlist already exists).

**Not done / follow-ups:** existing 15 probes don't yet emit to --evidence-dir
(only the 5 new ones + report do) — retrofitting them is mechanical and would make
the report bundle capture the whole engagement; worth a follow-up. Nested
skills/pen_test/agents/pen_test.md still duplicates root agents/pen_test.md (both
kept in sync this round). No new dependencies added.
