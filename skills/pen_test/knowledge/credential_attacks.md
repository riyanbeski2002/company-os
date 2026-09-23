---
name: credential-attacks
description: Methodology for brute force, password spraying, credential stuffing, and offline cracking (passwords, hashes, JWT secrets) — with the tooling (auth_probe.py, hydra/ffuf, hashcat/john) and the controlled-testing discipline that keeps it authorized, not abusive.
---

# Credential Attacks

Guessing and cracking credentials, done as controlled testing. The finding is
usually *the missing control* (no lockout, no rate limit, weak policy) as much as the
cracked credential itself.

## Discipline first (this is what makes it authorized, not abuse)

- **Authorized single target only** (in `config/authorized-targets.yaml`); never spray
  across many orgs/hosts — that's the mass-targeting line we don't cross.
- **Lockout-aware & rate-limited** — stop the moment a lockout/CAPTCHA/rate signal
  appears; `auth_probe.py` does this automatically. A missing lockout is itself the finding.
- **Small, purposeful lists.** ~top-100 passwords, a seasonal spray (`Winter2026!`), or a
  targeted list — not rockyou-14M against prod. Prove the weakness, don't grind.
- **Never stuff real breach creds against real users' accounts** to gain access; test the
  *resistance* (does it rate-limit/lockout) with a controlled, small run.

## Online: guessing against the live auth

`native/auth_probe.py` (on `_httpcore`, session/proxy/rate/lockout-aware):
```bash
# password spraying — one password, many users (lowest lockout risk):
python3 native/auth_probe.py spray -u https://app/login --location json \
    --user-field email --pass-field password --users users.txt --password 'Winter2026!' --rate 2
# brute — many passwords, one user (higher lockout risk; watch it engage):
python3 native/auth_probe.py brute -u https://app/login ... --user admin --passwords top100.txt --rate 2
```
For raw scale / protocol logins beyond HTTP (SSH, RDP, SMB, DB), use the maintained tools:
`hydra`/`medusa`/`patator`, or `ffuf` as an HTTP brute-forcer
(`ffuf -w pw.txt -X POST -d 'user=admin&pass=FUZZ' -u https://app/login -fr 'Invalid'`).
These are registered utilities (see `tooling.md`), not native — brute *logic* is trivial;
the value is their protocol breadth and speed.

## Offline: cracking what you extracted

Once you have hashes/tokens (from a dump, a leak, a config), crack offline — no rate limit,
no lockout, no noise:
- **Password hashes** — `hashcat -m <mode> hashes.txt wordlist.txt -r rules/best64.rule`
  or `john --format=<fmt>`. Identify the mode first (`hashid`/`hashcat --identify`):
  bcrypt `-m 3200`, MD5 `-m 0`, SHA-256 `-m 1400`, NTLM `-m 1000`, Kerberos TGS
  `-m 13100` (see `technologies.md` roasting), sha512crypt `-m 1800`.
- **JWT HMAC secret** — `native/jwt_tool.py crack <token>` for the common list, or
  `hashcat -m 16500 jwt.txt wordlist.txt` for scale. → `authn_jwt_session.md`.
- **Archives / docs / etc.** — `john`'s `*2john` helpers (`zip2john`, `ssh2john`) → hashcat/john.
- **Wordlists & rules** — start targeted (company name, product, year, `rockyou` top-N) with
  a rule set (`best64`, `d3ad0ne`); mask attacks for known patterns
  (`hashcat -a 3 ?u?l?l?l?l?d?d?d?d`).

## User enumeration (multiplier)

Before spraying, find *which* usernames are real — it cuts noise and lockout risk:
`python3 native/auth_probe.py enum --users candidates.txt ...` compares valid-vs-invalid
response shape and timing on login/reset/register. A confirmed oracle is its own finding
and feeds `spray`.

## Validation bar

A cracked/guessed credential is confirmed by **logging in with it** and capturing the real
authed resource (`exploitation_depth.md`) — not by "hashcat printed a candidate." A
*missing-control* finding (no lockout, no rate limit, enumeration oracle) is confirmed by
the reproduced controlled run showing the control never engaged. Redact real passwords/
hashes in the report (prove the crack, don't publish the plaintext).
