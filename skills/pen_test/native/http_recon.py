#!/usr/bin/env python3
"""http_recon.py — owned web recon / fingerprint / exposure engine for pen_test.

This is the layer the skill was missing: before you attack a specific class,
you map the surface. The field engagements that hit CVE-2025-29927 (Next.js
middleware auth bypass) and leaked build metadata had no native tool feeding
that discovery — this closes that gap. It does, in one pass:

  * security-header audit   — CSP, HSTS, X-Frame-Options, X-Content-Type,
                              Referrer-Policy, Permissions-Policy (missing = finding)
  * technology fingerprint  — Server / X-Powered-By / framework signatures
                              (Next.js, React, Express, nginx, Apache, PHP, ...)
  * exposed-artifact probe  — /.git/HEAD, /.env, source maps, backups, actuator,
                              swagger, /server-status, etc. (each a real leak)
  * CORS misconfiguration   — reflected Origin + credentials
  * CVE-hint mapper         — maps the fingerprint to known-CVE follow-ups,
                              incl. the exact test for CVE-2025-29927

Findings are candidates to confirm, not confirmed exploits — recon points the
deeper probes (sqli_probe, ssrf_probe, nuclei) at the right target.

AUTHORIZATION: sends live requests. Authorized targets only.

Usage:
    python3 http_recon.py https://target.example.com
    python3 http_recon.py https://target -H "Cookie: session=..." --no-artifacts
"""

from __future__ import annotations

import argparse
import re
from urllib.parse import urljoin, urlparse

import _httpcore as core

SECURITY_HEADERS = {
    "content-security-policy": "no CSP — XSS/data-injection has no defense-in-depth",
    "strict-transport-security": "no HSTS — protocol downgrade / SSL-strip possible",
    "x-frame-options": "no X-Frame-Options (and no frame-ancestors CSP) — clickjacking",
    "x-content-type-options": "no nosniff — MIME-sniffing XSS vectors",
    "referrer-policy": "no Referrer-Policy — URLs/tokens may leak via Referer",
    "permissions-policy": "no Permissions-Policy — powerful features unrestricted",
}

# header/body signature -> (technology, note). Body regexes run against the HTML.
TECH_HEADER_SIGNS = {
    "x-powered-by": lambda v: f"X-Powered-By: {v}",
    "server": lambda v: f"Server: {v}",
    "x-aspnet-version": lambda v: f"ASP.NET {v}",
    "x-generator": lambda v: f"Generator: {v}",
}
TECH_BODY_SIGNS = [
    (re.compile(r"/_next/static/"), "Next.js (React SSR/SSG)"),
    (re.compile(r"__NEXT_DATA__"), "Next.js"),
    (re.compile(r"window\.__NUXT__"), "Nuxt.js"),
    (re.compile(r"data-reactroot|react(?:-dom)?\.production"), "React"),
    (re.compile(r"ng-version="), "Angular"),
    (re.compile(r"vue(?:\.runtime)?\.min\.js|data-v-[0-9a-f]{8}"), "Vue.js"),
    (re.compile(r"wp-content|wp-includes"), "WordPress"),
    (re.compile(r"csrfmiddlewaretoken"), "Django"),
    (re.compile(r"laravel_session|X-CSRF-TOKEN"), "Laravel"),
]

# Paths that, if reachable, are themselves a leak. (path, why, ok-if-body-has).
EXPOSED_PATHS = [
    ("/.git/HEAD", "critical", "git repo exposed — full source recovery", re.compile(r"ref:\s*refs/")),
    ("/.git/config", "critical", "git config exposed", re.compile(r"\[core\]|\[remote")),
    ("/.env", "critical", "environment file — likely secrets", re.compile(r"=|^[A-Z_]+")),
    ("/.env.local", "critical", "environment file", re.compile(r"=")),
    ("/config.json", "high", "config file exposed", re.compile(r"\{")),
    ("/.aws/credentials", "critical", "AWS credentials", re.compile(r"aws_access")),
    ("/.svn/entries", "high", "SVN metadata exposed", None),
    ("/.DS_Store", "low", "macOS dir listing leak", None),
    ("/server-status", "medium", "Apache mod_status exposed", re.compile(r"Apache Server Status")),
    ("/actuator", "high", "Spring Actuator exposed", re.compile(r"\"_links\"|health")),
    ("/actuator/env", "critical", "Spring env (secrets) exposed", re.compile(r"propertySources|systemEnvironment")),
    ("/swagger.json", "medium", "API schema exposed (maps attack surface)", re.compile(r"swagger|openapi")),
    ("/openapi.json", "medium", "OpenAPI schema exposed", re.compile(r"openapi")),
    ("/api-docs", "medium", "API docs exposed", None),
    ("/phpinfo.php", "high", "phpinfo() exposed", re.compile(r"PHP Version")),
    ("/.well-known/security.txt", "info", "security.txt present", None),
    ("/robots.txt", "info", "robots.txt (may reveal hidden paths)", None),
]


