# Code engine, look and pipeline

## Contents
1. The page contract and the template engine (`FILM.*`)
2. DOM, Canvas or WebGL
3. Curves (AE recipes as JS)
4. Type
5. The photographed look (lens, LED, bloom, grain)
6. Characters that feel alive
7. "Inside the system" kit (glyphs, rain, decode, bitmap type)
8. Motion blur
9. Pipeline tools
10. Sound
11. Bugs already paid for
12. Reference films — where to look

## 1. Contract and template
`capture.mjs` needs `window.__comp = {width,height,fps,duration}` and `window.__seek(t)` (pure function of t), optionally `__errors()`, `__qa()`, `__cues`. Set `__comp` only after fonts and assets load. The template (`assets/film-template/engine.js`) provides:
- `FILM.scene({id,t0,t1,pre,post,build(root),update(lt,t,root),zoom(lt)})` — scene roots are transparent 1920×1080 divs in one `#world`; `pre`/`post` make neighbours overlap (soft transitions); scenes without them are hard cuts (`__cues.hard`).
- `FILM.CAM` segments `{t0,t1,a,b,ease}` with `{cx,cy,s,rx,ry,rz}` → `#world` transform (perspective 2200 on `#film`); `?nocam=1` disables it.
- `FILM.BG` flowing mesh-gradient background (states, flows from an action point, iridescent fringe) on a canvas under `#world`.
- Helpers: `p, tw, kf, zoom, needle, pop, soft, bounce, rise, settleShake, type, cadence, typedN, caretOn, scramble, glyphs, riseGlyphs, drawOn, about, dirBlur, rand, hash, TQ, cue`.
- Query: `?only=s1,s2` (`?only=none` = background only), `?nocam=1`, `?t=3.2`.
- Its two example scenes are a working fly-through (needle into a button → next shot keeps flying forward, background floods from the button) — render them once to see the pipeline before writing your own.

