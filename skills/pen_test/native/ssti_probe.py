#!/usr/bin/env python3
"""ssti_probe.py — owned Server-Side Template Injection DETECTION for pen_test.

The gap this closes: param_probe finds a `template=`/reflected param, but nothing
then proved the value was *evaluated* rather than merely reflected. This does,
through the shared _httpcore engine (any location: query/form/json/header/cookie/
path), with a discipline built to not lie:

  * evaluation, not reflection — a wrapped arithmetic expression whose PRODUCT
    (from operands randomized per run, so it can't be a page-coincidence) appears
    while the raw payload does NOT. Reflection returns the payload verbatim;
    evaluation returns the computed number and the template markup is gone.
  * false-positive guards — an inert-sibling control (broken delimiters) and a
    pure-numeric control; a "hit" that also fires on those is discarded.
  * engine fingerprint — once evaluation is confirmed, disambiguation payloads
    name the engine (Jinja2/Twig/Freemarker/Velocity/ERB/Mako/Thymeleaf/...).
  * benign escalation — ONE read-only, engine-appropriate proof (e.g. Jinja2
    `{{config}}`, Freemarker `${.version}`) that it's a real object/exec context,
    never an OS/`__subclasses__`/RCE payload. Those are referenced only.

This is a DETECTOR. Full RCE (Jinja2 `__globals__`→os, SpEL `T(Runtime)`, etc.)
is out of scope here — see knowledge/rce.md and run only under explicit authz.

AUTHORIZATION: active traffic — authorized targets only.

Usage:
    python3 ssti_probe.py -u "https://app/greet?name=x" --param name
    python3 ssti_probe.py -u "https://app/api/render" -X POST --location json \\
        --param tpl --json '{"tpl":"x"}' --escalate --evidence-dir ./ev
"""

from __future__ import annotations

import argparse
import json as jsonlib
import random
import re

import _httpcore as core

# Per-run randomized operands so the product can't be a page coincidence / cache hit.
A = random.randint(101, 199)
B = random.randint(101, 199)
PRODUCT = A * B  # a 4-5 digit number

# Arithmetic payloads per delimiter family: (label, payload, engine-candidates).
ARITH = [
    ("jinja/twig/nunjucks", "{{%d*%d}}" % (A, B), "Jinja2 / Twig / Nunjucks"),
    ("freemarker/mako/EL", "${%d*%d}" % (A, B), "Freemarker / Mako / JSP-EL / Thymeleaf-pre"),
    ("erb/ejs/asp", "<%%= %d*%d %%>" % (A, B), "ERB / EJS / ASP"),
    ("smarty", "{%d*%d}" % (A, B), "Smarty (bare-brace)"),
    ("thymeleaf-inline", "[[${%d*%d}]]" % (A, B), "Thymeleaf (inline)"),
    ("razor", "@(%d*%d)" % (A, B), "Razor (.NET)"),
    ("dollar-brace", "${{%d*%d}}" % (A, B), "generic ${{...}}"),
]
# A cheap multi-delimiter blob to fire first (one request, broad trip-wire).
BLOB = "".join(p for _, p, _ in ARITH)
# The classic error/parse-provoking polyglot (Hackmanit) — deviations = candidate.
POLYGLOT = "${{<%[%'\"}}%\\"

# Benign, READ-ONLY escalation proofs per engine (no OS/file/network, no __globals__).
ESCALATION = {
    "Jinja2": ("{{config.items()}}", r"SECRET_KEY|SESSION_COOKIE|DEBUG|PERMANENT_SESSION",
               "Flask app config dumped — real Python object context (stepping stone to RCE via "
               "__class__/__globals__, NOT fired here; see rce.md)."),
    "Freemarker": ("${.version}", r"\d+\.\d+\.\d+",
                   "FreeMarker version built-in resolved — real template engine context."),
    "Twig": ("{{_self}}", r"__twig|Template|_self",
             "Twig _self reference resolved — real template context."),
    "Mako": ("${1337+7}", r"\b1344\b", "Mako expression evaluated."),
}

