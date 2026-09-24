#!/usr/bin/env python3
"""service_probe.py — owned unauthenticated / misconfigured network-service VA.

The infra-VA gap on the service layer: for each exposed service, do ONE benign,
read-only handshake and prove whether it's reachable WITHOUT auth — with the
literal response captured as evidence. Reachable != unauth: every "unauth"
verdict requires a positive data payload characteristic of the real resource
(a DB list, a pod list, a +PONG, a "None" VNC security type), never just an
open port.

Native (cheap, safe to hand-roll): redis, mongodb, elasticsearch, kibana,
memcached, ftp-anon, vnc, docker-api, k8s-apiserver, kubelet, snmp(v1),
rabbitmq(guest), mysql/postgres reachability, smb/rdp negotiate.
For depth this can't safely do natively (SMB null-session share enum, Oracle
TDS/O5LOGON, CVE-specific checks), the `infra` workflow runs `nmap --script vuln`
and `nuclei -tags network` — see knowledge/network_va.md.

Discipline: read-only verbs only (PING/INFO/stats/GET/isMaster/listDatabases),
no writes, no CONFIG SET / container create / script submit, no volume brute
(only the single documented defaults: ftp anonymous, rabbitmq guest:guest),
byte-capped reads, explicit timeouts, no third-party amplification.

AUTHORIZATION: active traffic — authorized targets only.

Usage:
    python3 service_probe.py 10.0.0.5
    python3 service_probe.py host --ports 6379,27017,9200 --evidence-dir ./ev
"""

from __future__ import annotations

import argparse
import base64
import http.client
import re
import socket
import ssl
import struct
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import _httpcore as core  # noqa: E402

MAXREAD = 65536


def _tcp(host, port, timeout):
    return socket.create_connection((host, port), timeout=timeout)


def _sr(sock, data: bytes, timeout=3, n=MAXREAD) -> bytes:
    sock.settimeout(timeout)
    try:
        if data:
            sock.sendall(data)
        return sock.recv(n)
    except OSError:
        return b""


def _http(host, port, path, tls=False, headers=None, timeout=4):
    try:
        if tls:
            ctx = ssl._create_unverified_context()
            conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("GET", path, headers=headers or {})
        r = conn.getresponse()
        body = r.read(MAXREAD).decode("utf-8", "replace")
        conn.close()
        return r.status, body
    except Exception:
        return None, ""


def _f(service, host, port, sev, title, proof):
    return core.Finding(vuln_class="exposed-service", tool="service_probe.py",
                        title=title, severity=sev, target=f"{host}:{port}",
                        status="confirmed", param=service, location="network",
                        proof=proof, response_excerpt=proof[:300],
                        reproduce=f"python3 service_probe.py {host} --ports {port}")


# ---- per-service probes: return Finding | None ----------------------------

def probe_redis(host, port, timeout):
    try:
        s = _tcp(host, port, timeout)
    except OSError:
        return None
    resp = _sr(s, b"PING\r\n", timeout)
    if not resp.startswith(b"+PONG"):
        s.close()
        return None  # -NOAUTH / not redis
    info = _sr(s, b"INFO server\r\n", timeout)
    cfg = _sr(s, b"CONFIG GET dir\r\n", timeout)
    s.close()
    ver = re.search(rb"redis_version:([\d.]+)", info)
    ver_s = ver.group(1).decode() if ver else "?"
    if cfg.startswith(b"*2") or cfg.startswith(b"*"):
        return _f("redis", host, port, "critical",
                  f"Unauthenticated Redis with CONFIG access (v{ver_s})",
                  f"PING->+PONG and CONFIG GET dir returned an array unauthenticated "
                  f"(RCE primitive). {cfg[:120]!r}")
    return _f("redis", host, port, "high", f"Unauthenticated Redis (v{ver_s})",
              f"PING returned +PONG with no auth; INFO readable. {info[:120]!r}")


def probe_mongodb(host, port, timeout):
    def bson_int(k):
        return b"\x10" + k.encode() + b"\x00" + struct.pack("<i", 1)

    def op_query(cmd):
        doc_body = bson_int(cmd)
        doc = struct.pack("<i", len(doc_body) + 5) + doc_body + b"\x00"
        body = (struct.pack("<i", 0) + b"admin.$cmd\x00" + struct.pack("<ii", 0, 1) + doc)
        header = struct.pack("<iiii", 16 + len(body), 1, 0, 2004)
        return header + body

    try:
        s = _tcp(host, port, timeout)
    except OSError:
        return None
    resp = _sr(s, op_query("listDatabases"), timeout)
    s.close()
    if not resp:
        return None
    if b"not authorized" in resp or b"requires authentication" in resp:
        return None
    if b"databases" in resp and (b"totalSize" in resp or b"\x04databases" in resp):
        return _f("mongodb", host, port, "critical", "Unauthenticated MongoDB (listDatabases)",
                  f"listDatabases succeeded with no auth — full DB listing exposed. {resp[:120]!r}")
    return None


