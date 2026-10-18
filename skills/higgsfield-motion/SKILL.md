---
name: higgsfield-motion
description: Design motion-design key frames, styleboards and code-rendered films (HTML/CSS/SVG/WebGL → PNG stills, MP4 with music and SFX) in ANY identity and Google Font, using the HFT token system (12 presets, 11 genres, derive() for new identities, Higgsfield as one brand) and a Russian handbook of frame laws from 84 launch films. Covers scenarios and launch / product / SaaS ad films that mix Higgsfield generations (Soul 2, Nano Banana, Seedance) with code motion, motion blur, sound (a cut track or a synthesised score) and frame-level QA. Use for frames, a storyboard, a styleboard, kinetic type, a logo ident, a launch / product / brand film or ad in code, a visual identity or tokens for motion, or Higgsfield-style frames. RU — моушн-дизайн, кадры для моушна, раскадровка, стайлборд, сценарий ролика, лаунч-ролик, рекламный ролик, ролик с генерациями, музыка к ролику, айдентика, токены.
---

# Higgsfield Motion: frames and films in any identity

Turns a brief into **beautiful, coherent key frames and short code-rendered films with sound**, for any brand, style or font. Three layers: universal laws, style axes + presets, brands (Higgsfield is one example). Visuals come from tokens (`scripts/hf-tokens.js`), the *why* from the handbook (`references/parts/`, Russian), taste from `references/client-taste.md` (**read before designing**), process from `references/production-lessons.md`.

## Working with this user (read first)

- **Something visible within 10–15 min**, before any infrastructure or agent workflow (a script, or a storyboard on grey stubs). Then send each deliverable the moment it exists. Never 15–20 min without a visible change. [P-01]
- **Status questions** («что там?», «сколько еще ждать?»): clock time · what changed · current stage · an image or video if one exists · a clock-time ETA (never «не скажу») · an offer to stop and ship. [CM-01]
- **Films start with the scenario**, sent before anything is built. "Scenario first" means deliver only that and stop. [S-01]
- **Calibrate before fan-out:** ~5 key frames for a new direction, 2–3 stills before a film-wide palette or font switch. [P-03]
- **«стоп», «пока стоп», «пока не надо», «все не надо»:** halt every workflow, generation and render at once, confirm nothing still spends credits, say what is done and resumable. [P-05]
- **At most one review round between client rounds.** Ship interims with sound and let the user review. More in `production-lessons.md` §0. [Q-05]

## Files

