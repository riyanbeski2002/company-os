#!/usr/bin/env python3
"""repeater.py — owned HTTP repeater / replay for pen_test.

The one general primitive our native set was missing versus a full agent
runtime: take a request, resend it (modified), inspect the response, and do it
at scale. Burp Repeater / Intruder-lite, on the shared _httpcore engine, so it
inherits authenticated sessions, proxy passthrough, and rate limiting.

Modes:
  send  — build a request from flags, fire once, show the full response
  raw   — parse a raw HTTP request (Burp "Copy as raw request" / a saved file
          or stdin), optionally tweak it, and send it — the fastest way to
          replay a real captured request
  race  — fire the SAME request N times concurrently (one-time-code reuse,
          coupon double-spend, TOCTOU / limit-overrun business-logic tests)
  diff  — send two variants and diff their responses (the manual core of every
          differential: authz, injection, cache-key, header-reflection)

This is a manual instrument, not a scanner — it does exactly what you tell it,
which is the point: when a probe flags a candidate, this is how you hand-confirm
and craft the PoC without leaving the toolchain.

AUTHORIZATION: sends live, attacker-controlled requests — authorized targets only.

Usage:
    python3 repeater.py send -u https://app/api/x -X POST --json '{"a":1}' --show-body
    python3 repeater.py raw req.txt --host https://app        # replay a captured request
    python3 repeater.py race -u https://app/redeem -X POST --data "code=ONCE" -n 30
    python3 repeater.py diff -u https://app/item?id=1 --header-b "X-Role: admin"
"""

from __future__ import annotations

import argparse
import difflib
import json as jsonlib
import sys
from urllib.parse import urljoin, urlparse

import _httpcore as core


def _print_response(r: core.Result, *, show_body: bool, show_headers: bool, label: str = "") -> None:
    tag = f"[{label}] " if label else ""
    if not r.ok:
        print(f"  {tag}TRANSPORT ERROR: {r.error}")
        return
    print(f"  {tag}status={r.status}  len={r.length}  time={r.elapsed:.3f}s  -> {r.url}")
    if show_headers:
        for k, v in r.headers.items():
            print(f"    {k}: {v}")
    if show_body:
        body = r.text if len(r.text) <= 4000 else r.text[:4000] + f"\n    …(+{len(r.text)-4000} bytes)"
        print("    " + body.replace("\n", "\n    "))


def parse_raw(text: str) -> dict:
    """Parse a raw HTTP request (request-line + headers + optional body)."""
    # normalise line endings, split headers/body on the first blank line
    text = text.replace("\r\n", "\n")
    head, _, body = text.partition("\n\n")
    lines = head.split("\n")
    if not lines or " " not in lines[0]:
        raise SystemExit("raw: first line must be 'METHOD path HTTP/x'")
    method, path, *_ = lines[0].split(" ")
    headers: dict[str, str] = {}
    for ln in lines[1:]:
        if ":" in ln:
            k, _, v = ln.partition(":")
            headers[k.strip()] = v.strip()
    return {"method": method, "path": path, "headers": headers, "body": body or None}


def _client(args) -> core.Client:
    return core.client_from_args(args)


def _kwargs_from_flags(args, *, extra_headers: dict | None = None) -> dict:
    headers = {}
    if extra_headers:
        headers.update(extra_headers)
    data = dict(core.parse_kv(args.data.split("&"), "=")) if getattr(args, "data", None) else None
    jbody = jsonlib.loads(args.json) if getattr(args, "json", None) else None
    return {
        "method": args.method, "url": args.url,
        "data": data, "json": jbody,
        "headers": headers or None,
        "allow_redirects": getattr(args, "follow", False),
    }


def run_send(args) -> None:
    client = _client(args)
    core.require_scheme(args.url)
    r = client.request(**_kwargs_from_flags(args))
    print(f"{args.method} {args.url}")
    _print_response(r, show_body=args.show_body, show_headers=args.show_headers)