def probe_elasticsearch(host, port, timeout):
    st, body = _http(host, port, "/", timeout=timeout)
    if st != 200 or "You Know, for Search" not in body:
        return None
    ver = re.search(r'"number"\s*:\s*"([\d.]+)"', body)
    st2, idx = _http(host, port, "/_cat/indices?v", timeout=timeout)
    if st2 == 200 and re.search(r"health\s+status\s+index", idx):
        return _f("elasticsearch", host, port, "critical",
                  f"Unauthenticated Elasticsearch with index listing (v{ver.group(1) if ver else '?'})",
                  f"/_cat/indices returned the index table unauthenticated. {idx[:150]!r}")
    return _f("elasticsearch", host, port, "high",
              f"Unauthenticated Elasticsearch (v{ver.group(1) if ver else '?'})",
              f"GET / returned cluster info unauthenticated. {body[:150]!r}")


def probe_kibana(host, port, timeout):
    st, body = _http(host, port, "/api/status", timeout=timeout)
    if st == 200 and ('"version"' in body or "kibanaVersion" in body):
        return _f("kibana", host, port, "high", "Unauthenticated Kibana status",
                  f"/api/status readable unauthenticated. {body[:150]!r}")
    return None


def probe_memcached(host, port, timeout):
    try:
        s = _tcp(host, port, timeout)
    except OSError:
        return None
    resp = _sr(s, b"stats\r\n", timeout)
    s.close()
    if re.search(rb"^STAT pid \d+", resp, re.M):
        ver = re.search(rb"STAT version ([\d.]+)", resp)
        return _f("memcached", host, port, "medium",
                  f"Unauthenticated Memcached (v{ver.group(1).decode() if ver else '?'})",
                  f"stats returned STAT lines with no auth. {resp[:120]!r}")
    return None


def probe_ftp(host, port, timeout):
    try:
        s = _tcp(host, port, timeout)
    except OSError:
        return None
    banner = _sr(s, b"", timeout)
    if not banner.startswith(b"220"):
        s.close()
        return None
    _sr(s, b"USER anonymous\r\n", timeout)
    resp = _sr(s, b"PASS anonymous@example.com\r\n", timeout)
    s.close()
    if resp.startswith(b"230"):
        return _f("ftp", host, port, "high", "Anonymous FTP login allowed",
                  f"USER anonymous / PASS -> {resp[:80]!r} (230 login successful).")
    return None


def probe_vnc(host, port, timeout):
    try:
        s = _tcp(host, port, timeout)
    except OSError:
        return None
    banner = _sr(s, b"", timeout)  # RFB 003.00x\n
    if not banner.startswith(b"RFB"):
        s.close()
        return None
    try:
        s.sendall(banner[:12])
        head = s.recv(1)
        if head and head[0] > 0:                       # RFB 3.7+: N security types follow
            types = s.recv(head[0])
        else:                                          # RFB 3.3: 4-byte type
            types = s.recv(3)
            types = (head + types)[-1:]
    except OSError:
        types = b""
    s.close()
    if b"\x01" in types:
        return _f("vnc", host, port, "critical", "VNC with no authentication",
                  f"server offered security-type 1 (None) — unauthenticated desktop access. types={types!r}")
    if b"\x02" in types:
        return _f("vnc", host, port, "medium", "VNC password auth (verify weak/default)",
                  f"server offers VNC DES auth only (type 2); candidate for default-password review. types={types!r}")
    return None


def probe_docker(host, port, timeout):
    for tls in (False, True):
        st, body = _http(host, port, "/version", tls=tls, timeout=timeout)
        if st == 200 and '"ApiVersion"' in body:
            st2, c = _http(host, port, "/containers/json?all=1", tls=tls, timeout=timeout)
            proof = f"/version exposed the Docker API unauthenticated ({'TLS' if tls else 'plaintext'}). {body[:120]!r}"
            if st2 == 200:
                proof += f" /containers/json readable -> unauth host RCE primitive."
            return _f("docker", host, port, "critical", "Unauthenticated Docker Engine API", proof)
    return None


def probe_k8s_api(host, port, timeout):
    st, body = _http(host, port, "/version", tls=True, timeout=timeout)
    if st != 200 or '"gitVersion"' not in body:
        return None
    st2, pods = _http(host, port, "/api/v1/namespaces/default/pods", tls=True, timeout=timeout)
    if st2 == 200 and '"PodList"' in pods:
        return _f("kubernetes", host, port, "critical", "Anonymous Kubernetes API pod read",
                  f"anonymous GET /api/v1/.../pods returned a PodList. {pods[:120]!r}")
    return None  # /version alone is unauth-by-default, not a finding


