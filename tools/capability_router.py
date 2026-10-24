#!/usr/bin/env python3
"""Goal router: turn a plain-language goal into a route.

The gap this closes (Riyan, 2026-10-24): keyword matching over a skill's name
and description can tell "redis" from "contract", but it cannot tell that
"build a launch video" needs a reel skill + a render tool + media sourcing,
while "do a VAPT on my app" needs an authorized-target check first. That is a
routing decision, and it belongs to company-pm, not to the user.

This module is the deterministic core the PM leans on:

    classify(goal)  -> which playbook kinds match, best first (no side effects)
    explain(goal)   -> the full route: kinds, the capabilities each step would
                       use (resolved through config/capability-map.yaml), the
                       hard gates, and the known gaps. NO cloning, NO loading.
    route(goal)     -> explain(goal) plus the concrete prepare actions
                       (clone/load) WITHOUT executing them — the caller
                       (company capability prepare) executes and logs them.

Nothing here clones, loads, installs, or runs anything. `explain` is safe to
run on any goal. T4 capabilities are never auto-selected (capability.py's
AUTO_TIERS); a step whose only supplier is T4 is reported as a gap, not loaded.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MAP = REPO_ROOT / "config" / "capability-map.yaml"
PLAYBOOKS = REPO_ROOT / "config" / "playbooks.yaml"
AUTO_TIERS = {"T0", "T1", "T2", "T3"}  # mirror of capability.py; T4 never auto


def load_map() -> dict:
    data = yaml.safe_load(MAP.read_text())
    return {e["id"]: e for e in data.get("entries", [])}


def load_playbooks() -> list:
    return yaml.safe_load(PLAYBOOKS.read_text()).get("playbooks", [])


def _provides_index(cmap: dict) -> dict:
    """tag -> list of map entries that supply it, best trust first."""
    idx: dict = {}
    for e in cmap.values():
        for tag in e.get("provides", []):
            idx.setdefault(tag, []).append(e)
    for tag, entries in idx.items():
        entries.sort(key=lambda e: e.get("trust", "T4"))  # T0 < T1 < ... < T4
    return idx


# --- shared primitives: paraphrase tolerance + conditional clauses ---------
# Pure-Python, stdlib only (no ML, no deps). A dumb deterministic stemmer plus
# token-overlap is enough to stop the classifier dropping a reworded goal — and
# dropping it meant dropping its safety gates (see RISK_GATES / Finding 1).
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "want", "need",
    "make", "build", "create", "set", "something", "me", "my", "you", "your",
    "but", "can", "will", "all", "any", "how", "what", "who", "a", "an", "to", "of",
    "on", "in", "it", "is", "are", "some", "like", "find", "best", "get", "help",
}  # note: "app" is deliberately NOT a stopword — it's a real build_app signal.
# "find"/"best"/"get"/"help" are stopped: too generic to route on, and "find"
# collided across vapt ("find vulnerabilities") and research ("find the best").


def _stem(w: str) -> str:
    # Order matters. "-es" strips only the "s" so an "-e" word's plural keeps its
    # stem ("medicines"->"medicine", "doses"->"dose", "shares"->"share"); the old
    # code stripped "es" and produced "medicin"/"dos", which never matched the
    # singular trigger. "-ies"->"y" ("allergies"->"allergy").
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ing") and len(w) > 5:
        return w[:-3]
    if w.endswith("ed") and len(w) > 4:
        return w[:-2]
    if w.endswith("es") and len(w) > 4:
        return w[:-1]
    if w.endswith("s") and len(w) > 3:
        return w[:-1]
    return w


def _norm(goal: str) -> str:
    """Lowercase + fold glyphs that tokenization would otherwise drop, so a
    brand written with a symbol still matches its word form ("disney+" ->
    "disney plus", "c#" -> "c sharp"). Without this, _signals' [a-z0-9]+ strips
    the "+", and a single-token trigger like "disney+" can never match."""
    g = goal.lower()
    g = g.replace("+", " plus ").replace("#", " sharp ")
    return g


def _signals(text: str) -> set:
    """Stemmed, stopword-filtered token set of a goal — the paraphrase surface."""
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) >= 3 and w not in _STOP}


def _when_match(when, goal_lower: str, signals: set) -> bool:
    """A `when:` clause gates a step/gate/gap. Absent/empty => always on.
    Single-word triggers match stem-vs-stem; multi-word triggers match as a
    substring of the goal (handles 'react native')."""
    if not when:
        return True
    for trig in when:
        t = trig.lower()
        if " " in t:
            if t in goal_lower:
                return True
        elif _stem(t) in signals:
            return True
    return False


# --- risk-keyed safety net (Finding 1, Layer B) ----------------------------
# These gates apply from the goal's own risk words, regardless of whether any
# playbook classified. A reworded or unmatched goal therefore cannot shed its
# safety layer. A false positive is a sentence the PM reads and dismisses; a
# missing gate is the failure this exists to prevent — so trigger lists stay
# specific, and the gate net errs toward surfacing.
# Two-tier risk net (audit, 2026-10-24). Single-token keyword matching trades
# recall against precision: broad lists gate real goals but also fire on
# ordinary engineering words ("token", "checkout", "users", "steps"). So each
# class has STRONG triggers (unambiguous — fire alone) and WEAK triggers
# (common words — fire only with corroboration: >=2 weak hits in the same
# class). This keeps the classification-independent safety property (a reworded
# or unmatched goal still gates) while not stamping a hard-stop banner on every
# normal dev task. A multi-word trigger (e.g. "my shares", "break into") matches
# as a substring, so a risk sense can be caught without a colliding bare token.
# Each entry: {"strong": [...], "weak": [...], "text": "..."}.
RISK_GATES = [
    {"strong": ["health", "medical", "phi", "patient", "clinical", "insulin",
      "glucose", "diabetes", "asthma", "cholesterol", "vaccine", "prescription",
      "medication", "medicine", "medicines", "meds", "migraine", "migraines",
      "bmi", "allergy", "allergies",
      "biometric", "menstrual", "wellness", "symptom", "symptoms", "therapist",
      "therapy", "vitals", "seizure", "diagnosis", "diagnose", "dosage",
      "pill", "pills",
      "my cycle", "menstrual cycle", "blood sugar", "blood pressure", "heart rate"],
     "weak": ["fitness", "workout", "calorie", "calories", "diet", "sleep",
      "heart", "pulse", "pressure", "steps", "weight", "mood", "period", "pill",
      "sugar", "mental", "anxiety", "depression", "pain", "injury",
      "wearable", "dose", "appointment", "doctor", "blood", "eat", "ate", "food",
      "meal", "meals", "gym", "run", "runs", "running", "exercise", "cycle",
      "move", "nutrition", "hydration", "cardio", "slept", "weigh", "felt",
      "symptom", "feel", "feelings", "moods"],
     "text": "Personal health data in scope: PHI/privacy handling and a mandatory "
      "security_review before any storage or ship; data residency/retention is an "
      "explicit decision, not a default."},
    {"strong": ["trading", "brokerage", "crypto", "bitcoin", "ethereum", "altcoin",
      "forex", "nasdaq", "hodl", "defi", "day trading", "stock market",
      "crypto market", "my shares", "sell shares", "buy shares", "margin trading",
      "options trading", "hedge fund", "money", "pays out", "winnings", "prize money",
      "deposit", "deposits", "withdraw", "withdrawal", "withdrawals", "cash out",
      "cashout", "buy stocks", "sell stocks", "buys stocks", "sells stocks",
      "buy and sell stocks", "buy and sell crypto", "buy and sell shares",
      "execute trades", "executes trades", "execute a trade", "automated trading",
      "automate trading", "market order", "market orders", "place orders",
      "places orders", "place a trade", "places trades", "buys and sells stocks",
      "trade on my behalf", "trades on my behalf"],
     "weak": ["trade", "invest", "stock", "stocks", "equity", "equities", "coin",
      "token", "wallet", "algo", "dividend", "ticker", "dips", "rebalance",
      "holdings", "positions", "money", "payment", "payout", "custody", "eth",
      "btc", "portfolio", "savings", "options", "cash"],
     "text": "Live money movement (real orders, withdrawals, custody) is an "
      "ESCALATION to Riyan, never a default; market-data access is licensed and "
      "cannot be assumed free."},
    {"strong": ["stripe", "paypal", "venmo", "payroll", "fintech", "401k", "ira",
      "mutual fund", "mutual funds", "bank account", "bank transactions",
      "credit card", "debit card", "wire transfer", "pay my contractors",
      "pay contractors", "pay suppliers", "pay vendors", "pay invoices",
      "connects to my bank", "connect to my bank", "card details", "card data",
      "stored card", "card on file", "cardholder", "subscription billing",
      "billing details", "payment details"],
     "weak": ["checkout", "bank", "banking", "invoice", "invoicing", "budget",
      "budgeting", "ecommerce", "payments", "retirement", "ach", "remittance",
      "billing", "subscription"],
     "text": "Handling payments or financial accounts (card data, bank "
      "connections, balances, transfers) requires a security_review, brings "
      "PCI/financial-data compliance obligations, and moving real funds is an "
      "explicit decision, never a silent default."},
    {"strong": ["instagram", "tiktok", "autopost", "post to instagram",
      "post to twitter", "to my channel", "to our channel", "on my youtube",
      "to my youtube", "social media", "post on my behalf", "auto-publish",
      "auto publish", "schedule posts", "my feed", "to my feed"],
     "weak": ["post", "posts", "posting", "publish", "upload", "schedule",
      "channel", "youtube", "twitter"],
     "text": "Posting to someone's accounts needs their credentials and explicit "
      "approval — it is an ESCALATION, never a silent integration."},
    {"strong": ["exploit", "vapt", "pentest", "penetration", "penetrate",
      "vulnerability", "vulnerabilities", "vulnerable", "intrusion", "hackable",
      "insecure", "security hole", "security holes", "security weakness",
      "security weaknesses", "security issue", "security issues",
      "security problem", "security problems", "security audit", "security test",
      "audit the security", "break into", "broken into", "hack into", "hack my",
      "hack our", "weak points", "without a password", "bypass auth",
      "bypass the login", "find holes", "find vulnerabilities", "weakness",
      "weaknesses", "pop a shell", "get a shell", "reverse shell", "spawn a shell",
      "drop a shell", "run an attack", "attack against", "attack my", "attack our",
      "privilege escalation", "sql injection", "rce", "remote code execution"],
     "weak": ["hack", "breach", "recon", "unauthorized", "attack", "holes"],
     "text": "Exploitation runs ONLY against a target listed in "
      "config/authorized-targets.yaml within its stated scope; otherwise it is a "
      "hard stop."},
    {"strong": ["spotify", "netflix", "drm", "copyright", "licensed catalog",
      "app store", "disney plus", "hulu", "hbo", "hbo max",
      "prime video", "apple music", "youtube music", "paramount", "peacock",
      "crunchyroll", "soundcloud", "twitch", "pandora", "tidal"],
     "weak": ["clone", "replica", "copies", "mirror", "mirrors", "catalog",
      "streaming", "stream", "licensed", "movies", "songs", "music"],
     "text": "Cloning a licensed catalog/content service: its licensed or "
      "DRM-protected catalog cannot be legally replicated. Buildable is the app "
      "shell plus the user's OWN content; licensed catalog access is a separate "
      "legal/commercial track."},
    {"strong": ["passport", "ssn", "fingerprint", "fingerprints", "biometric",
      "kyc", "cvv", "iban", "credit card", "card number", "date of birth",
      "social security", "national id", "driver's license", "drivers license",
      "driving licence", "medical record", "medical records"],
     "weak": ["login", "signin", "signup", "account", "accounts", "user", "users",
      "profile", "profiles", "auth", "authentication", "personal", "email",
      "address", "phone", "contact", "customer", "customers", "identity",
      "identification", "credit", "dob", "nationality", "citizenship", "visa", "tax"],
     "text": "Storing personal or identity/financial data (accounts, profiles, "
      "contact info, passports, SSNs, card/tax numbers, biometrics) requires a "
      "security_review before ship and an explicit data-handling decision "
      "(what is stored, where, for how long, which jurisdiction)."},
]


def _trigger_count(triggers, signals, goal_lower):
    """How many DISTINCT triggers hit: a single word stem-matches the goal's
    token set; a multi-word phrase matches as a substring. Distinct stems are
    counted, so singular/plural duplicates in a list ("user"/"users",
    "stock"/"stocks") can't fake a second corroborating hit."""
    hits = set()
    for t in triggers:
        if " " in t or "-" in t:
            if t.lower() in goal_lower:
                hits.add(t.lower())
        else:
            st = _stem(t)
            if st in signals:
                hits.add(st)
    return len(hits)


