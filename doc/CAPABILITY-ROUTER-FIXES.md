# Capability Router — Fix Design

Turns the independent audit (6/10) of the goal router into an implementable spec.
Scope: `tools/capability_router.py`, `config/playbooks.yaml`, `config/capability-map.yaml`,
`agents/company-pm.md`, and new tests in `tests/test_capability_map.py`. No change needed
in `tools/company/cli.py` — `cmd_capability_explain`/`cmd_capability_route` already pass
`gates`/`gaps` through verbatim, so every fix below lands by changing what `explain()` returns.

Constraints honoured throughout: stdlib only (no pip, tests run under `python3 -m unittest`);
paraphrase tolerance via pure-Python stemming + token overlap, no ML; `explain()` stays
side-effect-free; T4 is still never auto-selected; changes extend existing functions rather
than rewrite them.

## Shared primitives (add once, used by findings 1, 2, 5)

Add to `tools/capability_router.py`, above `classify()`:

```python
_STOP = {  # tiny, local; do not import capability.py's STOPWORDS (different purpose)
    "the", "and", "for", "with", "that", "this", "from", "into", "want", "need",
    "make", "build", "create", "set", "something", "app", "me", "my", "you", "your",
    "but", "can", "will", "all", "any", "how", "what", "who", "a", "an", "to", "of",
    "on", "in", "it", "is", "are", "some", "like",
}

def _stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w

def _signals(text: str) -> set:
    """Stemmed, stopword-filtered token set of a goal — the paraphrase surface."""
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) >= 3 and w not in _STOP}

def _when_match(when, goal_lower: str, signals: set) -> bool:
    """A `when:` clause gates a step/gate/gap. Absent/empty => always on.
    Matches if any single-word trigger (stemmed) is in signals, OR any
    multi-word trigger is a substring of the goal (handles 'react native')."""
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
```

Stemmer rationale: `workouts→workout`, `calories→calory` (we stem the triggers too, so the
list stores `calorie`→`calori`; match is stem-vs-stem, so write triggers as plain words and
let `_stem` normalise both sides), `channels→channel`, `shorts→short`. It is deliberately dumb
and deterministic; no lemmatiser, no deps.

---

## Finding 1 — Classifier brittleness is a safety bug (HIGHEST PRIORITY)

**Root cause.** `classify()` (L59–70) is literal substring matching; on fallthrough `explain()`
returns empty `gates`, and `agents/company-pm.md` (L326) sends the PM to the **gateless**
`company capability prepare`. So the health/trading/posting/exploit gates are only as reachable
as the exact wording. Reword the goal and the safety layer silently vanishes.

**Fix is two independent layers. Layer B is the guarantee; Layer A reduces how often we lean on it.**

### (a) Precise change

**Layer A — paraphrase-tolerant classification (best-effort, low-confidence allowed).**

1. In `config/playbooks.yaml`, add an optional `signals:` list of domain words per playbook
   (plain words; synonyms the `match` phrases miss). Examples:
   - `build_app`: `[tracker, track, calorie, workout, fitness, dashboard, clone, replica, photos, library]`
   - `trading_app`: `[trading, trade, invest, stock, crypto, equity, forex, portfolio, market, broker]`
   - `video_recreate`: `[reel, short, clip, promo, video, tiktok, instagram, trailer]`
   - `content_engine`: `[content, channel, publish, autopost, faceless, niche, cadence]`
   - `vapt`: `[vapt, pentest, exploit, vulnerability, attack, target, recon]`
   - `research`: `[research, compare, feasibility, investigate, benchmark]`

2. Rewrite `classify()` to score two tiers (keep its signature and return shape, add two keys):

```python
def classify(goal, playbooks=None):
    playbooks = playbooks if playbooks is not None else load_playbooks()
    g = goal.lower()
    sig = _signals(goal)
    scored = []
    for i, pb in enumerate(playbooks):
        phrase_hits = [m for m in pb.get("match", []) if m.lower() in g]
        # token pool = words from match phrases + explicit signals, stemmed
        pool = set()
        for m in pb.get("match", []):
            pool |= _signals(m)
        pool |= {_stem(s) for s in pb.get("signals", [])}
        token_hits = sorted(sig & pool)
        if phrase_hits:
            scored.append((0, -len(phrase_hits), i, pb["kind"], "high", phrase_hits))
        elif token_hits:
            scored.append((1, -len(token_hits), i, pb["kind"], "low", token_hits))
    scored.sort()
    return [{"kind": k, "confidence": conf, "matched_on": h}
            for _, _, _, k, conf, h in scored]
```

   High-confidence (literal) matches always rank above low-confidence (token) ones; existing
   callers that read `["kind"]` are unaffected.

**Layer B — risk-keyed safety-gate net, applied regardless of classification.** This is the
headline guarantee: gates survive even when `kinds == []`.

