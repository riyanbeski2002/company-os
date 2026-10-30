# Known routing/staffing gaps

Defects in company-pm's goal-routing layer (`config/capability-map.yaml`,
`config/playbooks.yaml`, `tools/capability_router.py`, `agents/company-pm.md`),
found by reading the wiring, not by running a session to failure first. Same
rigor as `KNOWN_ISSUES.md`: finding, evidence, fix, nothing softened.

This file is the running list. Add to it as more gaps surface — the point is
to find them before they cost a week of real work, not just the three below.

**All four below are fixed as of 2026-10-29**, via a general mechanism rather
than four one-off patches: `capability-map.yaml` entries can now carry
`confirm: true`. Such a supplier is real, trusted (T0-T3), and wired into the
router — it is never a gap — but is never auto-chosen either; it surfaces in
`explain()`'s new `needs_confirmation` list for the PM to ask Riyan about once.
`route()`'s `prepare_actions` only ever comes from auto-chosen capabilities, so
a `confirm: true` entry is never silently cloned or loaded. This is the
standing answer to gap #3's "this will keep recurring": the next onboarded-
but-risky-to-auto-select capability gets `confirm: true` and a wired map/
playbook entry, not left unwired until someone notices. See
`tools/capability_router.py::_resolve_step` and
`tests/test_capability_map.py::KnownGapsClosedTest`/`ResolveStepTest`.

---

## 1. `video_recreate`/`content_engine` never staff an agent, and have no review gate — HIGH

