# Вкус клиента: что нравится и что нет (все сессии, по темам)

## 1. How to read this file

**Read §1 before designing anything, then the sections for the job at hand.** This file holds taste: what the user liked, rejected and asked for. Process, recipes, generation technique, rendering and QA live in `production-lessons.md`.

- **Organised by topic, not by round.** The round-by-round history of the first two projects is the appendix at the end, kept as evidence.
- **Every rule ends with its ledger ID**, e.g. [T-02]. IDs come from the lessons ledger (all sessions, Oct 7–8 2026). `[pre-ledger]` marks a rule carried over from the previous version of this file (memory notes minimal-one-idea-per-beat, lipsync-frame-taste, generation-placeholders) that the ledger never contradicted.
- **«…» is the user's verbatim wording**, typos kept. A quote after → is the user's verdict on the fix.
- **Newer explicit feedback wins.** Where two sessions disagreed, the resolved rule is stated in its section, the 'What changed' table below lists the old rule, and the appendix marks it **SUPERSEDED**.

**Projects behind the evidence:**

| Project | What it was | Session |
|---|---|---|
| Lipsync 2.0 trial, Audio MCP | Higgsfield brand key frames, then a short film | 2746ff (A) |
| ZEVRA | AI SaaS launch in the style of a real company's board | 2746ff (B) |
| SHIFT | 30 s SaaS product ad (FLOW brief) | 257453 |
| PLAY | 30 s ad for an LLM that builds games | 5f377a |
| POST | 30 s copywriting-product ad on the user's track | 769e6b |
| onbeat | 15 s techno-SaaS film | b9e6af |
| PHYLLA | LLM launch film: living-lab identity + generated montage | f18bfc |
| Ad Multiplier remake | Higgsfield launch remake from a reel | fe5d90 (+ helper c75026) |

### The density principle (resolved)

**One focal idea per frame, and a rich film.** [K-01]

- **Banned:** decoration that belongs neither to the product nor to the identity: satellites around a hero, HUD rows, chip clouds, legends, corner marks, meta footers. [T-01]
- **Welcome:** density from ONE coherent source per frame [K-01, T-02..T-04, C-01]:
  - a world layer;
  - the real, believable product UI;
  - the product's own diegetic output;
  - identity-derived line work;
  - a higher shot count.
- **Genre decides the dose:**

| Job | Dose | Where the richness comes from | User's words |
|---|---|---|---|
| Higgsfield brand / launch key frames (Audio MCP, Lipsync) | Restrained: one focal idea, generous field; a few frames may be bolder | Material, light, type; one bold structure (orbit, exploded stack) | «слишком много фрагментов и лишнего мусора» |
| productDemo / SaaS / app ad (SHIFT, onbeat) | The whole app | One persistent app with full chrome; 2–4 functional details per shot | «не вгылядит как saas продукт» → «гуууд» |
| Game / playful product ad (PLAY) | The product's own output | Score/lives HUD, READY/GO banners, looping game screens | «добав куча элементов игровых и вау» |
| Identity-led launch film (PHYLLA) | World + identity line work | Construction lines, coordinate chips, orbits, rulers | «больше всяких линий и узоров на моушн по стилю» → «а так все вау» |
| Montage of generated footage (PHYLLA) | Many beats | Cut rate (~40–50 cuts per 30 s), every shot distinct | «еще быстрее нужно» → «а так все вау» |

[K-01, T-03, T-04, M-06]

### What changed against the old file

| Old rule | Now | IDs |
|---|---|---|
| "1 headline + 1 hero object + 1 small supporting element", lots of negative space | One focal idea + density from one coherent source; restraint only for Higgsfield brand key frames | T-02, K-01 |
| No HUD, counters or micro-labels | Decorative HUD stays banned; UI the product itself produces is content | T-04, K-22 |
| No glass | No 3D glass objects; flat UI frosted panels are fine | T-08, K-10 |
| Fonts locked to the brand | Fonts and colours follow the identity; the lock is for Higgsfield-brand films only | T-15, K-09 |
| Calm camera (handbook: static default, one verb) | Camera always active and motivated | CA-01, K-02 |
| Holds of 1.5–3 s | No dead air over 0.5–0.6 s outside listed reads | M-05, K-03 |
| Pool of ~6 images per film | Every item distinct on one→many beats | T-19, K-04 |
| End card mirrors the cover | Clean text packshot | T-18, K-05 |
| "No model-pretty faces" | Attractive, young, fashion-editorial cast; realism from camera and light | T-16, K-06 |
| Generations are always placeholders | Placeholders in a design trial only; production uses generations (see `production-lessons.md` §Generations) | T-22, G-01 |

