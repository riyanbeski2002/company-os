---
name: cloud-and-infra
description: Owned methodology for cloud, infrastructure, and network classes — cloud storage/buckets, IAM, containers/Kubernetes, serverless, CI/CD, DNS/subdomain takeover, email domain security, TLS/crypto, and network/MITM. Mostly manual or delegated to posture engines (prowler/trivy/checkov); scope-sensitive, authorized targets only.
---

# Cloud, Infrastructure & Network

Higher blast radius and tighter scope than app classes — an "authorized URL"
almost never authorizes its cloud account, DNS zone, or network segment. Confirm
scope before any of this. Cloud metadata via SSRF is in `ssrf_and_injection.md`;
dependency/container CVEs are in `secrets_and_supply_chain.md` (use `trivy`/
`grype`). Posture auditing uses `prowler` (installed by `install_extra_tools.sh`).

## Cloud storage (buckets / object stores)

- **Public buckets** — S3/GCS/Azure Blob/Supabase/Firebase Storage readable
  (or listable, or writable) anonymously. Test list + get + put.
- **Predictable object keys** — `/customer/123/passport.pdf` → try `124`;
  sequential or guessable keys defeat "unlisted = private".
- **Over-broad signed URLs** — expiry far in the future, no object binding,
  replayable, or still valid after the granting user is removed (see signed-URL
  section). Cross-tenant object access via a shared bucket.
- **Upload policy weakness** — client-controlled key/path on upload → overwrite
  another object or write outside your prefix.

## Cloud IAM

Excessive privileges, privilege-escalation paths (a role that can create/assume a
more privileged role, `iam:PassRole` chains), service-account impersonation,
confused-deputy (a service acting on attacker input with its own privileges),
cross-account trust errors, stale/long-lived credentials. `prowler` enumerates
these against a properly-scoped, authorized account — do not point it at an
account you weren't explicitly staffed for.

## Containers / Kubernetes

Exposed kubelet/dashboard/API with anonymous access, excessive RBAC, privileged
containers, host mounts / host networking, service-account token exposure inside
a pod (`/var/run/secrets/kubernetes.io/...`), insecure admission control,
namespace isolation gaps. Exposed etcd or the Docker socket is game-over — treat
as critical, prove read-only first.

## Serverless

Public function invocation with no auth, event injection (attacker-controlled
event fields reaching a sink), secrets in environment/config, function-to-function
trust, over-broad execution role, resource exhaustion, stale deployments still
reachable.

## CI/CD

Pipeline secret leakage (echoed in logs, in artifacts), untrusted PR execution
(a fork PR that runs privileged workflows / reaches secrets), artifact/dependency
poisoning, build-script injection, runner privilege, deployment credentials with
excessive scope, environment-separation failure. Overlaps supply chain
(`secrets_and_supply_chain.md`).

## DNS / subdomain takeover

- **Dangling DNS** — a CNAME pointing at a deprovisioned cloud resource (S3
  bucket, Heroku app, GitHub Pages, Azure) an attacker can claim. Enumerate only
  hosts explicitly in scope; a takeover is confirmed by actually serving content
  on the dangling host (benign proof).
- Wildcard DNS surprises, internal hostname disclosure, zone-transfer (`AXFR`)
  where the NS allows it.

## Email / domain security

SPF/DKIM/DMARC presence and enforcement (a missing/`p=none` DMARC allows
spoofing), mail-relay exposure, email-header injection in app-sent mail (reset,
verification), and reset/verification link security (host-header poisoning in
`web_infra.md`).

## TLS / transport & MITM

Weak TLS config/ciphers, certificate/hostname validation failures, mixed content,
insecure HTTP fallback, HSTS gaps, downgrade exposure, cert-pinning implementation
issues. MITM-class testing (traffic confidentiality, client accepting untrusted
certs, API calls bypassing TLS validation) is for authorized client/mobile review
and controlled lab networks only.

## Network L2/L3 (lab / explicitly-authorized only)

ARP/DNS/DHCP spoofing, rogue gateway/router, VLAN/segmentation isolation, lateral
movement. `port_scan.py` (and `nmap` for depth) maps exposed services;
active L2/L3 attacks are disruptive and require explicit, isolated-network
authorization — never on shared corporate or production networks casually.

## Cryptography

Weak algorithms/modes, static IVs / nonce reuse (catastrophic for CTR/GCM),
insecure randomness / predictable tokens, improper key derivation, hard-coded
keys, encryption without integrity (encrypt-then-nothing), secrets stored
plaintext, poor key rotation. Mostly found in code review (`Read`/`Grep`/
`semgrep`) — the tell is a fixed IV, `Math.random()` for tokens, or ECB.

## Signed URLs / temporary access

Excessive expiry, no binding to the specific object/user, replayable, predictable
parameters, scope too broad, and — the subtle one — access **surviving the user's
removal** because the URL was minted before revocation. Test by using a signed URL
after the granting account is disabled.

## Validation bar

Cloud/infra findings need the concrete artifact: the listed/read object, the IAM
policy JSON showing the excessive grant (from `prowler`/API), the anonymously
reachable dashboard, the claimed dangling host serving your marker. Scope
discipline is part of the bar — an out-of-scope host is not a finding, it's an
incident.
