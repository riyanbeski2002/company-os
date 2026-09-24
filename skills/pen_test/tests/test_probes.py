#!/usr/bin/env python3
"""test_probes.py — end-to-end tests for the native probes + evidence layer.

Starts the benignly-vulnerable mock_target in-process, runs each probe's real
CLI against it via subprocess with --evidence-dir, and asserts (1) the probe
reports a confirmed hit and (2) it writes a reportable, proof-bearing Finding.
Finally runs report.py and asserts the deliverable is produced with the findings
counted (and that a proof-less candidate is quarantined, not counted).

No pytest dependency — run directly:
    python3 tests/test_probes.py
Exit code 0 = all passed.
"""

from __future__ import annotations

import datetime
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
NATIVE = os.path.join(os.path.dirname(HERE), "native")
sys.path.insert(0, HERE)
sys.path.insert(0, NATIVE)
import mock_target  # noqa: E402


def start_selfsigned_tls_server():
    """A TLS server with an expired, self-signed, host-mismatched 2048-bit cert."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test.local")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime(2020, 1, 1))
            .not_valid_after(datetime.datetime(2021, 1, 1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("other.example")]), False)
            .sign(key, hashes.SHA256()))
    d = tempfile.mkdtemp()
    kp, cp = os.path.join(d, "k.pem"), os.path.join(d, "c.pem")
    open(kp, "wb").write(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    open(cp, "wb").write(cert.public_bytes(serialization.Encoding.PEM))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cp, kp)
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(5)
    port = srv.getsockname()[1]

    def serve():
        while True:
            try:
                c, _ = srv.accept()
                try:
                    ss = ctx.wrap_socket(c, server_side=True); ss.recv(200); ss.close()
                except Exception:
                    try: c.close()
                    except Exception: pass
            except OSError:
                break
    threading.Thread(target=serve, daemon=True).start()
    return srv, port


def start_redis_mock():
    """A fake unauthenticated Redis answering PING/INFO/CONFIG."""
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(5)
    port = srv.getsockname()[1]

    def handle(c):
        try:
            while True:
                d = c.recv(200)
                if not d:
                    break
                if d.startswith(b"PING"):
                    c.sendall(b"+PONG\r\n")
                elif d.startswith(b"INFO"):
                    c.sendall(b"$30\r\n# Server\r\nredis_version:7.2.1\r\n\r\n")
                elif d.startswith(b"CONFIG"):
                    c.sendall(b"*2\r\n$3\r\ndir\r\n$4\r\n/tmp\r\n")
                else:
                    c.sendall(b"-ERR\r\n")
        except OSError:
            pass

    def serve():
        while True:
            try:
                c, _ = srv.accept()
                threading.Thread(target=handle, args=(c,), daemon=True).start()
            except OSError:
                break
    threading.Thread(target=serve, daemon=True).start()
    return srv, port

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def run_probe(script, *args):
    cmd = [sys.executable, os.path.join(NATIVE, script), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return p.stdout + p.stderr


def load_findings(ev_dir):
    path = os.path.join(ev_dir, "findings.jsonl")
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def reportable(findings, vuln_class):
    return [f for f in findings if f["vuln_class"] == vuln_class and f.get("proof")]


def main():
    srv = mock_target.serve(0)
    port = srv.server_address[1]
    base = f"http://127.0.0.1:{port}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"mock target up on {base}\n")

    ev = tempfile.mkdtemp(prefix="pentest-ev-")

    # 1) SSTI
    print("[test] ssti_probe")
    out = run_probe("ssti_probe.py", "-u", f"{base}/ssti?name=x", "--param", "name",
                    "--escalate", "--evidence-dir", ev)
    check("ssti confirmed", "SSTI CONFIRMED" in out or "SSTI —" in out, out[-300:])
    check("ssti evidence", len(reportable(load_findings(ev), "ssti")) == 1)

    # 2) command injection (fast delays)
    print("[test] cmdi_probe")
    out = run_probe("cmdi_probe.py", "-u", f"{base}/cmd?host=127.0.0.1", "--param", "host",
                    "--t1", "1", "--t2", "2", "--escalate", "--evidence-dir", ev)
    check("cmdi confirmed", "command injection via" in out, out[-300:])
    check("cmdi echo-eval or time", ("echo-eval" in out or "time-based" in out))
    check("cmdi evidence", len(reportable(load_findings(ev), "cmdi")) == 1)

    # 3) traversal
    print("[test] traversal_probe")
    out = run_probe("traversal_probe.py", "-u", f"{base}/dl?file=a.txt", "--param", "file",
                    "--evidence-dir", ev)
    check("traversal confirmed", "FILE READ CONFIRMED" in out or "Path traversal" in out, out[-300:])
    check("traversal evidence", len(reportable(load_findings(ev), "path-traversal")) == 1)

    # 4) XXE
    print("[test] xxe_probe")
    out = run_probe("xxe_probe.py", "-u", f"{base}/xml", "-X", "POST", "--evidence-dir", ev)
    check("xxe confirmed", "XXE CONFIRMED" in out, out[-300:])
    check("xxe evidence", len(reportable(load_findings(ev), "xxe")) == 1)

    # 5) upload
    print("[test] upload_probe")
    out = run_probe("upload_probe.py", "-u", f"{base}/upload", "--field", "file",
                    "--evidence-dir", ev)
    check("upload confirmed exec/xss", ("EXECUTED" in out or "STORED-XSS" in out), out[-400:])
    check("upload evidence", len(reportable(load_findings(ev), "file-upload")) >= 1)

    # 6) TLS probe (network/infra VA)
    print("[test] tls_probe")
    tls_srv, tls_port = start_selfsigned_tls_server()
    out = run_probe("tls_probe.py", "127.0.0.1", "--port", str(tls_port),
                    "--timeout", "4", "--evidence-dir", ev)
    check("tls expired cert", "Expired TLS certificate" in out, out[-300:])
    check("tls self-signed", "self-signed" in out.lower())
    check("tls evidence", len(reportable(load_findings(ev), "tls")) >= 1)
    tls_srv.close()

    # 7) service probe (unauth Redis) — drive the real CLI with the mock mapped in
    print("[test] service_probe")
    import service_probe as sp
    redis_srv, redis_port = start_redis_mock()
    sp.PROBES[redis_port] = sp.probe_redis          # map the ephemeral port to the redis probe
    argv = sys.argv
    sys.argv = ["service_probe.py", "127.0.0.1", "--ports", str(redis_port),
                "--timeout", "3", "--evidence-dir", ev]
    try:
        sp.main()
    except SystemExit:
        pass
    finally:
        sys.argv = argv
    svc = [f for f in load_findings(ev) if f["vuln_class"] == "exposed-service" and f.get("proof")]
    check("service unauth-redis finding", any("Redis" in f["title"] for f in svc), str([f["title"] for f in svc]))
    check("service finding critical", any(f["severity"] == "critical" for f in svc))
    redis_srv.close()

    # 8) report.py aggregation + quarantine of proof-less candidates
    print("[test] report.py deliverable")
    # inject a proof-less candidate to verify quarantine
    with open(os.path.join(ev, "findings.jsonl"), "a") as fh:
        fh.write(json.dumps({"vuln_class": "sqli", "title": "no-proof candidate",
                             "severity": "high", "target": base, "status": "candidate",
                             "proof": ""}) + "\n")
    out = run_probe("report.py", ev)
    md = open(os.path.join(ev, "report.md")).read()
    rj = json.load(open(os.path.join(ev, "report.json")))
    check("report.md written", os.path.exists(os.path.join(ev, "report.md")))
    check("report counts reportable", len(rj["reportable"]) >= 5, f"got {len(rj['reportable'])}")
    check("report quarantines proof-less", any(f["title"] == "no-proof candidate"
                                               for f in rj["quarantined"]))
    check("proof-less NOT in reportable", all(f["title"] != "no-proof candidate"
                                              for f in rj["reportable"]))
    check("report md has quarantine section", "Unsubstantiated" in md)

    print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
    print(f"(evidence dir kept for inspection: {ev})")
    srv.shutdown()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
