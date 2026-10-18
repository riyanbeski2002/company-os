# Transition vocabulary for code films (with the numbers that shipped)

Every entry was built in a delivered film (Strata, Kadra, Reroll, Halftone, BLIP., LO.). Times are seconds at 30 fps; `E.*` are the template's curves (`assets/film-template/engine.js`). The AE originals of needle / morph / mockup / overlap are in `techniques.md`.

## Contents
0. Choosing: cut or continuous
1. Needle zoom on a persistent object
2. Fly-through / dive into an object — and the continuation rule
3. Object carry
4. Grow from a point
5. Smear and whip
6. UI morphs (card → card, button → CTA, tile → full-frame colour)
7. Mockup hand-off
8. Background transitions (flood, pour, hard plate cuts, exposure ramp, macro → reveal)
9. The infinite band
10. Geometric morph between shapes (letter → planet)
11. State changes instead of fades
12. Iris hand-off into a wordmark
13. Glitch cut
14. One continuous shot from shared elements
15. Camera rules
16. What failed

## 0. Choosing
- **Hard cuts with the speed peak on the cut** (Strata v1, praised) feel energetic; **no-cut object transitions** (Strata v4) feel premium. Both pass; mixing works too: Reroll ran 0–7 s as one continuous shot built from shared elements, then hit hard cuts on bar downbeats.
- Every transition is an *event with a cause* — a click, a key press, an object flying at the lens, a colour flooding from a button. If you can't name the cause, the client reads it as "рандом".
- Cuts sit on the beat grid (120 BPM → 0.5 s multiples); speed up the cut rate toward the climax (BLIP: stage cuts every 0.85 s, then pet cuts every 0.65 s).

## 1. Needle zoom on a persistent object
The object stays, the world cuts, the object "breathes" a zoom whose fastest frame is the cut.
- `FILM.needle(t, cut, 1, 1.12)` = keys at cut−0.2 / cut+0.2−1f, bezier(.95,0,.05,1) (AE influence 95/95). Halftone: ×1.12 on the persistent lockup, reversed by the same curve on a later cut; backgrounds hard-cut 3×/s underneath and never scale.
- Log space for big zooms: `zoom(t,t0,t1,a,b,E.in(k))` = exp(lerp(ln a, ln b, e)). BLIP: zIn 1.3→1.6 Z 2.9 (hook), Z 17 into the wordmark's period (which *is* the next scene's face), Z 11 into the dial hub; settle after with zOut (`E.out(3)`).
- **Move the pivot first**: LO moved the zoom pivot from the frame centre to the O's centre during 1.92–2.22, *before* the zoom accelerated (2.05–2.5, x⁵) — otherwise the target slides while it grows.
- Parallax sells depth: layers behind zoom at scale^0.6, layers in front at scale^1.35 (LO code rain).
- Extreme needles (×9+) strobe even at 10 sub-frames: give that window 16–24 sub-frames, or end on a smaller Z and let the next shot carry the rest.

## 2. Fly-through / dive into an object — the continuation rule
Into the cut: the camera (a parent wrapper) accelerates into a target; after the cut: the **next shot keeps flying forward** and decelerates in.
- LO (praised): A = ×1.04→×12 about the O, x⁵ over 0.45 s; B = ×0.26→×1 `E.out` over 0.9 s, then +4 % drift. Log-velocity +27/s → +15.8/s: same sign. The rejected v2 started B at ×5.2 and shrank (−10.3/s) — read as pulling back. The same flip slipped into LO's 12.5 cut (×6 into Send, then ×2.8→1): run `capture.mjs … --qa` on every film.
- Strata C1 fly-through: the lockup scales ×1→×3.4 `E.in(2)` about the selection centre over 0.35 s, fading only in its last 0.17 s; thin chrome (rulers, hairlines) fades *first* — scaled ×3 they become full-width rules. Incoming letters arrive ×1.9→×1 `E.out(3)`, 15–20 ms stagger, no overshoot.
- Halftone dive: a click starts `E.into` (bezier .5,0,.85,.625 — still accelerating on the cut frame) 0.58 s into a tile; cut at peak speed; the tile's on-screen width at the cut equals the next shot's prompt-bar width (match cut by size).
- Kadra: dolly *through* the gold mark ×1→×12 `E.expoIn` 0.48 s until gold fills the frame; next scene comes *out of* an orb ×5.2→×1 `E.out` 0.85 s (here the next shot is itself a pull-back from inside the colour — legitimate because the frame is a solid colour at the cut).
- Reroll: the ring flies past the camera (dz = 1320·`in(3)` over 0.5 s); the next scene opens at camera ×0.86→×1 `out(3)`; its letters start rising 0.16 s *before* the cut (animation clock pre-rolled, visibility from the cut).