| Path | What it is |
|---|---|
| `scripts/hf-tokens.js` | **The token system** (~730 KB, no deps; browser `window.HFT`, Node `require`): 12 presets, the Higgsfield brand (+ the user's own tokens.json as `.legacy`), genres, modules, `theme()`, `derive()`, `defineBrand()`, `validate()`, exporters, timing helpers. |
| `scripts/hf-motion.js` | Deterministic motion helpers driven by the theme's motion personality. |
| `scripts/setup.sh` | Once per machine: checks Node 22+, browser, swiftc, afconvert; compiles the Swift tools into `${HFT_BIN:-~/.cache/higgsfield-motion/bin}` (`$B` below). |
| `render.mjs` · `capture.mjs` · `strip.mjs` · `cdp.mjs` | Stills (size from `<meta name="frame">`; WebGL: `capture.mjs --stills`) · frame-exact capture of `__seek(t)` pages (`--stills --query --size --draft --workers --mb --shutter --check-determinism --lenient`) · strips (`--fps`) · the shared browser launcher. |
| `encode` · `encode_av` · `mux` · `master` (`.swift`) | Frames → silent H.264; frames + WAV in one pass; MP4 + .m4a mux; loudness master. |
| `music_window.py` · `cut_audio.py` · `render_audio.mjs` + `assets/templates/audio/score.html` | Supplied track: best window and hits, then the cut. No track: a score / SFX synthesised in code. |
| `extract.swift` + `assets/templates/shared/clips.js` | Footage → frames at native fps; the page-side clip player (clamps, never loops). |
| `probe.swift` · `fdiff.swift` · `activity.mjs` · `textcheck.mjs` | QA: encoded duration / fps / codec / audio + check frames; frame-diff spikes and freezes; dead air; effective text size and worst-pixel WCAG / APCA. |
| `references/client-taste.md` · `production-lessons.md` | Taste by topic · cadence, communication, orchestration, scenario, motion recipes, product films, generations / Higgsfield MCP, sound, rendering, QA checklist, delivery. |
| `assets/templates/` | `styleboard/` (4-archetype frames per preset, the best starting code) · `motion_demo/` (4 s template, `?style=` switches identity) · `shared/hero-glyph.js` (the 7-bar capsule wave per material). |

### Handbook map (`references/parts/`, Russian, ~1.3 MB: **never read it whole**, open only the part you need)

| Need | File in `references/parts/` |
|---|---|
| 15 rules, du, formats, safe areas, grid, composition archetypes, density, depth, "frame in 10 steps", 16:9 → 9:16 | `10_part1a_frame.md` |
| Type, legibility, reading time, localization, colour & light, contrast, materials, components | `11_part1b_type_colour.md` |
| Timing (fps / BPM), narrative templates, easing, motion grammar, transitions, camera | `12_part1c_motion_time.md` |
| Generations, 14 modules, honesty, beautiful-frame checklist & anti-patterns, production, passport | `13_part1d_practice.md` |
| Style axes, preset cards, genre × style matrix, brand schema, font pairings, `derive()` | `20_part2_3_styles_derive.md` |
| Exact token names and values | `40_part4_tokens.md` |
| Higgsfield: DNA, lime, worlds, registers A–E, motifs, film passport, launch ledger, recipes | `50_part5a_higgsfield.md` |
| 34 Higgsfield archetypes with Figma ids, usable in any style | `51_part5b_archetypes.md` |
| Evidence and sources | `60_part6_sources.md` |

Search all: `grep -n "^## \|^### " references/parts/*.md | grep -i <topic>`.

## Workflow

1. **Brief, passport, scenario.** Fill `HFT.templates.brief`: purpose, audience, key message, language, genre, style or brand, format(s), duration, fps / BPM, required text, assets, CTA.
   - A film also gets a passport (`13_part1d` → «Паспорт проекта»): one set of fonts, motif, palette and motion signature. Rules lifted at the user's request go in as exceptions, in the user's words. [P-14]
   - **Write the film's scenario and send it before building** [S-01, S-02, C-02]: idea and acts; a shot table on the beat grid (time · picture · camera · on-screen text · sound · sparse/dense, alternating every 1–2 cuts); a trigger map (time · visible cause in shot A · effect · how the camera follows); ≤2 decision questions.
2. **Pick the job and the look.**
   - **Genre:** `productDemo, explainer, brandFilm, kineticType, logoIdent, dataStory, editorialTitles, characterMotion, spatial3d, broadcastPackage, musicVisual` (inputs, flow, checks: `HFT.genres`).
   - **Style:** a preset (`higgsfield, swiss-editorial, luxury-serif, playful-pop, cinematic-noir, soft-pastel-ui, tech-terminal, brutalist-raw, organic-editorial, y2k-chrome-modern, kinetic-type, dot-matrix`); the brand `higgsfield`; or `HFT.derive({ seed: '#hex' | ['#a', '#b'], mood: [...], scheme })`, moods `calm, luxury, energetic, playful, technical, editorial`.
   - **Genre decides density** [T-02, T-03, M-06]: Higgsfield brand / launch key frames stay restrained; productDemo and SaaS / app ads show ONE persistent, believable app the camera travels through (sidebar, top bar, real lists from one dataset), never a floating card under a headline per scene; a montage of generations gets richness from cut rate (~40–50 cuts per 30 s, no image held >1 s).
   - A user reference outranks `HFT.genreStyleMatrix`: take its energy and structure, never its chrome or layout. [T-10]
   - **Higgsfield product with a launch family in the library:** open those frames via Figma MCP first (codes and node ids in `50_part5a` / `51_part5b`). [P-11]
3. **Resolve the theme.** `const th = HFT.theme('luxury-serif', { scheme: 'light', format: '9x16', genre: 'productDemo' })`; fix every `HFT.validate(th)` error; in HTML use `toCSSVars`, `fontLink`, `three`. Take sizes from the theme before writing the scenario. [TK-03]
4. **Design the frames** from `assets/templates/styleboard/styleboard.js`, never hard-coding colours or fonts.
   - **One focal idea per frame; density from ONE coherent source (world layer / real product UI / diegetic output / identity line work), never decorative fragments.** [T-01, T-02, T-03, T-04, C-01]
   - Composition archetype per frame. Centre only where ideal (lockups, CTA); elsewhere asymmetry, scale contrast, off-frame crops, macro, Z / corner pair, full-bleed, orbit or exploded stack.
5. **Render stills and review.** `node scripts/render.mjs <out_dir> frame1.html …` (1920×1080 default). **Read the PNGs** against `13_part1d` (beautiful-frame checklist + anti-patterns); fix, re-render.
6. **Motion** (if asked). One self-contained `index.html` exposes `window.__comp = { width, height, fps, duration }` and `window.__seek = async (t) => {…}`. Start from `assets/templates/motion_demo/`.
   - `__seek` is a **pure function of t**: no rAF clocks, CSS transitions or `Date.now`; three.js renders inside it. Continuous in fractional t (motion blur samples sub-frames), no NaN, dependencies computed in order, eased states instead of `t >= x` switches. Animate with `HF.*`; time with `HFT.timeline / ms2f / beatGrid / readTime`. [R-08]
   - **The camera is active and motivated:** it follows what moves or reveals the next information, eases in and out at both ends, and holds still only on listed reads. No unmotivated crash zooms, shake or roll; whips only to follow an object. [CA-01, CA-02]
   - **Every transition has a visible trigger** from the trigger map. [S-02]
   - **No dead air:** something new every 0.5–0.6 s. Stills only as listed reads: status 1.0 s · name + ✓ 0.6–0.7 s · three numbers 1.2 s · list item 0.8 s · end lockup 2 s. [M-05]
   - **Nothing pops:** entries = move + scale 0.96→1 + opacity + blur 8→0 px on an expo-out; exits mirror on a cubic-in; captions and CTAs take ~10 frames. [M-01]
   - **Footage** plays as `<img>` frames via `clips.js` (`"$B"/extract` at native fps); headless Chromium has no H.264. [R-09]
7. **Capture, sound, encode.** Once per machine: `zsh scripts/setup.sh`.
   - **Drafts:** `node scripts/capture.mjs page.html out/frames --draft` (JPEG, 4 workers, no blur: minutes). Number versions; never overwrite a file the user has seen. [P-02, R-06]
   - **Masters:** `--mb 8 --shutter 0.5 --clean` (180° sub-frame blur, ≈20 s of render per film second, a fresh folder). Never fake blur in CSS. [R-01]
   - **Sound is a default step:** no film goes out silent, interims included. [SN-01, R-02]
     - Track supplied: `python3 scripts/music_window.py track.mp3 --len 30 [--after 60]` → propose the window as a table → `cut_audio.py`; snap scenario times to the real hits. [SN-02]
     - No track: a score synthesised in code (`render_audio.mjs` + `score.html`); Higgsfield has no general music generator. [SN-03]
     - Master to −14 LUFS / −1.2 dBTP: `"$B"/master mix.wav master.wav`. You cannot hear audio: send each track alone with its structure and timestamps to check. [SN-07, SN-08]
   - **Encode:** in one pass `"$B"/encode_av out/frames 24 master.wav film.mp4 24`; or silent `"$B"/encode out/frames 24 film.mp4 20`, then `"$B"/mux film.mp4 music.m4a film_av.mp4`. Non-macOS: the ffmpeg equivalents are in the encode_av / mux headers.
   - **Deliverable:** 1920×1080, 24 fps, exact duration, H.264 High BT.709 at 20–30 Mbps + AAC 256 kbps; chat copy: `avconvert --preset Preset1920x1080 --source film.mp4 --output film_share.mp4`. Spec: `production-lessons.md` §11. [D-01]
   - **Probe the encoded file** and pull check frames from it, not from the source: `"$B"/probe film.mp4 check/`. [R-10]
   - Review strips: `--stills 0.5,1,…` → `node scripts/strip.mjs <stills_dir> strip.png "title"`.
8. **QA before delivery.**
   - **Every send:** `fdiff` (spikes, freezes ≥6 frames), `activity.mjs` (dead air), `textcheck.mjs`, sync at picture hits, stills every 2 frames ±0.5 s around each cut. Whole-frame metrics miss local defects. List what is still wrong, with timecodes. [Q-01, P-02]
   - **Deep multi-lens review only on the final candidate**, time-boxed (~8–10 min, ≤5 findings per critic), with a client-proxy lens. [Q-03, Q-04, Q-05]
   - "Есть дефекты": scan at once, send a ranked list with timecodes, ask which seconds they saw. [Q-01]
   - Re-check contrast after a palette change, layout after a format change, timing after an FPS change. Checklist: `production-lessons.md` §10.

## Non-negotiables

- **Tokens only.** Every colour, font, radius, shadow, easing and duration comes from the resolved theme. A new look is a preset, `HFT.defineBrand()` or `derive()` from the reference's seeds, never a hand-rolled palette. [TK-02]
- **Google Fonts only** via `HFT.fontLink(th)`; check script support (Space Grotesk has no Cyrillic → `HFT.scriptFallback`).
- **Legibility (16:9 in a phone feed):** meaningful text ≥64 px mixed case or ≥48 px caps, labels ≥28 px, nothing <20 px, weight ≥500. Effective size = CSS size × every ancestor and camera scale. `HFT.readTime` (`max(1.0 s, 0.35 s × words + 0.5 s) × k`; CJK / Thai by characters) is for lines read while the camera moves; still frames use the listed reads. [TY-01, M-05]
- **Contrast.** Body and text on accent ≥4.5:1; 3:1 only for large / bold text and essential graphics. Measure at the worst pixel under the glyphs, WCAG and APCA. Uppercase gets positive tracking. [TY-01, T-12]
- **Minimal is not empty.** Every frame has a world layer, real product UI, a frame-filling macro hero or identity line work, and reads as a poster, not a slide. [T-02]
  - Welcome: 2–4 crisp functional UI details per shot (meta rows, chips, status dots, cursor clicks); the product's own output (game score, READY / GO); identity line work (construction lines, orbits, rulers). [T-04]
  - Banned: decoration from neither product nor identity: satellites, HUD header rows, corner marks, chip clouds, ring text + legends, fake facts or counters. [T-01, T-04]
- **No odd or unclear ideas.** Never empty capsules. Would a viewer instantly get it and find it impressive?
- **Materials.** No detailed 3D objects (glass tubes, bubbles, macro glass, chrome, liquid floods). 3D = monumental matte forms (clay, satin, wax, felt) in a clean void. Flat frosted UI panels and glows inside SaaS UI are fine. [T-08]
- **Generations: two modes.** [G-01]
  - *Design trial* («просто дизайн»): no generations; a lit "✦ GENERATION" window with a one-line shot description.
  - *Production* (the user names models, authorises Higgsfield or asks for film assets): check the balance, preflight the cost (Seedance 2.5 1080p ≈ 12 credits/s), plan a ~30% reshoot reserve, generate alongside the motion, QC every clip, report the spend. Unclear: ask once at the start.
  - Casting (Soul 2 first, fashion-editorial), anti-slop, the user's Seedance format: `production-lessons.md` §7. [G-02, G-03, T-16]
- **Partner logos:** never draw other companies' logos; plain text (e.g. "Claude") or a labelled slot.
- **Honesty:** only supported product states; no fake progress %; mark concept vs real result; data keeps units and sources; the on-screen prompt matches its result; counters run monotonically; labels match counts. [S-10]
- **End card:** a clean, centred text packshot: co-brand row → wordmark (bigger than on the title) → product pill → CTA. No hero person, orbit or cards; wordmark on the final hit; hold ≥1.5–2 s. [T-18]
- **Accessibility.** ≤3 flashes/s; a white flash ≤2 frames.
- **Revisions.** A redesign called bad: revert to the last approved version, then apply only the requested changes, only to the frames named; never change approved copy, prompt or look unasked. Judges never override a client approval; keep a per-frame approval log (version, date, the user's words). [T-05, T-06]

## Higgsfield quick facts (brand `higgsfield`)

- **Colour:** lime `#D1FE17` is the action / generation colour, a light accent, not a flood; other identities do not inherit it. [T-13]
- **Worlds:** light `#FAFAFF` / `#F3F3F5`; dark `#0B0B0D` with surfaces `#131313` / `#1B1B1B`. Secondary accents: magenta `#ED1572`, cyan `#36CDFF`.
- **Type (Higgsfield-brand films only):** what `HFT.theme('higgsfield')` resolves: Inter, Inter Tight, Space Grotesk, JetBrains Mono. Other identities choose freely from Google Fonts per their references. [T-15, TK-03]
- **Signature motifs:** the flat S1 lime capsule wave and the light trail.
- **Timing:** 24 fps @ 120 BPM = 12 frames/beat; cut on beats. A supplied track's tempo replaces the grid. A brief asking for 30 fps: ask if firm (Seedance outputs 24 fps). [SN-02, G-12]
- **15 s template = a minimum skeleton:** hook 0–1 s · title 1–3 · prompt 3–5.5 · generate 5.5–6.3 · result 6.3–8.5 · one-to-many 8.5–11 · CTA + end 11–15. Plan ~10 shots: 1-beat bursts up front, short punches before hits, varied lengths (e.g. 2-1-1-4-6 beats). [S-04]
- **More:** `50_part5a_higgsfield.md`; 34 archetypes with Figma ids in `51_part5b_archetypes.md`.

## API cheat sheet

```js
const HFT = require('./scripts/hf-tokens.js'), HF = require('./scripts/hf-motion.js'); // Node: nothing is global
const th = HFT.theme('swiss-editorial', { scheme: 'light', format: '16x9', fps: 24, genre: 'explainer' }); // th.tokens['accent.action'] …
const nu = HFT.derive({ seed: '#FF5A1F', mood: ['energetic'], scheme: 'dark' });   // a new identity, already validated
HFT.validate(th)        // → issues [{level, rule, message}]
HFT.toCSSVars(th) · HFT.fontLink(th) · HFT.three(th) · HFT.toDTCG(th)   // DTCG JSON for Figma on demand
HFT.du(px, '9x16')      // design units (1 du = min(w, h) / 1080)
HFT.ms2f(500, 24)       // 12 frames; HFT.ms2f(ms, fps, {hold: true}) uses ceil
HFT.beatGrid(120, 25)   // fractional beats (12.5 frames)
HFT.timeline('changeAndResult', 6000, 24, 120).beats  // an object, not an array; beats have startFrame / endFrameExclusive
HFT.readTime('Make it move')                    // hold time, frames
HFT.list('styles' | 'brands') · HFT.genres · HFT.modules · HFT.templates.brief · HFT.quickStart · HFT.aliases
HFT.brands.higgsfield.legacy  // «мой tokens.json» (v2.0.0): the base; export JSON.stringify(…, null, 2); refs on color.brand.* need .hex [TK-01]
// Add a brand (HFT is never mutated): const R = HFT.defineBrand({ id: 'acme', name: 'Acme', style: 'swiss-editorial', … }); R.theme('acme')
//   or inline HFT.theme({ brand: {…} }). Brand fonts must exist in HFT.fonts. [TK-04]
// hf-motion.js: HF.use('luxury-serif'); HF.p(t, t0, t1, ease) · HF.tw(t, t0, t1, a, b, ease) · HF.kf(t, [[t, v, ease], …]) · HF.E.enter / exit / move / camera · HF.f2s(frames)
```

## Known limitations

- **The DTCG export is not strict** (some leaves use `$type: "string"`); Tokens Studio imports it.
- **The handbook predates the last engine fixes:** trust `hf-tokens.js` and `HFT.validate()` (pill overshoot now ≤6–8 %, never on logo / headline; the brand-schema example; tech-terminal sizes 192 / 136 / 50 + Doto accent, not 150 / 96 / 26). "Утверждено" on film15 / three3d is not a client approval; approved are Audio MCP stills 01, 03–14 (round 5). [TK-03, Q-08]
- **Node 22+** (global WebSocket) and a Chromium browser (auto-detected; `HFT_BROWSER` overrides). No ffmpeg on the user's Mac, stdlib-only Python 3.14: stay on Swift / AVFoundation, afconvert, avconvert, zero-dependency Node. zsh: quote paths (they contain spaces) and URLs with `?`. [R-13]
