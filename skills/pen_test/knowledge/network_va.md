---
name: network-va
description: Network / infrastructure vulnerability assessment — beyond web. Port + service discovery, TLS/SSL crypto assessment, unauthenticated / misconfigured exposed services (redis, mongo, elasticsearch, memcached, ftp, snmp, smb, rdp, vnc, docker/k8s, exposed DBs), and service-version -> CVE identification via nmap NSE + nuclei network templates. Owns the stable technique, depends on nmap/nuclei for the live CVE feed.
---

# Network / Infrastructure VA

Web probes assess the app; this assesses the *host and its services*. The split
follows the skill's rule — **own the stable technique, depend on the live feed**:
handshakes and crypto checks are stable and native; service-version→CVE mapping is
a moving feed, so `nmap --script vuln` and `nuclei -tags network` carry it.

Everything here is **benign and connect-only**: one read-only handshake per
service, no writes/CONFIG SET/container-create, no volume brute (only the
documented defaults: FTP `anonymous`, RabbitMQ `guest:guest`), byte-capped reads,
explicit timeouts, no third-party amplification. Reachable is not a finding —
every "unauth" verdict needs a positive payload of the real resource.

## The flow (the `infra` workflow runs this)

```
scripts/workflow.sh infra <host>
  1. port_scan.py        — which ports are open (+ best-effort banner)
  2. service_probe.py    — per-service unauth / misconfig, with captured evidence
  3. tls_probe.py        — TLS/SSL crypto assessment on 443 (or --starttls)
  4. nmap -sV --script vuln  — service/version + NSE vuln scripts (CVE feed)
  5. nuclei -tags network    — continuously-updated network CVE templates
  6. report.py <evidence-dir>  — the mandatory deliverable
```

## 1. Discovery — `port_scan.py`

Plain concurrent connect scan + banner. For SYN-stealth, OS fingerprint, UDP, and
NSE depth, use `nmap` (step 4). Feed the open-port list into `service_probe.py`.

## 2. TLS/SSL — `tls_probe.py`

Connect-only assessment (pure stdlib `ssl` + `cryptography`):
- **Protocols** — flags accepted SSLv3 (critical), TLS 1.0 (high), TLS 1.1 (medium);
  RFC 8996 deprecated 1.0/1.1. Distinguishes "server accepted" from "local OpenSSL
  can't even test it" — never a false pass.
- **Ciphers** — negotiated suite + weak-suite offer-tests (RC4/3DES/EXPORT/NULL,
  pinned to TLS 1.2 so a strong 1.3 suite can't mask it); forward-secrecy (TLS 1.3
  and ECDHE/DHE are FS; plain-RSA KEX is not).
- **Certificate** — expiry / not-yet-valid / self-signed / hostname-vs-SAN /
  SHA1-MD5 signature / <2048-bit RSA / untrusted chain (2nd pass against the system
  store). Internal/RFC1918 hosts are down-ranked (self-signed on a private box is
  expected, not an exposure).
- **STARTTLS** — `--starttls smtp|imap|pop3|ftp` assesses mail/ftp TLS too.
- **HSTS** — missing / short max-age on HTTPS.

**Honest limits** (the probe prints them): stdlib `ssl` can't craft raw
ClientHellos, read a stapled OCSP response, or see DH params — **Heartbleed, ROBOT,
Logjam DH-modulus, DROWN key-recovery are NOT safely testable here.** For those run
`testssl.sh` / `sslscan` / `nmap --script ssl-*`. Library-version bugs
(CVE-2022-3602/3786 OpenSSL punycode) are cert-content/version dependent and out of
a client's view — correlate via the version banner.

## 3. Exposed services — `service_probe.py`

Native, per-service unauth/misconfig checks with the literal response as evidence:

| Service | Port | Unauth proof | Severity |
|---|---|---|---|
| Redis | 6379/6380 | `PING`→`+PONG`; `CONFIG GET dir` array = RCE primitive | high / critical |
| MongoDB | 27017 | `listDatabases` succeeds (not `not authorized`) | critical |
| Elasticsearch | 9200 | `/` tagline + `/_cat/indices` table | high / critical |
| Kibana | 5601 | `/api/status` readable | high |
| Memcached | 11211 | `stats`→`STAT` lines (+ UDP amplification note) | medium / critical |
| FTP | 21 | `USER anonymous`→`230` | high |
| VNC | 5900+ | RFB security-type `1` (None) offered | critical |
| Docker API | 2375/2376 | `/version`+`/containers/json` = unauth host RCE | critical |
| Kubernetes API | 6443/8443 | anon `/api/v1/.../pods`→PodList | critical |
| kubelet | 10250/10255 | `/pods`→PodList (anonymous-auth) | critical |
| SNMP | 161/udp | v1 GET sysDescr with `public`/`private` | medium / high |
| RabbitMQ mgmt | 15672 | `guest:guest` works remotely | critical |
| MySQL/Postgres | 3306/5432 | version banner / Postgres trust-auth | medium / critical |
| SMB | 139/445 | SMB2 negotiate (SMB1 = EternalBlue class); depth→nmap | low / high |
| RDP | 3389 | X.224 negotiate: NLA not enforced = BlueKeep class | low / high |

**Delegated to engines** (fragile to hand-roll): SMB null-session share enum
(`nmap --script smb-enum-shares,smb-vuln-*`), Oracle TDS/O5LOGON
(`nmap --script oracle-*`), deep RDP crypto, and all version→CVE mapping.

## 4. Service-version → CVE — nmap + nuclei

- `nmap -sV --script vuln -Pn <host> -oX -` — service/version + NSE vuln scripts;
  parse XML (stdlib `xml.etree`) and grep script output for `CVE-\d{4}-\d+`.
- `nuclei -tags network -jsonl -u <host>` — the continuously-updated feed the
  native code deliberately doesn't hardcode (CVEs move faster than this file).
  Refresh templates with `scripts/update_engines.sh` first.
- Division of labor: native probes prove **unauthenticated reachability with real
  evidence**; nmap/nuclei add **version→CVE breadth**. Merge into one findings list.

## 5. Default credentials

Never brute at volume. **Name-only, verify manually**: MSSQL `sa`, Oracle
`system`/`sys`/`scott`, MySQL `root`, Postgres `postgres` — real damage + lockout
risk. **Safe to test once** (documented constants tied to unauth-by-design): FTP
`anonymous`, RabbitMQ `guest:guest`, and the no-cred-by-default stores (redis/
memcached/mongo — the unauth check *is* the test). Anything else: bounded (≤3),
≥2s spaced, lockout-aware, and only under explicit authorization
(`credential_attacks.md`).

## Field notes (2023-2026)

- Unauth **Docker API** on 2375 still exposes 1M+ hosts (Kinsing/TeamTNT worms);
  CVE-2025-9074 (Docker Desktop internal API) — correlate version.
- **MongoDB/Elasticsearch** remain top mass-ransom/wipe targets when exposed
  unauth; escalate severity for pre-7.x ES (no security by default).
- **kubelet** `--anonymous-auth=true` + `AlwaysAllow` is a *config* issue, not a
  CVE — still the modal cloud finding.
- **RDP/BlueKeep** (CVE-2019-0708) still found on EOL Windows; flag NLA-disabled
  for patch verification, never fire the trigger.

## Validation bar

A network finding is the captured, real handshake/response proving unauthenticated
access or the weak-crypto property — plus, for CVEs, the reproduced NSE/nuclei
signal against *this* host (banners lie; back-ports patch without version bumps).
Escalation (unauth-Redis→RCE, Docker-API→host, LFI-class service abuse) is
referenced only — run under explicit authorization per `exploitation_depth.md`.
