# Client taste — six launch films, Oct 2026

What this client approved and rejected across Strata 2.0, Kadra, Reroll, Halftone/Inkwell 3, BLIP. and LO. (all 15 s, 16:9, code-built). Read it before the first storyboard: these rules override the generic defaults. Quotes are verbatim (Russian), shortened.

## Contents
1. How they brief and what they expect back
2. What they loved — repeat it
3. Rejections → the rule each one implies
4. Smoothness numbers that passed
5. Iteration rules
6. Communication

## 1. Brief and deliverable
- The brief is short and emphatic: "динамичный, smooth и impressive моушн лаунч ролик на 15 секунд, сценарий и сеттинг сам придумай", usually with 1–5 reference videos/images and this skill attached. Often "full code-based", "не используй хиггсфилд / AE".
- They want **pictures first and a time estimate**: "сперва покажи мне картинками… подскажи сколько все займет". Later rounds: "перед рендером отправь сториборд". Approval is one word: "гоу", "ГООООО".
- Often in a hurry: "мне надо быстро сдать ролик", "сможем ускорить процесс?".
- Deliver **1920×1080, 30 fps** ("30 фпс" — they reverted a 60 fps switch), H.264, with sub-frame motion blur, plus a `_nosound` master. Their final soundtrack is made by a human in Premiere (the project folders hold human 15.000 s / 48 kHz / 24-bit mixes for BLIP., Strata and Reroll); a synthesized track is a welcome placeholder, not the deliverable.
- References are frequently Higgsfield launch films. Take their grammar, never their brand: no "Higgsfield" name, no lime `#D4FF3A` button ("это один в один как у Higgsfield получился"), no copied layouts.

## 2. What they loved
| Film | Quote | What it was |
|---|---|---|
| BLIP. | "ГООООО"; later "BLIP мне пиздец понравился… в эту сторону качества" — **the quality bar** | photographed LED (bulge, DOF, fringes, 3-scale bloom, sheen), fonts picked from a specimen, own palette, pets with personality in motion, needles into a persistent LED face, synth sound |
| Strata v1 | "бляяяя все охуенно", "переходы в 1 варианте были охуенные" | hard cuts with the speed peak on the cut: needle zoom, whip with layered parallax, push-in, match cut |
| Strata v4 | (final, no complaints) | no cuts: fly-through, object carry, grow-from-point, smears, mesh-gradient background flooding from the action point |
| Kadra v4 | "все супер" | one virtual camera, each cut one motivated move (swingOut/swingIn with matched speed), always-drifting rest pose |
| Halftone | "все охуенно" (storyboard and v1) | storyboard from the real timeline; later the zero-dissolve rebuild was accepted |
| LO. | "начало перехода с хука на 2 сцену нравится" | needle zoom INTO the letter O (×12, x⁵ ease, peak on the cut) |
| Reroll | "гоу" on the storyboard | one persistent object (vinyl = the 0 in 2016 = the o in the wordmark), Swiss editorial look |

