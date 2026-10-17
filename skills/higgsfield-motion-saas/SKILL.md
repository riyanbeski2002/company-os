---
name: higgsfield-motion-saas
description: Make smooth, professional SaaS / app / product launch motion — fully code-based (HTML/CSS/Canvas scenes → headless-Chromium capture → sub-frame motion blur → H.264, synthesized sound) or in After Effects via ExtendScript. Covers the whole 15 s launch-film job (concept → storyboard sheet with estimate → engine → render → review → revisions) and a tested library of transitions that hide the cut in peak speed (needle zoom, fly-through, UI morph, mockup hand-off, object carry, grow-from-point, smear, flowing background), overlapping keyframes / parent nulls, inertial-bounce entrances, typing with a caret, a photographed lens pass, motion QA. Use whenever the user wants a launch / promo / teaser / product video, UI animation, smooth transitions, match cuts, easing or speed-graph work, camera moves, or any scripted motion piece in AE or in code, in any language ("моушн лаунч ролик", "full code-based", "плавный переход", "SaaS ролик", "overlap ключей", "камера мувменты") — even if they don't name the skill.
---

# Higgsfield Motion SaaS: app and launch motion

Two engines, one motion grammar.
- **Code films** (what every launch film so far shipped as): a page whose `__seek(t)` draws frame t, captured by headless Chromium, blurred from sub-frames, encoded with AVFoundation. Toolkit in `scripts/code/`, engine template in `assets/film-template/`. Choose this when the user says "full code-based", "не используй AE", or gives no tool preference for a launch film. "Code-based" means no DCC at all — not even a scripted Blender or AE.
- **After Effects** (`scripts/saas_motion.jsx`, namespace `SM`): when the user wants an .aep, works in AE, or asks for AE explicitly. Every recipe and number in `references/techniques.md` comes from a frame-by-frame study of MahdiEdits' SaaS tutorials and is reproduced by the library within a few percent.

