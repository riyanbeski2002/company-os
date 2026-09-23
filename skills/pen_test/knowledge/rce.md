---
name: rce
description: Owned methodology for remote code execution — the highest-severity outcome, reached through many roads (command/argument injection, insecure deserialization, SSTI, file upload, resolution fallback, memory bugs). How to recognize the primitive, prove execution safely, and escalate.
---

# Remote Code Execution

RCE is usually not its own bug — it's the *destination* other classes reach. This doc
is the map of roads to RCE and the discipline for proving it without doing damage. Each
road has a dedicated class doc; this ties them together and defines the RCE-specific bar.

## The roads to RCE

| Road | Where it lives | Trigger to look for |
|---|---|---|
| OS command / argument injection | `ssrf_and_injection.md` | user input reaching `system`/`exec`/`popen`/shell, or smuggled CLI flags |
| Insecure deserialization | `modern_stack.md` | Java `rO0`/`AC ED`, .NET `AAEAAAD`/ViewState, PHP `O:`, pickle, Ruby Marshal, node-serialize |
| Template injection (SSTI) | `ssrf_and_injection.md`, `modern_stack.md` | `{{7*7}}`/`${7*7}`/`<%=7*7%>` evaluates → engine-specific RCE gadget |
| File upload → execution | `data_handling.md` | upload of `.php`/`.jsp`/`.aspx` into a served/executable path; polyglot + content-type confusion |
| Resolution / search-path fallback | `semantic_confusion.md`, `secrets_and_supply_chain.md` | npx/`PATH`/autoloader resolves an attacker-controlled name |
| SQLi → RCE | `sql_injection.md` | stacked queries, `xp_cmdshell`, `INTO OUTFILE`, UDF, `COPY ... PROGRAM` |
| SSRF → internal RCE | `ssrf_and_injection.md` | SSRF reaching an internal admin/metadata/CI endpoint that itself executes |
| Prototype pollution → RCE | `modern_stack.md` | polluted property flows into a template/`child_process` sink |
| Known-CVE RCE | `cve_playbook.md` | fingerprinted version with a public RCE (Apache path-trav→cgi, Spring, etc.) |
| Memory safety | (specialist) | only when reachable attacker input is proven — otherwise it's theoretical |

## Prove it safely — the RCE-specific bar

RCE is the finding most tempting to over-claim and most dangerous to over-exploit. The
proof must be **benign and reversible**:
1. **Non-destructive command execution** — `id`, `whoami`, `hostname`, `echo <marker>`,
   or a DNS/HTTP callback to your OAST with a unique token. Never `rm`, never write
   outside a scratch path, never touch data.
2. **Out-of-band confirmation for blind RCE** — if there's no output channel, prove it
   with a DNS/HTTP callback (`curl http://<token>.oast/`, `nslookup <token>.oast`). A
   timing delay (`sleep 5`) is a weaker secondary signal.
3. **Show the primitive, not a full shell** — a demonstrated `id` output or callback hit
   is the finding. Do **not** drop a persistent implant, pivot, or exfiltrate unless the
   engagement authorization *explicitly* covers post-exploitation.
4. **Record** the exact input, the sink, the road taken, and the benign proof output.

## Authorization gate (RCE-specific)

Everything above crosses from "read/prove" into "execute." Per the agent's authorization
gate, weaponize past a benign proof (`id`/callback) **only** under explicit
code-execution authorization. `--os-shell`/`--os-pwn` (sqlmap), reverse shells, and
gadget-chain payloads are post-exploitation — gated, never opportunistic.

## Severity

Unauth RCE on an internet-exposed surface is Critical; authenticated RCE is High (see
`finding_validation.md` for the full calibration). The `id`/callback proof is what makes
it defensible — an asserted RCE with no demonstrated execution is not a Critical, it's an
`open_proof_gap`.
