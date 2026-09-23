#!/usr/bin/env python3
"""idor_probe.py — owned IDOR/BOLA differential tester for pen_test.

The previous version varied IDs on a single token — which proves enumeration,
not an authorization bypass. This implements the real cross-account diff the
methodology (knowledge/idor_and_authz.md) actually requires: two distinct
identities, and a verdict that only fires when identity A can read/modify an
object that genuinely belongs to identity B.

Two modes:

  diff  (default, strongest) — needs two accounts. Establishes ground truth
        (B fetching B's own object), then tests the attack (A fetching B's
        object). A finding = A gets B's real data, not an error/redirect/empty.

  enum  (single account) — walk a range/list of IDs as one identity and flag
        substantive 200s. Weaker: proves reachability, still needs a human to
        confirm the returned objects aren't the caller's own.

Handles the id in the URL path ({id}), query, JSON body, form, or header, and
tests read and write directions separately (they are different findings).

AUTHORIZATION: uses live credentials against a live target — authorized only.

Usage:
    # two-account diff (A must NOT be allowed to see B's object #501):
    python3 idor_probe.py diff --url "https://api/orders/{id}" \\
        --a-header "Authorization: Bearer <A>" --a-id 500 \\
        --b-header "Authorization: Bearer <B>" --b-id 501

    # single-account enumeration:
    python3 idor_probe.py enum --url "https://api/orders/{id}" \\
        -H "Authorization: Bearer <A>" --ids 1-50
"""

from __future__ import annotations

import argparse
import json as jsonlib

import _httpcore as core


def _build_spec(url: str, method: str, location: str, param: str, body: str | None) -> core.RequestSpec:
    base_json = jsonlib.loads(body) if (body and location == "json") else None
    base_form = dict(core.parse_kv(body.split("&"), "=")) if (body and location == "form") else {}
    return core.RequestSpec(method=method, url=url, param=param, location=location,
                            base_json=base_json, base_form=base_form)


def _client(headers: list[str], cookies: list[str], bearer: str | None, args) -> core.Client:
    c = core.Client(timeout=args.timeout, verify_tls=not args.insecure,
                    proxy=args.proxy, retries=args.retries, rate=args.rate)
    if headers:
        c.add_headers(core.parse_kv(headers, ":"))
    if cookies:
        c.add_cookies(core.parse_kv(cookies, "="))
    if bearer:
        c.bearer(bearer)
    return c


def _similar(a: core.Result, b: core.Result) -> bool:
    """Rough 'same object body' heuristic: both 200 and lengths within 15%."""
    if not (a.ok and b.ok) or a.status != 200 or b.status != 200:
        return False
    if a.length == 0 or b.length == 0:
        return False
    ratio = min(a.length, b.length) / max(a.length, b.length)
    return ratio >= 0.85


def parse_ids(spec: str) -> list[str]:
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part and part.replace("-", "").isdigit():
            lo, hi = part.split("-")
            out.extend(str(i) for i in range(int(lo), int(hi) + 1))
        elif part:
            out.append(part)
    return out