def _risk_gates(signals: set, goal_lower: str = "") -> list:
    """Fire a class's gate if any STRONG trigger hits, or at least two WEAK
    triggers in that class hit (corroboration). This is classification-
    independent — it runs off the goal's own words, so a reworded or unmatched
    goal still carries its gate, without a single common word (token, checkout,
    users, steps) stamping a hard-stop on an ordinary dev task."""
    out = []
    for g in RISK_GATES:
        if _trigger_count(g["strong"], signals, goal_lower) >= 1 or \
           _trigger_count(g["weak"], signals, goal_lower) >= 2:
            out.append(g["text"])
    return out


def classify(goal: str, playbooks: list | None = None) -> list:
    """Playbook kinds for a goal, best first. Two tiers: a literal match of a
    `match` phrase is high confidence; a stemmed token overlap with a playbook's
    match-words + `signals:` is low confidence. High always outranks low, so
    exact wording still wins, but a reworded goal still routes (and carries its
    kind's gates) instead of falling through to nothing."""
    playbooks = playbooks if playbooks is not None else load_playbooks()
    g = _norm(goal)
    sig = _signals(g)
    scored = []
    for i, pb in enumerate(playbooks):
        phrase_hits = [m for m in pb.get("match", []) if m.lower() in g]
        pool = set()
        for m in pb.get("match", []):
            # Only single-word match phrases feed the single-token overlap pool.
            # A multi-word phrase like "penetration test" must NOT leak the bare
            # token "test" into vapt's low-confidence pool — it stays a literal
            # (high-confidence) substring match only. Intended extra tokens go
            # in the playbook's explicit `signals:` list.
            if " " not in m:
                pool |= _signals(m)
        pool |= {_stem(s) for s in pb.get("signals", [])}
        token_hits = sorted(sig & pool)
        if phrase_hits:
            scored.append((0, -len(phrase_hits), i, pb["kind"], "high", phrase_hits))
        elif len(token_hits) >= 2:
            # A low-confidence kind needs >=2 corroborating tokens. A single
            # common token ("token", "checkout", "stock", "post") is noise — it
            # must not create a kind that then drags in that playbook's hard-stop
            # gates. Real goals carry several signal words; the risk net covers
            # safety independently of classification.
            scored.append((1, -len(token_hits), i, pb["kind"], "low", token_hits))
    scored.sort()
    return [{"kind": k, "confidence": conf, "matched_on": h}
            for _, _, _, k, conf, h in scored]