## 3. Rejections → rules
| They said | What was wrong | Rule |
|---|---|---|
| "дешево смотрится … присмотрись к реф картинкам, какие-то эффекты дополнительно добавь" (BLIP v1) | flat, perfectly clean vector; no lens | Code-drawn work needs a photographed pass: bloom, chromatic fringes, slight barrel, vignette, DOF where there is depth (`lens.py` or an in-page lens). Materials get rim light, specular, contact shadow. |
| "шрифты доработай, тоже дешево" (BLIP), "шрифты тоже хуевые" (Kadra v2: Barlow Condensed + Geist + IBM Plex Mono) | stock or default faces | Render a specimen sheet in the film's real copy and pick display / motif / UI. Once a face is liked (Inter Display on Kadra v1), keep it. |
| "не копировать реф картинки 1 в 1, поменяем цвета, чуть форму" (BLIP), "я тебе не говорил повторять реф ролик, а взять как реф" (Kadra) | refs' palette, shapes, story copied | Write down how each ref element is transformed (palette, shape, type, glyphs, story) and show it on the storyboard ("Отличия от рефов"). |
| "давай возьмем цвета из реф картинок (надо создать вайб windows 98)" (LO) | an invented palette where the refs carried an era look | Era/style palettes may be taken; brand identity never. When unsure, offer "ref palette vs own" on the storyboard. |
| "переходы хуевые же, ты слишком буквально понял меня, камера мувмент добавляй в сами сцены, но не в переходах" (Strata v2) | a world camera flying 1 s between scenes: tiny unreadable content, no speed peak | Camera moves live inside scenes (depth during holds); transitions are object-driven and fast. The camera is neutral in transition windows. |
| "камеры мувменты, чтобы была какая-то глубина и логика переходов… не уходи в рандом" (×3 films) | camera moves without a cause | Every camera move has an on-screen cause: follow the caret, lean in on the click, crane back when results land, push in when a card grows, orbit when layers separate, pull out on export. |
| "не делай переходы через opacity" (Halftone v2, 28 fades) | dissolves everywhere | Hard cuts at peak speed, needles, morphs, carries, wipes, pushes, flips, exposure ramps. Opacity only for small details, never as the transition. |
| "убери эту уродливую черную плашку под текстом… можешь экспозицию фона затемнить" | a dark card behind text | No plates: `filter: brightness(.42) saturate(.9)` on the background + text shadow `0 8px 48px rgba(0,0,0,.45)`; ramp exposure back as the reveal. |
| "2 сцена все еще… дешево выглядит, можно вернуться к первому варианту сетки, с динамикой" | a curved 3D wall of skewed, blurred tiles with a floating card | "Depth" = motivated camera over flat, designed layouts. Don't tilt UI into 3D to fake depth. |
| "моушн блюр какой-то дешевый" | 4 fixed sub-frames → stepped copies | 4 + 10–16 in fast windows, 12 everywhere, or adaptive; 16–24 for extreme needles. |
| "убери шум" (Halftone) | visible grain overlay (soft-light .22) | Grain ≤ .02–.04 and luma-only, or none. (BLIP's grain was in fact missing and it still became the favourite.) |
| "слишком резко", "резковато", "более smooth" (Strata, Kadra, Halftone) | needles and pops on in-scene elements, 0.14 s whips, flashes | §4 numbers. Strong curves only where they hide a cut. |
| "плашка не обрывается и мы видим фон, это дешевит" (Kadra) | a band's end entered the frame during a camera swing | Anything that spans the frame must survive every camera move: overscan (+360 px each side), or keep the camera still in that scene. |
| "уведомление сбоя по центру и акцентируем красным, а то вообще не замечаешь" (LO) | the story's key event small, off-centre, in the base colour | The one accent colour and the frame centre are reserved for the story event. |
| "форму слова LOGIN сделаем более квадратным (это же пиксели)" (LO) | a pixel TTF at 540 px reads rounded | Draw real pixels (5×7 bitmap, squares at .86 px). |
| "переход на 4 секунде с O на планету… некачественно, халтурно" (LO) | two unrelated shapes crossfading; iris opened from the target's centre | A morph is geometric: map the source's own points into the target; reveals open from the SOURCE's centre. |
| "в обратную сторону скейлится неправильно, камера же залетает в O" (LO) | next shot started at ×5.2 and shrank | Zoom direction (sign of d ln s/dt) never flips across a cut. |
| "оставь сценарий из первой итерации, просто визуал поменяй" / "ты просто объедини мои два реф ролика, не надо каждый раз жестко все менять" (Kadra) | whole story rewritten on each round / around each new ref | §5. |
| "0–2.6 с анимация не нравится, сделай как в рефе" (Kadra) | own interpretation of the ref's opening | "As in the ref" = sample that range densely (0.08 s) and copy its motion grammar beat by beat, in your own palette and type. |
| "почему blender? я же прошу full code-based" (watch film) | a DCC driven by Python | Code-based = no DCC at all. State the toolchain in the first reply. |
| "давай избавимся от 8 сцены" (BLIP) | a photo-composite scene broke the cute-pets world | One world per film; cut the beat that breaks it and give its time to the heroes. |
| "давай побольше мелких дизайнерских деталей" (Strata) | clean frames looked thin | 6–12 small, *true* details near the hero (rulers, redlines, dimension pills, guides, swatches, comments) — texture, never clutter. |
| "чтобы питомцы реально ощущались живыми, харизматичными и милыми" (BLIP) | idle motion at "still-frame" amplitude read dead | Characters get motion signatures (frequency, squash, saccades, secondary lag), one FX motif and one voice each; idle amplitude ≈ 2× what feels right in a still; judge on 2-frame sheets. |
| "че там когда финалка?" (12.5 h in, watch film) | no ETA | Give an estimate up front and update it every round. |

## 4. Smoothness numbers that passed
- Entrances 0.45–0.7 s, `soft` = bezier(.16,1,.3,1); scale from ≥0.9; travel ≤40–70 px for UI; overshoot ≤2–4 % (`back` .04/.08), springs only on entrances.
- Moves between poses ≥0.5 s `smooth`/`glide`; staggers 50–80 ms (letters 30–60 ms).
- Text entrance: rise from a baseline mask, or opacity ×1.8 + rise 24 px + blur 12→0 (+ chromatic text-shadow 14–18 px →0).
- Cursors 0.6–0.9 s per move on a 5–15 % arc; click squash 0.92 in 0.12 s, release 0.2 s; cursors enter and leave from outside the frame.
- Typing ≤50–60 cps with a seeded human cadence; any must-read line fully readable ≥0.8 s; the end card holds clean ≥1 s.
- Nothing appears or vanishes in <0.2 s outside a motion-blurred transition; no full-frame flashes.
- Camera blur (DOM films): 180° shutter of the camera's screen travel × 0.32, max 44 px (0.5 / max 70 read smeared).
- Cut swings: out `expoIn` 0.36 s / 300 px, in `expoOut` 0.7 s / 600 px (equal slope at the cut → matched speed); 420/900 px was too far (empty frames).

## 5. Iteration rules
- Back up the approved version before touching anything (`film_v3_approved.js`, `_approved_v2/`).
- Change only what the feedback names. "Name and colours" means name and colours — script, timing and fonts stay.
- New reference mid-project → merge its beats into the approved cut and show a one-line-per-beat table (beat → source ref). Never swap the whole story to the newest ref.
- "vN was better" → extract vN's frames, copy its code and numbers verbatim, verify with a side-by-side cut sheet.
- When the user names this skill ("вспомни мой скилл"), re-read the relevant reference before reworking.
- Patch-render only the changed ranges; a round of fixes should take minutes, not a full re-render.

## 6. Communication
- Reply in Russian, short. Storyboard captions in Russian.
- First reply: concept in 3–5 lines, toolchain, estimate. Realistic estimates on this toolchain: storyboard 15–25 min; film 25–45 min after "гоу" for 4–7 scene files; a revision round 15–40 min; an agent-workflow round 30–60 min. Past estimates of "1.5–2 h" / "3–4 h" were 3–4× too high.
- Self-critique your own stills and contact sheets before sending; list remaining flaws honestly in the delivery message.
- Say plainly when audio was only checked numerically.
