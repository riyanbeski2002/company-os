#!/usr/bin/env python3
"""_httpcore.py — shared HTTP engine for the pen_test native probes.

This is the force-multiplier the individual probes were missing. Every probe
(sqli_probe, idor_probe, xss_probe, ssrf_probe, http_recon, graphql_probe)
imports this so they all get, for free and consistently:

  * a real authenticated session — arbitrary headers, cookies, bearer tokens
  * proxy passthrough — route every request through Burp/ZAP for manual review
    (`--proxy http://127.0.0.1:8080`), or an out-of-band collaborator
  * injection into ANY location — not just the query string, but form bodies,
    JSON bodies, headers, cookies, and URL path segments
  * concurrency with a global rate limit — fast, but polite to the target and
    to the target's own monitoring/WAF
  * TLS control (`--insecure` for self-signed test envs), retries, timeouts
  * one consistent Result object so probes compare responses the same way

AUTHORIZATION: this module sends real, active traffic. Only ever point it at a
target you own or have explicit written authorization to test — see
agents/pen_test.md's authorization gate and config/authorized-targets.yaml.

Nothing here is vendored from another tool; it is a thin, owned layer over the
standard `requests` library.
"""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

# Injection locations a payload can be placed into.
LOCATIONS = ("query", "form", "json", "header", "cookie", "path")


class RateLimiter:
    """Global minimum-interval limiter, shared across worker threads."""

    def __init__(self, per_second: float | None):
        self._min_interval = (1.0 / per_second) if per_second and per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        # Reserve this request's slot under the lock, but SLEEP OUTSIDE it.
        # Sleeping while holding the lock would serialize every worker to one
        # request at a time, silently defeating --concurrency. Here each worker
        # claims a distinct future deadline, releases the lock, then waits for
        # its own deadline — so N workers at rate R stay genuinely concurrent
        # up to R req/s in aggregate.
        with self._lock:
            now = time.monotonic()
            deadline = max(now, self._next_allowed)
            self._next_allowed = deadline + self._min_interval
        sleep_for = deadline - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)


@dataclass
class Result:
    """Uniform, cheap-to-compare view of a response (or a transport failure)."""

    ok: bool
    status: int = 0
    length: int = 0
    elapsed: float = 0.0
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    error: str = ""
    url: str = ""

    def signature(self) -> tuple[int, int]:
        """(status, length) — the coarse fingerprint most differentials use."""
        return (self.status, self.length)

    @property
    def snippet(self) -> str:
        return self.text[:400].replace("\n", " ")


@dataclass
class Client:
    """An authorized-target HTTP client with a persistent session."""

    timeout: float = 12.0
    verify_tls: bool = True
    proxy: Optional[str] = None
    retries: int = 1
    rate: Optional[float] = None
    max_text: int = 200_000  # cap response bodies we hold in memory

    def __post_init__(self) -> None:
        # requests.Session is NOT fully thread-safe (shared cookie jar / header
        # mutation), and run_concurrent() calls .request() from many threads.
        # So we hold the session CONFIG here and build one Session per thread
        # lazily via threading.local — each worker gets its own isolated jar.
        self._cfg_headers: dict[str, str] = {}
        self._cfg_cookies: dict[str, str] = {}
        self._local = threading.local()
        self._limiter = RateLimiter(self.rate)

    def _session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            if self.proxy:
                s.proxies.update({"http": self.proxy, "https": self.proxy})
            s.verify = self.verify_tls
            s.headers.update(self._cfg_headers)
            s.cookies.update(self._cfg_cookies)
            self._local.session = s
        return s

    # -- session setup -----------------------------------------------------
    def add_headers(self, headers: dict[str, str]) -> "Client":
        self._cfg_headers.update(headers)
        return self

    def add_cookies(self, cookies: dict[str, str]) -> "Client":
        self._cfg_cookies.update(cookies)
        return self

    def bearer(self, token: str) -> "Client":
        self._cfg_headers["Authorization"] = f"Bearer {token}"
        return self

    # -- core request ------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        data: Any = None,
        json: Any = None,
        headers: dict | None = None,
        cookies: dict | None = None,
        files: Any = None,
        allow_redirects: bool = False,
    ) -> Result:
        last_err = ""
        for attempt in range(self.retries + 1):
            self._limiter.wait()
            t0 = time.monotonic()
            try:
                resp = self._session().request(
                    method.upper(), url,
                    params=params, data=data, json=json,
                    headers=headers, cookies=cookies, files=files,
                    timeout=self.timeout, allow_redirects=allow_redirects,
                )
            except requests.exceptions.Timeout:
                return Result(ok=False, elapsed=time.monotonic() - t0,
                              error="timeout", url=url)
            except requests.exceptions.RequestException as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                if attempt < self.retries:
                    continue
                return Result(ok=False, elapsed=time.monotonic() - t0,
                              error=last_err, url=url)
            body = resp.text[: self.max_text]
            return Result(
                ok=True, status=resp.status_code, length=len(resp.content),
                elapsed=time.monotonic() - t0, text=body,
                headers={k: v for k, v in resp.headers.items()}, url=resp.url,
            )
        return Result(ok=False, error=last_err or "unknown", url=url)


