# Technique recipe cards

These are the After Effects recipes. The same ideas as JavaScript (and the transitions invented on the launch films: fly-through with forward continuation, object carry, grow-from-point, smear, flooding background, infinite band, geometric morph) are in `transitions.md`; curves as CSS beziers in `ease-math.md`.

Provenance tags: **[V]** said/shown in the tutorials, **[M]** measured frame-by-frame from the author's renders (@60), **[D]** derived with a numerical model of AE's bezier ease, **[O]** our default (not in the videos). Sources: MahdiEdits — "Top 3 Most Used SaaS Video Transitions" (v1), "Overlapping Keyframes" (v2), "Overlapping Keyframes in 3D" (v3).

## Contents
1. Match cut (and the "object swap" variant)
2. Zoom on the cut
3. UI morph
4. Mockup hand-off
5. Overlapping keyframes 2D
6. Null chain
7. Overlapping keyframes 3D
8. Supporting moves: entrance, typing, drift, cursor click, glass
9. Anti-patterns

---

## 1. Match cut
**Looks like:** one UI element (prompt bar, card, button, icon) stays put while everything around it hard-cuts every 0.4–1.0 s [M]. The world changes, the object lives on.
**Why it works:** the eye locks on the persistent object, so cuts read as one continuous shot with changing context instead of a slide show.
**Build:** backgrounds as a hard-cut sequence (`SM.cuts(plates, [t0, t1, ...])`), the hero object on top spanning all of them. Geometry across a cut stays within ≤1.4 px [M]. The object should still be *alive*: text keeps typing through background cuts [M], the glass picks up each background's tint [M], and one pair of cuts gets the zoom pulse (§2).
**The author's 4-step build [V]:** plain white bar over cuts → dynamic backgrounds → stylised UI (frosted glass, grain) → animate the object around the cut.
**Object-swap variant (step 4) [M]:** the old bar accelerates upward into the cut (Position Y rest → rest−160 over −46…+45 frames @60, ease (0,83)/(0,83) → ≈600 px/s on the last frame, out-point on the cut); the next shot starts with the object re-entering from below (§8 entrance) and the text field cleared. Only the *direction* (up) and the element carry over, not geometry.
**What can be continuous across the cut (pick one):** exact geometry; the centre (with a zoom); the frame/slot while scale drifts (§8); or just direction (object swap).
**QA:** stills on frames T−1 and T: object identical (or as intended); no dissolve anywhere.

