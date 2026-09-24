#!/usr/bin/env python3
"""tls_probe.py — owned TLS/SSL vulnerability assessment for pen_test.

The infra-VA gap on the crypto layer: connect-only (benign, no exploitation) and
report protocol/cipher/certificate weaknesses with real evidence. Pure stdlib
`ssl`+`socket`, plus `cryptography` (already a dep) for un-validated cert parsing.

  * protocols  — which of SSLv3/TLS1.0/1.1/1.2/1.3 the server ACCEPTS (each old
                 one is a finding; RFC 8996 deprecated 1.0/1.1). Distinguishes
                 "server accepted" from "local OpenSSL can't even test it".
  * ciphers    — negotiated suite + weak-suite offer-tests (RC4/3DES/EXPORT/NULL),
                 forward-secrecy inference (ECDHE/DHE vs plain-RSA KEX).
  * certificate— expiry / not-yet-valid / self-signed / hostname-mismatch /
                 SHA1-MD5 signature / <2048-bit RSA / untrusted chain (2nd pass
                 with the system trust store) — down-ranked for internal/RFC1918.
  * STARTTLS   — SMTP/IMAP/POP3/FTP upgrade so mail/ftp endpoints are assessed too.
  * HSTS       — over the established socket (missing/short max-age).

Honest limits (also printed): stdlib `ssl` can't craft raw ClientHellos, read a
stapled OCSP response, or see DH params — Heartbleed/ROBOT/Logjam-modulus are NOT
safely testable here (that needs testssl.sh/sslyze/nmap NSE — see network_va.md).

AUTHORIZATION: active traffic — authorized targets only.

Usage:
    python3 tls_probe.py example.com
    python3 tls_probe.py mail.example.com --port 587 --starttls smtp --evidence-dir ./ev
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import socket
import ssl
import sys
import warnings
from datetime import datetime, timezone

# Probing deprecated protocols intentionally touches deprecated ssl.TLSVersion members.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="tls_probe")
warnings.filterwarnings("ignore", message=".*TLSVersion.*")

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import _httpcore as core  # noqa: E402

try:
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import rsa, ec
    from cryptography.hazmat.primitives.hashes import MD5, SHA1
    _HAVE_CRYPTO = True
except Exception:
    _HAVE_CRYPTO = False

PROTOCOLS = [
    ("SSLv3", ssl.TLSVersion.SSLv3, "critical"),
    ("TLSv1.0", ssl.TLSVersion.TLSv1, "high"),
    ("TLSv1.1", ssl.TLSVersion.TLSv1_1, "medium"),
    ("TLSv1.2", ssl.TLSVersion.TLSv1_2, "info"),
    ("TLSv1.3", ssl.TLSVersion.TLSv1_3, "info"),
]
WEAK_CIPHER_RE = re.compile(r"NULL|EXPORT|\bRC4\b|\bDES\b|3DES|DES-CBC3|EDE|\bMD5\b|anon|\bRC2\b|IDEA", re.I)
WEAK_OFFER_TESTS = [  # (label, openssl cipher string, severity)
    ("RC4", "RC4", "high"),
    ("3DES/Sweet32", "3DES:DES-CBC3-SHA", "medium"),
    ("EXPORT", "EXPORT", "high"),
    ("NULL", "NULL:eNULL:aNULL", "critical"),
]


def _is_internal(host: str) -> bool:
    try:
        return ipaddress.ip_address(socket.gethostbyname(host)).is_private
    except Exception:
        return host.endswith((".local", ".internal")) or "." not in host


def _connect(host, port, ctx, timeout, starttls=None):
    sock = socket.create_connection((host, port), timeout=timeout)
    if starttls:
        _do_starttls(sock, host, starttls)
    return ctx.wrap_socket(sock, server_hostname=host)


def _recv(sock, timeout=5):
    sock.settimeout(timeout)
    try:
        return sock.recv(2048)
    except OSError:
        return b""


def _do_starttls(sock, host, proto):
    if proto == "smtp":
        _recv(sock); sock.sendall(f"EHLO probe\r\n".encode()); _recv(sock)
        sock.sendall(b"STARTTLS\r\n"); _recv(sock)
    elif proto == "imap":
        _recv(sock); sock.sendall(b"a1 STARTTLS\r\n"); _recv(sock)
    elif proto == "pop3":
        _recv(sock); sock.sendall(b"STLS\r\n"); _recv(sock)
    elif proto == "ftp":
        _recv(sock); sock.sendall(b"AUTH TLS\r\n"); _recv(sock)


def probe_protocols(host, port, timeout, starttls, findings):
    print("\n[protocols]")
    supported = []
    for name, ver, sev in PROTOCOLS:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.minimum_version = ver
            ctx.maximum_version = ver
        except (ValueError, OSError):
            print(f"  {name:8s} untestable — local OpenSSL won't offer it")
            continue
        try:
            with _connect(host, port, ctx, timeout, starttls) as s:
                supported.append(name)
                print(f"  {name:8s} ACCEPTED  ({s.cipher()[0]})")
                if sev in ("critical", "high", "medium"):
                    findings.append(core.Finding(
                        vuln_class="tls", tool="tls_probe.py",
                        title=f"Deprecated/weak protocol {name} accepted",
                        severity=sev, target=f"{host}:{port}", status="confirmed",
                        proof=f"server completed a {name} handshake (cipher {s.cipher()[0]}); "
                              f"RFC 8996 deprecates TLS 1.0/1.1, SSLv3 is broken (POODLE).",
                        reproduce=f"python3 tls_probe.py {host} --port {port}"))
        except ssl.SSLError:
            print(f"  {name:8s} rejected")
        except OSError as e:
            print(f"  {name:8s} connect error: {e}")
    if "TLSv1.3" not in supported and supported:
        print("  [i] no TLS 1.3 support (1.2-only is below the modern baseline) — informational")
    return supported


def probe_ciphers(host, port, timeout, starttls, findings):
    print("\n[ciphers]")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with _connect(host, port, ctx, timeout, starttls) as s:
            name, ver, bits = s.cipher()
            # TLS 1.3 suites are always ephemeral-DH (forward-secret) and are named
            # `TLS_AES_*` without an ECDHE/DHE token — don't false-positive on them.
            fs = (ver == "TLSv1.3") or bool(re.search(r"ECDHE|DHE", name))
            print(f"  negotiated: {name} ({ver}, {bits}-bit)  forward-secrecy={'yes' if fs else 'NO'}")
            if WEAK_CIPHER_RE.search(name):
                findings.append(core.Finding(
                    vuln_class="tls", tool="tls_probe.py",
                    title=f"Weak cipher negotiated by default: {name}",
                    severity="high", target=f"{host}:{port}", status="confirmed",
                    proof=f"default handshake negotiated weak suite {name} ({bits}-bit).",
                    reproduce=f"python3 tls_probe.py {host} --port {port}"))
            elif not fs:
                findings.append(core.Finding(
                    vuln_class="tls", tool="tls_probe.py",
                    title="No forward secrecy (plain-RSA key exchange)",
                    severity="medium", target=f"{host}:{port}", status="confirmed",
                    proof=f"negotiated {name} uses RSA key exchange — no forward secrecy.",
                    reproduce=f"python3 tls_probe.py {host} --port {port}"))
    except OSError as e:
        print(f"  could not establish a baseline handshake: {e}")
        return
    # offer-tests for weak suites. Pin max_version to TLS 1.2 so a strong TLS 1.3
    # suite can't "rescue" the handshake (TLS 1.3 ciphers aren't controlled by
    # set_ciphers()), and confirm the NEGOTIATED cipher is actually weak before flagging.
    for label, cstr, sev in WEAK_OFFER_TESTS:
        ctx2 = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx2.check_hostname = False
        ctx2.verify_mode = ssl.CERT_NONE
        try:
            ctx2.maximum_version = ssl.TLSVersion.TLSv1_2
            ctx2.set_ciphers(cstr)
        except (ssl.SSLError, ValueError, OSError):
            print(f"  {label:14s} untestable — local OpenSSL lacks these suites")
            continue
        try:
            with _connect(host, port, ctx2, timeout, starttls) as s:
                neg = s.cipher()[0]
                if not WEAK_CIPHER_RE.search(neg):
                    print(f"  {label:14s} not offered (negotiated strong {neg})")
                    continue
                print(f"  {label:14s} OFFERED ({neg})")
                findings.append(core.Finding(
                    vuln_class="tls", tool="tls_probe.py",
                    title=f"Server offers weak {label} cipher suite",
                    severity=sev, target=f"{host}:{port}", status="confirmed",
                    proof=f"TLS 1.2 handshake succeeded negotiating weak suite {neg} "
                          f"when the client offered only {label}.",
                    reproduce=f"python3 tls_probe.py {host} --port {port}"))
        except (ssl.SSLError, OSError):
            print(f"  {label:14s} not offered")


def probe_certificate(host, port, timeout, starttls, findings):
    print("\n[certificate]")
    internal = _is_internal(host)
    # pass 1: grab the cert regardless of validity
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with _connect(host, port, ctx, timeout, starttls) as s:
            der = s.getpeercert(binary_form=True)
    except OSError as e:
        print(f"  no certificate retrieved: {e}")
        return

    # pass 2: trust-store validation for the authoritative chain/host/expiry verdict
    trust_error = ""
    ctx2 = ssl.create_default_context()
    try:
        with _connect(host, port, ctx2, timeout, starttls):
            print("  chain: trusted by system store, hostname matches")
    except ssl.SSLCertVerificationError as e:
        trust_error = getattr(e, "verify_message", "") or str(e)
        sev = "low" if internal else "medium"
        print(f"  chain: NOT trusted — {trust_error}" + (" (internal host, down-ranked)" if internal else ""))
        findings.append(core.Finding(
            vuln_class="tls", tool="tls_probe.py",
            title=f"Certificate not trusted: {trust_error}",
            severity=sev, target=f"{host}:{port}", status="confirmed",
            proof=f"system-trust-store validation failed: {trust_error}"
                  + (" (RFC1918/internal host — expected lower risk)" if internal else ""),
            reproduce=f"python3 tls_probe.py {host} --port {port}"))
    except OSError:
        pass

    if not _HAVE_CRYPTO:
        print("  [i] `cryptography` not importable — expiry/keysize/sig-algo detail skipped "
              "(pip install cryptography). Trust-store verdict above still applies.")
        return
    try:
        cert = x509.load_der_x509_certificate(der)
    except Exception as e:
        print(f"  cert parse failed: {e}")
        return
    now = datetime.now(timezone.utc)
    na = cert.not_valid_after_utc
    nb = cert.not_valid_before_utc
    subj = cert.subject.rfc4514_string()
    print(f"  subject: {subj[:80]}")
    print(f"  validity: {nb.date()} .. {na.date()}")
    if now > na:
        _cf(findings, host, port, "Expired TLS certificate", "high",
            f"certificate expired on {na.isoformat()}.")
    elif (na - now).days < 30:
        _cf(findings, host, port, "TLS certificate expiring within 30 days", "medium",
            f"certificate expires {na.isoformat()} ({(na-now).days}d).")
    if now < nb:
        _cf(findings, host, port, "TLS certificate not yet valid", "medium",
            f"certificate not valid until {nb.isoformat()}.")
    if cert.issuer == cert.subject:
        _cf(findings, host, port, "Self-signed TLS certificate", "low" if internal else "medium",
            "issuer == subject (self-signed)" + (" on internal host" if internal else ""))
    algo = cert.signature_hash_algorithm
    if algo and isinstance(algo, (SHA1, MD5)):
        _cf(findings, host, port, f"Weak certificate signature ({algo.name})", "high",
            f"certificate signed with {algo.name}.")
    pk = cert.public_key()
    if isinstance(pk, rsa.RSAPublicKey) and pk.key_size < 2048:
        _cf(findings, host, port, f"Weak RSA key ({pk.key_size}-bit)", "high",
            f"certificate public key is {pk.key_size}-bit RSA (<2048).")
    # SAN / hostname coverage note
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = san.get_values_for_type(x509.DNSName)
        if names and not any(_host_matches(host, n) for n in names):
            _cf(findings, host, port, "Hostname not covered by certificate SAN",
                "low" if internal else "high",
                f"requested host {host!r} not in SAN {names[:5]}.")
    except x509.ExtensionNotFound:
        print("  [i] no SubjectAlternativeName extension")


def _host_matches(host, pattern):
    if pattern.startswith("*."):
        return host.split(".", 1)[-1] == pattern[2:]
    return host.lower() == pattern.lower()


def _cf(findings, host, port, title, sev, proof):
    print(f"  [{sev}] {title}")
    findings.append(core.Finding(
        vuln_class="tls", tool="tls_probe.py", title=title, severity=sev,
        target=f"{host}:{port}", status="confirmed", proof=proof,
        reproduce=f"python3 tls_probe.py {host} --port {port}"))


def probe_hsts(host, port, timeout, findings):
    if port not in (443, 8443):
        return
    print("\n[hsts]")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with _connect(host, port, ctx, timeout, None) as s:
            s.sendall(f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
            data = b""
            while len(data) < 8192:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        headers = data.decode("latin-1", "replace")
        m = re.search(r"strict-transport-security:\s*([^\r\n]+)", headers, re.I)
        if not m:
            _cf(findings, host, port, "HSTS not set on HTTPS endpoint", "low",
                "no Strict-Transport-Security response header.")
        else:
            age = re.search(r"max-age=(\d+)", m.group(1))
            if age and int(age.group(1)) < 31536000:
                _cf(findings, host, port, "HSTS max-age below 1 year", "low",
                    f"Strict-Transport-Security: {m.group(1).strip()}")
            else:
                print(f"  present: {m.group(1).strip()[:60]}")
    except OSError as e:
        print(f"  hsts check skipped: {e}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("host")
    p.add_argument("--port", type=int, default=443)
    p.add_argument("--starttls", choices=["smtp", "imap", "pop3", "ftp"],
                   help="negotiate STARTTLS on a mail/ftp port before assessing")
    p.add_argument("--timeout", type=float, default=6.0)
    core.add_evidence_args(p)
    args = p.parse_args()

    ev = core.evidence_from_args(args)
    findings: list[core.Finding] = []
    print(f"TLS assessment: {args.host}:{args.port}"
          + (f" (STARTTLS {args.starttls})" if args.starttls else ""))

    probe_protocols(args.host, args.port, args.timeout, args.starttls, findings)
    probe_ciphers(args.host, args.port, args.timeout, args.starttls, findings)
    probe_certificate(args.host, args.port, args.timeout, args.starttls, findings)
    probe_hsts(args.host, args.port, args.timeout, findings)

    print("\n" + "=" * 60)
    print("[i] Not tested by this connect-only probe (need testssl.sh/sslyze/nmap NSE): "
          "Heartbleed, ROBOT, Logjam DH-modulus, OCSP stapling, raw-ClientHello checks.")
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: order.get(f.severity, 9))
    if findings:
        print(f"\n{len(findings)} TLS finding(s):")
        for f in findings:
            print(f"  [{f.severity}] {f.title}")
    else:
        print("\nNo TLS weaknesses detected by the tested checks.")
    if ev:
        for f in findings:
            ev.add(f)
        print(f"[evidence] {len(findings)} finding(s) written to {ev.findings_path}")


if __name__ == "__main__":
    main()
