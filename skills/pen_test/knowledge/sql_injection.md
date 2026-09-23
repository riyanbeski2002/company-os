---
name: sql-injection
description: Original methodology for detecting and demonstrating SQL injection — boolean-blind, time-blind, error-based, UNION-based.
---

# SQL Injection

Any point where user input reaches a SQL statement without parameterization
is suspect: query params, path segments, headers (esp. `X-Forwarded-For`,
`Referer`), cookies, JSON/XML bodies, and identifiers used in `ORDER BY`/
column names (which can't be parameterized even in "safe" ORMs).

## Run it (native tooling first)

`native/sqli_probe.py` runs all four detection signals through the shared
`_httpcore` engine, so it tests **any** injection location, with a real
authenticated session, not just GET query strings:

```bash
# query param, all signals (default):
python3 native/sqli_probe.py -u "https://app/item?id=1" --param id
# JSON body field, authenticated, through Burp:
python3 native/sqli_probe.py -u "https://app/api/search" -X POST --location json \
    --param filter --json '{"filter":"x"}' -H "Authorization: Bearer $T" --proxy http://127.0.0.1:8080
# header / cookie injection:
python3 native/sqli_probe.py -u "https://app/" --param X-Forwarded-For --location header
```

`--location` accepts `query|form|json|header|cookie|path`. Once the probe
confirms a point, and ONLY then, escalate to the vendored `sqlmap` engine for
extraction depth (see decision tree below) — never open with sqlmap noise.

## Decision tree

1. `http_recon.py` first to map params/tech, then `sqli_probe.py` per candidate point.
2. Probe reports error-based/boolean/time/UNION hit → confirm with a second
   independent run (arithmetic true/false, or `--delay` doubled for time-based).
3. Confirmed + engagement needs data → `engines/sqlmap/sqlmap.py -u ... --batch
   --level=2 --risk=1`, escalating `--level/--risk` only as needed; add
   `--dbms`, `--technique`, and tamper scripts once the class is known.
4. Blocked by a WAF → see evasion section; confirm it's a filter, not a
   non-injectable param, before spending time on evasion.
5. OS-level access (`--os-shell`) ONLY if authorization explicitly covers it.

## Detection techniques

**Error-based.** Inject a syntax-breaking character (`'`, `"`, `)`, backslash)
and compare the response to a baseline. A stack trace, a changed HTTP status,
or a generic "internal error" that only appears with the broken syntax is a
signal. Different DBMS engines leak different tells (MySQL: `You have an
error in your SQL syntax`; Postgres: `unterminated quoted string`; MSSQL:
`Unclosed quotation mark`) — the exact error string can fingerprint the
backend.

**Boolean-blind.** Send two payloads that evaluate to `TRUE` and `FALSE`
respectively against the same injection point (e.g. `' OR '1'='1` vs.
`' OR '1'='2`) and diff the responses (length, status, specific content).
A page that renders differently between the two — even with no visible
error — confirms injection without needing the DB to leak anything.

**Time-blind.** When the response is identical regardless of true/false
(no content difference to diff), use a conditional sleep
(`' OR (SELECT CASE WHEN (1=1) THEN pg_sleep(5) ELSE pg_sleep(0) END)--`,
or MySQL's `SLEEP(5)`) and measure response latency. Establish a clean
baseline latency first — network jitter produces false positives on a
single sample; take several timing samples before concluding.

**UNION-based.** Once you know the column count (via `ORDER BY N` bisection
until it errors, or `UNION SELECT NULL,NULL,...` until it stops erroring),
`UNION SELECT` known-shape data (a marker string in each column) to confirm
which columns render in the response, then substitute real queries
(`table_name`, `column_name` from the DB's own information_schema/catalog)
into the rendering column(s).

**Stacked queries.** Some drivers/DBs allow `; <second statement>` in one
call — check for this before assuming a target is read-only-exploitable.

## Extraction, once confirmed

Prefer boolean/time-blind bisection over error-leaking for extraction when
no data renders directly: extract one character at a time via
`SUBSTRING(value,N,1) = 'X'` (or DB-specific equivalents), binary-search the
character set instead of linear-scanning it (log2(96) ≈ 7 requests per
character instead of up to 96).

## WAF/filter evasion, when a straightforward payload is blocked

- Case variation (`SeLeCt`), inline comments (`/**/`), whitespace
  alternatives (`%0a`, `%09`) in place of spaces
- Encoding: URL-double-encoding, Unicode normalization tricks
- Alternate syntax for the same semantics (`OR 1=1` vs `OR 'a'='a'` vs
  numeric comparison operators)
- Never assume evasion first — try it only after confirming the block is
  actually filter-based (vs. the parameter simply not being injectable)

## Validation bar

A confirmed finding has an actual extracted value (a DB version string, a
real table/column name, or a real row of data), or a timing differential
reproduced across multiple samples with a clean baseline — not "the error
message changed once."