## 3. Object carry (no cut)
An object from scene A becomes part of scene B; everything else leaves.
- **Contract in screen pixels**: measure the object's screen rect at the hand-off time (camera neutral, so `screen = 960 + s·(local − 960)`). Strata: Leo's cursor tip at (1740.66, 512.56) @4.55; the Follow button at (1644.66, 508.47).
- The incoming module draws an identical copy at exactly that rect; the outgoing module hides its original *under* the opaque copy (no ghost, no double).
- The copy lifts (×1.05–1.12 + shadow, 0.1 s), then travels with `E.smooth`; the rest of A whips or smears out.
- Variants: a collaborator cursor carried into the prompt bar, glides in and types (Strata C2); a phone carried from an exploded stack back into its slot on an infinite canvas (C5); a "Follow" button carried into the CTA (C6, see §6).

## 4. Grow from a point
Results are *born* from the thing that produced them (Strata C3): three variants start at the Generate button centre at ×0.06 and fly on gentle arcs to their places — position `E.out(3)`, scale `E.soft`, bank −6…+5°→0, opacity front-loaded over 0.06 s; centre first, sides +0.06/+0.12 s; details land 0.15–0.6 s after. Same idea: windows bursting from one point (LO: 10 windows in 0.24 s, stagger 0.024 s — 0.04 felt slow; pseudo-3D `s = z/(z−cz)`, cz −1.35→0 `out` 0.9 s, DOF |z−1|·6 px).

## 5. Smear and whip
- **Smear** (Strata C4/C6): side objects travel ~1150 px `E.in(2)` (≈9000 px/s at the end) and stay **opaque while crossing the frame edge** — the sub-frame blur draws the smear; fade only in the last 0.12 s. The pushed-into object stays sharp in the centre.
- **Whip with layered parallax** (Strata v1): wind-up +12 px `inOut(2)` 0.14 s, then `in(3)` to −1500 px over 0.3–0.55 s; travel factors per layer: dots 0.5, glow 0.7, type 1.0–1.05, UI 1.1, cursors 1.2 (cursors lead by 20 ms); x-blur ramped with `in(2)` ≤10–18 px; the incoming scene arrives from +1500 px `out(3)` 0.3 s.
- **Mirrored whip** (Reroll): A pans 0→−700 `in(2)` over 0.45 s, B pans +700→0 `out(2)` over 0.45 s — equal distance and duration ⇒ identical speed across the cut. Overlap the incoming content earlier than the cut, or the mid-whip frame is blank paper.
- **Swing pair** (Kadra camera): out `E.expoIn` 0.36 s / 300 px with 20–24° tilt away from travel; in `E.expoOut` 0.7 s / 600 px. Both bezier curves have slope 6.25 at the cut, so speeds match when D_out/T_out ≈ D_in/T_in.
- Hard 0.14 s `in(2)` whips with 46 px blur and 5–6 empty frames after the cut read "резковато": shorten travel (620 px, 0.34 s) and start the incoming content at the cut frame.

## 6. UI morphs
- **Card → card** (Halftone, = `SM.uiMorph`): outgoing height +18 % into the cut with `E.morph1` (.66,0,.9,.1); incoming from −18 % with `E.morph2` (.07,.44,.16,1); morph the box **size**, never `scale` (radius distorts). In a 3D rig, solve the incoming camera distance so widths match on screen: D = w·PERSP / w_screen.
- **Button → CTA → end frame** (Strata C6/C7): the Follow button (47×23 px, rotated 4.3°) lifts, flies to centre and grows in **log size** (`E.smooth` 0.55 s) into an 800×164 gradient pill; colour changes slightly earlier than size; the label rolls vertically (never two labels in the box); at the end it hands off to the real pill element pixel-identically. On click the pill turns white and blooms first ("leads the light"), then expands to the full frame `E.in(2)` (radius→0, colour→end-card background) exactly at the cut.
- **Tile → full frame colour match cut** (Reroll): the red tile at the peak of a dock-magnification ribbon lerps size and position to full frame `in(2)` over 0.45 s; its image fades so the frame is solid red at the cut; the next scene starts on that red.

