#!/usr/bin/env python3
"""graphql_probe.py — owned GraphQL recon/abuse detector for pen_test.

GraphQL endpoints have their own class of exposure the generic probes miss:

  * introspection left on   — dumps the entire schema (every query, mutation,
    type, field) = a complete map of the attack surface, often incl. admin-only
    mutations reachable by anyone who can craft the query
  * field suggestions       — even with introspection OFF, a typo'd field name
    often returns "Did you mean X?", leaking the schema piecemeal
  * mutation exposure       — dangerous mutations (deleteUser, setRole,
    createAdmin) reachable without the UI ever showing them = BFLA
  * batching / alias abuse  — many operations in one request bypass per-request
    rate limits (credential stuffing, OTP brute force via aliased mutations)

This maps the surface and flags the risks. Actually exploiting a specific
mutation is a follow-up with idor_probe / manual requests once the schema is known.

AUTHORIZATION: sends live queries. Authorized targets only.

Usage:
    python3 graphql_probe.py https://app/graphql
    python3 graphql_probe.py https://api/graphql -H "Authorization: Bearer <t>"
"""

from __future__ import annotations

import argparse

import _httpcore as core

INTROSPECTION = {
    "query": "query{__schema{queryType{name}mutationType{name}"
             "types{name kind fields{name args{name}}}}}"
}
MINIMAL_PROBE = {"query": "{__typename}"}
SUGGESTION_PROBE = {"query": "{__schema{quryType{name}}}"}  # deliberate typo
DANGEROUS = ("delete", "remove", "drop", "setrole", "makeadmin", "createadmin",
             "grant", "impersonate", "resetpassword", "updaterole", "setpassword")


def post_gql(client: core.Client, url: str, payload: dict) -> core.Result:
    return client.request("POST", url, json=payload,
                          headers={"Content-Type": "application/json"})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    core.add_common_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)
    client = core.client_from_args(args)

    print(f"Target: {args.url}")
    alive = post_gql(client, args.url, MINIMAL_PROBE)
    if not alive.ok:
        raise SystemExit(f"request failed: {alive.error}")
    if "__typename" not in alive.text and alive.status >= 400:
        print(f"  [-] Does not look like a live GraphQL endpoint (status={alive.status}).")
        print("      Try common paths: /graphql, /api/graphql, /v1/graphql, /query, /gql")
        return
    print(f"  live GraphQL endpoint (status={alive.status})")

    findings = []
    intro = post_gql(client, args.url, INTROSPECTION)
    if intro.ok and "__schema" in intro.text and "queryType" in intro.text:
        print("\n[!] INTROSPECTION ENABLED — full schema is dumpable (high; medium if API is public-by-design).")
        findings.append(("high", "introspection enabled — full schema exposed"))
        # cheap surface summary without a full JSON parse
        import json as jsonlib
        try:
            data = jsonlib.loads(intro.text)["data"]["__schema"]
            types = data.get("types", [])
            mutation_type = (data.get("mutationType") or {}).get("name")
            mutations = []
            for t in types:
                if t.get("name") == mutation_type:
                    mutations = [f["name"] for f in (t.get("fields") or [])]
            print(f"    types: {len([t for t in types if not str(t.get('name','')).startswith('__')])}"
                  f"  mutations: {len(mutations)}")
            dangerous = [m for m in mutations if any(d in m.lower() for d in DANGEROUS)]
            if dangerous:
                print(f"    [!] dangerous mutations present: {', '.join(dangerous)}")
                findings.append(("high", f"dangerous mutations reachable: {', '.join(dangerous)} — test authz (BFLA)"))
        except Exception as e:
            print(f"    (schema present but summary parse skipped: {e})")
    else:
        print("\n[introspection] disabled or restricted — trying field-suggestion leak...")
        sug = post_gql(client, args.url, SUGGESTION_PROBE)
        if sug.ok and "Did you mean" in sug.text:
            print("  [!] field SUGGESTIONS enabled — schema recoverable field-by-field despite introspection off.")
            findings.append(("medium", "field suggestions leak schema (introspection off but 'Did you mean' on)"))
        else:
            print("  no field-suggestion leak observed.")

    # batching support (alias/array) — rate-limit bypass primitive
    batch = client.request("POST", args.url, json=[MINIMAL_PROBE, MINIMAL_PROBE],
                           headers={"Content-Type": "application/json"})
    if batch.ok and batch.text.count("__typename") >= 2:
        print("\n[!] array BATCHING accepted — many ops per request can bypass per-request rate limits.")
        findings.append(("medium", "query batching enabled — OTP/credential brute-force amplification"))

    print("\n" + "=" * 60)
    order = {"high": 0, "medium": 1, "low": 2}
    for sev, msg in sorted(findings, key=lambda f: order.get(f[0], 9)):
        print(f"  [{sev}] {msg}")
    if not findings:
        print("  No GraphQL-specific misconfig found; still test authz on individual queries/mutations.")


if __name__ == "__main__":
    main()
