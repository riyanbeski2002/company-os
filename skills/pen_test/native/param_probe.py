#!/usr/bin/env python3
"""param_probe.py — original, owned hidden-parameter discovery for pen_test.

Arjun-style: finds request parameters the server honors but the UI/docs don't
advertise (debug flags, `admin=`, `redirect=`, mass-assignment fields), by
sending a unique marker in each candidate and detecting either reflection or a
response change beyond the page's own baseline noise. Discovered params are the
raw material for the other probes (feed a reflected one to xss_probe, an id-like
one to idor_probe, a url-like one to ssrf_probe/redirect_probe).

Runs through the shared _httpcore engine: --location query|form|json, real
authenticated session, proxy, concurrency, and rate limiting.

AUTHORIZATION: authorized targets only — see agents/pen_test.md.

    python3 param_probe.py -u "https://app/search" --location query
    python3 param_probe.py -u "https://app/api/user" -X POST --location json --wordlist params.txt
"""

from __future__ import annotations

import argparse
import random
import string

import _httpcore as core

# Compact, high-signal default list. Pass --wordlist for a real run.
DEFAULT_PARAMS = [
    "id", "user", "user_id", "userid", "account", "account_id", "uid", "email",
    "admin", "is_admin", "isAdmin", "role", "debug", "test", "dev", "internal",
    "redirect", "redirect_uri", "next", "url", "return", "return_url", "callback",
    "file", "path", "dir", "page", "template", "lang", "locale", "format",
    "q", "query", "search", "filter", "sort", "order", "limit", "offset", "count",
    "token", "api_key", "apikey", "key", "secret", "password", "pass",
    "price", "amount", "quantity", "qty", "discount", "coupon", "status", "state",
    "enable", "enabled", "active", "verified", "override", "force", "preview",
    "include", "fields", "expand", "with", "embed", "raw", "json", "xml",
]


def _rand_marker() -> str:
    return "pntst" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def _spec(url, method, location, param, base_form, base_json) -> core.RequestSpec:
    return core.RequestSpec(method=method, url=url, param=param, location=location,
                            base_form=base_form, base_json=base_json)


def run(args) -> None:
    client = core.client_from_args(args)
    core.require_scheme(args.url)
    base_form = core.parse_kv(args.data.split("&"), "=") if args.data else {}
    import json as _json
    base_json = _json.loads(args.json) if args.json else ({} if args.location == "json" else None)

    # Baseline noise: two clean requests. If their lengths differ, the page is
    # dynamic, so we widen the length band and lean on reflection.
    b1 = client.request(method=args.method, url=args.url,
                        data=base_form or None, json=base_json)
    b2 = client.request(method=args.method, url=args.url,
                        data=base_form or None, json=base_json)
    if not b1.ok:
        print(f"[abort] baseline request failed: {b1.error}")
        return
    base_status = b1.status
    noise = abs(b1.length - b2.length)
    band = max(noise * 3, 48)  # length-change threshold to call a difference real
    print(f"Param discovery: {args.method} {args.url}  location={args.location}")
    print(f"Baseline: status={base_status} len={b1.length} (noise={noise}B, change-threshold={band}B)")

    words = DEFAULT_PARAMS
    if args.wordlist:
        with open(args.wordlist, encoding="utf-8", errors="ignore") as f:
            words = [w.strip() for w in f if w.strip() and not w.startswith("#")]
    words = list(dict.fromkeys(words))  # dedupe, keep order
    print(f"Testing {len(words)} candidate params...\n")

    def test(name: str):
        marker = _rand_marker()
        spec = _spec(args.url, args.method, args.location, name, dict(base_form), dict(base_json) if base_json is not None else None)
        r = client.request(**spec.build(marker))
        if not r.ok:
            return (name, None, "err", r.error)
        reflected = marker in r.text
        status_changed = r.status != base_status
        len_changed = abs(r.length - b1.length) > band
        if reflected:
            return (name, r, "REFLECTED", f"marker echoed in response (status={r.status})")
        if status_changed:
            return (name, r, "STATUS", f"status {base_status}->{r.status}")
        if len_changed:
            return (name, r, "LENGTH", f"len {b1.length}->{r.length} (>{band}B)")
        return (name, r, None, "")

    results = core.run_concurrent(test, words, concurrency=args.concurrency)
    hits = [row for row in results if row[2] and row[2] != "err"]

    for name, r, kind, why in hits:
        print(f"  [{kind:9s}] {name:14s} {why}")

    print("\n" + "=" * 72)
    if hits:
        refl = [h[0] for h in hits if h[2] == "REFLECTED"]
        print(f"[!] {len(hits)} candidate param(s) the server reacts to.")
        if refl:
            print(f"    Reflected (feed to xss_probe / sqli_probe): {', '.join(refl)}")
        print("    A reaction is a lead, not a bug — confirm each param actually influences behavior")
        print("    (re-send with a second distinct value; rule out params that merely echo any input),")
        print("    then route it to the matching probe. Mass-assignment angle: knowledge/api_and_protocols.md.")
    else:
        print("[-] No candidate parameter changed the response beyond baseline noise.")
        print("    Try a larger --wordlist, or a different --location (query vs form vs json).")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True)
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("--location", default="query", choices=["query", "form", "json"])
    p.add_argument("--data", help="baseline form body k=v&k=v")
    p.add_argument("--json", help="baseline JSON body")
    p.add_argument("--wordlist", help="param-name wordlist (one per line); defaults to a built-in list")
    core.add_common_args(p)
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
