# Visual language of the SaaS pieces (measured from the reference examples)

This is the look of the MahdiEdits SaaS tutorials. For launch films, the client's own taste (`client-taste.md`) wins where they differ — e.g. the photographed lens pass, fonts from a specimen sheet, no visible grain, no text plates.

Take the techniques and the look; never the author's branded cards/wordmark, other products' UIs or logos (Wix, Base44, drink cans, YouTube mock pages), or the on-screen typos.

## Composition
- One large UI hero in the centre — a prompt bar ≈931×125 (≈48% of frame width), a card, a button, an app container — and the world changes around it.
- Product frames: a light macOS-like browser window centred (≈1303×782; title bar #F6F6F6, 48–58 px, three hollow grey circles, small grey title, radius 15–20 px). Content inside it is at ≈0.68–0.76 scale — work in %/s or full-frame px, not window px.
- Device shots: space-grey laptops on a dark glossy floor with a soft key light; phone in hand, laptop on a desk, tablet on a shelf; the same UI travels across devices.

## Materials
- **Frosted glass tinted by the background:** blur under the bar (≥40 px), ≈25% #BE96FF fill, 2 px warm-white rim (bottom brighter ≈#FCF0D8, top ≈#FDD7C0), a soft lavender spot ≈22% from the left that does not follow the cursor, no shadow; send button ≈95–100 px, lighter than the fill, white arrow; white text ≈40 px with a ≈58 px left inset. The tint changes with every background cut.
- **Dark indigo glass** for buttons/cards: fills #201A46 / #161534→#241E4A / #12122A, thin gradient rim brighter at top and bottom (#848290); morph cards: vertical gradient #1E1C45 → #2B2966, light-lavender rim #A5A4C3, white specular streaks on the sides.
- **Plain white bar** #FFFFFF with dark-grey text and a blinking caret (the basic version).
- Light grain and soft glow on text, glass and annotations almost everywhere.

## Backgrounds
- Organic full-frame plates contrasting the clean UI: grapefruit macro, pink fur (~#E89CB8), grass in wind, blurred bokeh (#B7C9D7 / #626E7A + warm #997D67), pink-lilac sky (#C2ABB5). In the final clip they are 30 fps footage (the grapefruit pans ≈200 px/s, fur and grass move in place); plates never scale with the object. Source: calm macro textures (stock or generated), no small text.
- Soft flat gradients: magenta #3A0436 / #4F0B48, olive #584815, navy #1C1D49.
- Explainer background: dark navy → indigo radial/mesh gradient with vignette and grain (corners #000000–#08050C, base #121028, glow #1C1D49–#222A5E); v2/v3 explainers use #000000 with a 125 px grid of #0C0C0C–#141414 lines.

## Type
- Neutral grotesk (SF Pro / Inter-like), off-white #E1E4E9–#F7F7FF, light grain and glow. Mixed weights per word: intro words light italic, accents bold/bold italic; second line smaller and lighter.
- Section titles heavy sans revealed through grain/noise and blur (≈0.45 s), words ≈0.15 s each with the line re-centring; v2/v3 titles use ultra-condensed caps (Bebas/Anton-like).
- Accent card trio "Direction / Speed / Timing" in three weights and colours (#8FB0E6 / #D6E05A / #E05A70).

## Accent palette
| Role | Colours |
|---|---|
| Interface blue / keys | #2F73DE, #3F7FF0, window frames #0F3774 → #2151A5 |
| Speed-graph overlay | yellow line #D9D45A / #E5D64A, white key dots |
| Cut marker | cyan column #38A6FF |
| Problem / solution / null timing | red #C73535–#DA433C / blue / green #628B27–#7FA538 |
| Product accent (3D) | lavender #9C9BDE–#9FA0F2 |

## Rhythm
- Cuts every 0.4–1.0 s (examples up to 1.6 s); between devices 0.6–1.4 s. A reel can fire 4 cuts in 0.8 s (0.2 s shots) and then hold 1.0–1.8 s with motion inside the shot.
- Between cuts the frame keeps living: the card slot shrinks −2.5…−3 %/s through the cuts, content accelerates into the next cut and settles after it.
- Windows and cards drop in from 58–84 px above and land in ≤0.4 s with ease-out, no overshoot, staggered left to right; exits go up with the same stagger.
- Glass panels expand in width with a strong ease-out (≈940 → 1820 px in ~1 s, height constant).
- No overshoot on moves that hide cuts; an inertial bounce only on an object's entrance.
- Motion is motivated: a cursor click triggers the move; text keeps typing through background cuts.

## Edit grammar
- **Author's result clip (5.5 s):** object entrance (rise with bounce, width, button turn, typing; 1.2 s) → hold ≈1.1 s → pull back into a browser window + cursor click → cut 0.1 s after the click, shot 0.43 s → cut with the zoom-in pulse, shot 0.6 s at ×1.35 → cut with the zoom-out, shot 0.83 s.
- **Sections:** hard cut to a dark title card (≈0.7 s hold), hard cut out.
- **Default for a 10–30 s piece [O]:** hero entrance → hold ≈1 s → action (click) → 3–5 cuts of 0.4–0.8 s with one zoom pulse → UI morph → mockup hand-off → final hold ≥1 s. Cuts on whole frames; sync to a beat only if a track is given.