## 2. Density and detail

- **Never build density from scattered decorative fragments.** No satellite cards around a hero, no HUD header rows ('BRAND ( PRODUCT ) · N° 03 — 12'), no corner marks, tool-call chip clouds, ring text + legends or meta footers. Nothing that reads as «лишний мусор». Evidence: the Audio MCP orbit frame, «то что ты сделал это слишком много фрагментов и лишнего мусора». [T-01]
- **Minimal is not empty.** Every frame needs at least one of: a world/environment layer, real product UI, a macro-scale hero that fills the frame, or identity line work. Never ship a film made of '1 headline + 1 object on a bare field'. [T-02]
  - Thumbnail test: does each frame read as a designed poster, or as a slide with one word?
  - Empty field stays inside the density table: titles 60–85%, UI/demo 40–75%.
  - The old default caused four rejections: Lipsync v1 «мне нравится дизайн, он примитивен слишком, нужно интересные подходы»; onbeat v1 (7 sparse shots, 75–90% dead field) «очень коротко и пусто»; SHIFT v001 (isolated cards on a pale gradient) «нужно динамично, и плюс дизайн не очень вообще / не вгылядит как saas продукт»; ZEVRA 15 s (mostly static) «задумка топ… а то вообще топорно выглядит».
- **Give the film one world.** One spatial structure derived from the concept, reused across shots: sharp, blurred, dimmed, light or dark; behind type frames and under the end card. It fills frames and gives continuity without HUD clutter, and counts as one group. [C-01]
  - Example (onbeat v2): a 12×16 drum-machine grid in CSS 3D (rotateX ~70°, perspective 1200). Wide in the hook, blurred at 0.32 behind the name, light on the scale beat, low under the lockup → «собери mp4».
- **Product ads show one persistent, believable app** the camera travels through: sidebar with live counters, top bar with breadcrumb / Search ⌘K / clock / avatars, real lists and states from one fictional dataset. Never one floating card under a centred headline per scene. [T-03]
  - Draw the 1–3 controls of the beat at full fidelity; everything else is quieter texture (≥28 px), cropped, or softened by depth.
  - Frameless OS window, never a device mockup; one radius, shadow and hairline family.
  - The product surface appears in ≥2 shots (UI demo = 20–40% of runtime).
  - Evidence: SHIFT «не вгылядит как saas продукт / давай с нуля но с той же айдентикой» → hybrid with full app chrome «гуууд»; onbeat v2 with cause cards + incident panel → «собери mp4».
- **Functional detail is welcome; decorative detail is not.** [T-04]
  - Welcome: 2–4 small, crisp product-UI details per shot inside the interface: meta rows 'a • b • c', chips '✦ add more details', status dots, cursor clicks, timecodes, highlighted prompt words, progress shimmer.
  - Welcome: the product's own diegetic output (game score/lives, READY/GO banners). UI the product itself produces is content; decorative HUD framing a shot is clutter. [K-22]
  - Welcome: technical annotation drawn from the identity references: construction lines, coordinate chips, orbits, rulers.
  - Still banned: decorative HUD rows around a frame, satellites, floating blurred pills or blobs, fake facts (funding, user counts), counters that do not come from the product.
  - Numbers: align to a baseline grid; consistent radii; chips ≥18 px and meta ≥16 px @1080p, as texture only; labels carry real data; lines at alpha ~0.55–0.6 with ≤1–2 labels per frame.
  - Keep the type layer around rich content clean.
  - Evidence: «добавь больше деталей что ли по шрифту и по градиенту» → «хорошо, очень» (ZEVRA); «добав куча элементов игровых и вау», «давай помощнее сделаем игры» (PLAY); «да ктстаи, добавь больше всяких линий и узоров на моушн по стилю» → «а так все вау» (PHYLLA).