3. Add a module-level table and helper to `capability_router.py`:

```python
RISK_GATES = [
    (["health", "medical", "phi", "patient", "fitness", "workout", "calorie",
      "diet", "wellness", "biometric", "symptom"],
     "Personal health data in scope: PHI/privacy handling and a mandatory "
     "security_review before any storage or ship; data residency/retention is an "
     "explicit decision, not a default."),
    (["trading", "trade", "invest", "stock", "crypto", "equity", "forex",
      "portfolio", "brokerage", "order", "payment", "payout", "custody", "money"],
     "Live money movement (real orders, withdrawals, custody) is an ESCALATION to "
     "Riyan, never a default; market-data access is licensed and cannot be assumed free."),
    (["post", "posting", "publish", "autopost", "upload", "channel", "schedule",
      "instagram", "youtube", "tiktok", "twitter"],
     "Posting to someone's accounts needs their credentials and explicit approval — "
     "it is an ESCALATION, never a silent integration."),
    (["exploit", "vapt", "pentest", "penetration", "vulnerability", "attack",
      "target", "recon", "breach"],
     "Exploitation runs ONLY against a target listed in "
     "config/authorized-targets.yaml within its stated scope; otherwise it is a hard stop."),
]

def _risk_gates(signals: set) -> list:
    out = []
    for triggers, gate in RISK_GATES:
        if signals & {_stem(t) for t in triggers}:
            out.append(gate)
    return out
```

