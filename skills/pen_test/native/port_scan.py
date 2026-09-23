#!/usr/bin/env python3
"""port_scan.py — original, owned TCP connect-scan for pen_test.

A plain-socket concurrent connect scanner. Deliberately not a nmap
reimplementation — no SYN-stealth scanning, no OS/service fingerprinting
database, no NSE scripts. Covers the common case (which ports are open,
with a best-effort banner grab) without any external tool dependency.
For full service/version fingerprinting depth, the registered `nmap`
(installed via package manager, not vendored) remains available — see
SKILL.md.

AUTHORIZATION: only use against a target you own or have explicit
permission to actively test. Port scanning an unauthorized host is
itself frequently treated as an attack by the target's own monitoring.

Usage:
    python3 port_scan.py <host> --ports 1-1024
    python3 port_scan.py <host> --ports 22,80,443,3000,5432,8080
"""

from __future__ import annotations

import argparse
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

COMMON_PORTS = "21,22,23,25,53,80,110,111,135,139,143,443,445,993,995,1723,3000,3306,3389,5000,5432,5900,6379,8000,8080,8443,9200,27017"

# port -> (service, note). A note flags a service that is frequently exposed
# without auth or with a known-dangerous default — worth immediate follow-up.
SERVICES = {
    21: ("ftp", "anonymous FTP?"), 22: ("ssh", None), 23: ("telnet", "cleartext — deprecated"),
    25: ("smtp", "open relay?"), 53: ("dns", None), 80: ("http", None), 110: ("pop3", None),
    135: ("msrpc", None), 139: ("netbios", None), 143: ("imap", None), 443: ("https", None),
    445: ("smb", "EternalBlue / share enum"), 993: ("imaps", None), 995: ("pop3s", None),
    1723: ("pptp", None), 3000: ("http-alt/node", None), 3306: ("mysql", "exposed DB"),
    3389: ("rdp", "BlueKeep / brute-force"), 5000: ("http-alt/flask", None),
    5432: ("postgresql", "exposed DB"), 5900: ("vnc", "often no/weak auth"),
    6379: ("redis", "often NO AUTH — try `redis-cli -h <host>`"),
    8000: ("http-alt", None), 8080: ("http-proxy", None), 8443: ("https-alt", None),
    9200: ("elasticsearch", "often NO AUTH — try /_cat/indices"),
    27017: ("mongodb", "often NO AUTH — try `mongo <host>`"),
    11211: ("memcached", "no auth + amplification"), 2375: ("docker-api", "unauth = host RCE"),
    9000: ("http-alt/php-fpm", None), 5601: ("kibana", None), 15672: ("rabbitmq-mgmt", None),
}


def parse_ports(spec: str) -> list[int]:
    ports: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            ports.update(range(int(lo), int(hi) + 1))
        elif part:
            ports.add(int(part))
    return sorted(ports)


def grab_banner(sock: socket.socket) -> str:
    try:
        sock.settimeout(1.0)
        return sock.recv(128).decode(errors="replace").strip()
    except OSError:
        return ""


def scan_port(host: str, port: int, timeout: float) -> tuple[int, bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            banner = grab_banner(sock)
            return port, True, banner
    except OSError:
        return port, False, ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host")
    parser.add_argument("--ports", default=COMMON_PORTS)
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--workers", type=int, default=100)
    args = parser.parse_args()

    ports = parse_ports(args.ports)
    print(f"Scanning {args.host} — {len(ports)} port(s), {args.workers} concurrent workers")

    open_ports = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(scan_port, args.host, p, args.timeout) for p in ports]
        for fut in as_completed(futures):
            port, is_open, banner = fut.result()
            if is_open:
                open_ports.append((port, banner))

    flagged = []
    for port, banner in sorted(open_ports):
        svc, note = SERVICES.get(port, ("unknown", None))
        line = f"  OPEN  {port:>5}/{svc}"
        if banner:
            line += f"  banner: {banner}"
        if note:
            line += f"   [!] {note}"
            flagged.append((port, svc, note))
        print(line)

    if not open_ports:
        print("  No open ports found in the scanned range.")
    elif flagged:
        print("\n  Priority follow-ups (exposed/weak-default services):")
        for port, svc, note in flagged:
            print(f"    - {port}/{svc}: {note}")


if __name__ == "__main__":
    main()