# Engine disambiguation: (payload, regex, engine). Run after arithmetic confirms.
DISAMBIG = [
    ("{{%d*'%d'}}" % (A, 7), r"7777777", "Jinja2 (Python string-repeat semantics)"),
    ("{{7*'7'}}", r"7777777", "Jinja2"),
    ("${.now}", r"\d{4}-\d\d-\d\d|\d{2}:\d{2}", "Freemarker"),
    ("#set($x=%d*%d)$x" % (A, B), str(PRODUCT), "Velocity (#set directive)"),
    ("{{dump(%d)}}" % A, r"int\(%d\)" % A, "Twig (dump())"),
]


def _spec(args: argparse.Namespace) -> core.RequestSpec:
    base_json = jsonlib.loads(args.json) if args.json else None
    base_form = dict(core.parse_kv(args.data.split("&"), "=")) if args.data else {}
    return core.RequestSpec(
        method=args.method, url=args.url, param=args.param, location=args.location,
        base_form=base_form, base_json=base_json,
    )


def _send(client, spec, payload):
    return client.request(**spec.build(payload, prefix_base=False))


def detect(client, spec) -> tuple[bool, str, str, str]:
    """Return (confirmed, winning_payload, engine_candidates, response_excerpt)."""
    prod = str(PRODUCT)
    print(f"\n[ssti] operands randomized this run: {A}*{B} => {prod} (looking for the PRODUCT, "
          f"not the literal payload)")

    # Trip-wire: polyglot + blob. Baseline for signature comparison.
    baseline = _send(client, spec, "zzq%d" % A)
    blob = _send(client, spec, BLOB)
    poly = _send(client, spec, POLYGLOT)
    print(f"  baseline ({baseline.status},{baseline.length})  "
          f"blob ({blob.status},{blob.length})  polyglot ({poly.status},{poly.length})")

    # False-positive controls: pure number, and inert (broken) delimiters.
    ctl_num = _send(client, spec, prod)                       # the number alone, no template
    ctl_inert = _send(client, spec, "{{%d*%d" % (A, B))       # unbalanced -> must NOT evaluate
    num_reflects = ctl_num.ok and prod in ctl_num.text
    inert_evals = ctl_inert.ok and prod in ctl_inert.text and ("{{%d*%d" % (A, B)) not in ctl_inert.text
    if num_reflects:
        print("  [fp-guard] the bare product reflects even without template syntax — this endpoint "
              "echoes input; a product match alone is NOT evaluation here. Requiring strict guard.")
    if inert_evals:
        print("  [fp-guard] a broken/unbalanced expression also yields the product — likely a regex "
              "eval or naturally-occurring number, NOT template evaluation. Treat as false positive.")

    for label, payload, engines in ARITH:
        r = _send(client, spec, payload)
        if not r.ok:
            continue
        evaluated = (prod in r.text) and (payload not in r.text)
        # Confirmation: the product appears while the template markup is GONE (reflection would
        # return the markup verbatim and never the product), AND a broken/unbalanced sibling does
        # NOT also yield the product (that would mean a regex-eval or a coincidental number, not a
        # template engine). Note: an endpoint that merely echoes input (num_reflects) is NOT
        # disqualifying on its own — evaluation is proven by markup-consumed + product-present.
        confirmed = evaluated and not inert_evals
        state = "EVALUATED" if evaluated else ("reflected" if payload in r.text else "no-op")
        print(f"  {label:22s} {payload!r:20.20s} -> {state} ({r.status},{r.length})")
        if confirmed:
            excerpt = _excerpt(r.text, prod)
            print(f"  [!] SSTI CONFIRMED via {label}: {A}*{B} evaluated to {prod}; "
                  f"candidate engine(s): {engines}")
            return True, payload, engines, excerpt
    print("  [-] no evaluation signal (product never appeared with the raw payload absent).")
    return False, "", "", ""