## 2. Zoom on the cut
**Looks like:** at the cut the persistent object "breathes" a small zoom; the speed graph is a narrow symmetric needle whose peak is exactly on the cut [V+M].
**Why:** the fastest frame of the zoom coincides with the cut, so the cut disappears into the motion. The author calls the speed graph "the most important part, more than the scale animation itself" [V].
**Build:** `SM.zoomAtCut(comp, {target: bar, cut: T, to: 115})`.
- A null above all layers; **only the persistent object** is parented to it, before any keys [V]. Backgrounds never scale [M].
- Null Anchor Point = Position = centre of the object [O; the author's pivot sat 33 px high — sloppiness, not technique, M].
- Scale keys at T − n and T + n − 1 frames, n = 0.2 s (12 @60, 6 @30, 5 @24) so the midpoint is T − ½ frame and the largest per-frame step lands on (T−1, T) [M].
- Speed 0 on both keys, inner influence 95 (95–98 measured; 90 fits twice as badly) [M]. With 95/95 the peak is 20× the average speed [D].
- 100 → 115% is the narrated value [V]; the author's own render uses a **pulse**: 100 → 135 on cut k, back 135 → 100 on cut k+1 ≥0.6 s later with a 0.24 s half-width [M] → `{to:135, back:{cut:T2}}`. Use the pulse on one pair of cuts in a sequence, not on every cut [M].
- Motion blur off in the reference [M].
**QA:** `SM.qa.zoom` → `largestStepEndsOnCut=true`, step ≈ 40–48% of amplitude @60 (57% @30).
**Direction across the cut [launch films]:** when the zoom flies *into* something (scale up into the cut), the next shot must keep going forward — start it smaller (×0.26–0.4) and decelerate to ×1. Starting the next shot zoomed in and shrinking reads as the camera pulling back; the client rejected exactly that (`transitions.md` §2).

## 3. UI morph
**Looks like:** a wide card turns into a tall card (or vice versa) "in one smooth breath" — actually two layers and a hard cut [V].
**Why:** a path morph on one layer peaks its speed nowhere in particular and distorts corners; two layers with a speed cusp on the cut hide the swap in the fastest moment, and the shared direction of growth makes it read as one shape [V+M].
**Build:** `SM.uiMorph(comp, {sl1, sl2, cut: T, axis: "y"})` with two `SM.card` layers.
- Property: `Contents > Rectangle 1 > Rectangle Path 1 > Size`, one axis only (Constrain Proportions off in the UI) — **not Scale** (distorts the radius) [V].
- SL1 grows +18% on the morph axis during its last 0.37 s (keys T−23f → T−1f @60); SL2 starts at −18% and grows to full over 0.37 s (T → T+22f) [V: 10–20%; M: 0.37 s].
- SL1 out-point = T, SL2 in-point = T; no parenting.
- Ease [M fits of the author's graph]: SL1 (0, 66) → (9×avg, 10). SL2 starts at the speed giving the **same relative speed** ρ = (dH/dt)/H as SL1 ends with [D], influence 7, then (0, min(86, 100·(1−1/r2))) where r2 is SL2's start speed in multiples of its average (≈6.25 for ±18%).
- Width and height jump at the cut; only the growth direction and ρ carry over — that is enough [M].
**Variations [O]:** content inside cards → separate layers, swapped hard on T; growth on both axes → match ρ per axis.
**QA:** `SM.qa.uiMorph` ratio 0.97–1.03; speed list rises to a spike on T−1 and starts at a spike on T.

## 4. Mockup hand-off
**Looks like:** a flat UI scrolls faster and faster, hard cut, the same UI is now on a device screen whose lid/screen swings into place with a fast-then-settling motion in the same screen direction [M].
**Why:** the cut is hidden by speed and direction, while the UI state (same viewport, same animation time) proves continuity. Pixels per second are *not* matched across the cut — the energy moves to another property [M].
**Build:**
1. Flat shot: `SM.scrollInto(comp, {prop, from, to, cut: T, ta: 3.0})` → accelerating scroll (0,50) → (2.5×avg, 15) that **ends exactly on the cut frame** [D fit to M; reference cut speed ≈2600 px/s full-frame, still rising].
2. Hard cut. The device screen uses the **same UI precomp** with startTime 0 in both shots, so UI time is continuous [V/M].
3. Device shot: `SM.settleAfterCut(comp, {prop: lid X Rotation | camera/null Position, from, to, cut: T})` → 1.2 s, (3.5×avg, 20) → (0, 95): ≈35% of the way after 0.1 s, ≈90% by 0.45 s [D fit, rms 0.011].
4. After the settle the camera drifts, then accelerates toward the next cut [M].
**Gap:** the author's full device-mockup build (3D iPhone without plugins) is in a separate tutorial not studied here; a real-AE teaser showed PNG UI pieces as 3D layers (Z ≈ −27) parented to a .glb phone, a two-node camera (zoom ≈5132 px, ≈96 mm), and two 3D nulls with overlapping keys (start 0.41·D1, length 1.15·D1) [M]. Treat that as a starting point, not a recipe.
**QA:** speed list into the cut keeps rising to the last frame; settle progress ≈0.35 / 0.66 / 0.8 / 0.88 at +0.1…0.4 s.

## 5. Overlapping keyframes 2D
**Looks like:** an object goes A → B → C as one flowing move with a rounded corner instead of stopping at B [V].
**Why:** three keys on one property force speed 0 at B — a few frames of pause the eye feels ("cheap and robotic") [V]. Putting B→C on a parent null that starts mid-way through A→B adds two bell-shaped speeds; when the object reaches B it is already moving toward C [V].
**Build:** `SM.overlap2D(comp, {layer, A, B, C, t0, mode})`.
- Object keeps only A→B. A null (pivot at B, identity transform) is created and the object parented to it **before** the null gets keys [V]. Null keys: rest → rest + (C − B) (relative offset, not absolute B/C) [V].
- `mode:"render"` (default) reproduces the author's render [M]: object 0 → D (D = 1.39 s on ≈1440 px), out 74 / in 56; null 0.42·D → 1.342·D, out 67 / in 69; ends on the same frame as the sequential version would.
- `mode:"taught"` is what the timeline shows [V]: Easy Ease everywhere, null 0.5·D → 1.62·D, D = 0.95 s.
- Start of the next move: 0.40–0.55 of the first (renders 0.41–0.47, drawings 0.48–0.53); hard limit: before the first move ends [V/M].
**QA:** `SM.qa.path` closest approach to B ≥5% of |AB| (below = timing wrong); author geometry A(232,546) B(1669,546) C(1669,261): render 7.9%, taught 6.3%; the min speed (≈11% render, ≈18% taught) must not be ≈0.

## 6. Null chain
Repeat the overlap "again and again" with more nulls [V]. `SM.overlapChain(comp, {layer, points:[P0..Pn], t0, D, step:0.5})`: move 1 on the object, each next move on a new null that becomes the new root (object → MOVE_2 → MOVE_3 → …) [O; for pure translations the order does not change the render, D]. Each move starts `step·D` after the previous one; Easy Ease, equal durations [O]. The author's diagram draws the order the other way round — equivalent for 2D [D].

## 7. Overlapping keyframes 3D
**Looks like:** a 3D object floats A → B → C, spinning as it travels, without a pause at B [V].
**Why the extra steps:** a null rotates around its own position. If the object is simply parented to a null somewhere else, the null's rotation swings the object around that distant point. Pasting the object's **B pose** (Position + X/Y/Z Rotation) onto the null puts the null's pivot and axes on the object, so the null's rotation spins the object in place [V order, D explanation].
**Build:** `SM.overlap3D(comp, {layer, A, B, C, t0, D1, mode})`, poses as `{pos:[x,y,z], rot:[x,y,z]}`.
1. Object: keys at A and B for Position, X, Y, Z Rotation [V].
2. Null: 3D switch **on first** [V].
3. Copy the object's B keys, paste onto the null at the **middle** of the first move [V] (`mode:"taught"`: 0.513·D1 [M of the drawing]).
4. **Only then** parent the object to the null [V] — compensation happens while the null holds the B pose; the test shows the pre-overlap path identical to an unparented copy (0 px).
5. C pose on the **null** (the narration says "move the 3D object to C" — doing that literally adds a third object key and brings the pause back) [V+D].
- Rotation in the author's piece: exactly one +360° Y turn per segment (B = A + 360° Y; C = B + 360° Y and Z ≈ −16°) [M]; sign of Y untested [O: +].
- `mode:"taught"` (default): Easy Ease, null lasts 1.08·D1, D1 ≈ 2.1 s on ≈1400 px [M]. `mode:"render"` (influence 64, start 0.47, length 1.25) only reproduces the render with poses fitted to it and dips to ≈3% speed in the turn — use it deliberately [D].
- 3D Model layers need the Advanced 3D renderer [V].
**QA:** min speed in the turn ≥5% of peak (taught ≈12–15%); projected size within ±2% during the overlap window [O]; with a full Y turn the object swings 63–101 px around B in taught mode [D] — reduce by starting the null later or with stronger ease if it reads as a wobble.

## 8. Supporting moves
**Entrance with inertial bounce** (`SM.entrance`) [M, v1 step 4 and the result clip]: rise from +217 px to rest **linearly** in 0.117 s (≈1860 px/s), then AE's inertial-bounce expression (amp .0375, freq 1.8, decay 3.2): −46 px overshoot at +14f, +19 at +30f, ±1 px by 1.2 s. Size X grows from a square (height×height) to full width in 0.98 s around a fixed centre, ease (0,75)/(0,75); the send button (constant size, right inner edge) spins +360° clockwise with the same timing.
**Typing** [M]: 23–40 chars/s (default 30); starts 0.42 s after the cut; caret ≈3×(31% of bar height), white, right after the last glyph, appears 2 frames before the first char, solid while typing, 2 Hz blink when idle; text left-aligned, ≈58 px inset, ≈40 px font. Text keeps typing through background cuts; cleared on an object swap.
**Drift between cuts** [M; keys O]: the content slot shrinks continuously −2.5…−3 %/s *through* the cuts; inside a shot content accelerates into the next cut and settles after it. Default: one `DRIFT` null over the whole series, Scale linear −2.75 %/s; into-cut segment like `scrollInto`; after-cut settle like `settleAfterCut` compressed to 0.4 s.
**Cursor click** [M]: macOS-style black arrow with ≈3 px white outline, large (≈130 px @1080, about the bar height); on press the icon shrinks for one frame and 5 chalky rays draw in 4 frames and fade by 0.28 s. Timing: press → first cut 0.1 s → zoom start 0.32 s → zoom peak 0.53 s. The click motivates the motion.
**Frosted glass bar** [M look; O build]: background under the bar blurred (≥40 px), ≈25% #BE96FF fill, 2 px warm-white rim (bottom brighter, ≈80%), soft lavender spot ≈22% from the left, no shadow. Build: adjustment layer with Fast Box Blur 40–60 matted to the bar shape + fill + stroke + radial gradient. (`ae_build_liquid_glass` exists in the AE MCP plugin; check its schema before relying on it.)

## 9. Anti-patterns (what the author shows as "amateur")
| Don't | Why | Do |
|---|---|---|
| Object frozen on the cut | cut reads as a slide change | needle zoom or move the object through the cut |
| Default Easy Ease on the zoom | peak spread over the whole move, cut not hidden | influence 95/95 needle |
| Zoom keys not symmetric around the cut | peak misses the cut | T−n / T+n−1 |
| Big zoom / >20% size change | motion competes with the UI | 115%, 10–20% one axis (135% pulse only as the author's render style) |
| Backgrounds parented to the zoom null | whole frame zooms, contrast lost | parent only the object |
| Path morph on one layer, or Scale for the morph | no event for the speed peak; distorted corners | two layers + Size |
| Easy Ease on the morph keys | speed 0 exactly at the joint | cusp |
| Dissolve or mismatched direction into a mockup | the seam shows | accelerate into a hard cut, same direction, settle after |
| Three Position keys A→B→C | pause at B | overlap on a parent null |
| Null starting after B, or absolute B/C on the null | no overlap / jump | start mid-way, relative offset |
| Parenting while the null is animated or offset | compensation bakes a wrong offset | parent while the null's pose is constant |
| 3D: parent before paste, 2D null, C keys on the object, no paste | stuck pose / no rotation / pause / orbiting | the 5-step order in §7 |
| Overshoot on a move that hides a cut | a second jolt after the cut | needle/cusp without overshoot; bounce only for entrances |
| Copying the drawn amplitudes of explainer diagrams | they are exaggerated 1.3–1.65× | use the stated numbers |