- **Subdue background particle fields** (stars, streaks, dust) so the hero action reads first: fewer, shorter, thinner, more transparent. Example: the cat game went from 190 stars to 80, streaks shorter and thinner at about half the opacity. «и давай игру с котиком, там звезды сильно мешают гоу убавим их». [T-21]
- **Carry over the IDEA of liked frames, never their devices.** When one or two frames are liked, reuse their one bold structure, not their ornaments as a system. Brief agents: "take the structural idea; density follows the genre rule". The Audio MCP v3 'system designer' shared HUD frames, N° numbering, satellites, ring text, cables and glow across all frames, and 25 min later got «слишком много фрагментов и лишнего мусора». [O-04]

## 3. Composition and references

- **Centre only where it is genuinely ideal:** hero, lockups, CTA. Elsewhere break the centred/Swiss layout when it adds energy: asymmetry, scale contrast, off-frame crops, macro close-ups, perspective, type/object interplay. «Если считаешь что по центру подходит идеально, не меняй кадр». Make only some frames off-centre (see §12). [T-22]
- **Macro scale and off-frame crops on hit beats.** [T-22]
- **Higgsfield key frames explain the product through bold graphic structures, not template UI:** orbits, exploded views, stacks, tunnels, cross-sections, and poster-grade typography. Use each as ONE clean structure per frame, never as a dashboard. [pre-ledger; scoped by O-04]
- **Higgsfield taste targets:** the team's own Figma style (original Audio MCP, Launch 50s), the reels at instagram.com/higgsfield.ai/reels, and other motion designers' work on X/Twitter. [pre-ledger]
- **Language beat:** one big native-script word plus one small accent, never slot lists or flags. Liked: big こんにちは + mini wave + "English → 日本語" caption. The slot-machine list of languages was «ужасная» («Страница 10 - ужасная»). [T-22]
- **Read a reference for its energy and structure, not its layout, chrome or signature decoration.** [T-10]
  - Take: scale contrast, saturated plates, type voice, structural devices. Sample colours from its pixels and map its energy onto the identity's hues.
  - Never copy: site chrome (logo + nav + CTA bar), literal layouts, copy or logos.
  - Expect heavy decorative backgrounds (ray shaders) and an italic-serif accent to be dropped.
  - When sources conflict: hard floors (legibility, contrast, no generated text, honesty) > brief > reference > house defaults. List the defaults you replaced.
  - The genre×style matrix is a fallback only; a user reference outranks it. SaaS → soft-pastel-ui produced the pale SHIFT v001, «дизайн не очень вообще». [K-21]
  - Evidence: header-chrome screenshot + «уберем, давай помощнее сделаем игры» (PLAY); «на первом уберем совсем фон заменим на более обычную… по визуалу прошлый нравится», «давай другой шрифт не брать serif» (ZEVRA).
- **'Make motion in this style' from a real company's board → a fictional brand with an original mark.** Never copy the logo, name or texts. Keep all copy in one config file (brand.js) and explain in NOTES how to swap brand, texts and colours. KOAH board → ZEVRA (a fan of 5 rays in a squircle): «сделай моушн в таком стиле» → «короче хорошо». [T-11]
- **Partners appear only as plain text**, even when the library ships their logo. [T-22]

## 4. Materials and 3D

- **No detailed or old-fashioned 3D objects:** glass tubes, meniscus, bubbles, macro glass, chrome, liquid floods, letters replaced by objects. «мне не нужен слишком детальный 3D дизайн, он выглядит старомодным». Keep a balance between minimalism and maximalism. [T-08]
- **3D means monumental sculptural forms** in matte clay, satin, wax, felt or thermal-emissive material, in a clean void. PHYLLA clay/sphere 3D → «Мощно». [T-08]
- **UI glass is allowed:** flat frosted-glass panels, gradient borders and glows inside SaaS UI. Keep them small and never nested. The ban covers 3D glass objects only. «может ui красивее сделать, градиентовую saas прям» → «гуууд». [T-08, K-10]
- **The capsule wave is the flat S1 lime capsule:** no glass tube, meniscus, glints or bubbles. The glass capsule waveform was too 3D. [T-22]
- **No mirrored floor reflections** of text or objects in the flat look. A soft coloured light pool under the object is the maximum. The V1 floor had a hard horizontal cut and mirrored text under the CTA pill; the final removed floors and reflections entirely. [T-09]

## 5. Type and colour

### Identity first

- **Fonts and colours follow the identity, not the Higgsfield lock.** The brand lock is the default only for Higgsfield-brand films. When the user lifts it or brings references, choose freely from Google Fonts. [T-15]
  - «не ограничай цветами и шрифтами» (Lipsync trial).
  - Prefer the user's own references over Claude's comparison sheets: a 6-grotesk comparison sheet did not land; the user's own UI references did.
  - Show 2–3 stills before switching the font of a whole film.
  - Serif and condensed caps are risky defaults for SaaS launches; keep them when they are part of a given identity. [K-09]

