# pen_test: close the network/infra VA gap

## Plan
- [x] R. Research (Sonnet + web) TLS/SSL assessment + unauth/misconfig service VA + nmap-NSE/nuclei-network usage
- [x] 1. native/tls_probe.py — protocols, ciphers, cert (expiry/self-signed/chain/host), STARTTLS, weak-config findings
- [x] 2. native/service_probe.py — unauth/misconfig checks: redis, mongodb, elasticsearch, memcached, FTP-anon, SNMP-public, SMB/RDP/VNC banner, DB exposure; default-cred hints
- [x] 3. Evidence integration: both emit Findings via --evidence-dir -> report.py
- [x] 4. Engines (depend-on-current): add nmap to install_extra_tools.sh; wire `nmap -sV --script vuln` + `nuclei -tags network`
- [x] 5. workflow.sh: new `infra` preset (port_scan -> nmap -> tls_probe -> service_probe -> nuclei network) with evidence + report
- [x] 6. knowledge/network_va.md — infra VA methodology
- [x] 7. Tests: TLS self-signed mock + unauth-redis mock in test_probes.py
- [x] 8. Update SKILL decision matrix + agent lifecycle
- [x] 9. Verify: run suite; review

## Review
(pending)

## Review (2026-09-24)
Closed the network/infra VA gap — pen_test is no longer web-only on the infra axis.
All work verified: 21/21 tests pass, both new probes live-checked, false positives fixed.

**Built (native/):**
- tls_probe.py — protocol/cipher/cert/STARTTLS/HSTS assessment (stdlib ssl + cryptography).
  Live test caught + fixed 2 real FPs (TLS1.3 suites bypass set_ciphers / lack "ECDHE" token).
- service_probe.py — benign unauth/misconfig checks for 15+ services (redis/mongo/ES/kibana/
  memcached/ftp/vnc/docker/k8s/kubelet/snmp/rabbitmq/mysql/postgres/smb/rdp); every verdict
  needs a positive real-resource payload; delegates SMB/Oracle/CVE depth to nmap+nuclei.

**Wired:** both emit to --evidence-dir -> report.py. New `infra` workflow preset chains
port_scan -> service_probe -> tls_probe -> nmap -sV --script vuln -> nuclei -tags network ->
report. nmap+sslscan added to install_extra_tools.sh. knowledge/network_va.md added. SKILL
decision matrix + native list + both agent files (root + nested) updated.

**Tests:** test_probes.py extended with a self-signed/expired TLS mock and an unauth-redis
mock (16 -> 21 checks).

**Honest limits (documented in-tool):** stdlib ssl can't test Heartbleed/ROBOT/Logjam-DH/OCSP
-> deferred to testssl/sslscan/nmap. SMB null-session enum, Oracle TDS, deep RDP crypto, and
all version->CVE mapping deferred to nmap NSE + nuclei (depend-on-current, not hardcoded).

**Still not full-scope VAPT:** AD/mobile remain knowledge-only; cloud is engines+knowledge
(prowler/scoutsuite), not owned probes; no post-exploitation (deliberate scope boundary).
Follow-up from prior round still open: retrofit the 15 legacy web probes to --evidence-dir.
No new dependencies (cryptography already in requirements.txt).