4. In `explain()`, compute `sig = _signals(goal)` once and prepend risk gates in **both**
   branches:
   - No-kinds branch (L100–103): set `"gates": _risk_gates(sig)` (was `[]`), and change the
     gap text to: `"No playbook matched — routing by hand with `company capability search`. "
     "The risk gates above still apply."`
   - Matched branch: initialise `gates = _risk_gates(sig)` before the per-kind loop so the
     net is unioned with (and de-duped against, via the existing `dict.fromkeys`) playbook gates.
   - Route low-confidence kinds too (they carry that kind's gates, which is the point); if any
     high-confidence kind exists, drive the route from those and still union the risk gates.

**Doc fix (removes the gateless-fallthrough instruction).** In `agents/company-pm.md` goal-intake
(L300–328): state that `explain` runs first on **every** goal and its `gates` apply even when
`KINDS` is `(none matched)`; the PM must surface those gates before doing anything else; the
`prepare` fallback is only for *selecting capabilities* for an unmatched goal and does **not**
replace the gates `explain` returned.

### (b) Acceptance tests (add to `tests/test_capability_map.py`, `RoutingTest`)

```python
REWORDS = {
    "i need to track my workouts and calories": ("build_app", "health"),
    "set up something that auto-publishes shorts to my channels": ("content_engine", "posting"),
    "make me a short promotional clip from this tiktok": ("video_recreate", None),
    "clone netflix but for my photos": ("build_app", None),
}

def test_rewordings_classify_best_effort(self):
    for goal, (kind, _) in self.REWORDS.items():
        kinds = [k["kind"] for k in router.classify(goal)]
        with self.subTest(goal=goal):
            self.assertIn(kind, kinds)

def test_health_reword_keeps_health_gate_even_if_unmatched(self):
    plan = router.explain("i need to track my workouts and calories")
    self.assertTrue(any("health" in g.lower() or "PHI" in g for g in plan["gates"]))

def test_posting_reword_keeps_posting_escalation(self):
    plan = router.explain("set up something that auto-publishes shorts to my channels")
    self.assertTrue(any("ESCALATION" in g and "account" in g.lower() for g in plan["gates"]))

def test_risk_gate_survives_total_fallthrough(self):
    # nonsense wrapper around a risk word → no kind, but gate must persist
    plan = router.explain("xyzzy frobnicate the crypto plugh")
    self.assertEqual(plan["kinds"], [])
    self.assertTrue(any("money" in g.lower() or "ESCALATION" in g for g in plan["gates"]))
```

(Existing `test_unknown_goal_is_honest` still passes: `"xyzzy frobnicate the plugh"` has no risk
word, so `kinds == []` and `gaps` is truthy.)

### (c) Risk / tradeoff

- Low-confidence classification can over-route (pull in a playbook's steps on a weak token).
  Mitigation: high-confidence always wins; the `confidence` field lets the PM/UI mark weak
  routes; it never *suppresses* a gate, which is the safe direction.
- `RISK_GATES` can fire on an innocent token (e.g. "stock photos" → trading gate). Accepted:
  a false gate is a surfaced sentence the PM reads and dismisses; a missing gate is the
  failure this whole fix exists to prevent. Keep trigger lists specific to limit noise.

---

## Finding 2 — Six map capabilities are unreachable

**Root cause.** No playbook step requires their `provides` tags:
`health-phi-compliance`(`phi_compliance`), `react-native-patterns`(`mobile_patterns`),
`product-launch-video`(`promo_video`), `finance-analyst`(`financial_modeling`),
`legal-analyst`(`legal_review`/`compliance_flag`), `ecc-security-review`(`secure_coding_ref`).

**Fix.** Introduce **conditional steps** (reusing the `when:` clause from the shared primitives)
and one small new playbook, so each entry is reachable on the goals it was made for.

### (a) Precise change

**Router** — in `explain()`, filter steps by `when` and tag each resolved cap:

```python
goal_lower = goal.lower()
sig = _signals(goal)
...
for step in pb.get("steps", []):
    if not _when_match(step.get("when"), goal_lower, sig):
        continue
    ...
```

**`config/playbooks.yaml`** — add steps (unconditional unless `when` shown):

- `build_app`, add:
  ```yaml
  - requires: [mobile_patterns]
    when: [mobile, ios, android, "react native", "cross platform", "cross-platform"]
    why: "Cross-platform mobile patterns when the app targets phones."
  - requires: [phi_compliance]
    when: [health, medical, phi, fitness, workout, calorie, patient, wellness]
    why: "PHI/privacy handling when the app stores personal health data."
  - requires: [secure_coding_ref]
    why: "Secure-coding checklist reference during the build, before formal review."
  - requires: [compliance_flag]
    when: [spotify, netflix, clone, replica, catalog, streaming, licensed, drm, copyright]
    why: "Flag content-licensing exposure when cloning a licensed service."
  ```
- `trading_app`, add:
  ```yaml
  - requires: [secure_coding_ref]
    why: "Secure-coding checklist reference before the independent review."
  - requires: [compliance_flag]
    why: "Flag market-data / brokerage licensing exposure."
  ```
- `video_recreate`, add:
  ```yaml
  - requires: [promo_video]
    when: [promo, promotional, product, launch, saas, brand, marketing]
    why: "Product-launch/promo treatment when the clip markets a product."
  ```
- New playbook (makes `financial_modeling` reachable):
  ```yaml
  - kind: finance_deliverable
    match: [financial model, dcf, lbo, valuation, comps, pitch deck,
            three statement, 3-statement, fundraise, cap table]
    signals: [valuation, model, financial, forecast, revenue, raise]
    clarify:
      - "What decision does this model support, and what is the time horizon?"
      - "Which scenarios/sensitivities must it show?"
    steps:
      - requires: [financial_modeling]
        why: "Build the model/deck from real inputs."
      - requires: [compliance_flag]
        when: [public, investor, fundraise, securities, offering]
        why: "Flag securities/disclosure exposure when materials face investors."
    gates: []
    gaps: []
  ```

`legal_review` is still supplied by `legal-analyst` (it shares the entry that provides
`compliance_flag`), so wiring `compliance_flag` makes that entry reachable. No separate
`legal_review` step is required unless a dedicated contract-review playbook is wanted later.

### (b) Acceptance tests

```python
def test_no_map_entry_is_unreachable(self):
    required = set()
    for pb in PLAYBOOKS:
        for step in pb.get("steps", []):
            required.update(step.get("requires", []))
    for e in CMAP:
        with self.subTest(id=e["id"]):
            self.assertTrue(set(e.get("provides", [])) & required,
                            f"{e['id']} provides nothing any playbook requires")

def test_health_app_loads_phi_skill(self):
    plan = router.explain("build a personal health tracking app")
    ids = [c["id"] for c in plan["capabilities"]]
    self.assertIn("health-phi-compliance", ids)

def test_mobile_build_loads_rn_patterns(self):
    plan = router.explain("build a cross-platform mobile health app")
    self.assertIn("react-native-patterns", [c["id"] for c in plan["capabilities"]])

def test_web_only_build_omits_mobile_patterns(self):
    plan = router.explain("build a web dashboard for my team")
    self.assertNotIn("react-native-patterns", [c["id"] for c in plan["capabilities"]])
```

### (c) Risk / tradeoff

- Conditional steps add a second way a step can be absent (gap vs. not-applicable). The
  `test_explain_has_no_dangling_steps_for_samples` invariant still holds because a step that is
  filtered out never appears in `route`. Document in the playbooks header that `when:` means
  "include only if the goal signals it".
- `test_no_map_entry_is_unreachable` is stricter than the existing supply test and will fail if
  a future map entry is added without a consuming step — that is the intended guard.

---

## Finding 3 — `use_when`/`not_when`/`cost` are cosmetic; `explain` overclaims

**Root cause.** `_resolve_step` (L73–91) copies only `id/kind/ref/for_tag/trust`; the plain-language
fields are never read, yet `agents/company-pm.md` L311 claims `explain` speaks "in plain
`use_when`/`not_when` terms".

### (a) Precise change

In `_resolve_step`, carry the editorial fields onto the chosen cap:

```python
chosen.append({"id": pick["id"], "kind": pick["kind"], "ref": pick["ref"],
               "for_tag": tag, "trust": pick.get("trust"),
               "use_when": pick.get("use_when", ""),
               "not_when": pick.get("not_when", ""),
               "cost": pick.get("cost", "")})
```

In `_print_human`, under each `use:` line, print the picked entry's `use_when`/`not_when` so the
human output actually contains them, e.g.:

```python
for c in s["use"]:
    print(f"      - {c['id']}({c['ref']})  trust={c['trust']}")
    if c["use_when"]:
        print(f"          use when: {c['use_when']}")
    if c["not_when"]:
        print(f"          not when: {c['not_when']}")
```

This makes the L311 claim true rather than requiring its removal. (If minimal diff is preferred,
alternatively soften L311; recommended path is to make it true.)

### (b) Acceptance tests

```python
def test_resolved_caps_carry_plain_language(self):
    plan = router.explain("build a personal health tracking app")
    self.assertTrue(plan["capabilities"])
    for c in plan["capabilities"]:
        with self.subTest(cap=c["id"]):
            self.assertIn("use_when", c)
            self.assertIn("not_when", c)
    # at least one non-empty, proving it is wired from the map, not a blank key
    self.assertTrue(any(c["use_when"] for c in plan["capabilities"]))
```

### (c) Risk / tradeoff

Pure additive to the dict shape; no existing test reads these keys, so nothing regresses. Slight
growth in `explain()` JSON size — negligible.

---

## Finding 4 — Gap detection is hand-curated; the T4 branch is dead

**Decision: hand-curated `gaps:` are acceptable by design** — they are editorial honesty ("no
resource exists for this part") that no computation can infer, and the PM is explicitly told to
surface them. Keep them. Two concrete fixes:

1. **Stop overclaiming.** The overclaim lives in Finding 3 (fixed there). Ensure neither the
   playbooks header nor `company-pm.md` implies gaps are *computed*; the header comment already
   says "honest notes", which is accurate — leave it, but do not add any "auto-detected gaps"
   wording when editing.

2. **The computed-gap paths that DO exist should be tested, not dead.** `_resolve_step` already
   computes two real gaps: "`<tag>` has no capability in the map" and "`<tag>` has only T4
   suppliers — not auto-selected". The second is currently unexercised only because the map has
   no T4 entry. Keep it as a forward-guard (it is correct the day a T4 entry lands) and make it
   live with a unit test that constructs the index directly — no fixture T4 entry needed in the
   real map:

### (a) Precise change

No production change required (keep the branch). Optionally add a one-line comment at L81 noting
it is a forward-guard covered by `test_t4_only_supplier_becomes_gap`.

### (b) Acceptance tests (new `ResolveStepTest` class)

```python
class ResolveStepTest(unittest.TestCase):
    def test_t4_only_supplier_becomes_gap(self):
        idx = {"x_tag": [{"id": "x", "kind": "catalog_unit", "ref": "r",
                          "trust": "T4"}]}
        chosen, gaps = router._resolve_step(["x_tag"], idx)
        self.assertEqual(chosen, [])
        self.assertTrue(any("only T4" in g for g in gaps))

    def test_missing_tag_becomes_gap(self):
        chosen, gaps = router._resolve_step(["nope_tag"], {})
        self.assertEqual(chosen, [])
        self.assertTrue(any("no capability in the map" in g for g in gaps))
```

### (c) Risk / tradeoff

None functional. The tradeoff is explicit: computed gaps cover only the two structural cases
(missing / T4-only); semantic gaps ("can't legally replicate a catalog") remain curated — see
Finding 5.

---

## Finding 5 — Bigger unflagged gaps (Spotify licensing, market-data, health residency)

**Root cause.** The Spotify goal routes as a plain `build_app` with no gap/gate; trading has no
market-data-licensing gap; health has no data-residency gap.

**Fix.** Extend the playbook `gaps:` schema to allow conditional entries, reusing `when:`, and add
the three missing notes. (Health residency is also covered by the Finding-1 health risk gate; the
gap states the *build* consequence, the gate states the *stop*.)

### (a) Precise change

**Router** — in `explain()`, replace `gaps.extend(pb.get("gaps", []))` with a form that accepts
either a string or a `{text, when}` mapping:

```python
for gp in pb.get("gaps", []):
    if isinstance(gp, str):
        gaps.append(gp)
    elif _when_match(gp.get("when"), goal_lower, sig):
        gaps.append(gp["text"])
```

(Apply the same string-or-mapping handling to `pb.get("gates", [])` so gates can be conditional
too; the existing all-string gates keep working unchanged.)

**`config/playbooks.yaml`** — add conditional gaps:

- `build_app.gaps`:
  ```yaml
  - text: "A 'clone' of a licensed catalog service (Spotify, Netflix, etc.) cannot
           legally replicate its licensed/DRM catalog. Buildable: the app shell plus
           the user's OWN content. Licensed catalog access is a separate legal/commercial
           track, not something the build can fake."
    when: [spotify, netflix, clone, replica, catalog, streaming, licensed, drm, copyright]
  - text: "Personal health data carries a data-residency and retention decision
           (where stored, how long, which jurisdiction) that must be made explicitly."
    when: [health, medical, phi, fitness, workout, calorie, patient, wellness]
  ```
- `trading_app.gaps` (append to the existing list):
  ```yaml
  - "Market-data is licensed: real-time/historical exchange or vendor feeds require a
     paid, terms-bound subscription; the build cannot assume free redistribution rights."
  ```

### (b) Acceptance tests

```python
def test_spotify_clone_flags_licensing_gap(self):
    plan = router.explain("build a replica of spotify for me, tailored to the songs i listen")
    self.assertTrue(any("licens" in g.lower() or "catalog" in g.lower() for g in plan["gaps"]))

def test_trading_flags_market_data_licensing(self):
    plan = router.explain("i want a AI trading app")
    self.assertTrue(any("market-data" in g.lower() or "market data" in g.lower()
                        for g in plan["gaps"]))

def test_health_flags_data_residency(self):
    plan = router.explain("build a personal health tracking app")
    self.assertTrue(any("residency" in g.lower() for g in plan["gaps"]))

def test_plain_webapp_has_no_spurious_licensing_gap(self):
    plan = router.explain("build a simple todo web app")
    self.assertFalse(any("catalog" in g.lower() for g in plan["gaps"]))
```

### (c) Risk / tradeoff

- These remain curated (per Finding-4 decision); they only fire on `when` signals, so plain apps
  stay clean (`test_plain_webapp_has_no_spurious_licensing_gap`).
- Schema is now string-or-mapping for both `gaps` and `gates`. Keep the playbooks header updated
  to document the two forms, and keep purely-unconditional entries as plain strings for readability.

---

## Implementation checklist (ordered, smallest blast radius first)

1. **Shared primitives** — add `_STOP`, `_stem`, `_signals`, `_when_match` to
   `capability_router.py`. (No behaviour change yet.)
2. **Finding 3** — carry `use_when`/`not_when`/`cost` through `_resolve_step`; print them in
   `_print_human`. Add `test_resolved_caps_carry_plain_language`. Run tests.
3. **Finding 4** — add the comment at the T4 branch; add `ResolveStepTest`
   (`test_t4_only_supplier_becomes_gap`, `test_missing_tag_becomes_gap`). Run tests.
4. **Finding 1 — Layer B first (the guarantee):** add `RISK_GATES` + `_risk_gates`; wire into
   both branches of `explain()`. Add `test_risk_gate_survives_total_fallthrough`,
   `test_health_reword_keeps_health_gate_*`, `test_posting_reword_keeps_posting_escalation`.
   Run tests — this is the priority fix; it must be green before moving on.
5. **Finding 1 — Layer A:** add `signals:` to each playbook; rewrite `classify()` with the
   two-tier score + `confidence`. Add `test_rewordings_classify_best_effort`. Confirm existing
   `test_samples_classify_to_expected_kind` and `test_unknown_goal_is_honest` still pass.
6. **Finding 2** — add `when`-filtering of steps in `explain()`; add the conditional steps and the
   `finance_deliverable` playbook. Add `test_no_map_entry_is_unreachable`,
   `test_health_app_loads_phi_skill`, `test_mobile_build_loads_rn_patterns`,
   `test_web_only_build_omits_mobile_patterns`. Run tests.
7. **Finding 5** — add string-or-mapping handling for `gaps`/`gates` in `explain()`; add the
   conditional gaps. Add the four Finding-5 tests. Run tests.
8. **Docs** — update `agents/company-pm.md` goal-intake (L300–328): `explain` runs first on every
   goal; its gates apply even when no playbook matched; `prepare` selects capabilities but never
   replaces those gates. Update the `config/playbooks.yaml` header to document `signals:`,
   `when:` on steps, and the string-or-mapping form of `gates`/`gaps`.
9. **Full run** — `python3 -m unittest tests.test_capability_map -v`; confirm all green.

## Preserved (do not regress)

Playbook shape (kind→steps→clarify→gates→gaps); the risky-goal gate design; T4 exclusion enforced
at `prepare_unit` (`RuntimeError`); map↔registry trust consistency; the clean
`explain`(no side effects)/`route`(plan)/`prepare`(executes) layering. Every change above is
additive to these — new helpers, new optional YAML keys, wider-but-compatible return shapes.

---

## Round 2 — second independent re-audit (2026-10-24, scored 7/10)

A fresh no-context Fable re-audit confirmed the five fixes above landed (gate
machinery real, T4 enforced, paraphrase + risk-net work for money/posting/
exploit), and found three more holes, now fixed:

1. **Health risk-net vocabulary hole (safety).** `RISK_GATES` health triggers
   missed everyday words (blood sugar/glucose, sleep, heart rate, weight, mood,
   medication …), so "log my blood sugar and sleep" shed its PHI gate. Fix:
   expanded the health trigger list AND `build_app` signals + the
   `phi_compliance` step/`residency` gap `when:` lists. Tested:
   `test_everyday_health_wording_keeps_phi_gate`.
2. **Copyright had no risk-net.** A reworded "copies netflix … my own movies"
   dropped the licensing gap entirely. Fix: added a licensing/catalog entry to
   `RISK_GATES` (so it fires regardless of classification) and broadened the
   `clone`/licensing `when:` + `build_app` signals to include copies/movies/
   songs/netflix/spotify. Tested: `test_copyright_reword_flags_licensing`.
3. **content_engine had no engineering of its own** — it leaned on `build_app`
   also matching. Fix: added `backend_build`, `code_review`, `verification`
   steps to the content_engine playbook. Tested:
   `test_content_engine_has_its_own_build_and_review`.
4. **Minor: spurious `research` match on "niche".** Removed `niche` from
   research signals and the opportunity `when:`. Tested:
   `test_content_goal_does_not_spuriously_match_research`.

---

## Round 3 — third independent re-audit (2026-10-24, scored 8.5/10)

Confirmed the hardest property (gates survive classification failure) is real,
and T4 exclusion / honest gaps / composes_with pruning all hold. Four
trigger-list/tokenization bugs kept it below 9.5, now fixed:

1. **PHI net under-triggered.** Missing common words (insulin, blood, allergy,
   bmi, doctor, diagnosis, dose, vaccine, asthma, diabetes, appointment, sugar…)
   so "track my insulin doses" shipped with no health gate. Fix: expanded the
   health `RISK_GATES` list, the `phi_compliance`/residency `when:` lists, and
   `build_app` signals (diary, calculator, history, records…). Test:
   `test_clinical_health_words_trigger_phi_net`.
2. **"tracks" cried wolf.** `_stem("tracks") == "track"` collided the music
   trigger with the verb, firing a false licensing gate on the flagship tracker
   use-case. Fix: removed "tracks" from the licensing trigger. Test:
   `test_track_verb_does_not_fire_licensing_gate`.
3. **Bare-token leak from multi-word match phrases.** `classify()` folded every
   match phrase through `_signals`, so "penetration test" injected the token
   "test" into vapt's low pool — any goal with "test" low-matched vapt. Fix:
   only single-word match phrases feed the token pool; multi-word phrases stay
   literal-only. Test: `test_the_word_test_does_not_pull_vapt`.
4. **Weak-word fan-out.** A running tracker ("count my daily runs") pulled
   build_app + trading_app + content_engine and their escalation gates. Fixed as
   a side effect of #3 (removing leaked tokens) plus the existing best-score
   filter. Test: `test_weak_tokens_do_not_fan_out_to_many_playbooks`.

---

## Round 4 — fourth independent re-audit (2026-10-24, scored 9.0/10)

Confirmed everything else is at/above 9.5 level. One severe finding + one minor,
both fixed:

1. **Personal-data net blind to identity/financial PII.** The trigger list had
   login/account/email/phone but not passport, ssn, credit card, dob, license,
   fingerprint, biometric — so "stores everyone's passport numbers" carried NO
   gate. Fix: extended the personal-data `RISK_GATES` list with identity-document
   and financial-identifier terms, and added passport/ssn/kyc/identity/biometric/
   spreadsheet to `build_app` signals so such data apps also route. Also fixed the
   no-kind gap line to only claim "risk gates still apply" when a gate actually
   fired. Tests: `test_identity_pii_triggers_data_gate`,
   `test_passport_pii_gate_survives_fallthrough`, `test_no_kind_no_risk_does_not_claim_gates`.
2. **Minor: `daily` too generic for content_engine.** Removed from its signals.
   Test: `test_daily_is_not_a_spurious_content_engine_signal`.

---

## Round 5 — fifth independent re-audit (2026-10-24, scored 9.1/10)

Two trigger-vocabulary gaps + one precision note, fixed:

1. **Money net missed everyday crypto/execution wording** (buy dips in ETH,
   rebalance BTC holdings, savings + algo, options positions) — routed with no
   gate. Fix: extended the money `RISK_GATES` list (bitcoin/btc/eth/coin/token/
   defi/rebalance/holdings/wallet/algo/securities/margin/leverage/dips/positions
   + multi-word "my shares"/"stock market"/"day trading"); added `_risk_gates`
   multi-word support so "my shares" catches the sense without a bare "share"
   collision; broadened trading_app signals so these also route. Removed the
   generic "order" (false-fired on e-commerce). Tests:
   `test_everyday_money_wording_keeps_money_gate`, `test_crypto_wording_routes_to_trading`,
   `test_money_gate_survives_fallthrough`, `test_money_net_no_false_positive_on_ecommerce`,
   `test_share_verb_does_not_fire_money_gate`.
2. **Health net missed lay words** (migraine, meds, pills, anxiety, therapy).
   Added to the health `RISK_GATES` list, the `when:` lists, and build_app
   signals. Test: `test_lay_health_words_trigger_phi_net`.
3. **content_engine route trimmed** — dropped `video_recreate` from its
   composes_with (it has its own video steps), removing an irrelevant clarify
   block. Goal 5 now routes content_engine + build_app (2 blocks, was 3).

---

## Round 6 — sixth independent re-audit (2026-10-24, scored 9.4/10)

Three precision collisions on core classes, fixed:

1. **security ↔ securities stem collision (required fix).** `_stem("securities")
   == "security"`, so the money trigger "securities" fired the live-money
   ESCALATION on every VAPT/security goal. Fix: removed "securities" from the
   money net and from trading_app signals (covered by stock/equity/invest).
2. **Bare "license" fired the PII gate** on "open-source license" / "license
   plate". Fix: removed bare license/licence from the personal-data net; added
   multi-word "driver's license"/"national id"/"social security"/"credit card"/
   "date of birth" so real identity docs still gate.
3. **Security intent routed to build_app, not vapt.** Added high-confidence vapt
   match phrases (security audit, security test, security holes, find holes,
   find weaknesses, break into, hack into) + weakness signals, and removed the
   over-generic vapt signals security/audit/assessment (so "add security
   headers"/"code audit"/"financial audit" no longer spuriously route vapt).
   Tests: test_security_does_not_fire_money_gate, test_security_intent_routes_to_vapt,
   test_bare_license_does_not_fire_pii_gate, test_drivers_license_still_gates_as_pii,
   test_generic_audit_does_not_fire_vapt.

---

## Round 7 — seventh independent re-audit (2026-10-24, scored 9.2/10)

1. **`portfolio` high-matched trading** — a design/photo portfolio site routed to
   trading and loaded trading skills. Fix: removed "portfolio" from trading
   match, money gate, and trading signals; added multi-word trading phrases
   (investment/stock portfolio, portfolio tracker, stock/crypto market, margin/
   options/day trading, hedge fund); added portfolio/site/photography/gallery to
   build_app signals.
2. **Payments/bank goals shed the money gate** — added a dedicated payments
   `RISK_GATES` entry (stripe/checkout/paypal/venmo/bank/401k/retirement/
   invoice/payroll/ecommerce/mutual funds/…) with a PCI/financial-data gate, and
   payments words to build_app signals so they route too.
3. **Security-testing intent + vulnerable wording** — added vapt match phrases
   (security issues/weaknesses/vulnerabilities, "is it vulnerable") and
   vulnerable/weakness to the exploit net.
4. **Generic single-token demotions** — removed margin/leverage/hedge/savings
   from the money net (css margin, leverage flexbox, hedge against risk, cost
   savings no longer fire), target/bypass/compromise from vapt signals (target
   audience, bypass cache no longer route vapt), market/markets from trading
   (marketing copy no longer trades), bare posts/channel from content_engine,
   and bare "copy" from the licensing net (added mirror/mirrors).
   Tests: test_portfolio_site_is_not_trading, test_investment_portfolio_still_routes_trading,
   test_payments_and_bank_goals_hit_a_financial_gate, test_common_words_do_not_fire_money_gate,
   test_generic_tokens_do_not_create_spurious_kinds, test_vulnerable_wording_routes_vapt.

---

## Round 8 — eighth re-audit (2026-10-24, scored 8.7/10): the structural fix

The prior rounds were word-list whack-a-mole with a precision/recall ceiling:
broad trigger lists gated real goals but fired on ordinary engineering words
(the audit found 17-20 of 20 dev sentences tripping a hard-stop gate). Fixed
structurally, not by more words:

1. **Two-tier risk net.** Each `RISK_GATES` class now has `strong` triggers
   (unambiguous — fire alone: passport, pentest, stripe, insulin, bitcoin) and
   `weak` triggers (common words — fire only with >=2 distinct hits in the
   class: token, checkout, users, steps, weight, post). Classification-
   independent safety is preserved; a lone common word no longer stamps a gate.
2. **Distinct-stem counting.** `_trigger_count` counts distinct stems, so
   singular/plural duplicates in a list ("user"/"users", "stock"/"stocks")
   can't fake a second corroborating hit.
3. **Low-confidence kinds need >=2 tokens.** A single weak signal token no
   longer creates a low-confidence kind (which used to drag in that playbook's
   hard-stop gates). Real goals carry several signal words.
4. Promoted decisive words to `strong` (money, pills, weakness/weaknesses),
   added recall vocab (eat/food/gym/run/cycle health; pay-contractors payments;
   on-my-youtube posting; hackable/insecure/weak-points/broken-into exploit),
   removed bare "stock" from the trading match (killed the "stock photos" high
   misroute).

Result on the audit's own batches: recall 0 misses (all lay-worded risk goals
keep their gate), precision 0/20 engineering sentences trip a gate (was 17-20),
six canonical goals unchanged, nonsense-wrapper gates still survive. Tests:
test_engineering_jargon_does_not_trip_risk_gates, test_lay_wordings_keep_their_gate,
test_single_weak_token_alone_does_not_gate.

---

## Round 9 — ninth re-audit (2026-10-24, scored 9.0/10)

Precision confirmed solved (2/30 engineering sentences, both defensible PII, 0
high-confidence misroutes). Remaining was a deterministic stemmer bug + health
recall:

1. **Stemmer `-es` bug (deterministic, wide footprint).** `_stem` stripped "es"
   before "s", so "-e" words' plurals never matched their singular trigger
   (medicines→medicin ≠ medicine, doses→dos, shares→shar). Fixed: "-es" now
   strips only the "s" (medicines→medicine); "-ies"→"y" preserved. A medicine
   app now gates and loads the PHI step.
2. **Lay health verb forms.** Added slept/ate/weigh/felt to the health weak
   triggers and period(s)/menstrual/slept/ate/weigh to the phi_compliance
   when-lists, so "jot down how i slept and what i ate" and "tracks my periods"
   gate and load the PHI step.
3. **Payout wording.** Added pays-out/winnings/prize-money to the money net.
   Tests: test_stemmer_handles_es_plurals_of_e_words, test_medicine_plural_goal_gates,
   test_lay_verb_forms_keep_health_gate, test_period_tracker_loads_phi_step.

---

## Round 10 — tenth re-audit (2026-10-24, scored 9.1/10)

Precision confirmed outstanding (0 spurious risk gates, 0 high-confidence
misroutes across 30 neutral sentences). Remaining items were safety-RECALL
misses on plausible phrasings, all closed:

1. **Exploitation phrasing** — "pop a shell", "reverse shell", "run an attack",
   "sql injection", "privilege escalation", "rce" added to the exploit strong
   list, so a technical exploitation request hits the authorized-targets stop.
2. **Card/billing** — "card details", "card data", "stored card", "cardholder",
   "subscription billing" (strong) + billing/subscription (weak) added to the
   payments net.
3. **Money movement** — deposit/withdraw/withdrawal/cash-out (strong) + cash
   (weak) added.
4. **Streaming brands** — disney+/hulu/hbo/prime video/apple music/paramount/
   etc. added to licensing strong.
5. **Mood diary** — feel/feelings/moods added to health weak (a lone "feel"
   still needs corroboration; "moods and how i feel" = 2 → gates).
   Tests: test_exploitation_phrasings_hit_authorized_gate, test_card_and_billing_hit_payments_gate,
   test_deposit_withdraw_hits_money_gate, test_more_streaming_brands_flag_licensing,
   test_mood_diary_gates_but_single_feel_does_not.

---

## Round 11 — eleventh re-audit (2026-10-24, scored 9.3/10)

One disqualifying one-line bug + one clean false positive, both fixed:

1. **`disney+` strong trigger was dead.** `_signals` tokenizes with `[a-z0-9]+`,
   stripping the "+", so the single-token trigger "disney+" never matched (only
   "disney plus" worked). Fix: added `_norm()` which folds "+"->" plus" and
   "#"->" sharp" before tokenizing, applied in both classify and explain. Now
   "clone disney+ with my own library" flags licensing. Test:
   test_brand_with_plus_glyph_flags_licensing.
2. **"feed" posting false positive.** "rebuild the feed" fired posting. Removed
   bare "feed" from the posting weak list, added "my feed"/"to my feed" strong,
   so "post updates to my feed" still gates but a cron feed rebuild does not.
   Test: test_feed_rebuild_is_not_posting_but_my_feed_is.

---

## Round 12 — twelfth re-audit (2026-10-24, scored 9.3/10)

One disqualifying trigger-list asymmetry, fixed:

**Trading verbs/stocks asymmetry.** The strong list had "buy shares"/"sell
shares" but not "buy stocks"/"sell stocks" or execution verbs, so "an app that
buys and sells stocks for me", "executes trades automatically", "places market
orders" routed to nothing with no live-money gate. Fix: added buy/sell stocks,
execute(s) trades, market order(s), place(s) orders/trades, trade on my behalf,
etc. to the money strong list and trading_app match. The three failing phrasings
now route trading_app + money gate; ordinary "sell my old furniture" / "buy
groceries" / "stock photo gallery" still do not fire. Tests:
test_buy_sell_execute_phrasings_route_and_gate_trading, test_ordinary_buy_sell_does_not_fire_money.