def run_diff(args) -> None:
    spec = _build_spec(args.url, args.method, args.location, args.param, args.body)
    ca = _client(args.a_header, args.a_cookie, args.a_bearer, args)
    cb = _client(args.b_header, args.b_cookie, args.b_bearer, args)

    a_own = ca.request(**spec.build(args.a_id))            # A's own object (authorized 200 shape)
    b_own = cb.request(**spec.build(args.b_id))            # ground truth: B's real object
    attack = ca.request(**spec.build(args.b_id))           # A reaching for B's object

    print(f"Object template: {args.method} {args.url}  (id in {args.location})")
    print(f"  A -> A#{args.a_id} (baseline) : status={a_own.status} len={a_own.length}")
    print(f"  B -> B#{args.b_id} (truth)    : status={b_own.status} len={b_own.length}")
    print(f"  A -> B#{args.b_id} (ATTACK)   : status={attack.status} len={attack.length}")

    # Guard against the "everyone gets the same page" false positive: if A's
    # own object and B's own object are indistinguishable, the endpoint returns
    # a shared shell / empty / access-denied page for everyone, so an A->B
    # "match" proves nothing. Objects MUST differ before a match means anything.
    objects_distinguishable = not _similar(a_own, b_own)

    verdict = "NOT VULNERABLE"
    if not objects_distinguishable:
        verdict = ("[-] INCONCLUSIVE — A's and B's own objects look identical "
                   "(shared/empty/denied page for everyone). Pick ids that return "
                   "distinct content, or this endpoint reveals nothing cross-account.")
    elif _similar(attack, b_own):
        verdict = "[!] IDOR CONFIRMED — A received B's object (matches B's own distinct response)"
    elif attack.ok and attack.status == 200 and attack.length > 0 and not _similar(attack, a_own):
        verdict = "[?] POSSIBLE IDOR — A got a 200 body for B's id; confirm it is B's data, not a shared/empty page"
    print(f"\n{verdict}")
    is_write = args.method.upper() in ("POST", "PUT", "PATCH", "DELETE")
    print(f"  Direction tested: {'WRITE' if is_write else 'READ'} "
          f"({args.method}). Read-IDOR and write-IDOR are separate findings — test both.")
    if verdict.startswith("[!]") or verdict.startswith("[?]"):
        print(f"  PoC: repeat `{args.method} {args.url.replace('{id}', args.b_id)}` with A's credentials.")


def run_enum(args) -> None:
    spec = _build_spec(args.url, args.method, args.location, args.param, args.body)
    c = _client(args.header, args.cookie, args.bearer, args)
    ids = parse_ids(args.ids)
    print(f"Enumerating {len(ids)} ids as one identity: {args.method} {args.url}")

    def fetch(i: str) -> tuple[str, core.Result]:
        return i, c.request(**spec.build(i))

    results = core.run_concurrent(fetch, ids, concurrency=args.concurrency)
    hits = [(i, r) for i, r in results if r.ok and r.status == 200 and r.length > 0]
    for i, r in results:
        flag = "REACHABLE" if (r.ok and r.status == 200 and r.length > 0) else ""
        print(f"  id={i:<8} status={r.status:>3} len={r.length:>7} {flag}")
    print(f"\n{len(hits)} reachable object(s). enum proves reachability only — a real IDOR")
    print("verdict needs the two-account `diff` mode to confirm these belong to other users.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)

    common_req = dict()

    d = sub.add_parser("diff", help="two-account cross-object differential")
    d.add_argument("--url", required=True, help="object URL; put {id} where the id goes")
    d.add_argument("-X", "--method", default="GET")
    d.add_argument("--location", default="path", choices=core.LOCATIONS)
    d.add_argument("--param", default="id", help="field name if id is in query/json/form/header")
    d.add_argument("--body", help="baseline body for write tests (k=v&.. or JSON)")
    d.add_argument("--a-id", required=True); d.add_argument("--b-id", required=True)
    d.add_argument("--a-header", action="append", default=[]); d.add_argument("--a-cookie", action="append", default=[])
    d.add_argument("--a-bearer")
    d.add_argument("--b-header", action="append", default=[]); d.add_argument("--b-cookie", action="append", default=[])
    d.add_argument("--b-bearer")
    core.add_common_args(d)

    e = sub.add_parser("enum", help="single-account id enumeration")
    e.add_argument("--url", required=True, help="object URL with {id}")
    e.add_argument("-X", "--method", default="GET")
    e.add_argument("--location", default="path", choices=core.LOCATIONS)
    e.add_argument("--param", default="id")
    e.add_argument("--body")
    e.add_argument("--ids", required=True, help="comma list and/or n-m ranges, e.g. 1-50,100,101")
    core.add_common_args(e)

    args = p.parse_args()
    core.require_scheme(args.url)
    if args.mode == "diff":
        run_diff(args)
    else:
        run_enum(args)


if __name__ == "__main__":
    main()
