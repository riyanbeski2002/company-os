---
name: secrets-and-supply-chain
description: Original methodology for secret exposure and dependency/supply-chain risk.
---

# Secrets and Supply Chain

## Secret detection

Use `native/secret_scan.py` (this skill's own scanner — 20+ named formats
plus Shannon-entropy detection and per-finding severity, no external
`gitleaks` dependency for the common cases) against:

```bash
python3 native/secret_scan.py path/to/tree        # working tree, severity-ranked
python3 native/secret_scan.py --git-history .      # full `git log -p` history
```

For live web targets, `native/http_recon.py` probes for exposed `.env`,
`.git/HEAD`, `/actuator/env`, source maps, and other artifacts that leak
secrets remotely — run it before assuming secrets are only a code-review concern.
Scan targets:
- The working tree and, separately, full git history (`git log -p`) — a
  secret removed in a later commit is still exposed in history unless the
  history itself was rewritten.
- Build artifacts and client-side bundles (a secret meant to be
  server-only sometimes leaks into a frontend JS bundle via a misconfigured
  env-var prefix, e.g. Next.js's `NEXT_PUBLIC_*` convention being applied
  to something that shouldn't be public).
- CI/CD config and logs (a secret echoed in a build log, or hardcoded in a
  workflow YAML instead of referenced from a secrets store).

**Common patterns worth a dedicated regex** (see `native/secret_scan.py`
for the actual implementation): AWS access keys (`AKIA[0-9A-Z]{16}`),
generic high-entropy strings assigned to variables named `*_key`/`*_token`/
`*_secret`/`*_password`, private key headers (`-----BEGIN ... PRIVATE
KEY-----`), Slack tokens (`xox[baprs]-`), GitHub tokens (`ghp_`, `gho_`,
`github_pat_`), Stripe keys (`sk_live_`, `rk_live_`).

**A found pattern isn't yet a confirmed secret** — regex matches produce
false positives (test fixtures, example/placeholder values, already-
rotated credentials). Where feasible and authorized, confirm liveness
(does the key actually authenticate against its real service) before
reporting it as an active exposure rather than a pattern match; if you
can't safely confirm liveness, report it as "found, not yet confirmed
live" rather than overstating it.

## Dependency / supply-chain risk

This is the one area where "build our own" is the wrong call, not a
missing feature: a from-scratch CVE database goes stale the moment it's
written, and vulnerability disclosure is a continuously-updated feed, not
a fixed body of technique knowledge like SQLi/XSS. Use the actual
maintained tools for this (registered, installed via package manager, not
vendored source — see `SKILL.md`'s toolbox table): `trivy`/`grype` for
known-CVE dependency and container scanning, `syft` for SBOM generation,
`checkov` for IaC misconfiguration. Native scripts here focus on
technique-based classes (injection, auth, business logic) where the
knowledge is genuinely stable and worth owning directly; CVE/dependency
scanning is the opposite case — the value is entirely in the up-to-date
database, not the scanning logic.

## Dependency confusion & package-runner (npx) confusion

A stable *technique* class worth owning (distinct from CVE scanning above):
getting a build/CI/agent workflow to execute an attacker-controlled package.

- **Classic dependency confusion:** an internal package name also resolvable on a
  public registry; the resolver prefers (or falls back to) the public one. Detect:
  internal `@scope/` or bare package names in `package.json`/`requirements.txt`/etc.
  that are unclaimed on the public registry.
- **Package-runner (npx) confusion** — resolver *fallback* semantics, not registry
  priority: `npx`, `npm exec`, `bunx`, `pnpm dlx`, `yarn dlx`, `deno run npm:` will
  fetch and execute a *remote* package when a **bare command** doesn't resolve
  locally. Vulnerable when all hold: (1) the executable isn't in `node_modules/.bin`,
  global bin, workspace, or cache for that runner; (2) the runner falls back to the
  registry for the bare token; (3) the intended package name ≠ the executable name
  (or a typo picks the wrong one); (4) the workflow has real authority (CI creds,
  release perms, agent capabilities).
  - **Detect:** grep `.mcp.json`, `turbo.json`, `package.json` scripts, CI workflows,
    composite actions, devcontainer config for `npx -y <bare>`, `bunx <bare>`,
    `pnpm dlx <bare>`, etc. Confirm the binary does **not** resolve locally *in that
    workflow's actual context* (not repo-root), and that the intended package is
    absent/differs on the registry.
  - **Impact = the workflow's authority** (RCE in CI, release pipeline, or an agent
    launcher). This is why it belongs here, not in "secrets."

## Validation bar

A secret finding needs the actual matched string (redacted appropriately
in the report — show enough to prove the match, not the full usable
credential) and its location (file + line, or commit hash). A dependency
finding needs the actual CVE ID and affected version range from the
scanning tool's own output, not a restated guess.