def _resolve_step(require_tags, provides_idx):
    """For a step's required tags, pick a supplier per tag. A tag with no
    non-T4 supplier becomes a gap. The T4-only branch is a forward-guard: the
    live map has no T4 entry today, so it is covered by ResolveStepTest, not by
    a real-map route (T4 stays reference-only, enforced at prepare_unit)."""
    chosen, gaps = [], []
    for tag in require_tags:
        suppliers = provides_idx.get(tag, [])
        eligible = [s for s in suppliers if s.get("trust") in AUTO_TIERS]
        if not eligible:
            if suppliers:
                gaps.append(f"'{tag}' has only T4 suppliers — not auto-selected")
            else:
                gaps.append(f"'{tag}' has no capability in the map")
            continue
        pick = eligible[0]
        if pick["id"] not in [c["id"] for c in chosen]:
            chosen.append({"id": pick["id"], "kind": pick["kind"],
                           "ref": pick["ref"], "for_tag": tag,
                           "trust": pick.get("trust"),
                           "use_when": pick.get("use_when", ""),
                           "not_when": pick.get("not_when", ""),
                           "cost": pick.get("cost", "")})
    return chosen, gaps


def _select_kinds(kinds, playbooks):
    """Precision filter for economy: when at least one kind matched at HIGH
    confidence, keep the high-confidence kinds plus any kind they explicitly
    `composes_with`, and drop the rest (stray low-confidence noise that would
    otherwise clone/load capabilities the goal doesn't need). With no
    high-confidence match, keep the low-confidence best-effort set unchanged —
    a weak route is better than none, and it still carries its gates."""
    high = [k for k in kinds if k.get("confidence") == "high"]
    if high:
        allowed = {k["kind"] for k in high}
        for hk in high:
            allowed |= set(playbooks.get(hk["kind"], {}).get("composes_with", []))
        return [k for k in kinds if k["kind"] in allowed]
    # No high-confidence match: keep only the best-scoring low matches, so a
    # single weak token shared with an unrelated playbook doesn't create a
    # spurious kind (and pull in its capabilities). Ties are kept.
    if not kinds:
        return kinds
    top = max(len(k.get("matched_on", [])) for k in kinds)
    return [k for k in kinds if len(k.get("matched_on", [])) == top]