## 7. Mockup hand-off
The same flat UI at the same screen rect and scale across the cut, with a light→dark polarity flip (Strata s5→s6: phone centred at ×1.35, scale speed ≈1.56/s on both sides); after the cut the energy moves to another property (the phone tilts into an exploded layer stack). Layers separate on one shared depth curve z = k·(70+150·i); stagger only the in-plane offsets (0.03 s per layer) — staggering depth made lower layers overtake upper ones.

## 8. Background transitions
- **Flood from the action point** (Strata v4, "фон пусть меняется переливанием"): `FILM.BG` — each state is a base + 4 radial blobs (r 820–1050, drifting on Lissajous ±140/±90 px) + dot grid; the new state spreads as a union of 3 wobbling soft circles (420 px feather), R = smooth(p)·(farthest corner + 504); an iridescent fringe ring rides the front (`screen` on dark). The origin is the action point's SCREEN position (the pressed button, the carried phone). Text over the front goes dark-on-dark: fade it before the front reaches it.
- **Pour** (LO): 48 px columns, centre-first stagger (.02 + hash·.24 + |i−n/2|/n·.14), each growing to full height in 0.34 s; the new paper is clipped to the columns, each column front carries a 6-glyph head.
- **Hard plate cuts 3×/s** under a persistent object (Halftone hook): each plate drifts and scales +6 % within its 1/3 s.
- **Exposure ramp as a reveal** (Halftone): plates at `brightness(.42) saturate(.9)` under the type, back to 1/1 over 0.75 s as the grid is revealed — replaces both the text plate and the fade.
- **Macro → reveal** (Halftone, accepted): the last hook background *is* the eye cell of the next grid, shot at k = 1920/560·1.02; a tap motivates the pull-out (log-space zoom); the lockup shrinks into the centre cell and hands over on the beat.

## 9. The infinite band (Kadra)
A band that carries the type must never show its end: overscan it (+360 px each side, 2640 px wide), keep the camera from swinging in that scene (drift only: z 0→50, rotateY ±1.5°), let the transition happen *inside* the band — colour panels wipe through it right→left (`lerp(1940,−80, smooth)`, 0.1 s stagger), the last panel is the next scene's paper entering `in(3)` 0.38 s, and the band's clip opens to full frame (top/bottom → 0/1080, `in(3)`) at the cut: the band becomes the next scene. Its texture keeps drifting (−36 px/s); the next scene enters in the same direction. Same rule for any canvas background under a moving camera: overscan (+460 px).

## 10. Geometric morph between shapes (LO: the letter O becomes the planet)
Never crossfade two shapes. Map the source's own points into the target: the O's halftone dots → points on an ellipse → 3D ring points (x = u·cosφ, z = u·sinφ, y = −v) tilted 0.32·m about X → six copies at φk = k/6·π·m unroll into meridians → a wireframe sphere → dotted Earth. Depth-sort; back half at alpha 0.3. Centre and radius lerp from the O to the globe (`ioC` 0.57 s). The night iris opens from the **source's** centre to its rim, then floods (one continuous radius); dots are drawn twice (blue, and light clipped to the iris) so the colour flips exactly at the edge. Call the morph from both scenes so it straddles the boundary.

## 11. State changes instead of fades (Halftone v3/v4)
Tile flip on the beat (0.42 s; the back face carries the next style) · push-swap in a grid (the new tile pushes the old one out, 0.42 s) · hard font swap per beat with a 6 % scale pulse · `clip-path` wipe reveal · panels sliding out from under the canvas · a dot shrinking while the logo grows on the same spot · tagline rising from a mask · selection boxes switching hard on/off, staggered 0.02–0.035 s · glyphs born as random characters that resolve (`FILM.scramble`, 28 Hz) · dots born as glyphs that pop (LO). Drive discrete states with `FILM.TQ(t)` so sub-frame blur never shows two states at half opacity.