## The rule behind every technique
**At an event the speed is never zero — and at a cut it is at its maximum.**
- A cut hides inside the fastest moment of motion: a symmetric *needle* (zoom), an asymmetric *cusp* (morph), an acceleration *into* the cut handed to another property after it (mockup).
- **The direction survives the cut.** If the camera flies *into* something, the next shot starts *farther away* (scale < 1) and decelerates in — it never starts zoomed in and shrinks. Check the sign of d(ln scale)/dt on both sides of every cut (`window.__qa()` in the template; `SM.qa.zoom` in AE). The client caught a flip immediately: "камера же залетает в O и там дальше он должна пролететь и остановиться".
- At a **pose**, start the next move at ≈0.45 of the current one, on a parent wrapper (the "null"), so speeds add instead of queueing.
- Keep one thing continuous across a cut (an object's geometry, its direction and relative speed, the UI state, or a colour) and hard-cut the rest. **Nothing important appears or leaves by opacity alone** — it is carried, grown, pushed, wiped, morphed or cut ("не делай переходы через opacity").
- Strong curves (needles, `in(3)`/`out(3)`) belong to transitions only. Inside scenes everything is soft (entrances 0.45–0.7 s, overshoot ≤2 %) — the client calls hard in-scene motion "резко".

## Launch-film workflow (code path) — details in `references/launch-film.md`
0. **Read the room first.** Load `references/client-taste.md` — the client's rules from six launch films (what read "дешево", what got "охуенно"). It changes the defaults below.
1. **Setup (2 min):** `source scripts/code/env.sh` (finds Node ≥21, a Chromium browser, numpy+PIL), `scripts/code/build_tools.sh` (compiles encode / mux / extract with swiftc; no ffmpeg needed). Check free disk (`df -h`): a 12-sub-frame render writes ~2 GB; put `WORK` on the big volume.
2. **Study refs:** `scripts/code/bin/extract ref.mp4 refs/r1 0.5` + `sheet.py` → a contact sheet every 0.5 s; dense sheets (1/15 s) around each transition you will borrow. YouTube refs: open in the browser pane, seek, screenshot — don't hunt through old sessions.
3. **Concept:** a hook, one persistent hero object that travels through the film (an LED face, a vinyl record, the letter O, a prompt bar), 6–9 beats on a 120 BPM grid (cuts on 0.5 s multiples), payoff + CTA + clean end card. Invent the product/brand — never a real brand's name, logo or signature colour.
4. **Storyboard gate:** render the beats' hold poses **with the film engine itself** (`stills.sh`), lay them out with `assets/storyboard/` (RU captions, passport card: palette, fonts set in themselves, tech line, "Отличия от рефов", estimate). Send it with a time estimate and wait for "гоу". Pick fonts from a rendered specimen (`assets/specimen/`) in the film's real copy — check Cyrillic.
5. **Build:** copy `assets/film-template/`, one scene module per file, transitions from `references/transitions.md`, contracts per cut written down (times, curve, amplitude, pivot, hand-off pose).
6. **QA before rendering:** `capture.mjs film/index.html /tmp --qa` (zoom direction), stills at cut−1f / cut / cut+1f of every cut, a 2-frame-step sheet of every character/idle motion (stills hide dead motion), contrast of text over moving backgrounds.
7. **Render:** draft `render_film.sh film/index.html film/draft.mp4 1 8`; final `render_film.sh … 4 8 10 "<fast windows>"` (16+ sub-frames for extreme needles) with `LENS=1` for the photographic pass. Patch-render only changed ranges (`FROM/TO`, `KEEP=1`).
8. **Sound:** `capture.mjs … --cues cues.json` → `sound_template.py` / `sound_kit.py` → `bin/mux`. Synth sound is a placeholder: the client's final mix is made by a human in Premiere — always deliver `*_nosound.mp4` too, and say the track was checked numerically, not listened to.
9. **Verify the delivered MP4** (extract frames back out; check duration/frame count), then send with a short beat list and honest remaining flaws.
10. **Revisions:** back up the approved version (`_approved_vN/`), change only what the feedback names, re-render only what changed.

## Technique → where it lives
| Technique | Code (template `FILM.*`, recipes in `references/transitions.md`) | After Effects (`SM.*`) |
|---|---|---|
| Needle zoom on a cut | `FILM.needle(t,cut,a,b)`, `FILM.zoom(…,E.in(k))` in log space | `SM.zoomAtCut` (influence 95/95) |
| Fly-through / dive into an object | zoom ×6–12 `E.in(4–5)` about the object, next shot from ×0.26–0.4 `E.out(3)` | zoomAtCut + settleAfterCut |
| UI morph card → card / button → CTA | size (not scale) +18 % `E.morph1` → −18 % `E.morph2`, or log-size growth `E.smooth` | `SM.uiMorph` (Rectangle Size, cusp) |
| Mockup hand-off | same UI at the same screen rect across the cut, energy moves to another property | `SM.scrollInto` + `SM.settleAfterCut` |
| Object carry / grow-from-point / smear | `references/transitions.md` §3–5 | — |
| Flowing background ("переливание") | `FILM.BG` flood from the action point | — |
| Overlap A→B→C | parent wrapper starting at 0.45 of the move; camera keys as summed deltas | `SM.overlap2D/3D`, `SM.overlapChain` |
| Entrance with inertial bounce | `FILM.rise(dt, 217)` + `E.width` from a square | `SM.entrance` |
| Typing + caret | `FILM.cadence` + `FILM.typedN` (TQ-quantised), `FILM.caretOn` | `SM.typeOn`, `SM.caret` |
| Decode / code rain / glyph streams | `FILM.scramble`; `assets/reference-films/lo/kit.js` (`K.rain`, `K.atlas`, `K.stream`, `K.bitmap`) | — |
| Photographed look | `scripts/code/lens.py` (any film) or in-page WebGL lens (`reference-films/lo/kit.js K.lens`) | — |
| QA of motion | `--qa`, cut stills, 2-frame sheets, `verify()` for sound onsets | `SM.qa.*` speed graphs |

The AE recipes with the *why*, provenance and failure modes are in `references/techniques.md`; the math (needle/cusp/relative speed, log-space zoom matching, bezier equivalents) in `references/ease-math.md`.

## After Effects path
1. **Probe read-only:** `bash scripts/ae.sh scripts/probe.jsx /tmp/probe.txt`. The open project is the user's workspace: build into new comps only, never close or overwrite it. If osascript hangs, macOS is asking for Automation access — ask the user to allow it.
2. **Build script** from `examples/build_template.jsx`; all work inside `SM.run(OUT, function (log) {...})` (errors go to the log, dialogs are suppressed). Run: `bash scripts/ae.sh build.jsx out.txt '{"save":"/abs/p.aep","stills":"/abs/stills"}'`.
3. Read the logged QA numbers, shoot stills (`SM.shoot` → `python3 scripts/stills.py dir --expect N`), save, `bash scripts/render.sh project.aep "Comp" out.mp4` (aerender renders the saved file).
4. Library essentials: `SM.seg(prop,t1,v1,t2,v2,[r,infl],[r,infl])` takes speed as a multiple of the segment's average, so recipes are size- and fps-independent; `SM.addNull` makes identity nulls; parent before a null gets keys; morph with Size, not Scale; no overshoot on a move that hides a cut. ExtendScript is ES3; script keys start LINEAR until `SM.ease` sets BEZIER. A modal dialog blocks every later call — if `ae.sh` times out twice, ask the user to look at AE.

## Things that silently break code films
- **Not a pure function of t** (rAF clocks, CSS transitions, `Math.random`, `Date.now`) → frames differ per worker. Seed everything (`FILM.rand`).
- **Fonts:** `document.fonts.ready` resolves before an unused face loads → measured layouts drift. List every face/weight in `FILM.fonts`. A display font without Cyrillic silently falls back.
- **Measuring hidden layout** (`display:none`) returns 0 → measure in `build()` (root visible), use `offsetWidth` (ignores transforms) in `update()`.
- **Parallel capture on one DevTools port** mixes scenes → unique `CAP_PORT` per worker (render_film.sh does it). Browser profiles and sub-frame JPEGs fill disks (ENOSPC kills the shell) → `CAP_TMP`/`WORK` on a big volume, profiles are deleted on exit.
- **Motion blur:** 3–5 fixed sub-frames show stepped copies; use 4 + 10–16 in fast windows (`--subhi/--hiwin`) or 12 everywhere; extreme needles (×9+) want 16–24. Sub-frames never straddle a hard cut (capture reads `__cues.hard`). Discrete events (typed characters, swaps) are quantised with `FILM.TQ` so the blur doesn't double them.
- **A hung worker** leaves holes; `render_film.sh` refuses to encode a sequence with missing frames. Run long renders with `run_in_background`; foreground jobs die with the session.
- `file://` images taint canvases (`getImageData` fails) — capture.mjs passes `--allow-file-access-from-files`. `encode` needs an absolute output path. A prebuilt Swift binary copied from elsewhere can be SIGKILLed (137): rebuild with `build_tools.sh`. In zsh, `set -- $r` does not word-split.
- numpy 2.0 + Accelerate prints bogus overflow warnings on float32 matmul; write weighted sums explicitly. No scipy here — numpy + PIL only.

## Files
- `references/launch-film.md` — the end-to-end job: phases, gates, realistic time estimates, storyboard and SPEC formats, agent orchestration, QA checklists, delivery.
- `references/client-taste.md` — this client's taste: praise and rejections across Strata, Kadra, Reroll, Halftone/Inkwell 3, BLIP., LO., with the rules they imply.
- `references/transitions.md` — the code transition vocabulary with numbers, plus camera rules.
- `references/code-engine.md` — engine API, look (lens, type, glyph kit, characters, backgrounds), motion blur, sound, pipeline, bugs.
- `references/techniques.md`, `references/ease-math.md`, `references/visual-language.md` — the AE recipe cards, the math, the MahdiEdits SaaS look.
- `scripts/code/` — `capture.mjs`, `render_film.sh`, `stills.sh`, `sheet.py`, `blend.py`, `lens.py`, `sound_kit.py`, `sound_template.py`, `encode/mux/extract.swift`, `build_tools.sh`, `env.sh`.
- `assets/film-template/` (engine + 2 example scenes, verified end to end), `assets/storyboard/`, `assets/specimen/`, `assets/reference-films/` (BLIP. — the quality bar —, LO., Strata v4 sources to read, not to run).
- `scripts/*.jsx|sh|py`, `examples/` — the After Effects library, self-test and examples.