def _conditional(items, goal_lower, sig):
    """Flatten a playbook `gates:`/`gaps:` list whose entries may be a plain
    string (always on) or a {text, when} mapping (on only if `when` signals)."""
    out = []
    for it in items:
        if isinstance(it, str):
            out.append(it)
        elif _when_match(it.get("when"), goal_lower, sig):
            out.append(it["text"])
    return out


def explain(goal: str) -> dict:
    cmap = load_map()
    playbooks = {pb["kind"]: pb for pb in load_playbooks()}
    provides_idx = _provides_index(cmap)
    goal_lower = _norm(goal)
    sig = _signals(goal_lower)
    kinds = classify(goal, list(playbooks.values()))
    kinds = _select_kinds(kinds, playbooks)

    if not kinds:
        # No playbook matched — but the goal's own risk words still carry their
        # gates. The safety layer does not depend on classification.
        risk = _risk_gates(sig, goal_lower)
        msg = ("No playbook matched — routing by hand with "
               "`company capability search`.")
        if risk:
            msg += " The risk gates above still apply."
        return {"goal": goal, "kinds": [], "route": [], "gates": risk,
                "gaps": [msg], "capabilities": []}

    route, caps = [], []
    gates = _risk_gates(sig, goal_lower)  # risk net first; unioned with playbook gates
    gaps = []
    for k in kinds:
        pb = playbooks[k["kind"]]
        steps_out = []
        for step in pb.get("steps", []):
            if not _when_match(step.get("when"), goal_lower, sig):
                continue              # conditional step not signalled by this goal
            chosen, step_gaps = _resolve_step(step.get("requires", []), provides_idx)
            steps_out.append({"why": step.get("why", ""),
                              "requires": step.get("requires", []),
                              "use": chosen})
            gaps.extend(step_gaps)
            for c in chosen:
                if c["id"] not in [x["id"] for x in caps]:
                    caps.append(c)
        route.append({"kind": k["kind"], "confidence": k.get("confidence", "high"),
                      "clarify": pb.get("clarify", []), "steps": steps_out})
        gates.extend(_conditional(pb.get("gates", []), goal_lower, sig))
        gaps.extend(_conditional(pb.get("gaps", []), goal_lower, sig))

    # de-dup gates/gaps preserving order
    gates = list(dict.fromkeys(gates))
    gaps = list(dict.fromkeys(gaps))
    return {"goal": goal, "kinds": [k["kind"] for k in kinds], "route": route,
            "gates": gates, "gaps": gaps, "capabilities": caps}