| Font move | Verdict |
|---|---|
| Serif accent | Rejected in ZEVRA; kept as identity in SHIFT; the one accent word in PHYLLA |
| Geist | Rejected in ZEVRA; accepted in PLAY |
| Mono/terminal faces for 'технологичное' | Rejected: «давай другой шрифт не брать serif, а что то технологичное» → «шрифт не очень» |
| Condensed heavy caps (Anton) | Replaced in PLAY within 45 min («замени шрифт») |
| Approved Audio MCP final | Instrument Serif, Inter Tight, Noto Sans JP, JetBrains Mono |

[T-15]

### The converged SaaS-launch look

- **For AI/SaaS product launches the user converges on a white SaaS look:** [T-13]
  - a white or milk base, optionally with a light dot grid;
  - a soft, grainy pastel mesh glow, only behind the product;
  - one bright blue/violet action accent;
  - a friendly modern grotesk in sentence case (Plus Jakarta Sans / Geist, plus Inter for UI);
  - app windows with a title bar; a prompt input with an AI gradient ring and a black button.
- **Higgsfield lime and acid greens do not carry into other identities.** A dark base with acid accents was requested, then rejected once seen. «давай все таки с белым основным цветом», «замени шрифт, и сделай дизайн saas стиле» → «Хорошо»; «добавь синего яркого цвета, а не зеленый» → «хорошо, очень». [T-13]

| Film | Type | Base | Accent |
|---|---|---|---|
| ZEVRA | Plus Jakarta Sans + Inter | #FAF8F5, pastel mesh | #1F4BFF |
| PLAY | Geist | #FBFBFC + dot grid | #7C5CFF |
| SHIFT | Plus Jakarta Sans + Instrument Serif | not recorded | #3A4BFF |

[T-13]

### Gradient-SaaS surface language

- **Asked for a 'more beautiful SaaS UI', use the gradient-SaaS language as one system, built only from the identity's hues.** Saturated chapter plates beat pale pastel washes. 'More energy' means deeper OKLCH steps of the existing hues, never a new hue. [T-12]
  - Parts: aurora/mesh chapter plates; a light horizon under the active panel; small frosted popovers; 1–1.5 px gradient hairlines; brand-tinted layered shadows; a coloured glow under the focused card; a gradient primary button with an inner highlight; gradient KPI tiles and chart strokes; static fine grain.
  - The action colour goes only on the acted-on object (+≤1 echo, ≤8% of frame), never on a plate of its own hue.
  - Atmosphere hues sit ≥60° away from the action hue.
  - Check APCA on saturated plates: 6.4:1 WCAG was only Lc 49.5.
  - Evidence: «может ui красивее сделать, градиентовую saas прям» → «гуууд»; pale v001 «дизайн не очень вообще».

### Living Lab (PHYLLA identity, approved)