## 2. DOM, Canvas or WebGL
| | DOM/CSS/SVG (Strata, Kadra, Reroll, Halftone) | Canvas2D (BLIP., LO.) |
|---|---|---|
| Good for | UI mockups, type, layout, design-tool details, CSS 3D camera | particles, thousands of glyphs, SDF characters, halftone dots, custom lenses |
| Lens | `lens.py` on the frames (post) | in-page: `BL.post` (Canvas2D) or `K.lens` (WebGL) on a second canvas |
| Cost | ~0.5 s/frame per worker for heavy scenes | CPU SDF rasters dominate (~1 s per sub-frame) |
Mixing is fine: a canvas inside a DOM scene. For a WebGL post pass the whole frame must be a canvas (DOM can't be read back in-page).

## 3. Curves
| Name | Definition | Use |
|---|---|---|
| `in(k)` / `out(k)` | p^k / 1−(1−p)^k | into / out of a cut; end slope of `in(k)` = start slope of `out(k)` = k·Δ/T → equal speeds across a cut when k·Δ/T match (zooms: Δ in ln scale) |
| `soft` | bezier(.16,1,.3,1) | entrances (= expoOut) |
| `smooth` | bezier(.5,0,.1,1) | pose → pose |
| `glide` / `sine` | bezier(.45,0,.55,1) / (.37,0,.63,1) | drifts, camera, cursors |
| `expoIn` | bezier(.7,0,.84,0) | swing/whip out of a scene |
| `needle` | bezier(.95,0,.05,1) | `SM.zoomAtCut` (influence 95/95) |
| `into` | bezier(.5,0,.85,.625) | still accelerating on the cut frame (`SM.scrollInto`) |
| `settle` | bezier(.2,.7,.05,1) | after a cut (`SM.settleAfterCut`) |
| `morph1` / `morph2` | (.66,0,.9,.1) / (.07,.44,.16,1) | UI morph out / in |
| `width` | bezier(.75,0,.25,1) | entrance width, button spin |
| `back(s)` | overshoot | chips/pills only, ≤2–5 % |
| `pop(t,t0,d)` | 1−e^(−6.5x)·cos(10.5x) | spring entrance (~6 %) |
| `soft(t,t0,d)` | 1−(1+kx)e^(−kx), k=7/d | critically damped, no overshoot |
| `rise(dt,dist)` | linear 1860 px/s then AE inertial bounce (amp .0375, freq 1.8, decay 3.2) | `SM.entrance` |

## 4. Type
- **Glyph mask-rise:** each glyph wrapped in `clip-path: inset(-60% -30% -0.14em -30%)` (negative insets, or ascenders get cut), `translateY(110–160%)→0` with `soft`, 0.45–0.6 s, stagger 0.02–0.06 s; exits upward with `in(2)`, stagger 0.015, 0.14 s.
- **Typing:** a seeded human cadence (`FILM.cadence`: gaps .55–1.45, ×1.3 after spaces/commas, normalised to [T0,T1]), ≤50–60 cps, the first character one frame early (or the first typed frame is blank); caret solid while typing, blinks after (2–4 Hz), appears 2 frames before the first char. Quantise with `TQ`. A typing cursor can become an I-beam riding the caret. Glyph flip variant (Halftone): each new glyph shows in a pixel font for 2 frames, another face for 2 frames, then its own face.
- **Decode:** `FILM.scramble(s,k,t)` — per-char threshold i/len·.55 + hash·.25, random glyphs at 28 Hz; monospace keeps the layout stable.
- **True pixel type:** draw squares (5×7 cells, square .86 of the pitch) — a pixel TTF at display size reads rounded (`reference-films/lo/kit.js` `K.bitmap`; extend its `BM` glyph table).
- **Ring text** (Reroll): `textLength` makes letters drift; instead n = round(C/u) repeats with u = measured width + 0.02·size, font size fs = size·C/(n·u)·.975.
- **Baseline measurement:** a zero-size inline element as the first child of a `align-items: baseline` flex row; its rect top is the baseline; cap line ≈ baseline − 0.727·fs.
- Load every face/weight (`document.fonts.load`) before measuring; for non-Latin captions load `&text=` subsets (LO: Noto Serif JP/SC/KR/Naskh/Devanagari).

## 5. The photographed look
Flat clean vector reads "cheap"; a lens makes it read as photographed.
- **`lens.py` (any film, on frames):** barrel k, radial chromatic aberration (R scaled up, B down with radius), 3-scale bloom on highlights (h·.006/.02/.06, weights .7/1/.45, screen; auto-off on bright frames), vignette smoothstep(.35→1.25 r), luma grain seeded per frame in the mid-tones. Defaults k .04, ca 1.5, bloom .35, vig .35, grain .02; per-scene `--sched`.
- **BLIP.'s in-page stack (Canvas2D, `reference-films/blip/kit.js`):** `BL.led` — dot lattice with barrel bulge k .10–.17 (position ×(1+k r²), dot size ×(1+1.6k r²), brightness ×clamp(1+1.4k r², .35, 1)); lit dots on their own layer reused for spill (blur 1.6·pitch, α .25–.45), dot-level fringes (#FF2A3C +ca x, #2A6BFF −ca x +.3ca y, α .55, `lighter`), sheen (radial at 30 %/12 %, α .07–.25), bottom shadow (α .25–.55), DOF (blurred copy masked outside a focus disc .55→1.5 r), pillow mask (edge blur 30–80), halo (60–90 px), bloom at .3b/b/3b (α .7/1/.45, b 16–24). `BL.post` — radial CA by splitting R/G/B and scaling about the centre, vignette, grain (keep the noise tile *outside* any pooled/cleared canvas — BLIP lost its grain that way).
- **LO.'s WebGL lens (`reference-films/lo/kit.js` `K.lensInit/K.lens`):** barrel k (CRT .2, paper .035–.05) with auto-zoom to fill, rounded corners, CA .0032·r (0.012 was far too much), scanlines .32, flicker, vignette .3–.7, grain .07, band glitch on cuts.
- **Materials:** rim light, a specular blob, a contact shadow; tint bloom cores (pure white cores read cheap).
- **Grain:** subtle (≤.02–.04) or none; seed it by frame number so all sub-frames share it.

## 6. Characters that feel alive (BLIP.)
- CPU SDF bodies at ⅓ resolution → `ImageData` → upscale with `blur(5px)`; smooth-min unions of ellipses/circles/tapered capsules; outer glow exp(−d/30)·.45, rim light, specular, a darker "core plate" behind the eyes for readability.
- **Motion signatures** (units ≈ 600 per body height; phase offsets so the cast never syncs):
  - grumpy: jitter sin83t·8 + sin61t·5 scaled by a huff = max(0, sin5t)^5, stomp at 2.5 Hz, squint on the huff, steam;
  - clingy: hops 1.9 Hz (y = −air^0.8·104), land squash sx 1+.19 / sy 1−.17, ears flop with hop velocity, heart eyes pulse;
  - sleepy: float sin2.4t·32, breathing scale, bubble, drifting "z";
  - hyper: hops 2.6 Hz, saccade eyes sign(sin5.2t)·|sin|^0.2·26, antenna lag.
- **Idle amplitude ≈ 2× what looks right in a still** — the first pass at half these values read dead on a 2-frame sheet.
- Arrival squash .1·e^(−7a)·sin(19a); glance at its own name; blink every 1.7–2.3 s.
- SDF lerps between unlike glyphs make ugly "cup" intermediates — hide them behind a blink or a cut. Colour-mixed backgrounds mid-morph go muddy grey — snap them with smoothstep(.38,.62).
- Vector characters from a reference (Halftone's Shiba): one `<g>` per semantic layer, palette sampled from the ref, shading as thick round strokes clipped to the shape, outline redrawn last; render alone and compare with the ref before use; idle = breath scaleY 1+.014·sin(2.4t) at the base, head 2.5 px / 1.2°, tail 4°·sin(1.9t). Watermarked stock refs: draw an original close version and say why.

## 7. "Inside the system" kit (LO., `reference-films/lo/kit.js`)
- **Glyph atlas** per (font, size, colour, weight), `drawImage` per glyph — mandatory once a frame holds thousands of glyphs.
- **Code rain** (`K.rain`): per column speed 80–420 px/s, length 4–30, head glyph changes at 16 Hz, trail at 2.5 Hz, alpha (1−j/L)^1.5·.8; pure function of t. On dark it must be ≥30 px at α .8 to survive the lens; on paper α .07–.085 as texture. Two depths for parallax; blur the near layer once offscreen.
- **Streams** (`K.stream`): windows dissolve into ~38 glyphs each along quadratic Béziers into a target (0.72 s, scale 1.3→.35, α sin(πs)).
- **Dots born as glyphs**, **glyph shockwave** (rings of 56/40 glyphs, r 240→1250 `out` 0.5 s), **logo rains in** as 3-glyph trails and freezes into dots.
- Crash beat: freeze and dim the rain to .4, then resume at 1.3×; frame tears into 36 px bands; a red modal pops dead centre with `back(.16)`, shakes (16 px, 5 Hz, decay 9), blinks once, collapses like a CRT (scaleY → .015).

## 8. Motion blur
- 180° shutter centred on the frame: sub-frame k of N at t = (n + 0.5·((k+.5)/N − .5))/fps; `blend.py` averages in float.
- Counts: 3–5 strobe on fast or spinning things; 6 is the minimum for rolling objects; 12 everywhere or 4 + 10–16 in fast windows (`--subhi/--hiwin`); extreme needles 16–24. Physical bound: enough slices that each moves ≤~0.75 px — unreachable on needles, so the window gets the most samples.
- Adaptive per frame (Halftone): measure the mean luma difference between t−½ and t+½ at ¼ resolution; n = 1 if diff < .5 else clamp(3 + 1.6·diff, 5, 14).
- Sub-frames never cross a hard cut (capture.mjs reads `__cues.hard`, or `--cuts`).
- Discrete events quantised to the frame (`FILM.TQ`) so typed characters and swaps never appear at half opacity.
- DOM camera blur: SVG `feGaussianBlur stdDeviation="x y"` from the camera's half-frame travel × 0.32 (max 44).
- Grain/noise seeded per frame, not per sub-frame.

## 9. Pipeline tools (`scripts/code/`)
| Tool | What it does |
|---|---|
| `env.sh` | finds Node ≥21, a Chromium browser (`HFT_BROWSER`), checks numpy+PIL |
| `build_tools.sh` | compiles `encode` (frames → H.264 High, BT.709, Mbps), `mux` (passthrough video + AAC), `extract` (video → frames, zero tolerance) |
| `capture.mjs` | CDP capture: `--stills`, `--from/--to/--every`, `--sub/--shutter/--subhi/--hiwin`, hard-cut clamp, `--qa`, `--cues out.json`; `CAP_PORT`, `CAP_TMP`; deletes its browser profile |
| `render_film.sh` | N interleaved workers (`--from i/fps --every N`: heavy scenes spread evenly — 3:09 vs 5:18 for contiguous chunks) → blend → continuity gate → optional `lens.py` → encode |
| `stills.sh` | stills at given times + labelled sheet |
| `sheet.py` | contact sheet from frames (times / range / every n) or any image folder |
| `blend.py` | sub-frame average (ProcessPool, `__main__` guard) |
| `lens.py` | photographic pass (§5) |
| `sound_kit.py`, `sound_template.py` | soundtrack (§10) |
Bitrate: 24–30 Mbps for 1080p30 (15 s ≈ 45–57 MB). Encode needs an absolute output path.

## 10. Sound (`sound_kit.py`, numpy only)
- `S.init(dur)`, `S.add(sig, t, gain, pan, bus, hall, room, echo)`, `S.add_end(sig, t)` (risers that END on the cut), `S.hit(t, peak, size, chord, …)` (kick + impact + optional clap/stab/cymbal/downlifter scaled to an exact peak — the peaks set the loudness hierarchy: hero hit > big cuts > soft cuts), instruments (kicks, hats, cymbals, impacts, pads, saw pad, bass, stab, plucks, bells, chimes, whoosh/riser/riser2/downlifter/whip/shockwave, UI foley: mclick, keyclick, enter_thock, wpop, pop, tick, caret_tick, thunk, paper, bit, sparkle, `decode` chatter), `S.master(wav)` (ducking, hall/room IR reverbs, ping-pong echo, compressor, soft clip, −1 dBFS, AAC via `afconvert`), `S.verify(cues)` (onset error per cue in its band — expect 0–5 ms).
- Rules: the cuts are the rhythm (a hit on every cut, a riser into every needle); picture sounds on the contact frame (spring start + ~0.13 s); mute the arpeggio in the 0.3 s before big cuts; per-character voices for characters; one source of truth for timing (`--cues`).
- It is a placeholder for the client's human mix: always ship `_nosound`, and say it was verified numerically, not listened to.

## 11. Bugs already paid for
| Symptom | Cause | Fix |
|---|---|---|
| frames from different scenes mixed | parallel captures on one DevTools port | unique `CAP_PORT` per worker |
| layouts drift 7–20 px | `fonts.ready` resolved before faces loaded | `FILM.fonts` force-load every face |
| zero-size rects | measuring a `display:none` root | measure in `build()`; `offsetWidth` in `update()` |
| Bash dies with ENOSPC | browser profiles + check renders | `CAP_TMP`/`WORK` on a big disk; profiles deleted |
| `BrokenProcessPool` | no `__main__` guard on macOS | guard (already in `blend.py`) |
| MP4 not written | relative output path | absolute path |
| stepped ghosts | 3–5 sub-frames | §8 |
| film silently shorter / NSException in encode | a hung worker left holes | continuity gate in `render_film.sh`; re-capture the range |
| exit 137 running `encode` | copied unsigned binary | `build_tools.sh` |
| `getImageData` throws | `file://` images taint the canvas | `--allow-file-access-from-files` (in capture.mjs) |
| grain missing from the whole film | noise tile in a pooled canvas that is cleared on reuse | keep it outside the pool; measure the output |
| blink smears into a blob | SDF squashed without rescaling distance | divide distance by max(squash, .3) |
| semi-transparent doubled text | discrete change mid-shutter | `FILM.TQ` |
| glyph tops cut | `clip-path: inset()` without negative insets | −20 %… −60 % insets |
| PIL floodfill does nothing | array-backed image | `Image.fromarray(a).copy()` |
| `globalAlpha` ignored by a helper | helper set instead of multiplied | `*=` |
| bogus overflow warnings | numpy 2.0 float32 matmul on macOS | explicit weighted sums |
| sound off by up to 0.14 s | cue times hand-copied before a retime | `--cues` + re-run sound |

## 12. Reference films (`assets/reference-films/`, read — not runnable without their assets)
- `blip/` — **the quality bar.** `kit.js`: `BL.led` (photographed LED), `BL.face/G/morph` (SDF eyes), `BL.aura/PETS/petMotion` (characters and motion signatures), `BL.post` (Canvas2D lens); `film.js`: needle chain through a persistent face (`zIn/zOut`), `letters()`, `typeLED()`, `stageLife()`, scene table + `__seek`; `sound.py`: the first synth score.
- `lo/` — `kit.js`: glyph atlas, `K.rain`, `K.scramble`, `K.stream`, `K.bitmap`, Win98 chrome, halftone dot text, globe, WebGL lens with cut glitch; `film.js`: needle into the O + forward continuation (`S2Z`), pour, O→sphere morph (`morph`, `irisPath`), crash modal, `CUTS/glitchAt/LENS`; `sound_lo.py`: the full synth score (buses, IR reverbs, cue verification) that `sound_kit.py` distils.
- `strata/` — `engine_v4.js` (DOM engine with camera segments and the flooding background), `s89_cta_end.js` (Follow → CTA pill → full-frame end card), `s4_prompt.js` (carried cursor, human typing cadence, Generate press + AI bloom), `SPEC_v4.md` (a per-cut contract spec for agents).