## 12. Iris hand-off into a wordmark (Reroll end)
The hero object (vinyl) flies in from a corner decelerating out of the cut, spinning (rotation = distance/radius·57.3° when rolling); the red layer's `clip-path: circle()` shrinks from 1150 px to the record's radius ×0.96 while staying centred on the moving record; the record shrinks into the "o" slot of the wordmark while the other letters rise on either side.

## 13. Glitch cut (LO, "inside the system")
In the WebGL lens: a triangular envelope ±0.07 s around chosen cuts (strength 1/.9/.8/.7); 34 horizontal bands, a band shifts when hash > 1 − 0.55·g by up to ±0.035 of the width, wrapped with `fract`; chromatic aberration ×(1+5g). Unwrapped offsets smeared the frame edges. Use on 3–4 cuts, not all.

## 14. One continuous shot from shared elements (Reroll 0–7 s)
28 tiles with pose functions (fan → graph → ring) blended per tile with `smooth(p)` and a 0.014–0.02 s stagger; assignment fan→graph is greedy nearest-node and ring slots are sorted by angle so paths never cross; threads draw on between live tile positions; pseudo-3D pinhole (f 1500, yaw −3°→3°, 150-unit dolly) with fake DOF by scale.

## 15. Camera rules
- **Inside scenes only, neutral in transition windows** (rotation 0, known scale) — then cross-scene contracts are plain screen pixels. In-scene: orbits ry ≤2.5°, rx ≤1.6°, push ×1.02–1.09 with `E.glide`; Kadra used bigger rest poses (z +40…90 px, rx 2–10°, ry ±3–6°) — keep everything drifting, never dead still.
- **Motivated** (Halftone, accepted): settle the cut's inertia (D −150, `settle`); follow the caret while typing (px +290, rx 11°); lean in on the click; crane back as results land below (D +1450, rx 20°); push in as a card grows; orbit as layers separate (ry −28°, rx −12°); frontal pull-out on Export (D×1.62); pull back on the burst (D×2.5).
- **Camera keys as summed deltas** (`path(init, [[t0,t1,{props},ease],…])`): each key adds its delta, so overlapping keys behave like stacked parent nulls — the camera never stops dead between moves.
- Open on a tilted view that settles frontal (Strata: {s 1.12, rx 14, ry −11, rz −1.5} → frontal over 1.4 s, bezier(.3,.3,.15,1)).
- Screen chrome (rulers, HUD) is counter-transformed so it stays screen-fixed; rulers tilting in perspective looked wrong.
- DOF in a DOM rig: blur = min(18, k·|1 − D/depth|), k 6–10; hide anything closer than 40 px to the lens. Camera blur: SVG `feGaussianBlur` with x/y = the camera's screen travel over half a frame × 0.32 (max 44).
- A layer that scales with the camera shows its edge on a push (Kadra's planet): give it its own layer with weaker parallax (`scale(1+0.18·push)`).

## 16. What failed
| Transition | Why it failed | Instead |
|---|---|---|
| World camera flying 1 s between artboards (Strata v2) | slow, content tiny mid-flight, no speed peak, "слишком буквально" | fast object-driven transitions; camera in scenes |
| Crossfades for tiles, words, cards, windows (Halftone v2) | "не делай переходы через opacity" | §11 |
| Fly-through a decorative ring into an unrelated wall (Halftone v2) | no cause | dive into the thing the user just clicked |
| Shape A fades while shape B fades in, iris from B's centre (LO v2) | "халтурно" | §10 |
| Next shot starts zoomed in and shrinks after a fly-in (LO v2) | direction flips | §2 |
| Band ends entering the frame during a camera swing (Kadra v6) | "дешевит" | §9 |
| 0.14 s whips, 46 px blur, empty frames after cuts (Kadra v3) | "резковато" | §5 numbers, content from the cut frame |
| Pop overshoot + needles on in-scene elements + full-frame flashes (Strata v1 details) | "резко" | strong curves only in transitions |
| Pre-rolled incoming scene visible on top of the outgoing one | ghost text before the cut | pre-roll the animation clock, not the visibility |
| Sub-frames straddling a hard cut | a half-transparent mix frame | capture.mjs keeps sub-frames on the frame's side of `__cues.hard` |
