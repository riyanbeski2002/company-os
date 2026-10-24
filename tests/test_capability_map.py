"""The capability map and playbooks (Riyan, 2026-10-24): company-pm turns a
goal into a route without asking the user how or why.

These tests pin the invariants that keep the map honest:
  - every map `ref` resolves to a real agent, native skill, catalog unit, or
    registry id (a dangling ref would route the PM to nothing);
  - each map entry's `trust` matches the registry (no laundering T4 as T2);
  - every `provides` tag a playbook step requires is supplied by some entry;
  - the six sample goals classify to the expected kinds;
  - hard gates surface for trading/VAPT/content, and T4 is never auto-selected.
"""
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import capability_router as router  # noqa: E402

CMAP = yaml.safe_load((ROOT / "config" / "capability-map.yaml").read_text())["entries"]
PLAYBOOKS = yaml.safe_load((ROOT / "config" / "playbooks.yaml").read_text())["playbooks"]
REGISTRY = {e["id"]: e for e in
            yaml.safe_load((ROOT / "config" / "capability-registry.yaml").read_text())["entries"]}
INDEX_UNITS = {u["unit_id"]: u for u in
               yaml.safe_load((ROOT / "config" / "capability-index.yaml").read_text())["units"]}
AGENTS = {p.stem for p in (ROOT / "agents").glob("*.md")}
NATIVE_SKILLS = {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}