def run_raw(args) -> None:
    raw = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8", errors="replace").read()
    parsed = parse_raw(raw)
    client = _client(args)
    # Resolve URL: --host + path from the request line, or Host header.
    host = args.host or (("https://" + parsed["headers"]["Host"]) if "Host" in parsed["headers"] else None)
    if not host:
        raise SystemExit("raw: provide --host https://target (or a Host header in the request)")
    url = urljoin(host.rstrip("/") + "/", parsed["path"].lstrip("/"))
    hdrs = {k: v for k, v in parsed["headers"].items() if k.lower() != "content-length"}
    r = client.request(method=parsed["method"], url=url, data=parsed["body"],
                       headers=hdrs, allow_redirects=args.follow)
    print(f"{parsed['method']} {url}")
    _print_response(r, show_body=args.show_body, show_headers=args.show_headers)


def run_race(args) -> None:
    client = _client(args)
    core.require_scheme(args.url)
    # deliberately no rate limit for a race: set --rate 0/unset and high concurrency
    kwargs = _kwargs_from_flags(args)
    print(f"[race] firing {args.n}x concurrently: {args.method} {args.url}")
    results = core.run_concurrent(lambda _: client.request(**kwargs), range(args.n), concurrency=args.n)
    from collections import Counter
    sigs = Counter((r.status, r.length) for r in results if r.ok)
    errs = sum(1 for r in results if not r.ok)
    for (st, ln), c in sigs.most_common():
        print(f"  status={st} len={ln}  x{c}")
    if errs:
        print(f"  transport errors: {errs}")
    distinct = len(sigs)
    print(f"\n{args.n} sent, {distinct} distinct response shape(s). A rare/odd shape among many"
          "\nidentical ones is the race signal (e.g. 2 successes where the limit is 1) — confirm the"
          "\nstate change actually happened (balance, redemption count), not just the status code.")


def run_diff(args) -> None:
    client = _client(args)
    core.require_scheme(args.url)
    hb = core.parse_kv(args.header_b, ":") if args.header_b else {}
    ha = core.parse_kv(args.header_a, ":") if args.header_a else {}
    ra = client.request(**_kwargs_from_flags(args, extra_headers=ha))
    rb = client.request(**_kwargs_from_flags(args, extra_headers=hb))
    print(f"A vs B: {args.method} {args.url}")
    _print_response(ra, show_body=False, show_headers=False, label="A")
    _print_response(rb, show_body=False, show_headers=False, label="B")
    same = ra.signature() == rb.signature()
    print(f"\nsignatures {'MATCH' if same else 'DIFFER'} (A={ra.signature()} B={rb.signature()})")
    if args.show_body and ra.ok and rb.ok and ra.text != rb.text:
        print("\n--- unified body diff (A -> B), first 60 lines ---")
        d = difflib.unified_diff(ra.text.splitlines(), rb.text.splitlines(),
                                 "A", "B", lineterm="")
        for i, line in enumerate(d):
            if i > 60:
                print("  …(diff truncated)"); break
            print("  " + line)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)

    def add_req_flags(sp, *, with_url=True):
        if with_url:
            sp.add_argument("-u", "--url", required=True)
            sp.add_argument("-X", "--method", default="GET")
            sp.add_argument("--data", help="form body k=v&k=v")
            sp.add_argument("--json", help="JSON body")
        sp.add_argument("--follow", action="store_true", help="follow redirects")
        sp.add_argument("--show-body", action="store_true")
        sp.add_argument("--show-headers", action="store_true")
        core.add_common_args(sp)

    s = sub.add_parser("send", help="fire one request, show response"); add_req_flags(s)
    r = sub.add_parser("raw", help="replay a raw HTTP request (file or - for stdin)")
    r.add_argument("file"); r.add_argument("--host", help="https://target if the request line is a path")
    add_req_flags(r, with_url=False)
    rc = sub.add_parser("race", help="fire the same request N times concurrently"); add_req_flags(rc)
    rc.add_argument("-n", type=int, default=20, help="number of concurrent requests")
    d = sub.add_parser("diff", help="send two variants, diff responses"); add_req_flags(d)
    d.add_argument("--header-a", action="append", default=[], help="header only on variant A (repeatable)")
    d.add_argument("--header-b", action="append", default=[], help="header only on variant B (repeatable)")

    args = p.parse_args()
    {"send": run_send, "raw": run_raw, "race": run_race, "diff": run_diff}[args.mode](args)


if __name__ == "__main__":
    main()