@dataclass
class RequestSpec:
    """A base request whose one injection point a probe will mutate.

    A probe takes the operator's real, working request and asks this class to
    produce a copy with `payload` spliced into exactly one location — so the
    only thing that changes between the baseline and the attack request is the
    payload itself. That is what makes a differential trustworthy.
    """

    method: str
    url: str
    param: str                      # the field/segment name being injected
    location: str = "query"         # one of LOCATIONS
    base_params: dict = field(default_factory=dict)
    base_form: dict = field(default_factory=dict)
    base_json: dict | None = None
    base_headers: dict = field(default_factory=dict)
    base_cookies: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.location not in LOCATIONS:
            raise ValueError(f"location must be one of {LOCATIONS}, got {self.location!r}")
        # Absorb any query already present in the URL into base_params.
        parsed = urlparse(self.url)
        if parsed.query:
            for k, v in parse_qsl(parsed.query, keep_blank_values=True):
                self.base_params.setdefault(k, v)
            self.url = urlunparse(parsed._replace(query=""))

    def _url_with_path(self, payload: str) -> str:
        # Replace a literal {param}-style placeholder or append to the path.
        placeholder = "{" + self.param + "}"
        if placeholder in self.url:
            return self.url.replace(placeholder, payload)
        return self.url.rstrip("/") + "/" + payload

    def build(self, payload: str, *, prefix_base: bool = False) -> dict:
        """Return kwargs ready to splat into Client.request().

        prefix_base=True keeps the original value and appends the payload
        (the common `id=1' OR 1=1` pattern); False replaces it outright.
        """
        params = dict(self.base_params)
        form = dict(self.base_form)
        jbody = dict(self.base_json) if self.base_json is not None else None
        headers = dict(self.base_headers)
        cookies = dict(self.base_cookies)
        url = self.url

        def mix(current: str | None) -> str:
            base = current if (prefix_base and current is not None) else ""
            return f"{base}{payload}"

        if self.location == "query":
            params[self.param] = mix(params.get(self.param))
        elif self.location == "form":
            form[self.param] = mix(form.get(self.param))
        elif self.location == "json":
            jbody = jbody or {}
            jbody[self.param] = mix(jbody.get(self.param))
        elif self.location == "header":
            headers[self.param] = mix(headers.get(self.param))
        elif self.location == "cookie":
            cookies[self.param] = mix(cookies.get(self.param))
        elif self.location == "path":
            url = self._url_with_path(payload)

        return {
            "method": self.method,
            "url": url,
            "params": params or None,
            "data": form or None,
            "json": jbody,
            "headers": headers or None,
            "cookies": cookies or None,
        }


def run_concurrent(fn, items: Iterable, concurrency: int = 8) -> list:
    """Map fn over items with a bounded thread pool, preserving input order."""
    from concurrent.futures import ThreadPoolExecutor

    items = list(items)
    if concurrency <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(fn, items))


# --- shared CLI plumbing so every probe speaks the same dialect ----------

def add_common_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("session / transport (shared)")
    g.add_argument("--header", "-H", action="append", default=[],
                   metavar="'Key: Value'", help="repeatable request header")
    g.add_argument("--cookie", "-b", action="append", default=[],
                   metavar="'name=value'", help="repeatable cookie")
    g.add_argument("--bearer", metavar="TOKEN", help="Authorization: Bearer <TOKEN>")
    g.add_argument("--proxy", metavar="URL",
                   help="route through an intercepting proxy, e.g. http://127.0.0.1:8080")
    g.add_argument("--insecure", "-k", action="store_true",
                   help="skip TLS verification (self-signed test envs)")
    g.add_argument("--timeout", type=float, default=12.0)
    g.add_argument("--rate", type=float, default=None,
                   metavar="REQ/S", help="global request rate cap")
    g.add_argument("--concurrency", type=int, default=8)
    g.add_argument("--retries", type=int, default=1)


