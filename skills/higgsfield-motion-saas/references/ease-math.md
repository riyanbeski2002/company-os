# Ease math: how AE's speed/influence shapes the speed graph

## The segment model
A temporal-bezier segment between keys (t1, v1) and (t2, v2), D = t2 − t1, has the 1D control polygon
`P0 = (t1, v1)`, `P1 = (t1 + i1·D, v1 + s1·i1·D)`, `P2 = (t2 − i2·D, v2 − s2·i2·D)`, `P3 = (t2, v2)`
where s1/i1 are the first key's **out** speed/influence and s2/i2 the second key's **in** speed/influence (influence as a fraction). `KeyframeEase.speed` is the property's real speed at that key (units/s, signed for non-spatial properties; path speed for spatial Position); influence only decides how long the curve keeps that speed. Average speed v̄ = |v2 − v1| / D.

`SM.seg` takes speed as **r = speed / v̄**, so a recipe like "(9×, 10)" is size-, distance- and fps-independent.

## Four target shapes
| Shape | Where | Keys | Peak |
|---|---|---|---|
| Easy Ease arch | the mistake at an event | (0, 33.33) both | 1.5·v̄ mid-segment, **0 at the keys** (it is exactly smoothstep) |
| Needle | zoom on the cut | (0, a) both, a = 95 | v̄ / (1 − a) mid-segment → 20·v̄ at 95, 10·v̄ at 90; put the midpoint on T − ½ frame |
| Cusp | UI morph joint | outer (0, a), joint (r·v̄, b) | on the joint key; no overshoot while 1/(1−a) ≤ r ≤ 1/b |
| Relay | overlap at a pose | two bells, the second starts ≈0.45 into the first | the sum never reaches 0 at the pose |

## Matching speed across a cut between two layers
Absolute px/s cannot be matched when the two shapes differ in size (the incoming card's peak disappears). Match the **relative** speed ρ = (dH/dt) / H instead:
- SL1 ends with speed s1 = r1·v̄1 at height H1·(1+p) → ρ1 = s1 / (H1(1+p)).
- SL2 starts at height H2(1−q) → s2 = ρ1·H2(1−q), i.e. r2 = r1 · p/(1+p) · (1−q)/q · D2/D1.
- With r1 = 9, p = q = 0.18, equal durations: r2 = 6.25; SL2's end influence = min(86, 100·(1 − 1/r2)) = 84.
Self-test numbers (912×312 → 662×900 cards, @60): ρ1 = 3.74/s, ρ2 = 3.80/s, ratio 1.017.

## Overlap metrics (A→B→C, translation)
| Version | Closest approach to B (% of \|AB\|) | Min speed (of peak) |
|---|---|---|
| Sequential, Easy Ease (amateur) | 0 | ≈0 (the pause) |
| Taught (Easy Ease, null 0.5→1.62·D) | 6.3 (6.2–6.6 model) | ≈18% |
| Render (object 74/56, null 0.42→1.342·D at 67/69) | 7.9 (measured 7.9) | ≈11% (≈330 px/s at the object's B key; ≈26% at the moment of closest approach) |
| Hybrid "Easy Ease object + 70% null" | 3.9–4.3 → reject | — |
Numbers depend on geometry (they are for A(232,546) B(1669,546) C(1669,261)); the stable checks are "closest approach ≥5%" and "min speed clearly above 0".

## Reading `SM.qa.speedGraph`
It prints |Δvalue|/frame·fps for each frame step, i.e. AE's speed graph as numbers. Self-test examples @60:
- Zoom needle 100→135 (±0.2 s, 95/95): `2 5 9 14 20 28 38 53 77 120 244 880 244 120 77 ...` — peak on the step that ends on the cut.
- Morph SL1 then SL2 (px/s): `... 301 420 623 1030 | 2441 1618 1120 837 ...` — rises into the cut, starts at a spike after it.
- Mockup scroll into the cut: `1225 1239 ... 1747 1777 1810` — still rising on the last frame.
If a list touches 0 in the middle of a move, there is a pause; if the peak is off the cut by a frame, move the keys, not the influence.

## Quick offline model (planning without AE)
```python
def ae_value(t, T, s1, i1, s2, i2, D=1.0):           # 0..T time, 0..D value, speeds in value/s, influences 0..1
    P = [(0, 0), (i1*T, s1*i1*T), (T - i2*T, D - s2*i2*T), (T, D)]
    lo, hi = 0.0, 1.0
    for _ in range(60):                                 # solve x(u) = t
        u = (lo + hi) / 2
        x = (1-u)**3*P[0][0] + 3*(1-u)**2*u*P[1][0] + 3*(1-u)*u*u*P[2][0] + u**3*P[3][0]
        lo, hi = (u, hi) if x < t else (lo, u)
    u = (lo + hi) / 2
    return (1-u)**3*P[0][1] + 3*(1-u)**2*u*P[1][1] + 3*(1-u)*u*u*P[2][1] + u**3*P[3][1]
```

## The same math in code films
- **Power curves at a cut.** `in(k) = p^k` ends with slope k, `out(k) = 1−(1−p)^k` starts with slope k. For a move of Δ over T the speed at the cut is k·Δ/T on both sides — choose k, Δ, T so the two products match (Reroll's mirrored whip: −700 px `in(2)` 0.45 s into the cut, +700 px `out(2)` 0.45 s out of it → identical speed).
- **Zooms are matched in log scale.** Speed of a zoom is d(ln s)/dt. Strata s5→s6: s5 eases the scale ×1→1.35 with `in(3)` over 0.35 s → ds/dt at the cut = 3·0.35/0.35 = 3.0/s, i.e. 2.22/s in ln-scale; s6 opens at ×1.35 and adds 0.185 with `out(3)` over 0.27 s → ds/dt = 2.06/s (1.52/s in ln). Same sign, ratio ≈1.5. LO: ×12 needle (x⁵) +27/s → next shot ×0.26→1 `out` +15.8/s. **The sign must match** (the fly-in continues); a ratio within ~2× reads as one move.
- **Bezier pairs with equal end slopes.** `expoIn` bezier(.7,0,.84,0) and `expoOut` bezier(.16,1,.3,1) both have slope 6.25 at the cut, so a 300 px / 0.36 s swing out matches a 600 px / 0.7 s swing in (833 vs 857 px/s).
- **AE speed/influence as CSS beziers** (Halftone port): needle (95/95) ≈ bezier(.95,0,.05,1); scrollInto ≈ (.5,0,.85,.625); settleAfterCut ≈ (.2,.7,.05,1); uiMorph out/in ≈ (.66,0,.9,.1)/(.07,.44,.16,1); entrance width ≈ (.75,0,.25,1); Easy Ease = (.333,0,.667,1).
- **Log-space zoom helper:** s(t) = exp(lerp(ln a, ln b, e(p))). A linear-in-scale zoom of ×1→×12 spends almost all its visible motion at the end; log space makes equal ratios take equal time.
- **QA in code:** `window.__qa()` (template) prints d(ln s)/dt on the last frames of each outgoing scene and the first frames of the next one, flagging sign flips — the code twin of `SM.qa.zoom`.