def route(goal: str) -> dict:
    """explain() plus the prepare actions the caller should execute: which map
    entries need their repo cloned and which skills loaded. Does NOT execute."""
    plan = explain(goal)
    cmap = load_map()
    actions = []
    for c in plan["capabilities"]:
        entry = cmap[c["id"]]
        if entry["kind"] in ("catalog_unit",):
            actions.append({"action": "prepare_unit", "unit_id": entry["ref"],
                            "map_id": c["id"]})
        elif entry["kind"] in ("repo", "tool", "external_tool"):
            actions.append({"action": "ensure_clone", "registry_id": entry["ref"],
                            "map_id": c["id"], "note": "clone only; not installed"})
        # agent / native_skill: already present in-repo, nothing to fetch
    plan["prepare_actions"] = actions
    return plan


def _print_human(plan: dict):
    print(f"GOAL: {plan['goal']}")
    print(f"KINDS: {', '.join(plan['kinds']) or '(none matched)'}\n")
    for r in plan["route"]:
        conf = r.get("confidence", "high")
        print(f"[{r['kind']}]" + ("  (low-confidence match)" if conf == "low" else ""))
        if r["clarify"]:
            print("  ask to clarify:")
            for q in r["clarify"]:
                print(f"    - {q}")
        print("  route:")
        for s in r["steps"]:
            print(f"    * {s['why']}")
            if not s["use"]:
                print("      use: — GAP —")
            for c in s["use"]:
                print(f"      - {c['id']}({c['ref']})  trust={c['trust']}")
                if c.get("use_when"):
                    print(f"          use when: {c['use_when']}")
                if c.get("not_when"):
                    print(f"          not when: {c['not_when']}")
        print()
    if plan["gates"]:
        print("GATES (hard stops, not questions):")
        for g in plan["gates"]:
            print(f"  ! {g}")
        print()
    if plan["gaps"]:
        print("KNOWN GAPS (surface to Riyan, do not hide):")
        for g in plan["gaps"]:
            print(f"  ~ {g}")


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2 or argv[0] not in ("explain", "classify", "route"):
        sys.exit("usage: capability_router.py <explain|classify|route> <goal...>")
    cmd, goal = argv[0], " ".join(argv[1:])
    if cmd == "classify":
        print(json.dumps(classify(goal), indent=2))
    elif cmd == "explain":
        _print_human(explain(goal))
    else:
        print(json.dumps(route(goal), indent=2))


if __name__ == "__main__":
    main()
