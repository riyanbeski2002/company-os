#!/usr/bin/env python3
"""mock_target.py — a deliberately, BENIGNLY vulnerable HTTP server for tests.

Simulates just enough of each vulnerability class for the native probes to trip
their *confirmed* path against a known-good oracle — no real interpreter, no real
filesystem, no real shell. Used only by tests/test_probes.py. Never deploy this.

Endpoints:
  GET  /ssti?name=       — evaluates {{a*b}} / ${a*b} / <%= a*b %> (fake Jinja-ish)
  GET  /cmd?host=        — honors `sleep N`, reconstructs split echo markers, `id`
  GET  /dl?file=         — returns fake /etc/passwd on traversal; php://filter b64
  POST /xml              — resolves file:///etc/passwd SYSTEM entity + inert canary
  POST /upload           — accepts dangerous files; GET /u/<name> "executes" .php
  GET  /safe             — inert control endpoint (reflects nothing dangerous)
"""

from __future__ import annotations

import base64
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

FAKE_PASSWD = "root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
FAKE_SOURCE = "<?php $secret='hunter2'; echo 'app'; ?>"
_UPLOADS: dict[str, tuple[str, bytes]] = {}

# Require a proper closing delimiter, so an unbalanced/broken sibling does NOT "evaluate"
# (a real template engine errors on `{{a*b` with no closer). Groups come in pairs per family.
ARITH_RE = re.compile(
    r"\{\{\s*(\d+)\s*\*\s*(\d+)\s*\}\}"       # {{a*b}}
    r"|\$\{\s*(\d+)\s*\*\s*(\d+)\s*\}"        # ${a*b}
    r"|<%=\s*(\d+)\s*\*\s*(\d+)\s*%>")        # <%= a*b %>