**Status.** Fixed. `video-editor` wired into `capability-map.yaml` (`video_build`), `video_recreate`/`content_engine` require it (`confirm: true` — ask before staffing), and both playbooks now end in a `video_quality_check` step (see #4) instead of stopping at render.

**Finding.** Every `requires:` tag in the `video_recreate` and `content_engine`
playbooks resolves to a `kind: catalog_unit` entry in `capability-map.yaml`
(`hyperframes`, `media-use`, `reel-recreate`, `ffmpeg`, `product-launch-video`,
`motion-as-code`) — skills to load, not a worker to staff. The `video-editor`
Tier-2 agent exists and is documented in `agents/company-pm.md:468` as the
right owner for rendered-video work, but it is referenced nowhere in
`capability-map.yaml` and provides no `requires:` tag any playbook step asks
for. `route()`/`explain()` — the output company-pm is supposed to act on
without guessing — never names it. On top of that, `video_recreate` is the
only content-producing playbook with no `code_review`/`verification` step;
`build_app` and `content_engine` both end in `code_review` → `verification`,
`video_recreate` ends at `video_transform` and stops.

**Evidence.**
```
config/capability-map.yaml: grep "video-editor" -> no hits
config/playbooks.yaml (video_recreate, lines 159-186): steps end at
  `requires: [video_transform]`, no code_review/verification step
config/capability-map.yaml lines 139-178: hyperframes/media-use/reel-recreate/
  ffmpeg/product-launch-video are all `kind: catalog_unit`
```

**Why it matters.** A week-long video session with no good output is the
predicted outcome of this wiring: nobody is staffed with ownership of the
deliverable in a worktree with acceptance criteria, and nothing checks a
render against the brief before the PM can call it done.

**Fix (not yet applied).** Add a `video-editor` entry to `capability-map.yaml`
(`kind: agent`, providing e.g. `video_build`), make `video_recreate`'s
`video_compose`/`animation` step require it instead of (or alongside)
`hyperframes`, and add `code_review`/`verification`-equivalent steps to both
video playbooks so a render is checked against the clarify-phase brief
(message, CTA, aspect ratio/length) before ship.

---

## 2. `morluto-rea` is registered and indexed but completely unwired from routing — HIGH

**Status.** Fixed. Added the `reverse_engineer` playbook kind and a `morluto-rea` map entry (`confirm: true` — the registry's own bought-engagement flag means this one is never loaded without asking).

**Finding.** `morluto-rea` (reverse-engineering agent, T3, approved
2026-10-16) exists in `config/capability-registry.yaml` and
`config/capability-index.yaml` with real skill units
(`reverse-engineer-anything`, `rea-ci-tests-audit`, etc.). It appears in
**zero** entries of `config/capability-map.yaml` and **zero** `kind:` values
in `config/playbooks.yaml`. `classify()` has no playbook to route a "reverse
engineer this" goal to, and `route()` has no capability-map entry to resolve
even if a kind existed.

**Evidence.**
```
grep -c "morluto-rea\|reverse" config/capability-map.yaml   -> 0
grep -n "  - kind:" config/playbooks.yaml                   -> build_app,
  trading_app, video_recreate, content_engine, vapt, research,
  finance_deliverable (no reverse-engineering kind)
```

**Why it matters.** This is the specific case Riyan hit: Claude "is unable to
run REA because company-os fails to staff and execute it properly." It is not
a classifier precision/recall bug (that's `doc/CAPABILITY-ROUTER-FIXES.md`'s
scope) — it is a capability that was onboarded and then never connected to
the thing that is supposed to make it reachable without the user having to
say how.

**Fix (not yet applied).** Add a `reverse_engineer` playbook kind (match
phrases: "reverse engineer", "decompile", "how does this binary/app work",
"REA this") with a `requires: [reverse_engineering]` step, and a
`capability-map.yaml` entry for `morluto-rea` providing that tag, `kind: tool`
or `kind: repo` per its registry `type`, trust mirrored as T3. Given the
registry's own bought-engagement flag on this repo, the map's `use_when`
should repeat the caution rather than hide it, same as the registry does.

---

## 3. Unwired capabilities silently fall back to `backend-engineer` — MEDIUM, same root cause as #2

**Status.** Fixed for the concrete case (#2). The general fallback rule is also now explicit in `agents/company-pm.md`'s goal-intake protocol: an unmatched goal is named as unmatched, never silently handed to `backend-engineer`.

**Finding.** `backend-engineer`'s `use_when`/`not_when` in `capability-map.yaml`
are correctly scoped ("APIs, services, data models, business logic inside
owned globs" / "not pure UI work"). The overstaffing Riyan is seeing is not
`backend-engineer` reaching outside its lane — it is company-pm, finding no
capability-map entry for the actual job (REA being the concrete case), falling
back to "this needs code written" and reaching for the generic coding agent
because nothing more specific was ever wired in. Confirmed: every current
`requires: [backend_build]` step in the three playbooks that use it
(`build_app`, `trading_app`, `content_engine`) is legitimately backend work —
the mis-staffing happens off-playbook, when a goal matches nothing and
company-pm improvises.

**Evidence.** `grep -B3 "requires:.*backend_build" config/playbooks.yaml` shows
all three uses are genuine (data model/API work, a trading engine's execution
layer, a content pipeline's queue/scheduler) — none is a case of `backend_build`
standing in for a more specific missing tag.

**Why it matters.** This will keep recurring for every capability like #2:
onboarded into the registry, never wired into the map, so the PM's only
fallback is the generalist. The fix is not "constrain backend-engineer" — it's
closing wiring gaps like #2 as they're found, and (separately, if this keeps
happening) giving company-pm an explicit "no capability-map entry matches —
say so and ask, don't default to backend-engineer" rule for the no-match case.

**Fix (not yet applied).** Covered by #2's fix for the REA case specifically.
Generally: audit `capability-registry.yaml`/`capability-index.yaml` entries
against `capability-map.yaml` for onboarded-but-unwired capabilities (this is
the audit Riyan asked to run next), and add a fallback rule to
`agents/company-pm.md`'s goal-intake protocol: an unmatched goal is named as
unmatched, not silently handed to backend-engineer.

---

## 4. `video-editor`'s own registered toolset is invisible to the router — HIGH, found by auditing registry vs. map

**Status.** Fixed. Seven entries wired into `capability-map.yaml`, all `confirm: true`: `video-editor`, `buildwithdarius-reel-editor` (`video_quality_check` — now a required step in both video playbooks, not optional), `diffusionstudio-core`/`diffusionstudio-editor`/`remotion-dev-skills` (`video_render_alt`), and the two placement MCPs (`video_placement`). Sharper restatement of #1, found by diffing all 116
`capability-registry.yaml` entries against `capability-map.yaml`'s 25 wired
`ref`s.

**Finding.** Most of the ~110 unwired registry entries are correctly unwired
— `capability-map.yaml`'s own header says it only wires what's "worth routing
to," the rest stays browsable via `company capability search`. But seven
entries each name `video-editor` specifically in their own `purpose:` text as
the intended consumer, are documented by hand in `agents/video-editor.md`,
and are still absent from `capability-map.yaml` and every playbook:

- `buildwithdarius-reel-editor` (T3) — the actual **quality doctrine**: cut
  on the audio RMS envelope, no gap over 0.25s, nothing frozen past 2s, a new
  visual every 2–3s, -14 LUFS/-1 dBTP, and a self-check that pulls a frame at
  every cut and looks at it before showing anyone.
- `diffusionstudio-core` + `diffusionstudio-editor` (T2) — an alternate
  WebCodecs render path to HyperFrames/Remotion.
- `remotion-dev-skills` (T3) — the React-composition second option Riyan
  explicitly asked to keep.
- `hetpatel-11-adobe-premiere-pro-mcp`, `samuelgursky-davinci-resolve-mcp`,
  `hiteshk03-davinci-resolve-mcp` (T2) — real-timeline placement tools (the
  Resolve Free-vs-Studio distinction is already correctly reasoned through in
  the registry's own purpose text).

**Evidence.**
```
grep -c "<each id above>" config/capability-map.yaml   -> 0 for all seven
agents/video-editor.md lines 178-251: all seven documented in prose only
```

**Why it matters.** This is a better explanation than #1 alone for a week of
video work with no good output: `buildwithdarius-reel-editor` is the one
resource whose entire purpose is catching a bad cut before it ships (frame-
by-frame self-check, loudness spec, pacing rule), and nothing in the routing
layer requires or even surfaces it. A session can staff `video-editor`
correctly and still never load the thing that would have caught the defect,
because discovering it depends on the worker reading its own agent file's
prose rather than anything `route()` returns.

**Fix (not yet applied).** Same fix as #1, more specific: once `video-editor`
has a `capability-map.yaml` entry (`kind: agent`), add a `video_quality_check`
`provides` tag for `buildwithdarius-reel-editor` and make it a **required**
step (not optional) in `video_recreate`/`content_engine` before
`video_transform` — this is the review gate those playbooks are missing, not
a generic `code_review`. Wire the two render-path alternatives
(`diffusionstudio-*`, `remotion-dev-skills`) and the two placement MCPs as
`not_when`-disambiguated alternates on the same `video_compose`/
`video_placement` tags, so the router states the choice instead of leaving it
to prose only video-editor's own file carries.

---

## 5. Audio had no quality-check gate either, and nine more registered video/audio capabilities sat unwired — HIGH, found by `tools/capability_gap_audit.py`

**Status.** Fixed, 2026-10-29. `tools/capability_gap_audit.py` added (the
deterministic version of the by-hand registry-vs-map diff used to find #1-#4)
and run against the live registry.

**Finding.** `leonxlnx-earshot` — the audio-side equivalent of
`buildwithdarius-reel-editor`: LUFS/true-peak/spectrum measurement, a
sound-design critique with a ranked fix list — was registered T2 and
completely unwired. Same shape as #1/#4, just for audio: nothing in
`video_recreate`/`content_engine` required an `audio_quality_check` tag,
so a video could pass its visual quality gate with broken audio and nobody
would know. The audit tool also turned up a confirmed regex bug of its own
(`_names_agent` escaped the joined character-class string instead of each
piece before joining, so `[ -]` became the literal text `\[ \-\]` and the
tool silently failed to match any hyphenated agent name, including
`video-editor` — fixed same day, see `ResolveStepTest`-adjacent tests) —
worth recording here because it's the exact "a check that already exists but
sits silently broken is the finding" case this tool exists to catch in
*other* code, and it caught the mistake in itself first.

Once the regex was fixed, the tool correctly surfaced `0xsline-openchatcut`
(video placement, AGPL — real local editable app, alternate to the Premiere/
Resolve MCPs), `sunwood-ai-labs-hyperframes-motion-reel-skill` (HyperFrames-
native showreel motion graphics), `abubakrchan-product-launch-motion` and
`higgsfield-motion`/`higgsfield-motion-saas` (promo/render-path alternates,
the latter two with no formal license — flagged, not hidden), and
`fishaudio-fish-audio-plugin`/`resembleai-chatterbox` (voiceover alternates —
cloud and local-monetizable voice cloning respectively) as genuine misses:
each purpose text named `video-editor` or an already-wired HyperFrames
capability directly.

**Fix.** All twelve wired into `capability-map.yaml`, `confirm: true`. New
`audio_quality_check` tag required by both video playbooks; `voiceover`
(previously a provided-but-never-required bonus tag on `media-use`) is now
explicitly required alongside `media_sourcing`, so its four new confirm-gated
alternates are reachable. `tests/test_capability_map.py::KnownGapsClosedTest`
covers all three waves.

**Second pass, same day:** Riyan pushed back on the first wave's "already
decided, not an oversight" list — reasonably: three of those five turned out
to be inconsistently-applied exclusions, not real ones. `harry0703-
moneyprinterturbo` and `k2-fsa-omnivoice`/`debpalash-voicestudio` had only
been marked "reference only"/"metadata-only review" at adoption time, which
records that no deep review happened, not that they were rejected — unlike
`imaginpro-imaginepro-claude-plugin`, which the registry records as
**actively evaluated and rejected** for swapping one paid vendor for another.
And `debpalash-voicestudio`'s AGPL-3.0 had been treated as disqualifying
while `0xsline-openchatcut`'s identical AGPL-3.0 was wired the same day with
a "fine standalone, flag redistribution" caveat — the same license applied
two different ways in one pass is the kind of inconsistency this file exists
to catch, including in its own work. All three now wired the same way as
`0xsline-openchatcut`. **Left unwired, for reasons distinct enough to survive
a second look:** `tuzhechen2005-painted-animation` (not a standalone
capability — it's reelmimic's own internal sub-dependency, already reachable
through the already-wired `edenfunf-reelmimic`), `jimliu-baocut` (T4 —
wiring it would be cosmetic: `_resolve_step`'s `AUTO_TIERS` filter runs
before the `confirm` check, so a T4 supplier never appears in `chosen` or
`needs_confirmation` regardless, and `video_placement` already has three
non-T4 suppliers so it wouldn't even surface as a "T4-only" gap message),
`openwhispr-openwhispr` (wrong direction entirely — speech-to-text dictation,
not text-to-speech voiceover generation), `imaginpro-imaginepro-claude-plugin`
(stands: an explicit prior rejection on record, not a stale default),
`calesthio-openmontage` (stands: AGPL-3.0, 700+ files, a whole competing
production system — "one resource for one purpose," not this, unless Riyan
names a specific piece).

---

## 6. `legal-analyst` had a map entry but no playbook route — HIGH, found by auditing every agent, not just video-editor

**Status.** Fixed, 2026-10-30.

**Finding.** Riyan asked the broader version of the video-editor question:
does every agent have its relevant skills actually wired, or just
referenced? Checked by computing, for every `kind: agent` entry in
`capability-map.yaml`, whether any of its `provides` tags is required by any
playbook step. Ten of eleven agents passed. `legal-analyst` did not:
`capability-map.yaml` carried a full entry (`use_when: "Contract/NDA review
against a playbook..."`, correctly scoped `not_when`, `provides:
[legal_review, compliance_flag]`) but `legal_review` appeared in zero
playbook steps, and no playbook kind matched "review this contract,"
"NDA triage," or anything like it. `compliance_flag` was reachable, but only
as an ancillary gate inside `build_app`/`trading_app`/`finance_deliverable` —
never as legal-analyst's actual job, contract/NDA review itself.

**Evidence.**
```
grep -n "legal\|contract\|nda" config/playbooks.yaml   -> 0 hits before the fix
```
A map entry existing is necessary but not sufficient — this is exactly
`agents/video-editor.md`'s original problem (known-to-prose, invisible to
`classify()`), on a different agent, found by checking systematically instead
of waiting for it to cost a session.

**Fix.** New `legal_review` playbook kind, routing to `legal-analyst` via the
already-`provides`d `legal_review` tag — not `confirm: true` (unlike the
video/REA additions): this is a first-party T0 agent doing exactly its
documented job, not a newly-wired third-party resource. Carries its own gate
("assists, never replaces, licensed counsel"). `EveryAgentIsReachableTest`
in `tests/test_capability_map.py` now asserts this for every agent going
forward, not just checks it once: a future agent added to the map without a
real route fails the suite instead of sitting silent until someone notices.
The four advisor agents (`cfo`/`ciso`/`coo`/`cto-advisor`) are correctly
absent from `capability-map.yaml` entirely — they run on a separate,
unprompted dispatch (`company advise`), not the goal router, confirmed by
reading `cli.py`'s `advise.OFFICERS` mechanism, not assumed.

---

## 7. No live channel for concurrently running subagents to avoid duplicating each other's exploration

**Status.** Fixed, 2026-10-30.

**Finding.** Riyan pointed at `microsoft/Agensh` (a Microsoft Research
multiagent harness, arXiv 2609.26781) and asked for its *mechanisms* mined
into real company-os skills/features — explicitly not a reference entry,
not an adoption, not anything run. Read its actual source (not the paper):
`board-service/shared_lessons.py`, `verifier.py`, and
`mini-router/src/dispatcher.ts`. Three mechanisms were real and not already
covered by anything in this repo:

1. A typed, terse, peer-visible note (their vocabulary: FACT / OBSERVED /
   FAIL / CLAIM / PATCH_SUMMARY) that lets one concurrently running agent
   tell its peers "I already falsified that" or "I'm taking this angle" —
   company-os's existing `lessons.py` is PM-curated and post-hoc, never
   published live by a running subagent to its peers mid-task.
2. A deterministic text gate rejecting placeholder evidence ("should work",
   "pending", "TBD") specifically on a completion claim, before it would
   even reach a gate — the same failure mode `eventlog.py`'s
   `_rejects_stale_gate_verdict` already catches one layer later, at a real
   PASSED/FAILED verdict, but with nothing catching it earlier.
3. A self-expiring claim (TTL) instead of a lock, and a check for a turn
   that produced real work but published nothing peers could use (their
   dispatcher's "forced-write nudge").

None of this applies to the standard single-worker Tier-2 pipeline — a
task's owned file globs already prevent two workers colliding on the same
code, and `gategroup.py` already merges/reviews the result. The gap is fan-
out work with no such structural protection: parallel debugging, parallel
research subagents, parallel gap-finding (the kind of work this very
conversation did, by hand, to find gaps #1-6 above).

**Fix.** `tools/company/board.py` (new): `BOARD_NOTE` event type (added to
`eventlog.py`'s `EVENTS`, validated by `board.validate_note`), six note
types (`FACT`/`OBSERVED`/`FAIL`/`CLAIM`/`DONE_SUMMARY`/`DIRECTIVE` — renamed
from Agensh's vocabulary to fit this repo's conventions, and `DIRECTIVE`
added for company-pm to redirect every peer on a subject at once, the
equivalent of their deadline-phase `@all` broadcasts), a deterministic
evidence gate on `DONE_SUMMARY` content, TTL-expiring `CLAIM`s, and `FAIL`
invalidating the same actor's own later `CLAIM`/`DONE_SUMMARY`. No separate
service, no database — one event in the existing append-only log, folded on
read exactly like every other derived view in this system (`taskstate.py`'s
own pattern), consistent with D1 (the log is the only authoritative state).
`company board note/read/check` (CLI), 28 new tests
(`tests/test_board.py`, `tests/test_board_cli.py`) plus two in
`test_eventlog.py`. Documented in `agents/company-pm.md`, scoped explicitly
to fan-out work. No new agent: company-pm already fills the coordinator
role this would otherwise duplicate.