def probe_kubelet(host, port, timeout):
    tls = port != 10255
    st, body = _http(host, port, "/pods", tls=tls, timeout=timeout)
    if st == 200 and '"PodList"' in body:
        return _f("kubelet", host, port, "critical", "Unauthenticated kubelet /pods",
                  f"kubelet /pods returned a PodList unauthenticated (anonymous-auth). {body[:120]!r}")
    return None


def probe_rabbitmq(host, port, timeout):
    auth = base64.b64encode(b"guest:guest").decode()
    st, body = _http(host, port, "/api/overview", headers={"Authorization": f"Basic {auth}"}, timeout=timeout)
    if st == 200 and ("rabbitmq_version" in body or "management_version" in body):
        return _f("rabbitmq", host, port, "critical", "RabbitMQ default guest:guest works remotely",
                  f"/api/overview accepted guest:guest from a remote source. {body[:120]!r}")
    return None


def probe_snmp(host, port, timeout):
    def enc_arc(a):
        if a < 128:
            return bytes([a])
        out = []
        while a:
            out.insert(0, a & 0x7f); a >>= 7
        for i in range(len(out) - 1):
            out[i] |= 0x80
        return bytes(out)

    def get_pkt(community):
        oid = (1, 3, 6, 1, 2, 1, 1, 1, 0)
        ob = bytes([oid[0] * 40 + oid[1]]) + b"".join(enc_arc(a) for a in oid[2:])
        oid_der = b"\x06" + bytes([len(ob)]) + ob
        vb = b"\x30" + bytes([len(oid_der) + 2]) + oid_der + b"\x05\x00"
        vbl = b"\x30" + bytes([len(vb)]) + vb
        pdu_body = b"\x02\x01\x01\x02\x01\x00\x02\x01\x00" + vbl
        pdu = b"\xa0" + bytes([len(pdu_body)]) + pdu_body
        comm = community.encode()
        mb = b"\x02\x01\x00" + b"\x04" + bytes([len(comm)]) + comm + pdu
        return b"\x30" + bytes([len(mb)]) + mb

    for community, sev in (("public", "medium"), ("private", "high")):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            s.sendto(get_pkt(community), (host, port))
            data, _ = s.recvfrom(2048)
            s.close()
        except OSError:
            continue
        if data and data[0] == 0x30 and b"\xa2" in data[:6] + data:  # GetResponse PDU present
            txt = re.findall(rb"[ -~]{4,}", data)
            return _f("snmp", host, port, sev, f"SNMP community '{community}' valid",
                      f"SNMPv1 GET sysDescr with community '{community}' answered. {b' '.join(txt)[:120]!r}")
    return None


def probe_mysql(host, port, timeout):
    try:
        s = _tcp(host, port, timeout)
        data = _sr(s, b"", timeout)  # server sends handshake first
        s.close()
    except OSError:
        return None
    if not data or len(data) < 6:
        return None
    ver = re.search(rb"([0-9]+\.[0-9]+\.[0-9]+[\w.-]*)\x00", data[4:])
    if ver:
        return _f("mysql", host, port, "medium", f"Exposed MySQL/MariaDB (v{ver.group(1).decode()})",
                  f"reachable; server handshake banner v{ver.group(1).decode()}. Default-cred candidates "
                  f"(verify, don't brute): root:(blank)/root/toor. banner={data[:60]!r}")
    return None


def probe_postgres(host, port, timeout):
    try:
        s = _tcp(host, port, timeout)
        params = b"user\x00postgres\x00database\x00postgres\x00\x00"
        s.sendall(struct.pack("!ii", 8 + len(params), 196608) + params)
        data = _sr(s, b"", timeout)
        s.close()
    except OSError:
        return None
    if not data:
        return None
    if data[:1] == b"R" and data[5:9] == b"\x00\x00\x00\x00":
        return _f("postgresql", host, port, "critical", "PostgreSQL trust-auth (no password)",
                  "StartupMessage with user=postgres and NO password got AuthenticationOk — trust/peer misconfig.")
    if data[:1] in (b"R", b"E"):
        return _f("postgresql", host, port, "medium", "Exposed PostgreSQL",
                  "reachable; requires auth. Default-cred candidates (verify, don't brute): "
                  "postgres:postgres / postgres:(blank).")
    return None