STRMUL_RE = re.compile(r"\{\{\s*(\d+)\s*\*\s*'(\d+)'\s*\}\}")  # Jinja2 {{7*'7'}} string-repeat
SLEEP_RE = re.compile(r"sleep\s+(\d+)")
PING_N_RE = re.compile(r"ping\s+-n\s+(\d+)")
# split-echo: echo MK_$(echo AB)$(echo CD)_END  OR  echo MK_TOK_$((4+4))END
ECHO_SPLIT_RE = re.compile(r"echo\s+MK_\$\(echo\s+(\w+)\)\$\(echo\s+(\w+)\)_END")
ECHO_ARITH_RE = re.compile(r"echo\s+MK_(\w+)_\$\(\(4\+4\)\)END")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code=200, body=b"", ctype="text/html", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if isinstance(body, str):
            body = body.encode()
        self.wfile.write(body)

    # -- SSTI ------------------------------------------------------------
    def _ssti(self, qs):
        val = (qs.get("name", [""])[0])
        if "config.items()" in val:
            return self._send(body="dict_items([('SECRET_KEY', 'xxx'), ('DEBUG', True)])")
        sm = STRMUL_RE.search(val)
        if sm:  # Jinja2 string-repeat semantics: 7*'7' -> '7777777'
            return self._send(body="Hello " + sm.group(2) * int(sm.group(1)))
        m = ARITH_RE.search(val)
        if m:  # "evaluate" the arithmetic, drop the template markup (like a real engine)
            nums = [g for g in m.groups() if g is not None]
            return self._send(body=f"Hello {int(nums[0]) * int(nums[1])}")
        return self._send(body=f"Hello {val}")  # reflect otherwise

    # -- command injection ----------------------------------------------
    def _cmd(self, qs):
        val = qs.get("host", [""])[0]
        s = SLEEP_RE.search(val)
        if s:
            time.sleep(min(int(s.group(1)), 30))
        pn = PING_N_RE.search(val)
        if pn:
            time.sleep(min(int(pn.group(1)) - 1, 30))
        out = "PING 127.0.0.1: alive"
        m = ECHO_SPLIT_RE.search(val)
        if m:
            out += f" MK_{m.group(1)}{m.group(2)}_END"
        m2 = ECHO_ARITH_RE.search(val)
        if m2:
            out += f" MK_{m2.group(1)}_8END"
        if re.search(r"(^|[;&|`])\s*id\s*($|[;&|])", val) or ";id;" in val:
            out += " uid=33(www-data) gid=33(www-data) groups=33(www-data)"
        return self._send(body=out)

    # -- traversal / LFI -------------------------------------------------
    def _dl(self, qs):
        val = qs.get("file", [""])[0]
        if val.startswith("php://filter") and "etc/passwd" in val:
            return self._send(body=base64.b64encode(FAKE_PASSWD.encode()).decode())
        if val.startswith("php://filter"):
            return self._send(body=base64.b64encode(FAKE_SOURCE.encode()).decode())
        # normalize a plain ../ ladder; only serve passwd when it truly escapes to it
        norm = re.sub(r"(\.\./)+", "", val).lstrip("/")
        if norm in ("etc/passwd",) and "../" in val:
            return self._send(body=FAKE_PASSWD)
        return self._send(code=404, body="not found")

    # -- XXE -------------------------------------------------------------
    def _xml(self, body: str):
        if 'SYSTEM "file:///etc/passwd"' in body or "SYSTEM 'file:///etc/passwd'" in body:
            return self._send(body=f"<r>{FAKE_PASSWD}</r>", ctype="application/xml")
        if 'href="file:///etc/passwd"' in body:  # XInclude
            return self._send(body=f"<r>{FAKE_PASSWD}</r>", ctype="application/xml")
        m = re.search(r'<!ENTITY x "([^"]+)"', body)  # inert canary
        if m:
            return self._send(body=f"<r>{m.group(1)}</r>", ctype="application/xml")
        return self._send(body="<r>ok</r>", ctype="application/xml")

    # -- upload ----------------------------------------------------------
    def _upload(self, body: bytes):
        # crude multipart parse: find filename and the following payload bytes
        m = re.search(rb'filename="([^"]+)"', body)
        if not m:
            return self._send(code=400, body="no file")
        name = m.group(1).decode()
        if name.lower().endswith(".exe"):
            return self._send(code=400, body="invalid file type")
        # payload = bytes after the blank line following this part's headers
        part = body[m.end():]
        payload = part.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in part else b""
        payload = payload.rsplit(b"\r\n--", 1)[0]
        stored = name.replace("%00", "").split("/")[-1]
        _UPLOADS[stored] = (name, payload)
        return self._send(body=f'{{"ok":true,"url":"/u/{stored}"}}', ctype="application/json")

    def _serve_upload(self, name):
        if name not in _UPLOADS:
            return self._send(code=404, body="nope")
        orig, payload = _UPLOADS[name]
        low = name.lower()
        if low.endswith((".php", ".php5", ".phtml", ".pht", ".gif")) or ".php" in low:
            # "execute": echo the computed marker instead of the source
            m = re.search(rb'PROBE_MARKER_"\.\(41\+8\)\."_(\w+)', payload) or \
                re.search(rb'PROBE_MARKER_\.\(41\+8\)\._(\w+)', payload)
            tok = m.group(1).decode() if m else "TOK"
            return self._send(body=f"PROBE_MARKER_49_{tok}")
        if low.endswith(".svg"):
            return self._send(body=payload, ctype="image/svg+xml")
        if low.endswith((".html", ".htm")):
            return self._send(body=payload, ctype="text/html")
        return self._send(body=payload, ctype="application/octet-stream")

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query, keep_blank_values=True)
        if u.path == "/ssti":
            return self._ssti(qs)
        if u.path == "/cmd":
            return self._cmd(qs)
        if u.path == "/dl":
            return self._dl(qs)
        if u.path.startswith("/u/"):
            return self._serve_upload(u.path[3:])
        if u.path == "/safe":
            return self._send(body="static page, nothing to see")
        return self._send(code=404, body="not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        u = urlparse(self.path)
        if u.path == "/xml":
            return self._xml(raw.decode("utf-8", "replace"))
        if u.path == "/upload":
            return self._upload(raw)
        # also allow POSTed cmd/ssti forms
        if u.path == "/cmd":
            return self._cmd(parse_qs(raw.decode("utf-8", "replace")))
        return self._send(code=404, body="not found")


def serve(port=0):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return httpd


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    srv = serve(port)
    print(f"mock target on http://127.0.0.1:{srv.server_address[1]}")
    srv.serve_forever()
