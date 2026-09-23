#!/usr/bin/env python3
"""secret_scan.py — original, owned regex-based secret scanner for pen_test.

Covers the common, well-known secret formats directly. Not a replacement
for the registered gitleaks/trufflehog when you need their broader
pattern libraries and (trufflehog) live-verification — see
knowledge/secrets_and_supply_chain.md for when to reach for those
instead. This script exists so the common cases don't require installing
anything at all.

Usage:
    python3 secret_scan.py <path>                  # scan working tree
    python3 secret_scan.py --git-history <repo>    # scan full git log -p
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# name -> (compiled pattern, severity). Severity guides triage; a live key is
# always worse than the pattern suggests, so these are floors, not ceilings.
PATTERNS = {
    "aws_access_key": (re.compile(r"AKIA[0-9A-Z]{16}"), "critical"),
    "aws_secret_key": (re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"), "critical"),
    "private_key_header": (re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"), "critical"),
    "github_pat": (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "critical"),
    "github_fine_grained": (re.compile(r"github_pat_[A-Za-z0-9_]{60,}"), "critical"),
    "gitlab_pat": (re.compile(r"glpat-[A-Za-z0-9\-_]{20,}"), "critical"),
    "slack_token": (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "high"),
    "slack_webhook": (re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}"), "high"),
    "stripe_live_key": (re.compile(r"(sk|rk)_live_[A-Za-z0-9]{24,}"), "critical"),
    "stripe_test_key": (re.compile(r"(sk|rk)_test_[A-Za-z0-9]{24,}"), "low"),
    "google_api_key": (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "high"),
    "google_oauth": (re.compile(r"[0-9]+-[0-9a-z_]{32}\.apps\.googleusercontent\.com"), "medium"),
    "twilio_key": (re.compile(r"SK[0-9a-fA-F]{32}"), "high"),
    "sendgrid_key": (re.compile(r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}"), "high"),
    "mailgun_key": (re.compile(r"key-[0-9a-zA-Z]{32}"), "high"),
    "npm_token": (re.compile(r"npm_[A-Za-z0-9]{36}"), "high"),
    "pypi_token": (re.compile(r"pypi-AgEIcHlwaS5vcmc[A-Za-z0-9\-_]{50,}"), "high"),
    "azure_storage_key": (re.compile(r"(?i)AccountKey=[A-Za-z0-9+/=]{80,}"), "critical"),
    "jwt": (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "medium"),
    "db_connection_string": (re.compile(r"(?i)(postgres|postgresql|mysql|mongodb(\+srv)?|redis)://[^\s:@/]+:[^\s:@/]+@"), "high"),
    "generic_secret_assignment": (re.compile(
        r"(?i)\b(secret|password|passwd|api[_-]?key|token|access[_-]?key|private[_-]?key)\b\s*[:=]\s*['\"]([^'\"\s]{12,})['\"]"
    ), "medium"),
}

# Variable names whose high-entropy string value is very likely a real secret.
ENTROPY_HINT = re.compile(
    r"(?i)\b(secret|passwd|password|api[_-]?key|token|access[_-]?key|auth|credential|private[_-]?key)\b"
    r"\s*[:=]\s*['\"]([A-Za-z0-9+/=_\-]{20,})['\"]"
)
ENTROPY_THRESHOLD = 4.0  # bits/char; base64/hex secrets sit well above this


def shannon_entropy(s: str) -> float:
    import math
    if not s:
        return 0.0
    counts = {c: s.count(c) for c in set(s)}
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())

# Filenames/extensions almost never worth scanning — cuts noise substantially.
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".pdf", ".lock"}


def scan_text(text: str, source: str) -> list[tuple[str, str, str]]:
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        matched_spans = []
        for name, (pattern, severity) in PATTERNS.items():
            m = pattern.search(line)
            if m:
                snippet = m.group(0)
                matched_spans.append(m.span())
                redacted = snippet[:6] + "…redacted…" + snippet[-4:] if len(snippet) > 14 else "…redacted…"
                findings.append((f"{severity}:{name}", f"{source}:{lineno}", redacted))
        # Entropy pass — catch secrets no named pattern knows, but only when the
        # variable name signals intent AND the value is genuinely high-entropy.
        em = ENTROPY_HINT.search(line)
        if em and not any(em.start(2) >= s and em.end(2) <= e for s, e in matched_spans):
            value = em.group(2)
            ent = shannon_entropy(value)
            if ent >= ENTROPY_THRESHOLD:
                redacted = value[:4] + "…redacted…" + value[-2:]
                findings.append((f"medium:high_entropy({ent:.1f}b)", f"{source}:{lineno}", redacted))
    return findings


def scan_path(root: Path) -> list[tuple[str, str, str]]:
    findings = []
    candidates = [root] if root.is_file() else root.rglob("*")
    for p in candidates:
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in SKIP_EXT:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        findings.extend(scan_text(text, str(p)))
    return findings


def scan_git_history(repo: Path) -> list[tuple[str, str, str]]:
    result = subprocess.run(
        ["git", "-C", str(repo), "log", "-p", "--all"],
        capture_output=True, text=True, check=False,
    )
    return scan_text(result.stdout, "git-history")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--git-history", metavar="REPO", help="also scan full git log -p for this repo")
    args = parser.parse_args()

    findings = scan_path(Path(args.path))
    if args.git_history:
        findings.extend(scan_git_history(Path(args.git_history)))

    if not findings:
        print("No pattern or entropy matches found. Regex+entropy covers common formats and")
        print("high-entropy assignments; for live credential VERIFICATION reach for trufflehog.")
        return

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: order.get(f[0].split(":", 1)[0], 9))
    print(f"{len(findings)} potential secret(s) — UNVERIFIED, confirm liveness before reporting as active:\n")
    for kind, location, redacted in findings:
        print(f"  [{kind}] {location}  {redacted}")
    print("\nEntropy/generic matches have higher false-positive rates than named-format matches.")
    sys.exit(2)


if __name__ == "__main__":
    main()