def probe_smb(host, port, timeout):
    # SMB2 NEGOTIATE — best-effort: prove reachable + hint SMB1. Deep null-session
    # share enum is delegated to `nmap --script smb-enum-shares` (network_va.md).
    neg = bytes.fromhex(
        "000000c0fe534d4240000000000000000000000000000000000000000000000000000000"
        "0000000000000000000000000000000000000000000000000000000000000000")
    try:
        s = _tcp(host, port, timeout)
        resp = _sr(s, neg, timeout)
        s.close()
    except OSError:
        return None
    if resp[4:8] == b"\xfeSMB":
        return _f("smb", host, port, "low", "SMB reachable (run nmap smb-vuln/enum for depth)",
                  "SMB2 NEGOTIATE answered. Follow up: nmap --script smb-enum-shares,smb-vuln-* "
                  "(EternalBlue/null-session are out of native scope).")
    if resp[4:8] == b"\xffSMB":
        return _f("smb", host, port, "high", "SMBv1 enabled (EternalBlue exposure class)",
                  "server answered on the SMB1 dialect — verify MS17-010/CVE-2017-0144 patch level.")
    return None


def probe_rdp(host, port, timeout):
    cr = bytes.fromhex("0300001300e0000000000001000800000000")  # requestedProtocols=0 (PROTOCOL_RDP)
    try:
        s = _tcp(host, port, timeout)
        resp = _sr(s, cr, timeout)
        s.close()
    except OSError:
        return None
    if len(resp) < 19 or resp[0] != 0x03:
        return None
    # X.224 CC then optional RDP_NEG_RSP(0x02)/FAILURE(0x03) at offset 11
    if len(resp) >= 12 and resp[11] == 0x02:
        sel = struct.unpack("<I", resp[15:19])[0] if len(resp) >= 19 else 0
        if sel == 0:
            return _f("rdp", host, port, "high", "RDP with NLA not enforced (BlueKeep exposure class)",
                      "server accepted PROTOCOL_RDP (legacy security), NLA not required — verify "
                      "CVE-2019-0708 patch level. No exploit fired.")
    return _f("rdp", host, port, "low", "RDP reachable (NLA appears enforced)",
              "server responded to the X.224 negotiation; NLA/CredSSP appears required.")


PROBES = {
    21: probe_ftp, 445: probe_smb, 139: probe_smb, 1433: None, 3306: probe_mysql,
    3389: probe_rdp, 5432: probe_postgres, 5601: probe_kibana, 5900: probe_vnc,
    5901: probe_vnc, 6379: probe_redis, 6380: probe_redis, 6443: probe_k8s_api,
    8443: probe_k8s_api, 9200: probe_elasticsearch, 10250: probe_kubelet,
    10255: probe_kubelet, 11211: probe_memcached, 15672: probe_rabbitmq,
    27017: probe_mongodb, 2375: probe_docker, 2376: probe_docker,
}
SNMP_PORT = 161  # UDP, handled separately
DEFAULT_PORTS = sorted(p for p, fn in PROBES.items() if fn)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("host")
    p.add_argument("--ports", help="comma list to probe (default: all known service ports)")
    p.add_argument("--snmp", action="store_true", help="also probe SNMP (161/udp) public/private")
    p.add_argument("--timeout", type=float, default=3.0)
    core.add_evidence_args(p)
    args = p.parse_args()

    ports = [int(x) for x in args.ports.split(",")] if args.ports else DEFAULT_PORTS
    ev = core.evidence_from_args(args)
    print(f"Service VA: {args.host} — probing {len(ports)} service port(s)")

    findings = []
    for port in ports:
        fn = PROBES.get(port)
        if not fn:
            continue
        try:
            f = fn(args.host, port, args.timeout)
        except Exception as e:
            print(f"  {port:>5}: error {e}")
            continue
        if f:
            print(f"  [{f.severity}] {port:>5}/{f.param}: {f.title}")
            findings.append(f)
        else:
            print(f"  {port:>5}: no unauth/misconfig signal")
    if args.snmp:
        try:
            f = probe_snmp(args.host, SNMP_PORT, args.timeout)
            if f:
                print(f"  [{f.severity}] {SNMP_PORT}/snmp: {f.title}")
                findings.append(f)
            else:
                print(f"  {SNMP_PORT}/udp: no SNMP response to public/private")
        except Exception as e:
            print(f"  snmp: error {e}")

    print("\n" + "=" * 60)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: order.get(f.severity, 9))
    if findings:
        print(f"{len(findings)} service finding(s):")
        for f in findings:
            print(f"  [{f.severity}] {f.target} — {f.title}")
        print("\n[i] For version->CVE depth run: nmap -sV --script vuln + nuclei -tags network "
              "(see knowledge/network_va.md; wired in the `infra` workflow).")
    else:
        print("No unauthenticated/misconfigured services detected on the probed ports.")
    if ev:
        for f in findings:
            ev.add(f)
        print(f"[evidence] {len(findings)} finding(s) written to {ev.findings_path}")


if __name__ == "__main__":
    main()