def parse_kv(items: list[str], sep: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in items:
        key, _, value = raw.partition(sep)
        if key.strip():
            out[key.strip()] = value.strip()
    return out


def client_from_args(args: argparse.Namespace) -> Client:
    """Build a configured Client from the shared args above."""
    c = Client(
        timeout=getattr(args, "timeout", 12.0),
        verify_tls=not getattr(args, "insecure", False),
        proxy=getattr(args, "proxy", None),
        retries=getattr(args, "retries", 1),
        rate=getattr(args, "rate", None),
    )
    if getattr(args, "header", None):
        c.add_headers(parse_kv(args.header, ":"))
    if getattr(args, "cookie", None):
        c.add_cookies(parse_kv(args.cookie, "="))
    if getattr(args, "bearer", None):
        c.bearer(args.bearer)
    if not c.verify_tls:
        try:  # silence the noisy per-request InsecureRequestWarning
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
    return c


def require_scheme(url: str) -> None:
    if "://" not in url:
        raise SystemExit("URL must include a scheme (http:// or https://)")


# ============================================================================
# Evidence layer — the mandatory deliverable.
# ----------------------------------------------------------------------------
# A pentest is only worth what it can PROVE. Every probe emits structured
# Findings into a shared evidence directory; `report.py` aggregates them into
# the severity-ranked deliverable. A finding with no captured proof is a
# candidate, never a reportable finding (see knowledge/exploitation_depth.md
# and finding_validation.md). This is enforced downstream by report.py.
# ============================================================================

import json as _json
import os as _os
import hashlib as _hashlib
from datetime import datetime, timezone

SEVERITIES = ("critical", "high", "medium", "low", "info")
_SEV_ORDER = {s: i for i, s in enumerate(SEVERITIES)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Finding:
    """One structured, evidence-bearing result from a probe.

    `status`:
      * "candidate"  — a signal fired; not yet independently confirmed.
      * "confirmed"  — reproduced, counter-evidence ruled out.
    `proof` is the concrete, benign, REAL evidence (an extracted record, an
    evaluated marker like 733*733 -> 537289, an OOB callback id). A finding
    whose proof is empty is not reportable — report.py quarantines it.
    """

    vuln_class: str
    title: str
    severity: str                 # one of SEVERITIES
    target: str
    status: str = "candidate"     # candidate | confirmed
    param: str = ""
    location: str = ""
    proof: str = ""               # the real, benign evidence string
    request: str = ""             # how to reproduce the exact request
    response_excerpt: str = ""    # bounded, redacted snippet
    reproduce: str = ""           # exact CLI command to reproduce
    notes: str = ""
    tool: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}, got {self.severity!r}")
        if self.status not in ("candidate", "confirmed"):
            raise ValueError("status must be 'candidate' or 'confirmed'")

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in (
            "vuln_class", "title", "severity", "target", "status", "param",
            "location", "proof", "request", "response_excerpt", "reproduce",
            "notes", "tool")}
        return d


class EvidenceLog:
    """Append-only sink: findings.jsonl + saved raw artifacts, under one dir.

    Probes get one via `evidence_from_args(args)`; None when --evidence-dir was
    not passed (interactive/manual runs still print, they just don't persist).
    """

    def __init__(self, evidence_dir: str):
        self.dir = evidence_dir
        self.artifacts_dir = _os.path.join(evidence_dir, "artifacts")
        _os.makedirs(self.artifacts_dir, exist_ok=True)
        self.findings_path = _os.path.join(evidence_dir, "findings.jsonl")

    def _save_artifact(self, vuln_class: str, name: str, content: str) -> str:
        digest = _hashlib.sha1(content.encode("utf-8", "replace")).hexdigest()[:10]
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:40]
        fname = f"{vuln_class}-{safe}-{digest}.txt"
        path = _os.path.join(self.artifacts_dir, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return _os.path.relpath(path, self.dir)

    def add(self, finding: "Finding", artifacts: dict[str, str] | None = None) -> dict:
        rec = finding.to_dict()
        rec["ts"] = _now_iso()
        if artifacts:
            rec["artifacts"] = {
                name: self._save_artifact(finding.vuln_class, name, content)
                for name, content in artifacts.items() if content
            }
        with open(self.findings_path, "a", encoding="utf-8") as fh:
            fh.write(_json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


def add_evidence_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("evidence (shared)")
    g.add_argument("--evidence-dir", metavar="DIR",
                   help="persist structured findings + artifacts here for report.py "
                        "(the mandatory engagement deliverable)")


def evidence_from_args(args: argparse.Namespace) -> Optional["EvidenceLog"]:
    d = getattr(args, "evidence_dir", None)
    return EvidenceLog(d) if d else None