class MapIntegrityTest(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [e["id"] for e in CMAP]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_ref_resolves(self):
        for e in CMAP:
            kind, ref = e["kind"], e["ref"]
            with self.subTest(id=e["id"]):
                if kind == "agent":
                    self.assertIn(ref, AGENTS)
                elif kind == "native_skill":
                    self.assertIn(ref, NATIVE_SKILLS)
                elif kind == "catalog_unit":
                    self.assertIn(ref, INDEX_UNITS)
                elif kind in ("repo", "tool", "external_tool"):
                    self.assertIn(ref, REGISTRY)
                else:
                    self.fail(f"unknown kind {kind}")

    def test_repo_paths_exist_on_disk(self):
        for e in CMAP:
            if e["kind"] == "repo" and "path" in e:
                p = ROOT / REGISTRY[e["ref"]]["local_path"] / e["path"]
                with self.subTest(id=e["id"]):
                    self.assertTrue(p.exists(), f"{p} missing")

    def test_trust_matches_registry_where_registry_knows(self):
        for e in CMAP:
            reg_id = e["ref"].split(":")[0] if e["kind"] == "catalog_unit" else e["ref"]
            if reg_id in REGISTRY and REGISTRY[reg_id].get("trust_tier"):
                with self.subTest(id=e["id"]):
                    self.assertEqual(e["trust"], REGISTRY[reg_id]["trust_tier"])


class PlaybookIntegrityTest(unittest.TestCase):
    def test_every_required_tag_is_supplied(self):
        supplied = set()
        for e in CMAP:
            supplied.update(e.get("provides", []))
        for pb in PLAYBOOKS:
            for step in pb.get("steps", []):
                for tag in step.get("requires", []):
                    with self.subTest(kind=pb["kind"], tag=tag):
                        self.assertIn(tag, supplied)

    def test_sensitive_playbooks_have_gates(self):
        by_kind = {pb["kind"]: pb for pb in PLAYBOOKS}
        for kind in ("trading_app", "vapt", "content_engine"):
            self.assertTrue(by_kind[kind]["gates"], f"{kind} must have gates")


class RoutingTest(unittest.TestCase):
    SAMPLES = {
        "i want a AI trading app": "trading_app",
        "i want to recreate this reel and share a instagram link": "video_recreate",
        "build a personal health tracking app": "build_app",
        "build a replica of spotify for me, tailored to the songs i listen": "build_app",
        "do a full VAPT on the app i built": "vapt",
    }

    def test_samples_classify_to_expected_kind(self):
        for goal, expected in self.SAMPLES.items():
            kinds = [k["kind"] for k in router.classify(goal)]
            with self.subTest(goal=goal):
                self.assertIn(expected, kinds)
                self.assertEqual(kinds[0], expected, f"{expected} should rank first")

    def test_content_engine_goal_is_multi_kind(self):
        goal = ("build a AI content creation engine that picks a niche, creates "
                "videos and posts on my IG and YT on regular basis")
        kinds = [k["kind"] for k in router.classify(goal)]
        self.assertIn("content_engine", kinds)

    def test_explain_has_no_dangling_steps_for_samples(self):
        for goal in self.SAMPLES:
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertTrue(plan["capabilities"])
                for r in plan["route"]:
                    for step in r["steps"]:
                        # every step either resolves to a capability or is a
                        # declared gap, never silently empty
                        self.assertTrue(step["use"] or plan["gaps"])

    def test_vapt_route_surfaces_authorization_gate(self):
        plan = router.explain("do a full VAPT on the app i built")
        self.assertTrue(any("authorized-targets.yaml" in g for g in plan["gates"]))

    def test_trading_route_surfaces_live_money_gate(self):
        plan = router.explain("i want a AI trading app")
        self.assertTrue(any("ESCALATION" in g for g in plan["gates"]))

    def test_content_engine_posting_is_a_declared_gap(self):
        plan = router.explain("build a content creation engine that posts on my IG and YT")
        self.assertTrue(any("posting" in g.lower() for g in plan["gaps"]))

    def test_unknown_goal_is_honest(self):
        plan = router.explain("xyzzy frobnicate the plugh")
        self.assertEqual(plan["kinds"], [])
        self.assertTrue(plan["gaps"])

    def test_route_never_selects_t4(self):
        for goal in list(self.SAMPLES) + ["make a video", "generate a voice clone"]:
            plan = router.route(goal)
            for c in plan["capabilities"]:
                with self.subTest(goal=goal, cap=c["id"]):
                    self.assertIn(c["trust"], {"T0", "T1", "T2", "T3"})

    def test_route_actions_mark_tools_as_clone_only(self):
        plan = router.route("i want to recreate this reel")
        for act in plan["prepare_actions"]:
            if act["action"] == "ensure_clone":
                self.assertIn("not installed", act["note"])

    # --- Finding 1: paraphrase tolerance + gates-never-dropped ---------------
    REWORDS = {
        "i need to track my workouts and calories": "build_app",
        "set up something that auto-publishes shorts to my channels": "content_engine",
        "make me a short promotional clip from this tiktok": "video_recreate",
        "clone netflix but for my photos": "build_app",
    }

    def test_rewordings_classify_best_effort(self):
        for goal, kind in self.REWORDS.items():
            kinds = [k["kind"] for k in router.classify(goal)]
            with self.subTest(goal=goal):
                self.assertIn(kind, kinds)

    def test_health_reword_keeps_health_gate_even_if_unmatched(self):
        plan = router.explain("i need to track my workouts and calories")
        self.assertTrue(any("health" in g.lower() or "PHI" in g for g in plan["gates"]))

    def test_posting_reword_keeps_posting_escalation(self):
        plan = router.explain("set up something that auto-publishes shorts to my channels")
        self.assertTrue(any("ESCALATION" in g and "account" in g.lower()
                            for g in plan["gates"]))

    def test_risk_gate_survives_total_fallthrough(self):
        # "money" is a risk trigger but no playbook's match/signal word, so the
        # goal routes to no kind yet must still carry the live-money gate.
        plan = router.explain("xyzzy frobnicate the money plugh")
        self.assertEqual(plan["kinds"], [])
        self.assertTrue(any("money" in g.lower() or "ESCALATION" in g
                            for g in plan["gates"]))

    # --- Finding 2: no map entry is unreachable ------------------------------
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
        self.assertIn("health-phi-compliance", [c["id"] for c in plan["capabilities"]])

    def test_mobile_build_loads_rn_patterns(self):
        plan = router.explain("build a cross-platform mobile health app")
        self.assertIn("react-native-patterns", [c["id"] for c in plan["capabilities"]])

    def test_web_only_build_omits_mobile_patterns(self):
        plan = router.explain("build a web dashboard for my team")
        self.assertNotIn("react-native-patterns", [c["id"] for c in plan["capabilities"]])

    def test_trading_app_loads_research_loop(self):
        plan = router.explain("i want a AI trading app")
        ids = [c["id"] for c in plan["capabilities"]]
        self.assertIn("trading-research-loop", ids)

    def test_finance_goal_reaches_financial_modeling(self):
        plan = router.explain("build me a DCF valuation model")
        self.assertIn("finance_deliverable", plan["kinds"])
        self.assertIn("finance-analyst", [c["id"] for c in plan["capabilities"]])

    # --- Finding 3: plain-language fields are actually carried ---------------
    def test_resolved_caps_carry_plain_language(self):
        plan = router.explain("build a personal health tracking app")
        self.assertTrue(plan["capabilities"])
        for c in plan["capabilities"]:
            with self.subTest(cap=c["id"]):
                self.assertIn("use_when", c)
                self.assertIn("not_when", c)
        self.assertTrue(any(c["use_when"] for c in plan["capabilities"]))

    # --- Finding 5: bigger gaps flagged, no spurious ones --------------------
    def test_spotify_clone_flags_licensing_gap(self):
        plan = router.explain("build a replica of spotify for me, tailored to the songs i listen")
        self.assertTrue(any("licens" in g.lower() or "catalog" in g.lower()
                            for g in plan["gaps"]))

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

    # --- Re-audit round 2 (2026-10-24): everyday-wording robustness ----------
    def test_everyday_health_wording_keeps_phi_gate(self):
        # "blood sugar"/"sleep"/"glucose" — no clinical jargon, must still gate.
        for goal in ("i'd like software to log my blood sugar and sleep",
                     "an app to track my glucose and heart rate",
                     "something to record my weight and mood every day"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertIn("build_app", plan["kinds"])
                self.assertTrue(any("PHI" in g or "health" in g.lower()
                                    for g in plan["gates"]),
                                "health risk gate must survive everyday wording")

    def test_copyright_reword_flags_licensing(self):
        # "copies netflix ... my own movies" — none of clone/replica/catalog.
        plan = router.explain("i need a program that copies netflix but only my own movies")
        surfaced = plan["gates"] + plan["gaps"]
        self.assertTrue(any("catalog" in s.lower() or "licens" in s.lower()
                            for s in surfaced))

    def test_content_engine_has_its_own_build_and_review(self):
        plan = router.explain("set up a system that keeps pumping out short clips "
                              "to my channels every day")
        ids = [c["id"] for c in plan["capabilities"]]
        for needed in ("backend-engineer", "code-reviewer", "qa-engineer"):
            with self.subTest(cap=needed):
                self.assertIn(needed, ids)

    def test_content_goal_does_not_spuriously_match_research(self):
        goal = ("build a AI content creation engine that picks a niche, creates "
                "videos and posts on my IG and YT on regular basis")
        self.assertNotIn("research", [k["kind"] for k in router.classify(goal)])

    # --- Push to 9.5: precision + completeness ------------------------------
    def test_promo_clip_for_saas_routes_to_video_not_build(self):
        # "saas" must not high-match build_app and bury the actual video intent.
        plan = router.explain("make a punchy promo clip for my saas launch")
        self.assertEqual(plan["kinds"][0], "video_recreate")

    def test_single_weak_token_does_not_create_spurious_kind(self):
        # "find" collided across vapt + research; attack phrasing must stay vapt.
        plan = router.explain("break into the staging server and find holes")
        self.assertIn("vapt", plan["kinds"])
        self.assertNotIn("research", plan["kinds"])
        self.assertTrue(any("authorized-targets.yaml" in g for g in plan["gates"]))

    def test_signup_app_routes_and_gates_personal_data(self):
        plan = router.explain("an app where users sign up with their email and profile")
        self.assertIn("build_app", plan["kinds"])
        self.assertTrue(any("security_review" in g.lower() or "personal" in g.lower()
                            for g in plan["gates"]))

    def test_personal_data_gate_survives_fallthrough(self):
        # trigger-only words (contact/phone/address) — no playbook signal.
        plan = router.explain("xyzzy keep each contact phone and address plugh")
        self.assertEqual(plan["kinds"], [])
        self.assertTrue(any("security_review" in g.lower() or "personal" in g.lower()
                            for g in plan["gates"]))

    def test_trading_app_has_full_pipeline(self):
        # completeness: a trading app is software — it must get review + verification.
        ids = [c["id"] for c in router.explain("i want a AI trading app")["capabilities"]]
        for needed in ("code-reviewer", "qa-engineer", "frontend-design"):
            with self.subTest(cap=needed):
                self.assertIn(needed, ids)

    def test_personalization_is_flagged_as_its_own_workstream(self):
        plan = router.explain("build a replica of spotify tailored to the songs i listen")
        self.assertTrue(any("ml" in g.lower() or "recommend" in g.lower()
                            for g in plan["gaps"]))

    def test_high_confidence_suppresses_stray_low_kind(self):
        # "recreate this reel" is high video; "post to instagram" must not add
        # a content_engine kind.
        plan = router.explain("recreate this reel and post to instagram")
        self.assertEqual(plan["kinds"], ["video_recreate"])

    # --- Audit round 3: risk-net vocabulary + tokenization precision --------
    PHI_NET = "PHI/privacy"  # the RISK_GATES health text, distinct from the
                             # build_app static "personal/health/financial" gate

    def test_clinical_health_words_trigger_phi_net(self):
        for goal in ("track my insulin doses",
                     "an allergy diary for my kid",
                     "a BMI calculator with history",
                     "keep track of my doctor appointments and test results",
                     "track my blood pressure and medication"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertIn("build_app", plan["kinds"])
                self.assertTrue(any(self.PHI_NET in g for g in plan["gates"]),
                                "clinical wording must hit the PHI risk net")

    def test_track_verb_does_not_fire_licensing_gate(self):
        # "tracks" (music) once stemmed to "track" and cried wolf on trackers.
        for goal in ("track my insulin doses", "track my reading habits"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertFalse(any("licensed catalog" in g.lower()
                                     for g in plan["gates"]))

    def test_the_word_test_does_not_pull_vapt(self):
        # "penetration test" must not leak the bare token "test" into vapt.
        for goal in ("test my app before launch",
                     "keep track of my doctor appointments and test results"):
            with self.subTest(goal=goal):
                self.assertNotIn("vapt", [k["kind"] for k in router.classify(goal)])

    def test_weak_tokens_do_not_fan_out_to_many_playbooks(self):
        # a running tracker must not pull trading_app / content_engine escalations.
        plan = router.explain("app to count my daily runs and km")
        self.assertEqual(plan["kinds"], ["build_app"])
        self.assertFalse(any("ESCALATION" in g for g in plan["gates"]))

    # --- Audit round 4: identity/financial PII + honest fallthrough ---------
    def test_identity_pii_triggers_data_gate(self):
        for goal in ("a spreadsheet that stores everyone's passport numbers",
                     "collect customer SSN and credit card numbers",
                     "an app that stores users date of birth and drivers license",
                     "a KYC onboarding flow with fingerprint"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertTrue(any("security_review" in g.lower()
                                    or "identity/financial" in g.lower()
                                    for g in plan["gates"]),
                                "identity/financial PII must hit the data gate")

    def test_passport_pii_gate_survives_fallthrough(self):
        # trigger-only PII words (fingerprint/iban) — no build_app signal.
        plan = router.explain("xyzzy keep each fingerprint and iban plugh")
        self.assertEqual(plan["kinds"], [])
        self.assertTrue(plan["gates"])

    def test_no_kind_no_risk_does_not_claim_gates(self):
        plan = router.explain("find a good pizza recipe")
        self.assertEqual(plan["kinds"], [])
        self.assertEqual(plan["gates"], [])
        # the gap line must NOT assert risk gates exist when none fired
        self.assertFalse(any("risk gates above still apply" in g.lower()
                             for g in plan["gaps"]))

    def test_daily_is_not_a_spurious_content_engine_signal(self):
        for goal in ("a daily journal app", "a to-do app for daily chores"):
            with self.subTest(goal=goal):
                self.assertNotIn("content_engine",
                                 [k["kind"] for k in router.classify(goal)])

    # --- Audit round 5: everyday money/crypto wording + collisions ----------
    MONEY_NET = "live money movement"

    def test_everyday_money_wording_keeps_money_gate(self):
        for goal in ("a bot that buys dips in ETH automatically",
                     "auto rebalance my bitcoin and btc holdings",
                     "sell my shares when the price drops",
                     "put my savings to work with an algo",
                     "a dashboard for my options positions"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertTrue(any(self.MONEY_NET in g.lower() for g in plan["gates"]),
                                "live-money wording must hit the money gate")

    def test_crypto_wording_routes_to_trading(self):
        plan = router.explain("a bot that buys dips in ETH automatically")
        self.assertIn("trading_app", plan["kinds"])

    def test_money_gate_survives_fallthrough(self):
        # money-only trigger words (custody/payout) — not trading_app signals.
        plan = router.explain("xyzzy custody the payout plugh")
        self.assertEqual(plan["kinds"], [])
        self.assertTrue(any(self.MONEY_NET in g.lower() for g in plan["gates"]))

    def test_money_net_no_false_positive_on_ecommerce(self):
        # generic "order" was removed from the money net; shipment/lunch orders
        # must not fire a live-money gate.
        for goal in ("track shipments for my etsy orders",
                     "place an order for lunch",
                     "a work order management tool"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertFalse(any(self.MONEY_NET in g.lower() for g in plan["gates"]))

    def test_lay_health_words_trigger_phi_net(self):
        for goal in ("keep a diary of my migraines and the meds I took",
                     "log the pills I take each morning",
                     "track my anxiety and therapy sessions"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertTrue(any("PHI/privacy" in g for g in plan["gates"]))

    def test_share_verb_does_not_fire_money_gate(self):
        # "my shares" is a multi-word trigger; the bare verb "share" must not be.
        for goal in ("share photos with my family",
                     "recreate this reel and share a instagram link"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertFalse(any(self.MONEY_NET in g.lower() for g in plan["gates"]))

    # --- Audit round 6: stemmer/token collisions on core classes -----------
    def test_security_does_not_fire_money_gate(self):
        # "securities" (money) once stemmed to "security", firing the money gate
        # on every VAPT/security goal.
        for goal in ("do a security audit of my backend",
                     "find security holes in my web app",
                     "add security headers to my app"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertFalse(any(self.MONEY_NET in g.lower() for g in plan["gates"]))

    def test_security_intent_routes_to_vapt(self):
        for goal in ("do a security audit of my backend",
                     "check my staging site for weaknesses before launch",
                     "find security holes in my web app"):
            with self.subTest(goal=goal):
                self.assertIn("vapt", [k["kind"] for k in router.classify(goal)])

    def test_bare_license_does_not_fire_pii_gate(self):
        for goal in ("add an open-source license to my repo",
                     "a license plate reader for my parking lot"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertFalse(any("identity/financial" in g.lower()
                                     for g in plan["gates"]))

    def test_drivers_license_still_gates_as_pii(self):
        plan = router.explain("an app that stores users drivers license and dob")
        self.assertTrue(any("security_review" in g.lower() or "identity/financial"
                            in g.lower() for g in plan["gates"]))

    def test_generic_audit_does_not_fire_vapt(self):
        for goal in ("do a code audit of my repo", "a financial audit dashboard"):
            with self.subTest(goal=goal):
                self.assertNotIn("vapt", [k["kind"] for k in router.classify(goal)])

    # --- Audit round 7: portfolio misroute, payments net, generic demotions -
    def test_portfolio_site_is_not_trading(self):
        for goal in ("make a portfolio website to show my design work",
                     "make me a portfolio site for my photography"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertNotIn("trading_app", plan["kinds"])
                self.assertFalse(any(self.MONEY_NET in g.lower() for g in plan["gates"]))

    def test_investment_portfolio_still_routes_trading(self):
        for goal in ("track my investment portfolio",
                     "rebalance my stock portfolio"):
            with self.subTest(goal=goal):
                self.assertIn("trading_app", [k["kind"] for k in router.classify(goal)])

    def test_payments_and_bank_goals_hit_a_financial_gate(self):
        for goal in ("an e-commerce store with stripe checkout",
                     "a budgeting app that connects to my bank",
                     "a personal finance app that imports my bank transactions",
                     "help me pick mutual funds for retirement",
                     "an agent that manages my 401k"):
            plan = router.explain(goal)
            gl = " ".join(plan["gates"]).lower()
            with self.subTest(goal=goal):
                self.assertTrue("payments or financial" in gl or self.MONEY_NET in gl,
                                "money/payments goal must carry a financial gate")

    def test_common_words_do_not_fire_money_gate(self):
        for goal in ("fix the css margin and leverage flexbox for the layout",
                     "the client wants a hedge against vendor lock-in",
                     "estimate the cost savings for q3",
                     "give me a few options for the onboarding flow"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertFalse(any(self.MONEY_NET in g.lower() for g in plan["gates"]))

    def test_generic_tokens_do_not_create_spurious_kinds(self):
        # options/margin/leverage/hedge/target/marketing-copy must not route.
        for goal in ("give me a few options for the onboarding flow",
                     "fix the css margin and leverage flexbox for the layout",
                     "who is the target audience for this landing page"):
            with self.subTest(goal=goal):
                kinds = [k["kind"] for k in router.classify(goal)]
                self.assertNotIn("trading_app", kinds)
                self.assertNotIn("vapt", kinds)

    def test_vulnerable_wording_routes_vapt(self):
        for goal in ("is my login flow vulnerable? please test it",
                     "test my app for security issues"):
            with self.subTest(goal=goal):
                self.assertIn("vapt", [k["kind"] for k in router.classify(goal)])

    # --- Audit round 8: two-tier risk net (strong vs weak triggers) ---------
    # Precision: ordinary engineering sentences must NOT trip a risk gate. Each
    # contains a single weak token (token/checkout/clone/users/steps/...) that
    # used to fire a hard-stop. A weak trigger now needs >=2 distinct hits.
    ENGINEERING_SENTENCES = [
        "add jwt token refresh to the api client",
        "git checkout the release branch and tag it",
        "clone the repo into the ci runner",
        "return 401 unauthorized when the header is missing",
        "let users filter the table by column",
        "add setup steps to the readme",
        "increase the font weight on the headings",
        "use stock photos on the landing page",
        "profile the slow function in the parser",
        "mirror the docker images to our registry",
        "there is a trade-off between latency and cost",
        "set the performance budget for the bundle",
        "stream the logs to the console",
        "publish the npm package on release",
        "write a post-mortem for the outage",
        "use a sorting algo that is stable",
        "list the pain points in the current checkout flow",
        "give me a few options for the onboarding flow",
    ]

    def test_engineering_jargon_does_not_trip_risk_gates(self):
        for goal in self.ENGINEERING_SENTENCES:
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertEqual(plan["gates"], [],
                                 f"ordinary dev sentence tripped a gate: {plan['gates']}")

    # Recall: real goals phrased in lay/natural language still gate. Each uses a
    # strong trigger or >=2 weak triggers in one class.
    def test_lay_wordings_keep_their_gate(self):
        cases = [
            ("help me track what I eat and how much I move each day", "PHI"),
            ("log my runs and gym sessions", "PHI"),
            ("track my cycle", "PHI"),
            ("log the pills I take each morning", "PHI"),
            ("pay my contractors every month from the app", "payments or financial"),
            ("put this video on my youtube channel", "ESCALATION"),
            ("is my website hackable", "authorized-targets"),
            ("find the weak points in our login flow", "authorized-targets"),
            ("check whether our api can be broken into", "authorized-targets"),
            ("try to get into my app without a password", "authorized-targets"),
            ("can someone hack my app", "authorized-targets"),
            ("a dashboard for my options positions", "live money"),
            ("put my savings to work with an algo", "live money"),
        ]
        for goal, needle in cases:
            gl = " ".join(router.explain(goal)["gates"]).lower()
            with self.subTest(goal=goal):
                self.assertIn(needle.lower(), gl, f"lay goal shed its gate: {goal}")

    def test_stemmer_handles_es_plurals_of_e_words(self):
        # "-es" plural of an "-e" word must stem to the singular, not drop the e.
        for word, singular in (("medicines", "medicine"), ("doses", "dose"),
                               ("shares", "share"), ("invoices", "invoice"),
                               ("allergies", "allergy")):
            with self.subTest(word=word):
                self.assertEqual(router._stem(word), router._stem(singular))

    def test_medicine_plural_goal_gates(self):
        for goal in ("an app for my medicines",
                     "a medicine reminder app that tracks my pills"):
            with self.subTest(goal=goal):
                plan = router.explain(goal)
                self.assertTrue(any("PHI/privacy" in g for g in plan["gates"]))

    def test_lay_verb_forms_keep_health_gate(self):
        # irregular/other forms: slept, ate, felt, weigh
        for goal in ("an app where i jot down how i slept and what i ate",
                     "log what i ate and how i felt after"):
            with self.subTest(goal=goal):
                plan = router.explain(goal)
                self.assertTrue(any("PHI/privacy" in g for g in plan["gates"]))

    def test_period_tracker_loads_phi_step(self):
        plan = router.explain("an app that tracks my periods")
        self.assertIn("health-phi-compliance",
                      [c["id"] for c in plan["capabilities"]])

    # --- Audit round 10: recall closers (shell/card/deposit/brands/moods) ---
    def test_exploitation_phrasings_hit_authorized_gate(self):
        for goal in ("run an attack against my staging site to pop a shell",
                     "get a reverse shell on the box",
                     "try sql injection on the login"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertTrue(any("authorized-targets.yaml" in g for g in plan["gates"]))

    def test_card_and_billing_hit_payments_gate(self):
        for goal in ("subscription billing with stored card details",
                     "save my customers card details on file"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertTrue(any("payments or financial" in g.lower()
                                    for g in plan["gates"]))

    def test_deposit_withdraw_hits_money_gate(self):
        plan = router.explain("let users deposit cash and withdraw to their bank")
        self.assertTrue(any("live money" in g.lower() for g in plan["gates"]))

    def test_more_streaming_brands_flag_licensing(self):
        for goal in ("rebuild disney plus including all the shows",
                     "an app like hulu for my own videos"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                gl = " ".join(plan["gates"]).lower()
                self.assertTrue("catalog" in gl or "licens" in gl)

    def test_buy_sell_execute_phrasings_route_and_gate_trading(self):
        for goal in ("an app that buys and sells stocks for me",
                     "an app that executes trades automatically",
                     "a bot that places market orders for me"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertIn("trading_app", plan["kinds"])
                self.assertTrue(any("live money" in g.lower() for g in plan["gates"]))

    def test_ordinary_buy_sell_does_not_fire_money(self):
        for goal in ("sell my old furniture online", "buy groceries list app",
                     "a stock photo gallery"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                self.assertFalse(any("live money" in g.lower() for g in plan["gates"]))

    def test_brand_with_plus_glyph_flags_licensing(self):
        # "disney+" must gate the same as "disney plus" — the + is normalized.
        for goal in ("clone disney+ with my own library", "build a disney+ clone"):
            plan = router.explain(goal)
            with self.subTest(goal=goal):
                gl = " ".join(plan["gates"]).lower()
                self.assertTrue("catalog" in gl or "licens" in gl)

    def test_feed_rebuild_is_not_posting_but_my_feed_is(self):
        self.assertFalse(any("ESCALATION" in g for g in
                             router.explain("schedule a nightly cron to rebuild the feed")["gates"]))
        self.assertTrue(any("ESCALATION" in g for g in
                            router.explain("post updates to my feed automatically")["gates"]))

    def test_mood_diary_gates_but_single_feel_does_not(self):
        self.assertTrue(any("PHI/privacy" in g for g in
                            router.explain("keep a diary of my moods and how i feel")["gates"]))
        # a lone "feel" in a non-health sentence must not gate
        self.assertFalse(any("PHI/privacy" in g for g in
                             router.explain("how do i feel about the new layout")["gates"]))

    def test_single_weak_token_alone_does_not_gate(self):
        # one weak token in isolation must not fire (distinct-stem count == 1)
        for goal in ("add a token bucket rate limiter",
                     "a page that lists all users",
                     "add a ticker tape widget to the header"):
            with self.subTest(goal=goal):
                # may or may not classify, but no risk gate from a lone weak word
                gates = router.explain(goal)["gates"]
                self.assertFalse(any("ESCALATION" in g or "PHI" in g for g in gates))


class ResolveStepTest(unittest.TestCase):
    """The two computed-gap paths in _resolve_step. The T4-only branch is a
    forward-guard (the live map has no T4 entry), exercised directly here."""

    def test_t4_only_supplier_becomes_gap(self):
        idx = {"x_tag": [{"id": "x", "kind": "catalog_unit", "ref": "r", "trust": "T4"}]}
        chosen, gaps = router._resolve_step(["x_tag"], idx)
        self.assertEqual(chosen, [])
        self.assertTrue(any("only T4" in g for g in gaps))

    def test_missing_tag_becomes_gap(self):
        chosen, gaps = router._resolve_step(["nope_tag"], {})
        self.assertEqual(chosen, [])
        self.assertTrue(any("no capability in the map" in g for g in gaps))


if __name__ == "__main__":
    unittest.main()