def audit_security_headers(headers: dict) -> list[tuple[str, str, str]]:
    lower = {k.lower(): v for k, v in headers.items()}
    out = []
    for h, why in SECURITY_HEADERS.items():
        if h not in lower:
            out.append(("low" if h != "content-security-policy" else "medium", f"missing:{h}", why))
    # Positive risky signals
    acao = lower.get("access-control-allow-origin")
    if acao == "*" and lower.get("access-control-allow-credentials", "").lower() == "true":
        out.append(("high", "cors", "ACAO:* with credentials:true — invalid but sometimes honored"))
    return out


def fingerprint(headers: dict, body: str) -> list[str]:
    lower = {k.lower(): v for k, v in headers.items()}
    tech = []
    for h, fmt in TECH_HEADER_SIGNS.items():
        if h in lower:
            tech.append(fmt(lower[h]))
    for pat, name in TECH_BODY_SIGNS:
        if pat.search(body) and name not in tech:
            tech.append(name)
    return tech


def cve_hints(tech: list[str]) -> list[str]:
    joined = " ".join(tech).lower()
    hints = []
    if "next.js" in joined or "next" in joined:
        hints.append("Next.js -> test CVE-2025-29927 (middleware auth bypass): resend a request to a "
                     "middleware-protected path adding header `x-middleware-subrequest: middleware` "
                     "(or `src/middleware`), and see if the auth/redirect is skipped. Also enumerate "
                     "/_next/static/ for source maps and leaked build/env vars.")
    if "nginx" in joined:
        hints.append("nginx -> check for path-traversal via mis-set alias, and off-by-slash location merges.")
    if "apache" in joined:
        hints.append("Apache -> if version < 2.4.50, test CVE-2021-41773/42013 (path traversal -> RCE with cgi).")
    if "wordpress" in joined:
        hints.append("WordPress -> enumerate /wp-json/wp/v2/users, plugins in /wp-content/plugins/, run wpscan.")
    if "spring" in joined or "actuator" in joined:
        hints.append("Spring -> /actuator/{env,heapdump,mappings}; heapdump can leak live secrets.")
    if "php" in joined:
        hints.append("PHP -> test for LFI/RFI on include params and known deserialization sinks.")
    return hints


def cors_check(client: core.Client, url: str) -> tuple[str, str, str] | None:
    evil = "https://pentest-evil.example"
    r = client.request("GET", url, headers={"Origin": evil})
    if not r.ok:
        return None
    acao = {k.lower(): v for k, v in r.headers.items()}.get("access-control-allow-origin", "")
    acac = {k.lower(): v for k, v in r.headers.items()}.get("access-control-allow-credentials", "")
    if acao == evil:
        sev = "high" if acac.lower() == "true" else "medium"
        return (sev, "cors-reflect", f"Origin reflected into ACAO ({evil}); credentials={acac or 'n/a'}")
    return None


def probe_exposed(client: core.Client, base: str) -> list[tuple[str, str, str]]:
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"

    def check(entry):
        path, sev, why, body_pat = entry
        r = client.request("GET", urljoin(root + "/", path.lstrip("/")))
        if r.ok and r.status == 200 and r.length > 0:
            if body_pat is None or body_pat.search(r.text):
                return (sev, f"exposed:{path}", why)
        return None

    return [x for x in core.run_concurrent(check, EXPOSED_PATHS, concurrency=8) if x]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("--no-artifacts", action="store_true", help="skip exposed-path probing")
    core.add_common_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)
    client = core.client_from_args(args)

    base = client.request("GET", args.url, allow_redirects=True)
    if not base.ok:
        raise SystemExit(f"Could not reach target: {base.error}")

    findings: list[tuple[str, str, str]] = []
    print(f"Target: {args.url}  ->  status={base.status} len={base.length}\n")

    tech = fingerprint(base.headers, base.text)
    print("[fingerprint]")
    for t in (tech or ["(no obvious framework signature)"]):
        print(f"  - {t}")

    print("\n[security headers]")
    hf = audit_security_headers(base.headers)
    for sev, key, why in hf:
        print(f"  [{sev}] {key}: {why}")
    findings += hf
    if not hf:
        print("  all core security headers present")

    cors = cors_check(client, args.url)
    if cors:
        findings.append(cors)
        print(f"\n[cors]\n  [{cors[0]}] {cors[2]}")

    if not args.no_artifacts:
        print("\n[exposed artifacts]")
        ex = probe_exposed(client, args.url)
        for sev, key, why in ex:
            print(f"  [{sev}] {key}: {why}")
        findings += ex
        if not ex:
            print("  none of the probed paths were reachable")

    hints = cve_hints(tech)
    if hints:
        print("\n[CVE / follow-up hints]")
        for h in hints:
            print(f"  -> {h}")

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    ranked = sorted(findings, key=lambda f: order.get(f[0], 9))
    print("\n" + "=" * 60)
    top = [f for f in ranked if f[0] in ("critical", "high")]
    if top:
        print("Priority findings (confirm before reporting):")
        for sev, key, why in top:
            print(f"  [{sev}] {key} — {why}")
    else:
        print("No critical/high recon findings; deeper class-specific probing still warranted.")


if __name__ == "__main__":
    main()