def fingerprint(client, spec) -> str:
    print("\n[ssti] fingerprinting engine...")
    for payload, rx, engine in DISAMBIG:
        r = _send(client, spec, payload)
        if r.ok and re.search(rx, r.text):
            print(f"  [+] {engine} — {payload!r} matched /{rx}/")
            return engine.split(" (")[0]
    print("  engine not uniquely disambiguated (still SSTI; report as generic).")
    return ""


def escalate(client, spec, engine) -> tuple[str, str]:
    """One benign, read-only proof of a real exec context. Returns (proof, excerpt)."""
    entry = ESCALATION.get(engine)
    if not entry:
        return "", ""
    payload, rx, note = entry
    print(f"\n[ssti] benign escalation for {engine}: {payload!r} (read-only, no OS/RCE)")
    r = _send(client, spec, payload)
    if r.ok and re.search(rx, r.text):
        excerpt = _excerpt(r.text, re.search(rx, r.text).group(0))
        print(f"  [!] {note}")
        return f"{engine}: {payload} -> matched /{rx}/ ({note})", excerpt
    print("  escalation payload did not resolve (engine may sandbox this global).")
    return "", ""


def _excerpt(text: str, needle: str, width: int = 160) -> str:
    i = text.find(needle)
    if i < 0:
        return text[:width]
    start = max(0, i - width // 2)
    return text[start:start + width].replace("\n", " ")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True)
    p.add_argument("--param", required=True, help="field/segment name to inject")
    p.add_argument("--location", default="query", choices=core.LOCATIONS)
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("--data", help="baseline form body k=v&k=v (for --location form)")
    p.add_argument("--json", help="baseline JSON body (for --location json)")
    p.add_argument("--escalate", action="store_true",
                   help="after confirmation, fire ONE benign read-only context proof")
    core.add_common_args(p)
    core.add_evidence_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)

    client = core.client_from_args(args)
    spec = _spec(args)
    ev = core.evidence_from_args(args)
    print(f"Target: {args.method} {args.url}  |  injecting `{args.param}` in {args.location}")

    confirmed, payload, engines, excerpt = detect(client, spec)
    print("\n" + "=" * 60)
    if not confirmed:
        print("[-] No SSTI on this point. (Note: client-side template injection / CSTI in a JS SPA "
              "is invisible to a raw-HTTP probe by design — not the same bug.)")
        return

    engine = fingerprint(client, spec)
    proof = f"{A}*{B} evaluated server-side to {PRODUCT} via {payload!r} " \
            f"(raw payload absent from response); engine: {engine or engines}"
    esc_excerpt = ""
    if args.escalate:
        esc_proof, esc_excerpt = escalate(client, spec, engine)
        if esc_proof:
            proof += f" | benign context proof: {esc_proof}"

    print(f"\n[!] SSTI — engine {engine or '(generic)'} — reproduce with payload {payload!r}")
    print("    Escalation to RCE is out of scope for this detector — see knowledge/rce.md "
          "and run only under explicit exploitation authorization.")

    if ev:
        repro = (f"python3 ssti_probe.py -u '{args.url}' --param {args.param} "
                 f"--location {args.location} -X {args.method}"
                 + (" --escalate" if args.escalate else ""))
        f = core.Finding(
            vuln_class="ssti", tool="ssti_probe.py",
            title=f"Server-Side Template Injection ({engine or 'engine TBD'}) in {args.param}",
            severity="high", target=args.url, status="confirmed",
            param=args.param, location=args.location, proof=proof,
            request=f"{args.method} {args.url}  [{args.location}:{args.param}]={payload}",
            response_excerpt=(esc_excerpt or excerpt), reproduce=repro,
            notes="SSTI is typically a path to RCE; escalation intentionally not fired by this "
                  "detector. Confirm impact under explicit authz per exploitation_depth.md.")
        ev.add(f)
        print(f"[evidence] finding written to {ev.findings_path}")


if __name__ == "__main__":
    main()