- **Reuse the approved PHYLLA identity as the 'living-lab' preset** (bio-digital / techno-organic). The user asked for it as a preset and named it: «как назвать пресет? быстро» → 'Living Lab'. Full spec: `~/Downloads/PHYLLA/MASTER_PROMPT_EN.md`. [T-14]
  - Two alternating worlds: black instrument world (#050505, 2 px dot grid every 60 px #262626, dashed construction lines) and cream specimen paper (#EFE8DE with a #D3C8B8 dot grid).
  - Accents: petal pink #F49AC8, magenta #E8559B, cornflower #3F6FE8, apricot #F7B27A, thermal orange #F07A2E, butter #F6E27A, mint #7FE8C8, lime chip #E4F58C.
  - Type: Inter Tight 600/700; one Instrument Serif italic accent word per line (Cormorant for Cyrillic); JetBrains Mono for labels.
  - Elements: window tiles with mint corner handles, data chips, dot-matrix, thermal remap, phyllotaxis 137.5° mark, grain 0.04–0.07.

## 6. People and casting

- **Cast attractive, young (≈22–34), fit, well-groomed people** in fashion-editorial styling or fashionable plain athleisure (for this user, East Asian and white). Generate each identity in Soul 2 first, then animate in Seedance. [T-16]
  - Applies to every role, side characters included. Where age was the joke, adapt the role (dad → boyfriend).
  - Show 2 variants per hero.
  - Prompt 'no text, logos or prints on garments', then QC the cast sheet: text slipped onto 2–3 shirts.
  - Documentary realism only when the user asks for it.
  - Evidence: «давай бабушек заменим на красивыз девушкек, фэшн стилЬ, азиатки, милые и красотки, через soul 2 сначала» (PHYLLA); «… новых людей, красивых с модной спортивной одеждой, азиатов и белых, используй сначало soul 2», «да, перегенерь их моложе и красивее некоторых» (Ad Multiplier).
  - This overrides the older "ordinary, imperfect people / never pretty-model" note: slop comes from the glossy camera, light and staging, not from attractive people. [K-06]
- **Realism ('anti-slop') comes from camera, light and skin texture.** [T-16, G-02]
  - Slop signs: golden-hour light, catalogue rooms, symmetric hero framing, smooth skin, posed grins, stock UGC grids, perfectly stacked props.
  - Aim for phone-real footage: real optics and imperfect framing; mixed colour temperature, clutter and noise; natural, slightly awkward acting; zero legible text.
  - Never animate glossy Nano Banana Pro start frames for live action. Use stills as identity references, not as the literal first frame.
  - Exception: art-directed macro, nature and 3D shots may use controlled start frames when the user asks (PHYLLA NB Pro → Seedance i2v was approved). [K-07]
  - Evidence: «давай генерашки изменим, они сильно слопные» (Ad Multiplier v1 from NB Pro start frames).
- **A person who is the hero of a code-rendered piece (title, cover, orbit) is a live generated video cut-out** (moving, laughing), never a static photo cut-out. «и где девушка я думал будет живая генерация ее типа». Technique: `production-lessons.md` §Generations (green-screen plate + own chroma key). [T-17]
- **When the user supplies their own generations, use all of them and put theirs at the hero moments:** the full-bleed reveal after Generate, and the post/CTA. A mix of diverse genres sells 'any idea'. In ZEVRA the user's SUV clip replaced Claude's at the 12 s reveal, and the woman with a laptop went into the 'Now live' post. «и эти генерашки добавим»; «заменим на другую генерацию которую я скидывал, здесь тоже». [G-13]
- **No mannequin cut-out heads with sticker lips** («это точно не то»). [T-22]
- **Design trial (the user says «пока нет, просто дизайн»): no generations, no dropped-in existing images.** [T-22]
  - Put a designed placeholder in each generation slot: an elegant window plate (circle, arch or rectangle with a lighting gradient), a "✦ GENERATION" label and a one-line shot description, built into the composition.
  - Placeholders must look intentional and on-brand; they must never dominate the frame (big grey placeholders were part of Lipsync v1's rejection).
  - Production mode (the user names models, authorises Higgsfield or asks for assets) expects real generations: see `production-lessons.md` §Generations. [G-01]

## 7. Motion feel and camera

- **Nothing simply pops in or out.** Every entry combines move + scale (0.96→1) + opacity + blur (8→0 px) and lands on an expo-out; every exit mirrors it on a cubic-in. Captions and CTAs take ~10 frames to enter, not 2–3. ZEVRA v3: «задумка топ, нужно сделать прям smooth переходы а то вообще топорно выглядит» → v4 with this toolkit everywhere: «хорошо, очень». [M-01]
- **Energy comes from camera and staging, not frantic speed.** Once a film is 'powerful', default to the productive/house personality (hf.enter/exit/move/camera; headline 0.6 s, hero 0.9 s, camera 1.5 s): halve beat kicks, soften shake, lengthen zooms. Overshoot only on chips (≤6%) and props (≤10%). PLAY v2–v6 (energetic + playful: crash zooms, beat kicks, a cat hopping on every beat): «нужно дополишить по дизайну очень очень хорошо и аккуратно, сделать анимацию игры и чуть помедленнне» → house-easing version «Хорошо, давай motion blur…». [M-07]
- **The camera is always active and motivated.** In every shot it follows what moves (card, toast, cursor, courier, route dot) or reveals the next piece of information: trucks, pushes, pull-backs, quick whips between modules that come back. It stands still only on listed reads (§8), and holds keep a gentle drift. A locked-off camera over cut-together compositions reads as slides. [CA-01]
  - In a generated montage, every clip carries one clear, purposeful move, varied across the set (macro push, crane, orbit, FPV, rack focus).
  - Record the lifted handbook limits (one verb, moves ≥1 s, whip ≤1) as a client exception in the passport, with the user's words. [K-02]
  - Evidence: «короче хорошо, но нужно … сделать динамичнее… полноценно показать моушн / используй камеру мувмент» (ZEVRA); «давай динамичнее, сделаем, чтобы камера двигаласьб туда сюда» → «гуууд» (SHIFT); «также камера мувмент по моушн нужен», «камера мувмент мощный» (PLAY); «давай добавь еще камера мувменты» (PHYLLA).
- **Camera moves are logical and ease in and out at both ends.** [CA-02]
  - Banned: a crash zoom on every shot, a whip pan for its own sake, micro-shake, roll, jerky speed ramps.
  - Fast moves are fine when they follow an object or land on a hit, always with motion blur and a soft landing.
  - Shake ≤6 px, only on impacts.
  - Moves inside generated clips belong to the footage, so a montage may use FPV and crash zooms. [K-02]
  - Evidence: ZEVRA v1 gave every shot its own showy move → «камера мувмент была логичное и easy in easy out и тд». v2 used easeInOutCubic/Quint with zero end slopes, at most one fast travel per act, and direction carried across cuts.
- **On a one→many beat, fly the camera past every item.** Never a static ring or a plain pull-back. [CA-03]
  - Example: a carousel of 13 window cards ~28° apart turns ~200° with ease-in/out while the camera pulls back from the hero item.
  - Keep a slow rotation (~1°/s) under the end card.
  - Keep the hero card forward in Z (+220 Z, scaled ~0.9) so ring cards never slice through it.
  - Evidence: «давай здесь покажем камера мувментов игры»; repeated: «давай когда будем показывать это пусть мы покажем камера мувментов все игры типа» (PLAY).

## 8. Pace

- **Separate pace from motion speed.** Event density is high (no dead air, something new on every beat, many shots); each move stays smooth and unhurried. The PLAY slow-down was about frantic motion, not about holding longer. [K-03]
- **No dead air: something new happens every 0.5–0.6 s.** [M-05]
  - A still frame is allowed only as a listed read:

| Read | Hold |
|---|---|
| Status | 1.0 s |
| Name + ✓ | 0.6–0.7 s |
| Three numbers | 1.2 s |
| A list item | 0.8 s |
| End lockup | 2 s |

  - During every hold the next trigger is already arriving.
  - Strong music hits get a reaction on the hero: camera kick, light breath, highlight wipe, counter roll.
  - Measure dead air on a render instead of guessing (metric and tool: `production-lessons.md`). SHIFT v003 → v004: dead air 4.87 → 1.53 s, longest stretch 1.20 → 0.37 s, approved.
  - The readTime formula alone gave a cut that lingered; keep it for lines read while the camera moves.
  - Evidence: «гуууд, но хочется быстрее что ли, и давай чтобы не задержвалось на чем то долго» → «ок, жду финал» (SHIFT); «давай этьот момент долго держится на одном, гоу как то разбавим и улучшим» (PHYLLA).
- **Montage films built from generated footage cut fast:** ~40–50 cuts per 30 s; no single image held longer than ~1 s (split long beats into 2–3 angles of 0.5–0.75 s). Keep must-read lines readable by holding one line over 2–4 sub-cuts, not by slowing the cuts. [M-06]
  - The v2 kit that won: a 1.06→1.00 zoom punch on every bar downbeat; 6–10-frame flash words; an accelerating build (each cut ×0.8, down to 2 frames); a 0.5 s vacuum before the lift; 3-frame glitch slices on score stutters; white flashes only on drop, lift and final hit.
  - Evidence: v1 (~22 cuts) «Мощно, но думаю что нибудь улучшить, то ли динамики не хватает, еще быстрее нужно» → v2 (~45 cuts) «а так все вау» (PHYLLA).

## 9. One→many and alive content

- **When a film shows 'many outputs' (one→many, an infinite grid, a carousel, a montage), every visible item is a different variant:** different genre, technique and palette, never tinted into the brand colour. [T-19]
  - A grid needs ~20+ distinct clips with no repeats among neighbours, diagonals included.
  - In a montage every full-screen beat gets its own shot.
  - A photo↔dot-matrix twin of the same shot also reads as a repeat.
  - Labels match counts: 'Generate 12' followed by 20+ ads was flagged.
  - Check clip ids per cut yourself before sending.
  - The ~6-image pool rule is only for a consistent hero product or person in a product demo. [K-04]
  - Evidence: «и гры давай разнообразные сдлелаем» (PLAY); «там есть повторябщийся элементы их тоже гоу заменим, прооверь сам» (PHYLLA); helper «В сетке повторяются плитки» (Ad Multiplier).
- **Content inside cards, windows and screens is alive.** Ad cards play real 9:16 UGC video, not photos. Game and app screens loop animation (scroll, bob, blink at 0.5–2 Hz). The hero card keeps playing under the end card. [T-20]
  - Stage clips as frame sequences: 121 frames at 360 px for tiles, 720 px for hero cards. Choose in-points so the face shows at the key beats.
  - Evidence: «вместо обычных фото, давай ugc видео норм тоже сделаем» (Ad Multiplier); «сделать анимацию игры» (PLAY).
- **Fly the camera past the many** (§7). [CA-03]

## 10. End card and lockups

- **End on a clean, centred text packshot:** co-brand row → product wordmark (bigger than on the title) → product pill → CTA. No hero person, no orbit, no cards. [T-18]
  - Stage the elements one after another; land the wordmark on the music's final hit.
  - Hold clean for ≥1.5–2 s (a slow push of ≤3% is fine) over a soft sound tail.
  - Mirror the opening through type and position only. [K-05]
  - Evidence: the Ad Multiplier v3 END mirrored the cover (heroine, orbit, pill, CTA plate) → «конец убери просто тексто пэкшот сделай». The PLAY end card stacked PLAY., the taglines, ring cards over the letters and a prompt bar → «потом там текст сильно мешают друг другу, улучши чуть чуть по дизайну». Helper: «Финал перегружен».
- **Never insert a motif between the words of a lockup.** The lockup "Audio [mini wave] with / Claude × Higgsfield MCP" looked strange («04 страница странная смотрится»). [T-22]

## 11. Sound taste

- **«Музыка подинамичнее» means contrast and drive, not loudness.** Turning things up was never the fix. [SN-04]
  - Climax-level energy (choir, percussion, sound design on every transition) from the first drop, with only a short planned vacuum before the lift. A thinning breakdown made the first build the quietest part of the film.
  - Atmospheric texture locked to tempo: calls every bar, 16th-note ostinati, tape-stops at phrase ends, shimmers on downbeats.
  - Pickup fills and risers into transitions; a groove change per chapter.
  - A recurring 4–6-note motif, and sidechain pump.
  - A build that climbs into the drop.
  - Stutters mirrored by glitch slices in the picture.
  - Evidence: «отлично, но давай как с 20 секунды везде добавим мощную динамику и хора и всяких звуков чтобы не скучно было слушать»; «давай еще к музыке добавим типа звуков какиех как arrival но к темпу, а так все вау» (PHYLLA); «и музыка давай подинамичнее» → «гуууд» (SHIFT).

## 12. Revisions, approvals and rejected ideas

- **'Change some frames' means a few.** Name the 2–3 frames you will change and leave every other frame byte-identical. Don't make A/B variants of every frame and let judges choose: in the Audio MCP creative pass every frame got an A/B pair, judges picked B almost everywhere, and the user liked only 07 (tool-call pill arriving on a light trail) and 08 (voice pill in focus with a blurred orb carousel bleeding off the left). «я у тебя просил … только в некоторых страницах, а не во всех. мне нравится как ты сделал страницу 7, 8. Остальные страницы можно было оставить как есть.» [T-05]
- **Revert first; never overwrite an approval.** When the user calls a redesign bad or says the previous version was better, restore the last approved version and apply only the requested changes. Don't invent a new design. [T-06]
  - Never change approved copy, prompt text or look unless asked.
  - A judge agent's new variant never overrides an earlier client approval.
  - Keep a per-frame approval log (version, date, the user's words) and a snapshot of every version (v1_backup, v2_backup…) so reverts are cheap.
  - Evidence: «нет, ты не должен был менять страницу с японским языком, она мне понравилась.» (Audio MCP); «промпт как был до этого / по визуалу прошлый нравится, гоу также но с учетом всех правок» (ZEVRA).
- **Kill ideas a viewer would not instantly understand.** Sanity-check every idea: would a viewer instantly get it and find it impressive? «Идея с пустыми стеклянными капсулами максимально непонятна и не impressive. убери эту идею. в следующий раз не повторяй такого рода идеи». [T-07]
- **Purge rejected motifs from shared templates and kits.** The rejected empty glass capsule came back as the hero of the neutral styleboard and motion-demo templates, and for ~4 frames in ZEVRA. After a rejection, grep the templates for the motif. [T-07]
- **In critiques of Higgsfield brand key frames, don't treat the team's restraint as "emptiness".** This does not apply to product, game or montage films (§1 genre table). [pre-ledger; scoped by K-01]

---

## Appendix: Lipsync 2.0 and Audio MCP history (evidence)

The first two projects (session 2746ff-A, Oct 7–8), round by round. The rules above already include what is still valid. **SUPERSEDED** marks advice the later sessions changed.

### Lipsync 2.0 trial (design only)

| Step | What happened | User's words | Status now |
|---|---|---|---|
| Brief | Frames only, no generations; mark generation slots in text | «пока нет, просто дизайн» | Valid for design trials (§6) [T-22] |
| v1 | Flat centred layouts, generic UI boxes, big grey generation placeholders dominating | "too primitive" («мне нравится дизайн, он примитивен слишком, нужно интересные подходы») | Valid: drove the density principle [T-02] |
| v2 liked | **A/inputs:** a cut-out head on dark, "ANY FACE ✦ ANY VOICE ✦ ANY LANGUAGE" on a circular path around it, input cards linked by curves. **C/pipeline:** an exploded isometric stack (face plate → landmark mesh → phoneme track → output) with leader labels | «a inputs c pipeline» | Valid as single bold structures (§3) |
| v2 rejected | Mannequin cut-out silhouette head with sticker lips | «это точно не то» | Valid (§6) [T-22] |
| Instruction | Colours and fonts may go beyond the brand palette and Inter/Space Grotesk; fonts still from Google Fonts | "не ограничивай цветами и шрифтами" | Valid, now general (§5) [T-15] |

Why (from the old file): the user wants interesting, conceptual, dimensional frames that explain the product through bold graphic structures, not template UI.

### Audio MCP (Higgsfield brand key frames, then a film)

| Round | What happened | User's words | Lesson / status now |
|---|---|---|---|
| Dense redesign | Orbit frame with 6 satellites, tool chips, ring text; a shared HUD system across all frames | «слишком много фрагментов и лишнего мусора»; «минималистично… один бит один какой-нибудь дизайн, но при этом красиво» | Ban on decorative fragments: valid [T-01, O-04]. "Frames must be minimal: one hero, lots of negative space, beauty carried by material, light and typography": **SUPERSEDED** outside Higgsfield brand key frames by the density principle [T-02, K-01] |
| Minimal film | Every frame dead-centre; empty grey glass capsules as a motif | «уже намного ближе, но не хватает креатива»; «не ограничивай себя сильно»; capsules «максимально непонятна и не impressive» | Minimal ≠ always dead-centre; some frames may carry a few more elements or a bolder idea (§3) [T-22]. Kill unclear ideas, purge them from templates (§12) [T-07] |
| Creative pass (round 4) | A/B for every frame; macro glass capsules with bubbles, a letter replaced by a glass capsule, liquid flood; slot-machine language list | Only 07 and 08 liked; 3D looks «старомодным»; the language slot list «ужасная» | Change only a few frames (§12) [T-05]; no detailed 3D, balance minimalism and maximalism (§4) [T-08]; language beat = one word + one accent (§3) [T-22] |
| Round 5 | The liked minimal languages frame had been replaced; capsule still glassy; lockup with a mini wave between the words | «нет, ты не должен был менять страницу с японским языком, она мне понравилась.»; capsule «слишком 3d»; «04 страница странная смотрится» | Revert first (§12) [T-06]; flat S1 capsule (§4) [T-22]; no motif inside a lockup (§10) [T-22] |

**SUPERSEDED defaults from the old "How to apply":**
- "Default to 1 headline + 1 hero object + 1 small supporting element." Replaced by: one focal idea per frame + density from one coherent source; the dose depends on the genre (§1). [T-02, K-01]
- "Start each frame from the single object or statement that carries the beat. Add nothing that does not serve it." Still valid as a focus rule; world layers, real product UI, diegetic output and identity line work count as serving the beat. [K-01]
- "Generations are placeholders." Now scoped to design trials; production uses generations. [T-22, G-01]
