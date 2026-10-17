# Часть IV. Справочник токенов

*Генерируется скриптом `system/build/guide_part4.mjs` из данных (hf-tokens.json → core; hf-tokens.json → styles; hf-tokens.json → axes; hf-tokens.json → resolved). Не править вручную: исправления вносятся в данные, затем скрипт запускается заново. core 1.1.0 от 2026-10-08; 176 токенов контракта; 12 пресетов; 9 разделов осей.*

Эта часть — точные имена и значения. Почему значения такие, объясняют Часть I (законы `core`), Часть II (оси и пресеты) и Часть III (`derive()`). Код получает только **семантический слой**: роли вроде `bg.base`, `type.display`, `ease.enter` плюс `policy` и `issues[]` (`HFT.theme()`, `HFT.derive()`). Имена осей и пресетов в значениях токенов не встречаются.

## Как читать справочник

- **Меняется:** S — по схеме (`dark` / `light`), F — по формату (`16x9`, `9x16`, `1x1`, `4x5`), — — постоянен. Цвета, тени и свечения зависят от схемы; кегли, метрики кадра и фокусные точки — от формата; шрифты, кривые и длительности не зависят ни от чего.
- **Откуда:** ось или таблица `core`, которая производит значение.
- **Правило:** ограничение, которое проверяет `HFT.validate()` (текст правила — дословно из `core.json`, по-английски).
- **Статус:** «обяз. ★» — имя обязательно и названо в брифе системы; «обяз.» — обязательно; «опц.» — опционально. [обязательно] Код и кадры используют только канонические имена; алиасы (ниже) принимаются на входе и нормализуются.
- **Единицы:** px — нативный размер формата (на 16:9 1 px = 1 du, `du = min(w,h)/1080`); трекинг — em (−0.04 = −4%; в After Effects −40); цвет — sRGB hex, внутри данных ещё OKLCH [L, C, H]; время — мс или с, кадры — при `rhythm.fps` темы.
- **Тени** записаны нотацией Библии: `DS(x, y, blur, spread, #hex, α%)` — drop shadow, `IS(…)` — inner shadow; несколько слоёв соединены «+».

## Семантический контракт

176 токенов. Машинный список: `core.json → semanticContract.tokens`. Порядок разрешения темы: core → значения осей → переопределения стиля → бренд → схема × формат → вычисляемые токены → `validate()` (подробно — Часть I и `ARCHITECTURE.md` §1.3).

### Цвет (`$type: color`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `bg.base` | S | palette.neutrals | dark: OKLCH L 0.10-0.24, C <= 0.02; light: L 0.94-1.00, C <= 0.02 | обяз. ★ |
| `bg.raised` | S | palette.neutrals | dark: dY' >= 7 vs bg.base; light: >= 1.03:1 + shadow.card or line.stroke | обяз. ★ |
| `bg.sunken` | S | palette.neutrals | inputs/wells: between bg.base and bg.raised or dY' >= 7 from both | опц. |
| `bg.inverse` | S | palette.neutrals | opposite polarity ground for colour cards and flips | обяз. |
| `bg.overlay` | S | palette.neutrals | ground hue at alpha 0.4-0.7: scrims, text-over-image backing, freeze-dim | обяз. |
| `fg.primary` | S | palette.neutrals | target 12:1 / Lc 90, floor 7:1 / Lc 75 on bg.base, bg.raised, bg.overlay; on dark use off-white L 0.95-0.98 | обяз. ★ |
| `fg.muted` | S | palette.neutrals | floor 4.5:1 and Lc 50 (dark) / 60 (light) on bg.base and bg.raised; target Lc 60 / 68 | обяз. ★ |
| `fg.subtle` | S | palette.neutrals | floor 3:1 and Lc 38 (dark) / 45 (light); meta/texture only | обяз. |
| `fg.inverse` | S | palette.neutrals | on bg.inverse: WCAG >= 4.5 | обяз. |
| `fg.onAccent` | S | palette | on accent.action: target 4.5:1 / Lc 60, floor 3:1 / Lc 60 (labels >= 36 px bold = WCAG large text); `limit` flag drops it to 3:1 / Lc 45 for headline-size text only | обяз. |
| `accent.seed` | — | input / brand | the exact brand hex, never shifted; used for logo and brand mark only | обяз. |
| `accent.action` | S | palette.seed[0] / brand | the focal action fill (CTA, active, selected); non-text vs bg.base target 3:1 / Lc 30; if it fails: fill-only mode + accent.edge; area <= policy.accent.areaMax | обяз. ★ |
| `accent.text` | S | palette | accent as text on bg.base: target 4.5:1 / Lc 60, floor 3:1 / Lc 45 (floor band = display only, >= 64 px bold); minimal OKLCH-L shift along the ramp | обяз. |
| `accent.edge` | S | palette | fill-only mode only: ramp step >= 3:1 vs bg.base used as a 2-4 px edge or shadow tint so the fill still separates | опц. |
| `accent.actionDeep` | S | palette | bevel lip / lower edge / tinted shadow: accent L - 0.25...0.35 | обяз. |
| `accent.core` | S | palette | emitter hot core: L 0.98, C ~ 0.25 x C(accent) | обяз. |
| `accent.glow` | S | palette + material | glow colour; on light scheme the coloured-shadow colour | обяз. ★ |
| `accent.secondary` | S | palette.seed[1] | >= 90 deg OKLCH hue from accent.action; area <= 5% | опц. |
| `accent.secondaryText` | S | palette | same rule as accent.text | опц. |
| `line.hairline` | S | palette.neutrals | composite contrast 1.25:1 (~ white 8-10% on dark, ink 10% on light); 1-2 px; >= 2 px on moving elements | обяз. ★ |
| `line.strong` | S | palette.neutrals | container / divider stroke: composite contrast 1.6:1, 2-3 px; >= 3:1 when it carries meaning | обяз. |
| `line.focus` | S | palette | selection outline: accent.action if it passes non-text 3:1, else accent.edge, else accent.text | обяз. |
| `state.positive` | S | palette | keep / success (H ~145); text rule as accent.text; moves to H 165 if the accent is within 35 deg (one colour, one meaning) | обяз. |
| `state.negative` | S | palette | reject / change (H ~25); moves to H 5 if the accent is within 35 deg; \|L(positive) - L(negative)\| >= 0.15 or paired with a shape/label | обяз. |
| `state.pending` | S | palette.neutrals | neutral mid-tone; may pulse | опц. |
| `atmos.primary` | S | palette + material | bloom/pool colour incl. alpha (accent 6-16% on dark; pastel haze on light) | обяз. |
| `atmos.secondary` | S | palette + material | second bloom (diagonal pair); optional | опц. |
| `texture.ink` | S | texture | grain/dot/grid colour incl. alpha: light >= 4%, dark 6-10% | обяз. |
| `material.hero3d.color` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.hero3d.emissive` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.surface.color` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.surface.emissive` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.glass.fill` | S | material | only over imagery | обяз. |
| `material.glass.stroke` | S | material | only over imagery | обяз. |
| `state.warning` | S | palette | warning (H ≈ 85, ≥ 35° from the accent); text rule as accent.text | обяз. |
| `fg.onPositive` | S | palette | text on a filled state.positive chip: ≥ 4.5:1 (V22) | обяз. |
| `fg.onWarning` | S | palette | text on a filled state.warning chip: ≥ 4.5:1 (V22) | обяз. |
| `fg.onNegative` | S | palette | text on a filled state.negative chip: ≥ 4.5:1 (V22) | обяз. |
| `line.essential` | S | palette.neutrals | border that carries meaning: ≥ 3:1 composited on bg.base and bg.raised (V23); line.hairline / line.strong are decorative | обяз. |

### Градиенты (`$type: gradient`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `glow.pool` | S | palette + material | anti-banding light pool: centre OKLCH(L_bg + 0.075, accent hue) -> bg.base -> bg.sunken vignette at r ~ 900 px (16:9); >= 20 code values; light scheme: pearl haze tinted by the seed hue | обяз. |
| `gradient.scrim` | S | palette | bg.overlay alpha 0 -> 1 over the bottom 23-35% H | обяз. |
| `gradient.metal` | S | material | sweepable 3-stop fill for metallic/chrome type; only if material axis provides it | опц. |

### Шрифты (`$type: fontFamily`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `font.display` | — | typeVoice | Google Fonts family + generic fallback | обяз. |
| `font.text` | — | typeVoice | — | обяз. |
| `font.mono` | — | typeVoice | data / code only | обяз. |
| `font.accent` | — | typeVoice / brand | max one per film; one word or one title | опц. |
| `font.fallback.Cyrl` | — | typeVoice | face for ISO 15924 script Cyrl; cap-height matched | обяз. |
| `font.fallback.Grek` | — | typeVoice | face for ISO 15924 script Grek; cap-height matched | обяз. |
| `font.fallback.Jpan` | — | typeVoice | face for ISO 15924 script Jpan; cap-height matched | обяз. |
| `font.fallback.Kore` | — | typeVoice | face for ISO 15924 script Kore; cap-height matched | обяз. |
| `font.fallback.Hans` | — | typeVoice | face for ISO 15924 script Hans; cap-height matched | обяз. |
| `font.fallback.Hant` | — | typeVoice | face for ISO 15924 script Hant; cap-height matched | обяз. |
| `font.fallback.Arab` | — | typeVoice | face for ISO 15924 script Arab; cap-height matched | обяз. |
| `font.fallback.Deva` | — | typeVoice | face for ISO 15924 script Deva; cap-height matched | обяз. |
| `font.headline` | — | typeVoice / style | only when the headline face differs from the display face (same superfamily) | опц. |
| `font.label` | — | typeVoice / style | only when the label face differs from the text face | опц. |
| `font.fallback.Hebr` | — | typography.scriptFallback | as font.fallback.* | опц. |
| `font.fallback.Thai` | — | typography.scriptFallback | as font.fallback.* | опц. |

### Веса (`$type: fontWeight`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `weight.display` | — | typeVoice | — | обяз. |
| `weight.headline` | — | typeVoice | — | обяз. |
| `weight.body` | — | typeVoice | >= 500 for must-read body on video | обяз. |
| `weight.label` | — | typeVoice | — | обяз. |
| `weight.strong` | — | typeVoice | — | обяз. |

### Типографика (`$type: typography`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `type.mega` | F | typeVoice + format | hero number / one word; may bleed only if it is the single kinetic mega-word | опц. |
| `type.display` | F | typeVoice + format | title WORD; >= 1.333 x type.headline | обяз. ★ |
| `type.headline` | F | typeVoice + format | claims, 1-2 line headlines; >= 2 x type.body when co-present | обяз. ★ |
| `type.subhead` | F | typeVoice + format | second-level headline (keynote/split titles) | опц. |
| `type.body` | F | typeVoice + format | must-read support line and the scale base: = round(floorX / xHeight(text face)) for the strictest target context | обяз. ★ |
| `type.label` | F | typeVoice + format | kickers, tags, CAPS labels that carry meaning: >= floorCap of the strictest context (Inter CAPS 48 in feed16x9); tracking positive at small sizes | обяз. ★ |
| `type.caption` | F | typeVoice + format | subtitles / VO pill: 16:9 >= 48 px, 9:16 >= 52 px | обяз. |
| `type.ui` | F | typeVoice + format | text inside UI clones: >= 20 px floor; texture unless pushed in | обяз. |
| `type.code` | F | typeVoice + format | mono; tnum; prompts/timecodes | обяз. ★ |
| `type.number` | F | typeVoice + format | figures with tnum + case | опц. |

### Размеры (`$type: dimension`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `space.1` | — | core | 8 px | обяз. |
| `space.2` | — | core | 16 px | обяз. |
| `space.3` | — | core | 24 px | обяз. |
| `space.4` | — | core | 32 px | обяз. |
| `space.5` | — | core | 48 px | обяз. |
| `space.6` | — | core | 64 px | обяз. |
| `space.7` | — | core | 96 px | обяз. |
| `space.8` | — | core | 128 px | обяз. |
| `frame.w` | F | core.formats | — | обяз. |
| `frame.h` | F | core.formats | — | обяз. |
| `frame.margin` | F | core.grids + composition | film text margin | обяз. |
| `frame.marginCaption` | F | core.safeAreas | caption-on-footage margin (48-60 @16:9) | обяз. |
| `frame.gutter` | F | core.grids | — | обяз. |
| `frame.column` | F | core.grids | — | обяз. |
| `frame.safe.top` | F | core.safeAreas | must-read insets for the delivery context | обяз. |
| `frame.safe.right` | F | core.safeAreas | must-read insets for the delivery context | обяз. |
| `frame.safe.bottom` | F | core.safeAreas | must-read insets for the delivery context | обяз. |
| `frame.safe.left` | F | core.safeAreas | must-read insets for the delivery context | обяз. |
| `focal.home.x` | F | core.focal | — | обяз. |
| `focal.home.y` | F | core.focal | — | обяз. |
| `radius.chip` | — | shape | full (9999) | обяз. |
| `radius.pill` | — | shape | key-pill; ratio of height in $extensions (shape axis: sharp 0.1 ... round 0.5) | обяз. ★ |
| `radius.control` | — | shape | buttons, inputs, toggles: fraction of the short side (soft 0.25, round/pill 0.5 = full) | обяз. |
| `radius.card` | — | shape | reference card (16:9 hero ~1200 px); ratio of width in $extensions | обяз. ★ |
| `radius.cardSmall` | — | shape | <= 700 px cards | обяз. |
| `radius.media` | — | shape | hero media 860-1440 px | обяз. |
| `radius.panel` | — | shape | — | обяз. |
| `radius.window` | — | shape | — | обяз. |
| `radius.tile` | — | shape | thumbnails / icon tiles | обяз. |
| `stroke.hairline` | — | shape | 1-2 px | обяз. |
| `stroke.default` | — | shape | — | обяз. |
| `stroke.accent` | — | shape | >= 2 px; >= 3-4 px for chroma-only strokes | обяз. |
| `blur.far` | — | material | 2-8 | обяз. |
| `blur.backdrop` | — | material | glass background blur 10-64 | обяз. |
| `blur.plate` | — | material | 40-80 | обяз. |
| `blur.reveal` | — | motion | reveal-from blur 8-32 | обяз. |
| `material.glass.backdropBlur` | S | material | only over imagery | обяз. |

### Числа (`$type: number`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `frame.columns` | F | core.grids | — | обяз. |
| `material.hero3d.roughness` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.hero3d.metalness` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.hero3d.clearcoat` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.hero3d.clearcoatRoughness` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.hero3d.sheen` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.hero3d.transmission` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.hero3d.ior` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.hero3d.emissiveIntensity` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.hero3d.envMapIntensity` | S | material | three.js MeshPhysicalMaterial params | обяз. ★ |
| `material.surface.roughness` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.surface.metalness` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.surface.clearcoat` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.surface.clearcoatRoughness` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.surface.sheen` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.surface.transmission` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.surface.ior` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.surface.emissiveIntensity` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `material.surface.envMapIntensity` | S | material | secondary 3D objects / surfaces; same keys | обяз. |
| `light.keyAzimuth` | — | material | deg from vertical, -45...0 (top-left...top) | обяз. |
| `texture.amount` | — | texture | 0...0.05; 0 on UI | обяз. |
| `motion.overshoot` | — | motionPersonality | 0...0.12 of scale (default <= 0.08); never on logo, headline, product name, hero media | обяз. |
| `motion.cameraSpeed` | — | motionPersonality | 0.6...1.6 | обяз. |
| `motion.durationScale` | — | motionPersonality | m = 2^((0.5 - energy) x 1.2) x durMul, clamped to 0.5...1.8 | обяз. |
| `motion.blurShutter` | — | core | 180 | обяз. |
| `motion.peripheryDrift` | — | core | 8-16 px/s at 1080p | обяз. |
| `rhythm.fps` | — | spec / brand | 24 \| 25 \| 30 \| 48 \| 50 \| 60 (native fps of the footage) | обяз. |
| `rhythm.bpm` | — | spec / brand | integer frames per beat at rhythm.fps | обяз. |
| `rhythm.framesPerBeat` | — | derived | — | обяз. |

### Тени и свечения (`$type: shadow`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `shadow.float` | S | material + shape | hero / floating object (near tier) | обяз. ★ |
| `shadow.card` | S | material | resting card (mid tier) | обяз. |
| `shadow.near` | S | material | y ~18, blur ~35, alpha ~0.17 (dark) scaled by material | обяз. |
| `shadow.mid` | S | material | y ~9, blur ~20, alpha ~0.09 | обяз. |
| `shadow.window` | S | material | — | обяз. |
| `shadow.contact` | S | material | flat ellipse under objects | обяз. |
| `shadow.innerLight` | S | material | inset top light (inset: true) | опц. |
| `glow.action` | S | material + palette | 0-offset shadow in accent.glow; light scheme -> coloured drop shadow | обяз. ★ |
| `glow.selected` | S | material + palette | selection aura (inset or outer) | обяз. |
| `glow.hero` | S | material + palette | soft halo behind the hero | опц. |
| `material.glass.highlight` | S | material | only over imagery | обяз. |

### Кривые (`$type: cubicBezier`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `ease.enter` | — | motionPersonality | decelerating; x1,x2 in [0,1] | обяз. ★ |
| `ease.exit` | — | motionPersonality | accelerating | обяз. ★ |
| `ease.move` | — | motionPersonality | in-place moves | обяз. ★ |
| `ease.camera` | — | motionPersonality | symmetric in-out; default [0.65,0,0.35,1] | обяз. ★ |
| `ease.ui` | — | motionPersonality | productive | обяз. |
| `ease.expressive` | — | motionPersonality | hero moves in place | обяз. |
| `ease.loop` | — | core | [0,0,1,1] | обяз. |

### Длительности (`$type: duration`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `dur.chip` | — | motionPersonality x core | chip / sparkle pop: base 0.28 s x m, bounds max(5 f, 0.2 s) ... 0.6 s | обяз. |
| `dur.ui` | — | motionPersonality x core | card slide / UI move: base 0.40 s x m, bounds max(5 f, 0.2 s) ... 0.9 s | обяз. ★ |
| `dur.headline` | — | motionPersonality x core | headline line mask: base 0.60 s x m, bounds 0.4 ... 1.2 s | обяз. |
| `dur.hero` | — | motionPersonality x core | hero reveal: base 0.95 s x m, bounds 0.6 ... 2.0 s | обяз. ★ |
| `dur.exit` | — | motionPersonality x core | min(0.25 s x m, dur.ui - 2 f); bounds 5 f ... 0.5 s; always shorter than its entrance | обяз. |
| `dur.camera` | — | motionPersonality x core | base 1.5 s x m / cameraSpeed, bounds 1 ... 3 s | обяз. |
| `dur.sweep` | — | motionPersonality x core | light sweep 0.5-0.75 s | обяз. |
| `dur.hit` | — | core | >= 4 frames at 24-25 fps; never scaled down | обяз. |
| `dur.textMin` | — | core | 20 frames at rhythm.fps; never scaled | обяз. |
| `dur.endCard` | — | core | >= 2 s | обяз. |
| `stagger` | — | motionPersonality | cascade step = clamp(round(3 x m x staggerMul), 1, 8) frames (frames in $extensions); DTCG name stagger.$root | обяз. ★ |
| `stagger.line2` | — | motionPersonality | 3-4 f | обяз. |
| `stagger.accent` | — | motionPersonality | 4-6 f after its text | обяз. |
| `stagger.followThrough` | — | motionPersonality | 6-12 f | обяз. |

### Переходы (`$type: transition`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `transition.enter` | — | motionPersonality | DTCG transition composites of dur.* + ease.* | обяз. |
| `transition.exit` | — | motionPersonality | DTCG transition composites of dur.* + ease.* | обяз. |
| `transition.move` | — | motionPersonality | DTCG transition composites of dur.* + ease.* | обяз. |
| `transition.camera` | — | motionPersonality | DTCG transition composites of dur.* + ease.* | обяз. |

### Расширения (`$type: extension`)

| Токен | Меняется | Откуда | Правило | Статус |
| --- | --- | --- | --- | --- |
| `light.model` | — | material | flat \| soft \| rim \| emissive | обяз. |

### Политика темы (`policy`, не токены)

Политика едет вместе с токенами и задаёт решения, которые не выражаются одним значением.

| Ключ | Поля и диапазоны |
| --- | --- |
| `composition` | `primaryAxis`: centre \| leftAxis; `offAxisFamily`: zCorner \| thirds \| editorialSplit \| flanks; `archetypesPreferred`: [archetype ids]; `centredShareMax`: <= 0.75 |
| `density` | `level`: sparse \| balanced \| rich; `negativeSpacePctByFrameType`: {frameType: number inside core range} |
| `accent` | `targetPct`: moodTarget x ext; `maxPct`: moodMax x ext (<= 18; fill-only on light <= 8); `objects`: 1-2; `echoes`: 0-2; `mode`: solid \| fill-only; `textAllowed`: bool (computed); `secondaryMaxPct`: <= 6; `secondaryMeaning`: string; `flood`: rule string |
| `type` | `narrativeStylesMax`: 5; `accentFontWordsMax`: 1; `scripts`: [ISO 15924]; `framePairs`: [[tokenA, tokenB] with ratio >= 2]; `ratio`: >= 1.333 |
| `transitions` | `family`: [<= 2 counted types]; `signature`: string \| null (brand); `whipAllowed`: bool |
| `camera` | `verb`: one of camera.verbs; `reverse`: pullBack \| null |
| `texture` | `kind`: none \| grain \| dotGrid \| halftone \| scanlines; `amount`: number |
| `light` | `model`: flat \| soft \| rim \| emissive; `tactileObjectRequired`: bool |
| `formats` | [16x9, 9x16, 1x1, 4x5] |
| `contexts` | [legibility context ids the deliverable must pass] |

### Алиасы имён токенов

resolve() accepts either name and emits the canonical one; aliases exist so the derive prototype (DERIVE.md) and the brief stay compatible

| Алиас | Каноническое имя |
| --- | --- |
| `overshoot` | `motion.overshoot` |
| `motion.stagger` | `stagger` |
| `bg.scrim` | `bg.overlay` |
| `accent.actionText` | `accent.text` |
| `line.stroke` | `line.strong` |
| `radius.button` | `radius.control` |
| `material.surface3d` | `material.surface` |
| `gradient.pool` | `glow.pool` |
| `dur.micro` | `dur.chip` |
| `dur.enter` | `dur.headline` |
| `state.selected` | `accent.action` |
| `state.rejected` | `state.negative` |
| `rhythm` | `rhythm.fps + rhythm.bpm + rhythm.framesPerBeat` |
| `texture` | `policy.texture` |
| `density` | `policy.density` |
| `composition` | `policy.composition` |
| `line.decorative` | `line.hairline` |
| `line.borderEssential` | `line.essential` |
| `onAccent` | `fg.onAccent` |

### Сериализация

- **DTCG version:** `Design Tokens Format Module 2025.10`
- **DTCG color:** `{colorSpace, components, alpha?, hex?}`
- **DTCG dimension:** `{value, unit: px\|rem}`
- **DTCG duration:** `{value, unit: ms\|s}`
- **DTCG typography:** `{fontFamily, fontSize, fontWeight, letterSpacing (dimension), lineHeight (number)}`
- **DTCG nonStandard:** `$extensions["ai.higgsfield.hft"]`
- **DTCG trackingNote:** `letterSpacing is a px dimension in DTCG: emit em x fontSize per format mode; keep em in $extensions`
- **DTCG rootNote:** `a name that is both a token and a group (stagger / stagger.line2) is emitted as stagger.$root`
- **CSS-переменные:** `--{prefix-}{path with "." -> "-", camelCase -> kebab}; composites expand (-family, -size, -weight, -tracking, -leading)`. Примеры: `bg.base` → `--bg-base`; `type.display` → `--type-display-family`, `-size`, `-weight`, `-tracking`, `-leading`. Кривая → `cubic-bezier(…)`, длительность → `ms`, тень → полный CSS-список (`HFT.toCSSVars()`, DTCG — `HFT.toDTCG()`).
- **three.js:** `material.*` 1:1 соответствует параметрам `MeshPhysicalMaterial`; цвета — sRGB hex, перевод в linear делает потребитель (`HFT.three()`).

## Правила проверки `validate()`

`HFT.validate(theme)` возвращает `issues[] = {id, severity, token, message, value, limit}`; `HFT.derive()` исправляет то, что может (зажимает диапазоны, поднимает светлоту, меняет fallback письменности, увеличивает кегль), и записывает каждое исправление в `meta.fixes`. [обязательно] Тема с `severity: 'error'` в кадр не идёт.

| ID | Строгость | Ключ | Проверка |
| --- | --- | --- | --- |
| `V01` | error/warn | `contrast` | every role pair in accessibility.contrast.roles: below floor = error, between floor and target = warning (WCAG and APCA both) |
| `V02` | error | `accentText` | accent.text passes its floor on bg.base; text in the floor band carries minPx 64, bold |
| `V03` | error | `fillOnly` | if accent.action fails non-text 3:1 vs bg.base: fill-only mode, accent.edge present, no accent text/stroke < 12 px, area <= 8% |
| `V04` | warn | `hueSeparation` | accent.secondary hue >= 90 deg (OKLCH) from accent.action; state.* hue >= 35 deg from the accent |
| `V05` | warn/error | `accentArea` | policy.accent.maxPct <= moodMax x ext (warn above), never above 18% (error); fill-only on light <= 8% |
| `V06` | error/warn | `legibility` | type.body, type.headline, type.display, type.label: letter height >= floor of every target context (error) and >= target (warn), using the face's own x-height (mixed) or cap height (CAPS); 2% tolerance |
| `V07` | error | `absoluteFloor` | no type token below 20 px at a 1080 px short side (scale linearly for other sizes) |
| `V08` | error | `scaleSteps` | adjacent type tokens differ >= x1.333; policy.type.framePairs lists only pairs >= x2 |
| `V09` | error | `fontAvailability` | every family exists on Google Fonts with the requested weights/axes and covers every script in policy.type.scripts, else the role is reassigned to a fallback face |
| `V10` | error | `fontCount` | <= 2 narrative families + <= 1 accent + <= 1 mono |
| `V11` | warn | `tracking` | trackingEm inside core.typography.trackingBySize for the token's size and case |
| `V12` | error | `easing` | x1, x2 in [0, 1]; ease.enter lands softly, ease.exit leaves softly (rhythm.easingShape); overshoot <= personality cap <= 0.12 |
| `V13` | error/warn | `durations` | m in [0.5, 1.8]; every dur.* inside rhythm.durationScaling.tokenBounds; dur.exit < its entrance (warn); dur.textMin = 20 f; dur.hit >= 4 f @24 |
| `V14` | error | `rhythm` | stagger >= 1 frame; rhythm.fps in {24, 25, 30, 48, 50, 60}; frames per beat is an integer |
| `V15` | error/warn | `ground` | bg.base L inside the scheme range; bg.raised dY' >= 7 vs bg.base (error on dark, warn on light) unless an edge/shadow flag is set |
| `V16` | warn | `banding` | glow.pool and every large gradient span >= 20 code values; hue-to-hue gradients pass the midpoint rule |
| `V17` | warn | `lumaText` | coloured text with dY' < 60 vs its ground carries minPx 64 and strokes >= 4 px (4:2:0) |
| `V18` | error | `flash` | flash / slice / twinkle rate <= 3 per second |
| `V19` | warn | `stateLuminance` | state.positive vs state.negative: \|dL\| >= 0.15 or paired with a shape/label |
| `V20` | warn | `radiusConcentric` | nested radii = outer - padding |
| `V21` | warn | `mutedHierarchy` | \|Lc(fg.primary)\| - \|Lc(fg.muted)\| >= 20 |
| `V22` | error | `contrast (codex)` | text pairs our contract did not cover — on-status (fg.onPositive / onWarning / onNegative on state.*) and text on extra surfaces (surface.card) — WCAG ≥ 4.5 after compositing semi-transparent layers |
| `V23` | error | `essential graphics (codex)` | line.essential ≥ 3:1 on bg.base, bg.raised (and surface.card when the style defines it), composited |
| `V24` | error | `exceptions` | every documented shot exception carries a reason |

## Пресеты: ключевые значения

Значения — из разрешённых тем `HFT.theme('<пресет>', {scheme})` (формат 16:9, контекст «лента»), то есть ровно то, что получает код. Тексты «когда использовать», do / don't и подробности осей — в Части II.

### Оси пресетов

| Пресет | Статус | Настроение | typeVoice | palette | material | shape | motion | composition | density | texture | validate dark | validate light |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `higgsfield` | approved-current | technical | neo-grotesk | signal | flat + glass-modern | pill | productive | minimal-centred | sparse | grain | 0 ош. / 3 пред. | 0 ош. / 1 пред. |
| `swiss-editorial` | preset | editorial | neo-grotesk | signal | flat | sharp | productive | editorial-asymmetric | balanced | none | 0 ош. / 4 пред. | 0 ош. / 2 пред. |
| `luxury-serif` | preset | luxury | didone-luxury | tonal | metallic-subtle | sharp | luxury-slow | minimal-centred | sparse | none | 0 ош. / 5 пред. | 0 ош. / 4 пред. |
| `playful-pop` | preset | playful | quirky-grotesk | duotone | clay | round | playful-bouncy | maximal-collage | balanced | halftone | 0 ош. / 4 пред. | 0 ош. / 1 пред. |
| `cinematic-noir` | preset | calm | condensed-display | mono | metallic-subtle | sharp | cinematic | editorial-asymmetric | sparse | grain | 0 ош. / 2 пред. | 0 ош. / 2 пред. |
| `soft-pastel-ui` | preset | calm | geometric | pastel | soft-shadow + glass-modern | round | productive | minimal-centred | balanced | grain | 0 ош. / 4 пред. | 0 ош. / 0 пред. |
| `tech-terminal` | preset | technical | mono-terminal | signal | flat | sharp | glitch-tech | keynote-left-axis | balanced | scanlines | 0 ош. / 2 пред. | 0 ош. / 0 пред. |
| `brutalist-raw` | preset | energetic | expanded-display | signal | flat | sharp | glitch-tech | poster-type-led | rich | halftone | 0 ош. / 3 пред. | 0 ош. / 1 пред. |
| `organic-editorial` | preset | editorial | editorial-serif | tonal | paper-grain | soft | luxury-slow | editorial-asymmetric | balanced | grain | 0 ош. / 3 пред. | 0 ош. / 1 пред. |
| `y2k-chrome-modern` | preset | energetic | expanded-display | spectral | metallic-subtle + glass-modern | pill | expressive | minimal-centred | balanced | none | 0 ош. / 3 пред. | 0 ош. / 1 пред. |
| `kinetic-type` | preset | energetic | variable-kinetic | mono | flat | sharp | expressive | poster-type-led | sparse | none | 0 ош. / 4 пред. | 0 ош. / 0 пред. |
| `dot-matrix` | preset | calm | pixel | mono | neon-light | round | glitch-tech | minimal-centred | sparse | dot-grid | 0 ош. / 2 пред. | 0 ош. / 1 пред. |

«ош.» — ошибки `validate()`, «пред.» — предупреждения (значение между полом и целью). Предупреждения допустимы, ошибки — нет.

### Назначение и подпись

| Пресет | Когда | Не для | Подпись (signature) |
| --- | --- | --- | --- |
| **Higgsfield** `higgsfield` | Любой фильм, где бренд — Higgsfield: запуски моделей и фич, MCP/агенты, ко-бренды (регистр D с payoff в C). Это утверждённый текущий вид: финальные кадры Audio MCP 01–14, film15, three3d. | Чужие бренды и нейтральные продукты: лайм = «Higgsfield действует», на чужом продукте он запрещён. Для них — другой пресет или derive(). | Плоская лаймовая капсула S1 (7 баров, пик — бар 3) и лаймовый CTA-pill; лайм = «Higgsfield действует» |
| **Swiss Editorial** `swiss-editorial` | B2B и developer-запуски, отчёты и data-истории, конференции, объяснение механики числами и схемами. | Тёплые человеческие истории, lifestyle, люкс. | Красная линейка 4 px + гигантский индекс «01» на сетке |
| **Luxury Serif** `luxury-serif` | Премиум, мода, бьюти, ювелирка, престижные партнёрства, награды; флагманская модель с «дорогим» тоном. | Плотные UI-демо, быстрые соцролики, скидки и офферы. | Арка-окно с волосяной шампань-рамкой + одно слово курсивом Playfair |
| **Playful Pop** `playful-pop` | Потребительские приложения, соцфичи, шаблоны и стикеры, креаторские инструменты, молодёжные кампании. | Серьёзные B2B и финансы, чувствительные темы, люкс. | Стикер с поворотом −6° и squash-pop на сильную долю |
| **Cinematic Noir** `cinematic-noir` | Запуски видео-моделей, трейлеры, сторителлинг, кино-инструменты, тёмные премиальные реводы. | UI-демо с мелким текстом, яркие соцролики, детская аудитория. | Леттербокс 2,39:1 + разреженные узкие капители-титры + один тёплый практический свет |
| **Soft Pastel UI** `soft-pastel-ui` | Продуктивность и SaaS, онбординг, образование, wellness, функции AI-ассистента, дружелюбные UI-демо. | Драматичные трейлеры, агрессивные офферы, тёмные event-запуски. | Mesh-аура из двух пастельных пятен за парящими скруглёнными карточками |
| **Tech Terminal** `tech-terminal` | Developer tools, API/CLI, агенты и MCP, инфраструктура, changelog, бенчмарки и данные. | Lifestyle, мода, детская аудитория, эмоциональные истории. | Блочная каретка + лейблы в [скобках] + строка-промпт `>` |
| **Brutalist Raw** `brutalist-raw` | Манифесты и заявления, культурные дропы, «мы всё поменяли», бунтарские кампании. | Тонкие продуктовые UI-демо, люкс, спокойные темы. | Жёсткая смещённая тень 8 px без размытия + контраст ширин wdth 62 ↔ 125 в одном стеке |
| **Organic Editorial** `organic-editorial` | Сторителлинг, комьюнити и креаторы, устойчивость, еда и лайфстайл, документальные истории, человечные AI-месседжи. | Хай-тек демо, неон, агрессивные офферы. | Курсивное слово с «волной» Fraunces WONK + вырезанные бумажные формы с тенью-стопкой |
| **Y2K Chrome Modern** `y2k-chrome-modern` | Музыкальные, модные и креаторские дропы, AI-изображения и 3D-фичи, Gen-Z кампании, «новая эра». | B2B и данные, длинные объяснения, серьёзные темы. | Иридесцентная «жидкая» хром-капсула в мягком градиентном окружении + широкий Unbounded |
| **Kinetic Type** `kinetic-type` | Лирик- и манифест-ролики, опенеры событий, соц-нарезки, где шрифт и есть картинка; монтаж под музыку. | UI-демо, плотные данные, медитативные темы. | «Дыхание» ширины wdth 75 ↔ 125 на каждой доле + инверсия ч/б на сильной доле |
| **Dot Matrix** `dot-matrix` | Железо и устройства, состояния «AI думает», уведомления, минималистичные тех-анонсы, обратные отсчёты. | Тёплые человеческие истории, люкс, длинные тексты. | Растровое «включение» точек глифа (сверху вниз, 1 ряд/кадр) + одна красная точка-статус |

### Цвета: тёмная схема

| Пресет | `bg.base` | `bg.raised` | `fg.primary` | `fg.muted` | `accent.action` | `fg.onAccent` | `accent.text` | `accent.secondary` | `line.hairline` | `state.positive` | `state.negative` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `higgsfield` | `#0B0B0D` | `#131313` | `#EEEEE8` | `#A2A2A2` | `#D1FE17` | `#131313` | `#D1FE17` | `#ED1572` | `#2D2D2F` | `#B6FBDC` | `#F29A92` |
| `swiss-editorial` | `#0F0E0C` | `#181715` | `#EFEEED` | `#B2B1AF` | `#E4321B` | `#EFEEED` | `#FFAB9C` | — | `#252423` | `#C2FBC3` | `#F297AC` |
| `luxury-serif` | `#0F0C08` | `#181410` | `#F1EEEA` | `#B4B0AC` | `#C9AE7C` | `#120F0B` | `#C9AE7C` | `#E69497` | `#272420` | `#C0FBC1` | `#F29A92` |
| `playful-pop` | `#120E14` | `#1B161D` | `#F1EDF2` | `#B4AFB6` | `#FF5FA2` | `#120E14` | `#FFA5C4` | `#2ED3A0` | `#272329` | `#C0FBC0` | `#F29D76` |
| `cinematic-noir` | `#06090B` | `#0D1114` | `#ECEFF1` | `#AEB2B5` | `#E9A04A` | `#0C1013` | `#FDB35E` | `#5E9FAD` | `#202325` | `#BEFBBF` | `#F29992` |
| `soft-pastel-ui` | `#0F0F13` | `#18181C` | `#EEEEF1` | `#B1B0B5` | `#9D8CFF` | `#0F0F13` | `#C1BBFF` | `#FFB199` | `#242428` | `#C0FBC1` | `#F29A92` |
| `tech-terminal` | `#070B0C` | `#0F1415` | `#EBEFF1` | `#ADB2B4` | `#2BD9FF` | `#0C1012` | `#2BD9FF` | `#FFB224` | `#1F2325` | `#C0FBC1` | `#F29A92` |
| `brutalist-raw` | `#0A0A0A` | `#100F0D` | `#F2F2F2` | `#B1B1AF` | `#FFD500` | `#000000` | `#FFD500` | — | `#262626` | `#C0FBC1` | `#F29A92` |
| `organic-editorial` | `#15110B` | `#1E1A13` | `#F2EEE8` | `#B5B0A9` | `#C2643F` | `#F2EEE8` | `#FFAD8E` | `#6F8F5E` | `#2A2620` | `#C4FBC4` | `#F298AC` |
| `y2k-chrome-modern` | `#090B10` | `#111419` | `#ECEEF3` | `#AEB1B7` | `#8FE3FF` | `#0D0F15` | `#8FE3FF` | `#D58BFF` | `#212328` | `#C0FBC1` | `#F29A92` |
| `kinetic-type` | `#0B0B0A` | `#141412` | `#EFEEED` | `#B1B1AF` | `#3346FF` | `#EFEEED` | `#ACC2FF` | — | `#232322` | `#C0FBC1` | `#F29A92` |
| `dot-matrix` | `#070707` | `#0F0F0F` | `#EEEEEE` | `#B1B1B1` | `#F4F4F0` | `#0F0F0F` | `#F4F4F0` | `#FF3B30` | `#202020` | `#BCFBBD` | `#F19C74` |

### Цвета: светлая схема

| Пресет | `bg.base` | `bg.raised` | `fg.primary` | `fg.muted` | `accent.action` | `fg.onAccent` | `accent.text` | `accent.secondary` | `line.hairline` | `state.positive` | `state.negative` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `higgsfield` | `#FAFAFF` | `#FFFFFF` | `#131313` | `#68686D` | `#D1FE17` | `#131313` | `#657C06` | `#ED1572` | `#E3E3E7` | `#328163` | `#791E1F` |
| `swiss-editorial` | `#F6F6F3` | `#FEFEFE` | `#171612` | `#5C5B57` | `#E4321B` | `#FFFFFF` | `#C21800` | — | `#DEDEDA` | `#2F8037` | `#701B38` |
| `luxury-serif` | `#F8F2EC` | `#FEFBF8` | `#1C140C` | `#605A52` | `#967C4C` | `#FFFFFF` | `#7E6535` | `#5E1A22` | `#E0DAD3` | `#2E7E36` | `#711B1C` |
| `playful-pop` | `#FEF5EE` | `#FFFFFF` | `#181321` | `#5C5865` | `#D73880` | `#FFFFFF` | `#BB1369` | `#009770` | `#E5DDD8` | `#1D5622` | `#B1582D` |
| `cinematic-noir` | `#EEEAE5` | `#F1F0ED` | `#1A150E` | `#5E5A53` | `#B36E00` | `#FFFFFF` | `#935A00` | `#4A8B99` | `#D6D2CD` | `#2C7934` | `#6A191A` |
| `soft-pastel-ui` | `#F7F7FD` | `#FFFFFF` | `#16151D` | `#5A5A61` | `#6853C0` | `#FFFFFF` | `#6853C0` | `#FFB199` | `#DFDFE5` | `#308137` | `#751D1D` |
| `tech-terminal` | `#EEF5F7` | `#F9FCFE` | `#0E181B` | `#545D5F` | `#2BD9FF` | `#0E181B` | `#00758C` | `#FFB224` | `#D5DCDF` | `#2F7F36` | `#721C1C` |
| `brutalist-raw` | `#EBEBE8` | `#F0F0EF` | `#000000` | `#5B5B57` | `#FFD500` | `#000000` | `#635100` | — | `#D3D3D1` | `#2C7934` | `#6A191A` |
| `organic-editorial` | `#F2ECE3` | `#F8F4F0` | `#1D1407` | `#62594E` | `#C2643F` | `#FFFFFF` | `#A54A24` | `#6F8F5E` | `#DBD4CB` | `#2D7A34` | `#691934` |
| `y2k-chrome-modern` | `#ECF0F9` | `#F6F8FD` | `#111621` | `#565B65` | `#8FE3FF` | `#111621` | `#14748D` | `#A35ACA` | `#D4D8E1` | `#2E7C35` | `#6E1B1B` |
| `kinetic-type` | `#F4F3F1` | `#FCFCFB` | `#171613` | `#5B5B58` | `#3346FF` | `#FFFFFF` | `#3346FF` | — | `#DBDAD8` | `#2E7F36` | `#721C1C` |
| `dot-matrix` | `#F2F2F2` | `#FAFAFA` | `#161616` | `#5B5B5B` | `#0A0A0A` | `#F2F2F2` | `#0A0A0A` | `#FF3B30` | `#DADADA` | `#1C5321` | `#AD562C` |

`line.hairline` показан как непрозрачный эквивалент на `bg.base`; в данных он хранится и как rgba. `accent.text` — акцент для текста (светлота сдвинута до нужного контраста); если он равен `accent.action`, акцентный текст допустим без сдвига.

### Тени и свечения пресетов

| Пресет | shadow.float dark | glow.action dark | shadow.float light | glow.action light |
| --- | --- | --- | --- | --- |
| `higgsfield` |  | DS(0, 0, 48, 0, #D1FE17, 35%) | DS(0, 2, 8, 0, #151713, 6%) | DS(0, 12, 40, 0, #B9E213, 30%) |
| `swiss-editorial` |  | DS(0, 0, 48, 0, #E4321B, 11%) | DS(0, 2, 8, 0, #1A1514, 6%) | DS(0, 12, 40, 0, #BC2714, 25%) |
| `luxury-serif` | DS(0, 2, 4, 0, #000000, 40%) + DS(0, 24, 56, 0, #000000, 55%) | DS(0, 0, 48, 0, #C9AE7C, 16%) | DS(0, 2, 4, 0, #1B150B, 10%) + DS(0, 20, 48, 0, #1B150B, 14%) | DS(0, 12, 40, 0, #7B653D, 25%) |
| `playful-pop` | DS(0, 18, 36, -6, #000000, 40%) + DS(0, 4, 8, 0, #000000, 25%) | DS(0, 0, 48, 0, #FF5FA2, 28%) | DS(0, 18, 36, -6, #520F2E, 30%) + DS(0, 4, 8, 0, #1E1216, 8%) | DS(0, 12, 40, 0, #B12D69, 28%) |
| `cinematic-noir` | DS(0, 2, 4, 0, #000000, 40%) + DS(0, 24, 56, 0, #000000, 55%) | DS(0, 0, 48, 0, #E9A04A, 21%) | DS(0, 2, 4, 0, #1B150E, 10%) + DS(0, 20, 48, 0, #1B150E, 14%) | DS(0, 12, 40, 0, #935A00, 25%) |
| `soft-pastel-ui` | DS(0, 6, 4, 0, #000000, 30%) + DS(0, 32, 24, 0, #000000, 15%) | DS(0, 0, 48, 0, #9D8CFF, 21%) | DS(0, 4, 12, 0, #16151D, 6%) + DS(0, 16, 48, 0, #16151D, 10%) | DS(0, 12, 40, 0, #5542A0, 25%) |
| `tech-terminal` |  | DS(0, 0, 48, 0, #2BD9FF, 35%) | DS(0, 2, 8, 0, #0E181B, 6%) | DS(0, 12, 40, 0, #00BEE1, 30%) |
| `brutalist-raw` |  | DS(0, 0, 48, 0, #FFD500, 42%) | DS(0, 2, 8, 0, #171612, 6%) | DS(0, 12, 40, 0, #E1BC00, 32%) |
| `organic-editorial` | DS(0, 12, 28, -10, #000000, 65%) | DS(0, 0, 48, 0, #C2643F, 11%) | DS(0, 1, 2, 0, #1E130F, 8%) + DS(0, 10, 30, 0, #1E130F, 6%) | DS(0, 12, 40, 0, #A05233, 25%) |
| `y2k-chrome-modern` | DS(0, 2, 4, 0, #000000, 40%) + DS(0, 24, 56, 0, #000000, 55%) | DS(0, 0, 48, 0, #8FE3FF, 42%) | DS(0, 2, 4, 0, #0B181C, 10%) + DS(0, 20, 48, 0, #0B181C, 14%) | DS(0, 12, 40, 0, #00CFFD, 32%) |
| `kinetic-type` |  | DS(0, 0, 48, 0, #3346FF, 42%) | DS(0, 2, 8, 0, #151619, 6%) | DS(0, 12, 40, 0, #2800F6, 32%) |
| `dot-matrix` |  | DS(0, 0, 48, 0, #F4F4F0, 27%) | DS(0, 2, 8, 0, #161616, 6%) | DS(0, 12, 40, 0, #555555, 25%) |

### Шрифты по ролям (16:9, тёмная схема)

| Пресет | Роль | Семейство | Вес | Кегль, px | Трекинг, em | LH | Регистр | Пол, px |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `higgsfield` | display | Inter | 500 | 256 | -0.06 | 1.11 | sentence | 64.1 |
| `higgsfield` | headline | Inter Tight | 700 | 181 | -0.04 | 1 | sentence | 64.1 |
| `higgsfield` | body | Inter | 500 | 64 | -0.02 | 1.35 | sentence | 64.1 |
| `higgsfield` | label | Space Grotesk | 700 | 50 | -0.02 | 0.9 | upper | 50 |
| `higgsfield` | code | JetBrains Mono | 500 | 64 | 0 | 1.4 | sentence | 63.6 |
| `swiss-editorial` | display | Geist | 700 | 334 | -0.05 | 1 | sentence | 66 |
| `swiss-editorial` | headline | Geist | 600 | 149 | -0.03 | 1 | sentence | 66 |
| `swiss-editorial` | body | Geist | 500 | 66 | -0.015 | 1.35 | sentence | 66 |
| `swiss-editorial` | label | Geist Mono | 500 | 50 | -0.02 | 0.9 | upper | 49.3 |
| `swiss-editorial` | code | Geist Mono | 400 | 66 | 0 | 1.4 | sentence | 66 |
| `luxury-serif` | display | Playfair | 500 | 322 | -0.04 | 1.04 | sentence | 84.5 |
| `luxury-serif` | headline | Playfair | 400 | 199 | -0.03 | 1.04 | sentence | 84.5 |
| `luxury-serif` | body | Jost | 500 | 76 | -0.01 | 1.4 | sentence | 76.1 |
| `luxury-serif` | label | Jost | 500 | 50 | -0.02 | 0.9 | upper | 50 |
| `luxury-serif` | code | DM Mono | 300 | 70 | 0 | 1.4 | sentence | 70.6 |
| `playful-pop` | display | Bricolage Grotesque | 800 | 306 | -0.05 | 1 | sentence | 67.7 |
| `playful-pop` | headline | Bricolage Grotesque | 800 | 144 | -0.04 | 1 | sentence | 67.7 |
| `playful-pop` | body | Rubik | 500 | 68 | -0.01 | 1.4 | sentence | 67.3 |
| `playful-pop` | label | Rubik | 600 | 38 | 0 | 1.2 | sentence | 38.5 |
| `playful-pop` | code | DM Mono | 500 | 72 | 0 | 1.4 | sentence | 70.6 |
| `cinematic-noir` | display | Sofia Sans Extra Condensed | 800 | 335 | -0.03 | 0.88 | upper | 53.4 |
| `cinematic-noir` | headline | Sofia Sans Extra Condensed | 700 | 155 | -0.03 | 0.88 | upper | 53.4 |
| `cinematic-noir` | body | Sofia Sans | 500 | 72 | -0.01 | 1.38 | sentence | 71.7 |
| `cinematic-noir` | label | IBM Plex Mono | 400 | 50 | -0.02 | 0.9 | upper | 50.1 |
| `cinematic-noir` | code | IBM Plex Mono | 400 | 68 | 0 | 1.4 | sentence | 67.8 |
| `soft-pastel-ui` | display | Plus Jakarta Sans | 800 | 278 | -0.045 | 1.04 | sentence | 65.3 |
| `soft-pastel-ui` | headline | Plus Jakarta Sans | 700 | 156 | -0.03 | 1.04 | sentence | 65.3 |
| `soft-pastel-ui` | body | Plus Jakarta Sans | 500 | 66 | -0.015 | 1.4 | sentence | 65.3 |
| `soft-pastel-ui` | label | Plus Jakarta Sans | 600 | 48 | -0.02 | 0.9 | upper | 47 |
| `soft-pastel-ui` | code | DM Mono | 400 | 72 | 0 | 1.4 | sentence | 70.6 |
| `tech-terminal` | display | Martian Mono | 700 | 192 | -0.04 | 1.06 | sentence | 58.3 |
| `tech-terminal` | headline | Martian Mono | 600 | 136 | -0.03 | 1.06 | sentence | 58.3 |
| `tech-terminal` | body | IBM Plex Sans | 500 | 68 | -0.01 | 1.4 | sentence | 67.8 |
| `tech-terminal` | label | IBM Plex Mono | 500 | 50 | -0.02 | 0.9 | upper | 50.1 |
| `tech-terminal` | code | IBM Plex Mono | 400 | 68 | 0 | 1.4 | sentence | 67.8 |
| `brutalist-raw` | display | Archivo | 900 | 223 | -0.03 | 0.88 | upper | 51 |
| `brutalist-raw` | headline | Archivo | 800 | 149 | -0.03 | 0.88 | upper | 51 |
| `brutalist-raw` | body | Archivo | 500 | 66 | -0.01 | 1.35 | sentence | 66.5 |
| `brutalist-raw` | label | Space Mono | 700 | 50 | -0.02 | 0.9 | upper | 50 |
| `brutalist-raw` | code | Space Mono | 400 | 70 | 0 | 1.4 | sentence | 70.6 |
| `organic-editorial` | display | Fraunces | 400 | 354 | -0.04 | 1.04 | sentence | 72.6 |
| `organic-editorial` | headline | Fraunces | 300 | 158 | -0.03 | 1.04 | sentence | 72.6 |
| `organic-editorial` | body | Commissioner | 500 | 70 | -0.01 | 1.4 | sentence | 70.6 |
| `organic-editorial` | label | Commissioner | 600 | 50 | -0.02 | 0.9 | upper | 49.1 |
| `organic-editorial` | code | DM Mono | 400 | 70 | 0 | 1.4 | sentence | 70.6 |
| `y2k-chrome-modern` | display | Unbounded | 900 | 216 | -0.04 | 0.98 | upper | 46.7 |
| `y2k-chrome-modern` | headline | Unbounded | 700 | 96 | -0.02 | 0.98 | upper | 46.7 |
| `y2k-chrome-modern` | body | Manrope | 500 | 64 | -0.015 | 1.4 | sentence | 64.8 |
| `y2k-chrome-modern` | label | Geist Mono | 500 | 50 | -0.02 | 0.9 | upper | 49.3 |
| `y2k-chrome-modern` | code | Geist Mono | 400 | 66 | 0 | 1.4 | sentence | 66 |
| `kinetic-type` | display | Mona Sans | 900 | 198 | -0.03 | 0.9 | upper | 48 |
| `kinetic-type` | headline | Mona Sans | 200 | 114 | -0.02 | 0.9 | upper | 48 |
| `kinetic-type` | body | Mona Sans | 500 | 66 | -0.01 | 1.4 | sentence | 66.7 |
| `kinetic-type` | label | Mona Sans | 600 | 48 | -0.02 | 0.9 | upper | 48 |
| `kinetic-type` | code | JetBrains Mono | 500 | 62 | 0 | 1.4 | sentence | 63.6 |
| `dot-matrix` | display | Doto | 900 | 176 | 0.02 | 1 | upper | 50 |
| `dot-matrix` | headline | Doto | 800 | 108 | 0.03 | 1 | upper | 50 |
| `dot-matrix` | body | Onest | 500 | 66 | -0.01 | 1.4 | sentence | 66.4 |
| `dot-matrix` | label | Geist Mono | 500 | 50 | -0.02 | 0.9 | upper | 49.3 |
| `dot-matrix` | code | Geist Mono | 400 | 66 | 0 | 1.4 | sentence | 66 |

«Пол, px» — минимальный кегль роли для контекста просмотра темы (выводится из метрик шрифта, Часть I). Стеки fallback по письменностям — `font.fallback.*` и `HFT.fontLink(theme)`.

### Радиусы, px

| Пресет | `radius.chip` | `radius.control` | `radius.card` | `radius.cardSmall` | `radius.media` | `radius.panel` | `radius.window` | `radius.tile` | `radius.pill` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `higgsfield` | 9999 | 9999 | 64 | 48 | 40 | 48 | 45 | 53 | 9999 |
| `swiss-editorial` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `luxury-serif` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `playful-pop` | 9999 | 9999 | 41 | 24 | 32 | 30 | 25 | 39 | 9999 |
| `cinematic-noir` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `soft-pastel-ui` | 9999 | 9999 | 41 | 24 | 32 | 30 | 25 | 39 | 9999 |
| `tech-terminal` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `brutalist-raw` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `organic-editorial` | 12 | 24 | 30 | 18 | 22 | 21 | 23 | 26 | 25 |
| `y2k-chrome-modern` | 9999 | 9999 | 64 | 48 | 58 | 48 | 45 | 53 | 9999 |
| `kinetic-type` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `dot-matrix` | 9999 | 9999 | 41 | 24 | 32 | 30 | 25 | 39 | 9999 |

### Моушн: кривые (`ease.*`, cubic-bezier)

| Пресет | `ease.enter` | `ease.exit` | `ease.move` | `ease.camera` | `ease.ui` | `ease.expressive` |
| --- | --- | --- | --- | --- | --- | --- |
| `higgsfield` | `[0.05, 0.7, 0.1, 1]` | `[0.3, 0, 0.8, 0.15]` | `[0.2, 0, 0, 1]` | `[0.65, 0, 0.35, 1]` | `[0.2, 0, 0.38, 0.9]` | `[0.4, 0.14, 0.3, 1]` |
| `swiss-editorial` | `[0.05, 0.7, 0.1, 1]` | `[0.3, 0, 0.8, 0.15]` | `[0.2, 0, 0, 1]` | `[0.65, 0, 0.35, 1]` | `[0.2, 0, 0.38, 0.9]` | `[0.4, 0.14, 0.3, 1]` |
| `luxury-serif` | `[0.19, 1, 0.22, 1]` | `[0.45, 0, 0.55, 1]` | `[0.45, 0, 0.55, 1]` | `[0.37, 0, 0.63, 1]` | `[0.25, 0.1, 0.25, 1]` | `[0.19, 1, 0.22, 1]` |
| `playful-pop` | `[0.34, 1.56, 0.64, 1]` | `[0.36, 0, 0.66, -0.56]` | `[0.68, -0.6, 0.32, 1.6]` | `[0.65, 0, 0.35, 1]` | `[0.175, 0.885, 0.32, 1.275]` | `[0.34, 1.56, 0.64, 1]` |
| `cinematic-noir` | `[0.25, 0.46, 0.45, 0.94]` | `[0.55, 0.06, 0.68, 0.19]` | `[0.65, 0, 0.35, 1]` | `[0.45, 0, 0.55, 1]` | `[0.33, 0, 0.2, 1]` | `[0.7, 0, 0.2, 1]` |
| `soft-pastel-ui` | `[0.22, 1, 0.36, 1]` | `[0.3, 0, 0.8, 0.15]` | `[0.2, 0, 0, 1]` | `[0.65, 0, 0.35, 1]` | `[0.2, 0, 0.38, 0.9]` | `[0.4, 0.14, 0.3, 1]` |
| `tech-terminal` | `{"steps":4,"position":"end","css":"steps(4, jump-end)"}` | `{"steps":3,"position":"start","css":"steps(3, jump-start)"}` | `[0.9, 0, 0.1, 1]` | `[0.65, 0, 0.35, 1]` | `[0.2, 0, 0, 1]` | `{"steps":6,"position":"end","css":"steps(6, jump-end)"}` |
| `brutalist-raw` | `{"steps":2,"position":"start","css":"steps(2, jump-start)"}` | `{"steps":3,"position":"start","css":"steps(3, jump-start)"}` | `[0.9, 0, 0.1, 1]` | `[0.65, 0, 0.35, 1]` | `[0.2, 0, 0, 1]` | `{"steps":6,"position":"end","css":"steps(6, jump-end)"}` |
| `organic-editorial` | `[0.19, 1, 0.22, 1]` | `[0.45, 0, 0.55, 1]` | `[0.45, 0, 0.55, 1]` | `[0.37, 0, 0.63, 1]` | `[0.25, 0.1, 0.25, 1]` | `[0.19, 1, 0.22, 1]` |
| `y2k-chrome-modern` | `[0.16, 1, 0.3, 1]` | `[0.7, 0, 0.84, 0]` | `[0.83, 0, 0.17, 1]` | `[0.76, 0, 0.24, 1]` | `[0.2, 0, 0, 1]` | `[0.34, 1.56, 0.64, 1]` |
| `kinetic-type` | `[0.16, 1, 0.3, 1]` | `[0.7, 0, 0.84, 0]` | `[0.83, 0, 0.17, 1]` | `[0.76, 0, 0.24, 1]` | `[0.2, 0, 0, 1]` | `[0.34, 1.56, 0.64, 1]` |
| `dot-matrix` | `{"steps":4,"position":"end","css":"steps(4, jump-end)"}` | `{"steps":3,"position":"start","css":"steps(3, jump-start)"}` | `[0.2, 0, 0, 1]` | `[0.65, 0, 0.35, 1]` | `[0.2, 0, 0, 1]` | `{"steps":6,"position":"end","css":"steps(6, jump-end)"}` |

### Моушн: длительности, stagger, overshoot

| Пресет | fps | `dur.chip` | `dur.ui` | `dur.headline` | `dur.hero` | `dur.exit` | `dur.camera` | stagger | overshoot |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `higgsfield` | 24 | 292 мс / 7 к | 500 мс / 12 к | 583 мс / 14 к | 917 мс / 22 к | 250 мс / 6 к | 1500 мс / 36 к | 125 мс / 3 к | 0 |
| `swiss-editorial` | 24 | 292 мс / 7 к | 500 мс / 12 к | 583 мс / 14 к | 917 мс / 22 к | 250 мс / 6 к | 1500 мс / 36 к | 125 мс / 3 к | 0 |
| `luxury-serif` | 24 | 458 мс / 11 к | 750 мс / 18 к | 958 мс / 23 к | 1458 мс / 35 к | 417 мс / 10 к | 2417 мс / 58 к | 250 мс / 6 к | 0 |
| `playful-pop` | 24 | 250 мс / 6 к | 417 мс / 10 к | 542 мс / 13 к | 792 мс / 19 к | 208 мс / 5 к | 1333 мс / 32 к | 125 мс / 3 к | 0.12 |
| `cinematic-noir` | 24 | 375 мс / 9 к | 667 мс / 16 к | 792 мс / 19 к | 1208 мс / 29 к | 333 мс / 8 к | 2042 мс / 49 к | 167 мс / 4 к | 0 |
| `soft-pastel-ui` | 24 | 333 мс / 8 к | 542 мс / 13 к | 708 мс / 17 к | 1042 мс / 25 к | 292 мс / 7 к | 1708 мс / 41 к | 125 мс / 3 к | 0 |
| `tech-terminal` | 24 | 208 мс / 5 к | 333 мс / 8 к | 417 мс / 10 к | 625 мс / 15 к | 208 мс / 5 к | 1042 мс / 25 к | 42 мс / 1 к | 0 |
| `brutalist-raw` | 24 | 208 мс / 5 к | 333 мс / 8 к | 417 мс / 10 к | 625 мс / 15 к | 208 мс / 5 к | 1042 мс / 25 к | 42 мс / 1 к | 0 |
| `organic-editorial` | 24 | 375 мс / 9 к | 625 мс / 15 к | 792 мс / 19 к | 1167 мс / 28 к | 333 мс / 8 к | 1958 мс / 47 к | 250 мс / 6 к | 0 |
| `y2k-chrome-modern` | 24 | 250 мс / 6 к | 417 мс / 10 к | 500 мс / 12 к | 750 мс / 18 к | 208 мс / 5 к | 1292 мс / 31 к | 83 мс / 2 к | 0.06 |
| `kinetic-type` | 24 | 250 мс / 6 к | 417 мс / 10 к | 500 мс / 12 к | 750 мс / 18 к | 208 мс / 5 к | 1292 мс / 31 к | 42 мс / 1 к | 0.06 |
| `dot-matrix` | 24 | 208 мс / 5 к | 333 мс / 8 к | 417 мс / 10 к | 625 мс / 15 к | 208 мс / 5 к | 1042 мс / 25 к | 42 мс / 1 к | 0 |

«к» — кадры при `rhythm.fps` пресета; пересчёт на другую частоту — `HFT.ms2f(ms, fps)` (положительная длительность ≥ 1 кадра).

**Базовые длительности до множителя характера движения, с:** `chipPop` 0.28 · `cardSlide` 0.48 · `headlineMaskUp` 0.6 · `heroReveal` 0.9 · `cameraPush` 1.5 · `exit` 0.25 · `crossfade` 0.33. Длительность пресета = база × множитель `motionPersonality` (0.5–1.8, `core.rhythm`), с округлением до целых кадров.

### Грамматика переходов

| Переход | Правило |
| --- | --- |
| `match-cut` | объект/форма совпадает по позиции (±200 px) и масштабу через склейку |
| `push` | вся сцена сдвигается на ширину кадра или колонку; один easing на группу |
| `whip` | скоростной пан 4–8 кадров размытия; ≤1 на 15 с |
| `mask` | вайп/ирис/маска по форме объекта или по колонке сетки |
| `flash` | вспышка ≤2 кадра, ≤3/с, лаймовый/цветной хит ≥4 кадров |
| `morph` | форма A перетекает в форму B (pill → bar, кнопка → карточка) |
| `dissolve` | кросс-растворение 12–24 кадра (люкс, кино) |
| `dip` | уход в цвет фона/чёрный 8–12 кадров |
| `hard-cut` | прямая склейка на долю |
| `glitch-slice` | 4–8 горизонтальных полос со сдвигом 2–4 кадра |

### Материал 3D-героя (`material.hero3d.*`, тёмная схема)

| Пресет | color | metalness | roughness | clearcoat | clearcoatRoughness | sheen | transmission | ior | emissiveIntensity | envMapIntensity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `higgsfield` | `#D1FE17` | 0 | 1 | 0 | 0 | 0 | 0 | 1.5 | 0 | 1 |
| `swiss-editorial` | `#E4321B` | 0 | 1 | 0 | 0 | 0 | 0 | 1.5 | 0 | 1 |
| `luxury-serif` | `#C7BCA9` | 0.9 | 0.28 | 0 | 0 | 0 | 0 | 1.5 | 0 | 1.2 |
| `playful-pop` | `#FFB0CB` | 0 | 0.55 | 0.3 | 0.4 | 0.4 | 0 | 1.5 | 0 | 1 |
| `cinematic-noir` | `#D5B89A` | 0.9 | 0.28 | 0 | 0 | 0 | 0 | 1.5 | 0 | 1.2 |
| `soft-pastel-ui` | `#18181C` | 0 | 0.55 | 0 | 0 | 0.2 | 0 | 1.5 | 0 | 1 |
| `tech-terminal` | `#2BD9FF` | 0 | 1 | 0 | 0 | 0 | 0 | 1.5 | 0 | 1 |
| `brutalist-raw` | `#FFD500` | 0 | 1 | 0 | 0 | 0 | 0 | 1.5 | 0 | 1 |
| `organic-editorial` | `#1E1A13` | 0 | 0.92 | 0 | 0 | 0 | 0 | 1.5 | 0 | 1 |
| `y2k-chrome-modern` | `#A5C4CE` | 0.9 | 0.28 | 0 | 0 | 0 | 0 | 1.5 | 0 | 1.2 |
| `kinetic-type` | `#3346FF` | 0 | 1 | 0 | 0 | 0 | 0 | 1.5 | 0 | 1 |
| `dot-matrix` | `#070707` | 0 | 0.35 | 0 | 0 | 0 | 0 | 1.5 | 1.6 | 1 |

**Различимость пресетов.** 66 пар; минимум различающихся осей в паре — 4 (порог системы — 4); пары с общим дисплейным семейством: нет.

### Алиасы пресетов внешней версии

Пресеты из `tokens_universal.json` не заменяют наши, а принимаются как алиасы.

| Их пресет | Наш пресет | Пояснение |
| --- | --- | --- |
| `cleanGraphic` | `swiss-editorial` | чёткие формы, минимум эффектов — наш swiss-editorial (светлая схема) |
| `darkFocus` | `cinematic-noir` | контрастный герой в сдержанной тёмной среде; для бренда Higgsfield — theme("higgsfield", {scheme:"dark"}) |
| `boldType` | `kinetic-type` | масштаб и ритм букв ведут сцену |
| `softDepth` | `soft-pastel-ui` | мягкая глубина без обязательного стекла |
| `cinematicSpatial` | `cinematic-noir` | свет, пространство, оптика; рендер задаётся модулем spatial3d |
| `playfulGraphic` | `playful-pop` | деформация и неровный ритм; важный текст остаётся ясным |
| `documentaryOverlay` | `swiss-editorial` | это не стиль, а жанр/раскладка: графика поверх живого материала (layoutPatterns.lowerThird). Тема — сдержанный swiss-editorial в тёмной схеме; проверяйте контраст поверх меняющегося фона (скрим 40–70 %) |

## Жанры (`HFT.genres`)

Жанр — какую работу делает ролик; стиль — как он выглядит. Они ортогональны: `HFT.theme('<пресет>', {genre})`. Источник жанров — `tokens_universal.json` [стартовая настройка].

| Жанр | Задача | Обязательные входные данные | Модули | Ход |
| --- | --- | --- | --- | --- |
| `productDemo` | Показать, как работает реальный продукт и какой результат получает человек. | audience, userTask, verifiedProductCapabilities, approvedUiState, outputContext | audio, camera, compositing, type, ui, promptFlow, interactive | taskContext → userAction → productResponse → observableResult |
| `explainer` | Объяснить идею, процесс или связь с помощью понятных визуальных шагов. | audience, learningGoal, sourceMaterial, keyConcepts, outputContext | audio, shape, type | orientation → conceptIntroduction → relationshipOrProcess → concreteExample → takeaway |
| `brandFilm` | Выразить характер бренда через образ, ритм, историю или настроение. | brandIntent, audience, approvedBrandAssets, tone, outputContext | audio, camera, character, compositing, shape, spatial3d, type | establishTone → developMotif → emotionalOrVisualTurn → resolution |
| `kineticType` | Передать смысл и ритм через движение букв, слов и текстовых блоков. | approvedText, readingOrder, intendedEmphasis, outputContext | audio, compositing, type | introduceText → developEmphasis → changeRhythm → resolvePhrase |
| `logoIdent` | Создать короткую узнаваемую заставку, переход или петлю на основе знака. | approvedLogoAssets, brandIntent, placement, startAndEndStates, outputContext | audio, compositing, particles, shape, spatial3d, type, loop | entryState → identityGesture → resolvedState |
| `dataStory` | Показать вывод из данных, сохранив смысл чисел и пределы их интерпретации. | audience, editorialQuestion, sourceData, sourceReferences, sourceDates, measurementPeriod, unitsAndDefinitions, outputContext | audio, data, shape, type | stateQuestion → establishMeasure → showPattern → addContext → qualifiedConclusion |
| `editorialTitles` | Оформить название, авторов, главы или контекст произведения в его визуальном языке. | approvedTitleAndCredits, hierarchy, editorialContext, placement, outputContext | audio, compositing, type | establishContext → revealHierarchy → developSequence → handoff |
| `characterMotion` | Передать действие, реакцию или историю через поведение персонажа. | characterDesign, characterIntent, actionOrStory, performanceTone, outputContext | audio, camera, character, compositing, shape, spatial3d, type | establishIntent → act → respond → resolveOrContinue |
| `spatial3d` | Исследовать форму, пространство, объект или среду средствами объёмной анимации. | visualIntent, subjectOrScene, spatialStyle, assetConstraints, outputContext | audio, camera, compositing, particles, spatial3d, loop | establishSpace → developFormOrAction → reframeOrTransform → resolveState |
| `broadcastPackage` | Создать согласованную систему заставок, плашек, переходов и других элементов программы или трансляции. | packageInventory, contentSchema, brandAssets, playoutConstraints, deliverySpecification | audio, compositing, data, shape, type, broadcast | defineStates → introduceElement → holdOrUpdate → exitOrHandoff |
| `musicVisual` | Создать визуальное сопровождение музыки, выступления или звуковой композиции. | audioOrTimingReference, visualIntent, performanceContext, playbackMode, outputContext | audio, compositing, particles, shape, spatial3d, type, loop, interactive | establishMotif → developVariation → contrastOrPeak → resolveOrLoop |

### Матрица «жанр × стиль»

Шкала: ● — подходит, ○ — возможно, × — избегать. [Э] by whenToUse / avoidFor of each preset

| Жанр | `higgsfield` | `swiss-editorial` | `luxury-serif` | `playful-pop` | `cinematic-noir` | `soft-pastel-ui` | `tech-terminal` | `brutalist-raw` | `organic-editorial` | `y2k-chrome-modern` | `kinetic-type` | `dot-matrix` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `productDemo` | ● | ● | ○ | ● | ○ | ● | ● | ○ | ○ | ○ | ○ | ○ |
| `explainer` | ○ | ● | × | ● | × | ● | ● | ○ | ● | × | ○ | ○ |
| `brandFilm` | ● | ○ | ● | ● | ● | ○ | × | ● | ● | ● | ● | ○ |
| `kineticType` | ○ | ● | ○ | ○ | ○ | × | ○ | ● | ○ | ○ | ● | ○ |
| `logoIdent` | ● | ○ | ● | ● | ● | ○ | ○ | ○ | ○ | ● | ● | ● |
| `dataStory` | ○ | ● | × | ○ | × | ○ | ● | ○ | ○ | × | ○ | ○ |
| `editorialTitles` | ○ | ● | ● | × | ● | × | ○ | ○ | ● | ○ | ● | ○ |
| `characterMotion` | ○ | × | × | ● | ○ | ● | × | × | ● | ○ | × | × |
| `spatial3d` | ● | × | ● | ○ | ● | ○ | × | × | ○ | ● | × | ○ |
| `broadcastPackage` | ○ | ● | ○ | ○ | ● | ○ | ● | ○ | ○ | ○ | ● | ○ |
| `musicVisual` | ○ | × | ○ | ● | ● | × | ○ | ● | × | ● | ● | ● |

## Модули (`HFT.modules`)

Подключаются только нужные модули. Настройки — [стартовая настройка], если в поле `conflict` не сказано, что действует наше число из архива.

| Модуль | Задача | Настройки | Правил |
| --- | --- | --- | --- |
| `shape` | Векторные формы, линии, маски, схемы, иллюстрации и геометрия знака. | shapeAssets []; coordinateSpace design_units_or_normalized; strokeScaling project_defined | 5 |
| `camera` | Кадрирование, панорамы, приближения и перемещение точки наблюдения в 2D и 3D. | mode 2d_reframe; focusTarget —; startFrame —; endFrame —; maxScale —; verbsSource core.camera.verbs; oneDominantVerb true; reverseMax 1 | 5 |
| `particles` | Частицы, повторяемые элементы и процедурные поля. | seed integer, обязателен; count —; lifetimeMs —; emitter —; simulationCache —; reproducible true; densityNearText не выше 20 % яркости ниже текста | 5 |
| `type` | Титры и кинетическая типографика. | unitOfAnimation word; preserveReadingOrder true; decorativeTextAllowed true; unit буква \| слово \| строка \| блок; mustReadSeparatedFromTexture true | 4 |
| `ui` | Демо интерфейсов и интерактивные состояния. | cursorAsset —; cursorTravelMs 600; cursorDwellMs 160; pressMs 100; showOnlySupportedStates true; cursorTravelRangeMs [500,900]; cursorDwellRangeMs [150,250]; releaseMs 220; rippleMs [400,500]; cursorPx {"hero":[128,256],"ui":[96,128]}; conflict press: ours 100 ms (archive) wins over tokens_universal 120 ms; travel 600 / dwell 160 sit inside our ranges | 5 |
| `promptFlow` | Необязательный модуль для продуктов с вводом запроса и созданием результата. | actionLabel —; prompt —; resultType —; transition mask; promptMaxVisibleCharsDefault 60; promptMaxVisibleChars 60; typingCps {"verbatim":15,"max":20}; holdAfterTypingMs 500; placeholderLabel ✦ GENERATION + описание шота (концепт подписан, не выдаётся за результат); template15sIntentChars 30 | 5 |
| `data` | Графики, карты, числа и сравнения. | source —; sourceDate —; unit —; scaleType —; missingValuePolicy show_as_missing; roundingDigits —; missing показывать как отсутствие, никогда 0; axisChange видимой; tnum true | 7 |
| `character` | Анимация персонажей, предметов с характером и ригов. | rigAsset —; actionGoal —; poseStyle —; timingMode performance_driven | 6 |
| `spatial3d` | Объекты, камера, свет и сцены в 3D. | renderer —; rendererVersion —; worldUnit meter (отдельно от du); projection perspective; focalLengthMm —; sensorWidthMm —; orthographicScaleWorld —; workingColorSpace —; cameraMotion —; objectMotion —; motionBlurShutterDegrees —; fovDeg 28; fovRangeDeg [24,35]; focalLengthRule фокусное только вместе с шириной сенсора; cocMaxPx 34; rackFrames [12,24]; bloom {"threshold":1.15,"strength":[0.15,0.3]} | 6 |
| `compositing` | Графика поверх съёмки, трекинг и сборка слоёв. | plateAsset —; trackingMode —; workingColorSpace —; alphaMode — | 5 |
| `loop` | Бесшовные циклы, фоны, загрузчики и повторяемая сценическая графика. | seamType continuous; durationMs —; audioLoops false; checkCycles 3; seam ["позиция","масштаб","углы","прозрачность","камера","свет","эффекты","звук"] | 5 |
| `broadcast` | Эфирные титры, плашки, отбивки и графические пакеты. | deliverySpecification —; nameMaxChars —; holdMode indefinite_until_trigger; variants ["in","hold","out"]; liveDataSource —; states ["in","hold","out"]; hold управляется оператором (indefinite until trigger); titleSafe 90 % (SMPTE ST 2046-1) | 5 |
| `audio` | Музыка, речь, шумы и связь звука с действием. | musicAsset —; voiceAsset —; sonicLogoAsset —; bpm —; loudnessTargetLufs —; truePeakLimitDbtp —; loudness {"social":{"lufs":-14,"truePeakDbtp":-1},"broadcast":{"lufs":-23,"standard":"EBU R128"}}; silence планировать паузы вместе со звуком; subtitles когда речь несёт смысл — обязательно (accessibility.subtitles) | 5 |
| `interactive` | Моушн в приложениях, веб-интерфейсах и управляемых пользователем сценах. | triggers []; states []; reducedMotionAlternative —; interruptionPolicy —; reducedMotion показать B-rest кадр, убрать параллакс и камеру (prefers-reduced-motion); interruption описать прерывание и повторный запуск | 4 |

## Бренды (`HFT.brands`)

Схема бренда (поля `brandConfig`) и её заполненные экземпляры. Рецепты кадров, регистры, архив и legacy-значения — в Части V и в данных.

### Higgsfield (`higgsfield`)

| Поле | Значение |
| --- | --- |
| `id` | higgsfield |
| `name` | Higgsfield |
| `style` | higgsfield |
| `defaultScheme` | dark |
| `logoAsset` | — |
| `logoSlot` | wordmark instance from the brandbook (lime 340×67, black 470×92, white 368×72 / 592×116 @1920); never redrawn |
| `logoClearSpaceDu` | 32 |
| `logoMinSizeDu` | 48 |
| `approvedVariants` | lime; black; white; squiggle (signature, 64) |
| `toneOfVoice` | уверенный, точный, минимальный, но творческий; claim короткой фразой с точкой; Space Grotesk CAPS — голос рассказчика, Inter — голос продукта |
| `fonts` | {"display":"Inter","headline":"Inter Tight","body":"Inter","label":"Space Grotesk","data":"JetBrains Mono","numbers":"Space Mono","accent":"Instrument Serif","fallbackByScript":{"Cyrl":"Inter","Grek":"Inter","Jpan":"Noto Sans JP","Kore":"Noto Sans KR","Hans":"Noto Sans SC","Hant":"Noto Sans TC","Arab":"Noto Sans Arabic","Deva":"Noto Sans Devanagari","Thai":"Noto Sans Thai"}} |
| `fixedColorMeanings` | {"#D1FE17":"лайм = «Higgsfield действует»: Generate, отправка, выбор, статус, результат, payoff, CTA; свет Higgsfield","#ED1572":"magenta = изменение / метрика; ≤ 1 второй акцент на фильм","#131313":"инк: текст на лайме и светлых сценах"} |
| `secondaryMeaning` | изменение / метрика (magenta #ED1572) |
| `signatureMotion` | капсула S1: 7 баров 86 px, шаг 120, высоты 311/426/651/311/395/290/185, пик — бар 3, порядок появления 0,1,6,2,3,4,5 + лаймовый световой след |
| `signatureTransition` | prompt bar → ✦ загорается → лаймовый свип L→R (18–24 кадра @24) → матт идёт за свипом и открывает результат |
| `sonicIdentityAsset` | — |
| `locks` | typeVoice; palette |
| `laws` | лайм никогда не текст и не линия < 12 px на светлом фоне (1,06–1,17:1) — только заливка с инком #131313 (строже core V03: «никогда, при любом кегле»); никогда белый текст на лайме (1,17:1); никогда прямой градиент лайм → magenta (оранжевая середина); разводить пространственно; лайм ≤ 8 % площади (жёстко 10 %), один объект + одно эхо; UI-кадры обычно 1–3 %; Space Grotesk никогда для кириллицы и italic (нет глифов и курсива) → Inter; ключевой лайм входит через ~0,3 с после склейки тёмное → светлое; без детального старомодного 3D: стеклянные трубки, мениск, пузыри, хром; лайм работает как свет (emissive), а не пластик; генерации — плейсхолдер «✦ GENERATION» + описание шота, пока нет реального стилла; никогда не выдавать концепт за результат продукта |
| `rhythm` | {"fps":24,"bpm":120,"framesPerBeat":12} |
| `accentArea` | {"maxPct":10,"targetRangePct":[1,8],"objects":1,"echoes":1,"secondaryMaxPct":5} |
| `radius` | {"media":40,"panel":48} |
| `motifs` | капсула S1 (волна); лаймовый CTA-pill; тёмный стеклянный pill / промпт-бар; send-orb; ✦ sparkle (векторный инстанс, 0,8 × капитель); squiggle-водяной знак; планета end card |

**colorOverrides:** dark — 30 ролей; light — 31 ролей (полные значения — в данных и в Части V).

## Шаблоны (`HFT.templates`)

Паспорт проекта и манифесты. `null` = «не задано», а не ноль. Заполнение — шаг 1 и шаг 8 быстрого старта.

| Шаблон | Поля (= значение по умолчанию или тип) |
| --- | --- |
| `brief` | `title`, `purpose`, `audience`, `keyMessage`, `language`, `textDirection` = auto, `genreProfile` = productDemo, `profileInputs`, `stylePreset` = higgsfield, `theme`, `enabledModules` = ["type"], `narrativeTemplate`, `durationMs`, `deliveryProfile` = landscape, `fps` = 24, `bpm`, `voiceover` = false, `music` = false, `soundEffects` = false, `loop` = false, `viewingContext`, `requiredText`, `availableAssets`, `productFacts`, `dataSources`, `callToAction`, `customRequirements`, `exceptions`, `passport` {register/style + ground; scene mode (dark/light/schedule); accents (primary + <= 1 secondary, one meaning each); display voice; type scale (<= 5 narrative styles); text margin + primary axis + one off-axis family; container family (one radius formula, one shadow); light model; hero motif / travelling object; transition family (<= 2 counted types); camera verb (+1 motivated reverse); cast / world grade; anchors (fixed coordinates); ornament kit (one); fps / bpm; bookend (open <-> close)}, `_note` = паспорт проекта = projectBrief (tokens_universal) + Паспорт фильма (Bible, Приложение A): одно значение на строку на весь фильм |
| `brandConfig` | `id` = string, `name` = string, `style` = style preset id, `defaultScheme` = dark \| light, `logoAsset` = path \| null, `logoClearSpaceDu` = number \| null, `logoMinSizeDu` = number \| null, `approvedVariants` = […], `toneOfVoice` = string, `fonts` {display: GF family; headline: GF family?; body: GF family; label: GF family?; data: GF mono family; accent: GF family?; fallbackByScript: {ISO 15924: GF family}}, `colorOverrides` {dark: {role: hex \| rgba}; light: {role: hex \| rgba}}, `fixedColorMeanings` = {hex: meaning}, `secondaryMeaning` = string, `signatureMotion` = string, `signatureTransition` = string (not counted in the ≤ 2 transition types), `sonicIdentityAsset` = path \| null, `locks` = [axis keys a project may not change], `laws` = [stricter-than-core laws], `rhythm` = {fps, bpm}, `accentArea` = {maxPct, targetRangePct, objects, echoes, secondaryMaxPct}, `radius` = {class: px}, `recipes` = {name: CSS / geometry recipe}, `motifs` = […], `three` = three.js scene params, `archive` = evidence, `legacy` = old token file, unchanged, `rule` = A brand may only make core laws stricter, never looser (ARCHITECTURE §1.4). Every colour override is re-validated (V01–V23). |
| `deliveryConfig` | `platformName`, `specificationUrl`, `specificationCheckedOn`, `overlayAsset`, `forbiddenRegionsNormalized`, `requiredSafeRegionNormalized`, `cropVariants`, `pixelAspectRatio` = 1, `scanMode` = progressive, `alphaRequired` = false, `hdrRequired` = false, `noteRu` = houseInsetFraction задаёт эстетические поля, а не гарантированную safe zone. Размеры, частоту кадров, перекрытия платформы, область титров и параметры экспорта подтвердить для конкретной сдачи. Для эфирных и нестандартных носителей заменить стартовые настройки. |
| `assetManifest` | `id`, `kind`, `source`, `local_or_remote_reference`, `usage_rights`, `version`, `dimensions`, `fps_if_video`, `duration_if_timed`, `color_space`, `alpha_mode`, `used_in_shots` |
| `shotManifest` | `id`, `purpose`, `start_frame`, `end_frame_exclusive`, `layout`, `assets`, `required_text`, `motion`, `audio`, `exceptions`, `status` |

## Реестр шрифтов (Google Fonts)

Каждое семейство проверено по каталогу Google Fonts (2026-10-08). «Кириллица» = в CSS реально отдаётся subset `cyrillic` (U+0400–045F); `cyrillic-ext` без базовой кириллицы не считается. [обязательно] Для письменности без поддержки берётся fallback из `font.fallback.*`.

| Семейство | Категория | Кириллица | Оси | Основные subsets |
| --- | --- | --- | --- | --- |
| Alexandria | Sans Serif | нет | — | arabic, latin, vietnamese |
| Anybody | Display | нет | — | latin, vietnamese |
| Archivo | Sans Serif | нет | — | latin, vietnamese |
| Baloo 2 | Display | нет | — | devanagari, latin, vietnamese |
| Black Han Sans | Sans Serif | нет | — | korean, latin |
| Bricolage Grotesque | Sans Serif | нет | — | latin, vietnamese |
| Commissioner | Sans Serif | да | — | cyrillic, greek, latin, vietnamese |
| Cormorant | Serif | да | — | cyrillic, latin, vietnamese |
| DM Mono | Monospace | нет | — | latin |
| Dela Gothic One | Display | да | — | cyrillic, greek, japanese, latin, vietnamese |
| DotGothic16 | Sans Serif | да | — | cyrillic, japanese, latin |
| Doto | Sans Serif | нет | — | latin |
| Fraunces | Serif | нет | — | latin, vietnamese |
| Geist | Sans Serif | да | — | cyrillic, latin, vietnamese |
| Geist Mono | Monospace | да | — | cyrillic, latin, symbols2, vietnamese |
| Handjet | Display | да | — | arabic, armenian, cyrillic, greek, hebrew, latin, vietnamese |
| IBM Plex Mono | Monospace | да | — | cyrillic, latin, vietnamese |
| IBM Plex Sans | Sans Serif | да | — | cyrillic, greek, latin, vietnamese |
| IBM Plex Sans Arabic | Sans Serif | нет | — | arabic, latin |
| IBM Plex Sans Devanagari | Sans Serif | нет | — | devanagari, latin |
| IBM Plex Sans JP | Sans Serif | да | — | cyrillic, japanese, latin |
| IBM Plex Sans KR | Sans Serif | нет | — | korean, latin |
| IBM Plex Sans Thai | Sans Serif | нет | — | latin, thai |
| Instrument Serif | Serif | нет | — | latin |
| Inter | Sans Serif | да | — | cyrillic, greek, latin, vietnamese |
| Inter Tight | Sans Serif | да | — | cyrillic, greek, latin, vietnamese |
| JetBrains Mono | Monospace | да | — | cyrillic, greek, latin, vietnamese |
| Jost | Sans Serif | да | — | cyrillic, latin |
| Jua | Sans Serif | нет | — | korean, latin |
| Libre Caslon Text | Serif | нет | — | latin |
| Literata | Serif | да | — | cyrillic, greek, latin, vietnamese |
| Lora | Serif | да | — | cyrillic, latin, math, symbols, vietnamese |
| M PLUS Rounded 1c | Sans Serif | да | — | cyrillic, greek, hebrew, japanese, latin, vietnamese |
| Manrope | Sans Serif | да | — | cyrillic, greek, latin, vietnamese |
| Martian Mono | Monospace | да | — | cyrillic, latin |
| Mona Sans | Sans Serif | нет | — | latin, vietnamese |
| Noto Kufi Arabic | Sans Serif | нет | — | arabic, latin, math, symbols |
| Noto Naskh Arabic | Serif | нет | — | arabic, latin, math, symbols |
| Noto Sans Arabic | Sans Serif | нет | — | arabic, latin, math, symbols |
| Noto Sans Devanagari | Sans Serif | нет | — | devanagari, latin |
| Noto Sans Hebrew | Sans Serif | нет | — | — |
| Noto Sans JP | Sans Serif | да | — | cyrillic, japanese, latin, vietnamese |
| Noto Sans KR | Sans Serif | да | — | cyrillic, korean, latin, vietnamese |
| Noto Sans SC | Sans Serif | да | — | chinese-simplified, cyrillic, latin, vietnamese |
| Noto Sans TC | Sans Serif | нет | — | — |
| Noto Sans Thai | Sans Serif | нет | — | latin, thai |
| Noto Serif | Serif | да | — | cyrillic, greek, latin, math, vietnamese |
| Noto Serif Devanagari | Serif | нет | — | devanagari, latin |
| Noto Serif JP | Serif | нет | — | — |
| Noto Serif KR | Serif | да | — | cyrillic, korean, latin, vietnamese |
| Noto Serif SC | Serif | да | — | chinese-simplified, cyrillic, latin, vietnamese |
| Noto Serif TC | Serif | нет | — | — |
| Noto Serif Thai | Serif | нет | — | latin, thai |
| Onest | Sans Serif | да | — | cyrillic, latin, math, symbols, vietnamese |
| Oswald | Sans Serif | нет | — | — |
| PT Serif | Serif | да | — | cyrillic, latin |
| Playfair | Serif | да | — | cyrillic, latin, vietnamese |
| Plus Jakarta Sans | Sans Serif | нет | — | latin, vietnamese |
| Readex Pro | Sans Serif | нет | — | arabic, latin, vietnamese |
| Roboto Flex | Sans Serif | да | — | cyrillic, greek, latin, vietnamese |
| Rubik | Sans Serif | да | — | arabic, cyrillic, hebrew, latin |
| Shippori Mincho | Serif | нет | — | japanese, latin |
| Sofia Sans | Sans Serif | да | — | cyrillic, greek, latin |
| Sofia Sans Extra Condensed | Sans Serif | да | — | cyrillic, greek, latin |
| Source Serif 4 | Serif | нет | — | — |
| Space Grotesk | Sans Serif | нет | — | latin, vietnamese |
| Space Mono | Monospace | нет | — | latin, vietnamese |
| Syne | Sans Serif | нет | — | greek, latin |
| Tiny5 | Sans Serif | да | — | cyrillic, greek, latin |
| Tiro Devanagari Hindi | Serif | нет | — | devanagari, latin |
| Unbounded | Sans Serif | да | — | cyrillic, latin, vietnamese |
| ZCOOL KuaiLe | Sans Serif | нет | — | chinese-simplified, latin |
| ZCOOL QingKe HuangYou | Sans Serif | нет | — | chinese-simplified, latin |
| Zen Maru Gothic | Sans Serif | да | — | cyrillic, greek, japanese, latin |
| Zen Old Mincho | Serif | да | — | cyrillic, greek, japanese, latin |

## Что перенесено из core в бренд Higgsfield

Правила, которые Библия смешала с общими. Общая форма остаётся законом `core`, фирменное значение уходит в `brands.higgsfield` (Часть V).

| Правило Higgsfield | Общая форма (core) | Куда |
| --- | --- | --- |
| lime #D1FE17 = "Higgsfield acts" (Generate, select, status, result, CTA) | accent.action = the single action/focal signal | `brands.higgsfield` |
| lime <= 8% (10%), one object + one echo, counting rules | colour.areaBudget + accentCounting | `core (universal numbers) + brands.higgsfield (lime semantics)` |
| Inter + Space Grotesk; SG Bold CAPS narrator; SG never for non-Latin | typeVoice axis + scriptFallback law | `axes.typeVoice + brands.higgsfield` |
| five registers A-E (Dark Keynote, Light Stage, Dark Material, Co-brand, Editorial) | style presets (composition + material + scheme) | `styles.* (higgsfield variants)` |
| title formula: logo -> SG Bold WORD 170-235 -> capsule/plaque/pill | hierarchy.titleStack.universal | `brands.higgsfield.recipes` |
| Generate ✦ n button, credits always visible, macro key | narrative beat "action" + archetype macro | `brands.higgsfield.recipes` |
| signature transition: prompt -> ✦ ignites -> lime sweep L->R (18-24 f) -> matte reveal | transitions.countRule: one declared signature is not counted | `brands.higgsfield.signatureTransition` |
| grounds #131313 / #FFFFFF / #F3F3F3 / #EDEDEF / pearl #FCFCFD; surfaces #1C1E20 / #23262A | bg.base L ranges + raised dY' rule | `brands.higgsfield.palette` |
| lime as light (sunrise, pools, rim model AV5), ✦ sparkle kit, squiggle mark, planet end card | one light model + one ornament kit per film | `brands.higgsfield (motif, ornament kits)` |
| cursor 128-256 px hero / 96-128 UI; click rings coloured by surface | macro geometry cursor range (archive) and the 1:1-contrast ban | `brands.higgsfield + core.macro.avoid` |
| no device frames / no 3D device renders; frameless phone allowed | depth.threeD.taste | `core (taste) + brands.higgsfield` |
| 24 fps / 120 BPM house default | rhythm.recommendedPairs | `brands.higgsfield.rhythm` |
| magenta #ED1572 second accent = change / metric | secondAccent law | `brands.higgsfield.palette` |
| archive radii (9:16 card 6% W, hero media 2-3% W, chips full, key-pill 23-29% H) | shape.families (fraction of the short side); the archive is the `round` family | `axes.shape.round + brands.higgsfield` |
| muted grey #A2A2A2 on #131313 (Lc 51) | fg.muted floor Lc 50 / target Lc 60 on dark | `brands.higgsfield.palette override` |

## Данные в JSON

Компактные срезы данных: короткие узлы — в одну строку, длинные массивы и тексты сокращены (пометка «…»). Полные файлы: `system/hf-tokens.json` (или `system/design/core.json`, `system/design/styles.json`). Токены контракта, правила проверки и перенос в бренд здесь не повторяются: они в таблицах выше.

### core (компактно)

```json
{
  "meta": {
    "name": "Universal motion-frame system: CORE LAWS",
    "version": "1.1.0",
    "date": "2026-10-08",
    "companion": "ARCHITECTURE.md (same folder); section map: formats/canvas 3.1, safeAreas 3.2, grids 3.3, composition 3.4, density 3.5, hierarchy 3.6, typography 3.7, legibility 3.8, reading 3.9, focalContinuity 3.10, rhythm 3.11, narra…",
    "units": "px at the format's native size (16:9 = 1920x1080; 9:16 = 1080x1920; 1:1 = 1080x1080; 4:5 = 1080x1350); seconds; frames = round(seconds x fps)",
    "tags": {
      "scope": {"universal":"holds for any identity, style and typeface","higgsfield":"Higgsfield identity instance (moves to brands.higgsfield)"},
      "ev": {"A":"archive: 84 analysed projects / Bible","I":"peer-reviewed or craft research (direction, not the exact number)","S":"standard / platform spec","E":"heuristic: our number, to test","T":"client taste (5 review rounds)"},
      "start": "[стартовая настройка] tokens_universal.json (2026-10-08): editable default, not evidence"
    },
    "defaultScope": "universal",
    "sources": {"bible":"../../../bible_final.md (sections 1-11, 13)","research":"../../../research/*.md (9 reports)","tokensV1":"../../shared/tokens.json"},
    "precedence": "core constraints are validated AFTER axes, styles and brands merge; a value outside a core range is an error (validate) or is clamped (derive)",
    "mergedFrom": "tokens_universal.json — внешняя версия универсальной системы, предоставлена клиентом 2026-10-08 (числа = стартовые настройки, не доказательства)"
  },
  "layers": {
    "order": ["background","environment","contentBack","hero","contentFront","labels","brand","captions","notesNonExport"],
    "mapToDepth": {"background":"00_BG","environment":"01_ATMOS","contentBack":"02_FAR","hero":"03_HERO","contentFront":"04_NEAR_UI","labels":"05_TYPE","brand":"06_BRAND","captions":"08_CAPTIONS","notesNonExport":"99_NOTES"},
    "fx": "07_FX (sparkles, sweeps, rings — Screen / Add) живёт между brand и captions",
    "rule": "2D — этот порядок; 3D и перекрытия — реальная глубина и маски; notesNonExport не рендерится никогда",
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08) + core 3.15"
  },
  "formats": {
    "16x9": {"w":1920,"h":1080,"role":"master landscape: web, YouTube, X/LinkedIn feed, TV, events"},
    "9x16": {"w":1080,"h":1920,"role":"Reels / TikTok / Shorts / Stories; also the source for the 4:5 feed window"},
    "1x1": {"w":1080,"h":1080,"role":"feed square (LinkedIn, X, carousel, ads); never the master"},
    "4x5": {"w":1080,"h":1350,"role":"feed portrait (Instagram/Facebook feed, ads); = the centre window of a 9:16 master"},
    "rare": {"4x3":{"w":1440,"h":1080,"margin":80},"letterbox239":{"imageInside16x9":[1920,804],"barPx":138}},
    "masterRule": "16:9 is designed first; 9:16 is RE-COMPOSED (a centre crop keeps only 608/1920 px = 32%); 4:5 = the y285-1635 window of the 9:16; 1:1 is re-composed or cropped from a >= 2160 px 1:1/4:5 media master",
    "mediaMasterRule": "when the proof is a performance (lipsync, acting, camera move) generate one 4:5 or 1:1 master >= 2160 px short side, subject centred, and crop every format from it",
    "nativeRatiosOnly": "media sits in its native ratio (16:9, 9:16, 1:1, 4:5) in cards; never arbitrary ratios"
  },
  "canvas": {"baseUnit":8,"spacing":[8,16,24,32,48,64,96,128],"halfStepInsideUiClonesOnly":4,"roundAfterScale":true,"uiCloneScale":{"readable":[1.5,3],"macro":[2.6,4.6]}},
  "safeAreas": {
    "16x9": {
      "actionSafe": {"pct":93,"x":[67,1853],"y":[38,1042],"ev":"S","src":"SMPTE ST 2046-1; EBU R 95","required":"TV, OOH, event screens: all significant action"},
      "titleSafe": {"pct":90,"x":[96,1824],"y":[54,1026],"ev":"S","src":"SMPTE ST 2046-1; EBU R 95","required":"TV, OOH, event screens: all text, logo, CTA"},
      "houseSocial": {"ev":"A","displayOnFootageMin":48,"displayOnFootageCanon":60,"anyOtherTextMin":60,"uiOverFootageMin":120,"required":"social + web deliverables"},
      "textMarginByArchetype": {"cornerCaptionOnFootage":[48,60],"uiAndCentred":[60,100],"uiAndCentredMedian":70,"keynoteLeftAxis":96,"editorialSplitLight":[116,120],"editorialSplitWide":230,"centredStatementMinPctW":10,"imageLed":[40,91],"fullScreenCardInset":[40,60],"floatingProps":[116,140],"ev":"A","rule":"the archetype sets the margin; the film records one text margin (+ one caption-on-footage margin) in its passport"},
      "bleed": {"allowed":["glow","grids/texture","walls","windows","carousels","large ornaments"],"never":"text (only exception: a single kinetic mega-word)","ev":"A"},
      "dualDeliveryHedge": {"heroInsideX":[680,1240],"why":"survives a centre 9:16 cut (x656-1264)","ev":"I"}
    },
    "9x16": {
      "mustReadAds": {"x":[72,888],"y":[288,1248],"ev":"E","src":"third-party overlays Meta/TikTok/Shorts, cross-checked"},
      "mustReadOrganic": {"x":[72,888],"y":[240,1440],"ev":"E"},
      "rightRail": {"xFrom":888,"rule":"no text, no CTA in the right 192 px","ev":"E"},
      "centredTextMaxWidth": 696,
      "feedWindow4x5": {"y":[285,1635],"ev":"E","src":"Instagram shows Reels in the main feed as the centre 1080x1350 window (third-party guides, 2026)"},
      "profileGridWindow3x4": {"y":[240,1680],"ev":"E","src":"Instagram profile grid is 3:4 since Jan 2025 (third-party)"},
      "opticalCentreY": {"ads":768,"organic":840},
      "rule": "design 9:16 with must-read inside x72-888 and y288-1248: it then also survives the 4:5 feed window and the 3:4 grid crop",
      "verify": "overlay the current platform PNGs before delivery; numbers change"
    },
    "1x1": {
      "textMargin": 72,
      "ev": "E",
      "note": "no platform UI overlays in-feed for square media; keep 72 px (6.7%) like 9:16 so the grid ports",
      "fromNineBySixteen": "only if must-read sits inside y420-1500 of the 9:16 master (the centred 1080x1080 window); otherwise re-compose"
    },
    "4x5": {
      "textMargin": {"x":72,"y":75},
      "ev": "E",
      "profileGridCrop3x4": {"x":[34,1046],"note":"a 4:5 post is shown 1012x1350 in the profile grid; 72 px margins already survive it"},
      "ctaOverlayBottomPct": 15,
      "ctaNote": "paid feed placements may overlay a CTA bar on the bottom ~15%: keep must-read above y1148 in ads"
    }
  },
  "grids": {
    "16x9": {
      "ev": "A+I",
      "source": "Bible §2.2; grid-composition §2",
      "columns": 12,
      "marginX": 96,
      "gutter": 24,
      "column": 122,
      "columnStarts": [96,242,388,534,680,826,972,1118,1264,1410,1556,1702],
      "lastColumnEnd": 1824,
      "rows": 6,
      "rowTop": 96,
      "rowBottom": 96,
      "rowGutter": 24,
      "row": 128,
      "rowRanges": [[96,224],[248,376],[400,528],[552,680],[704,832],[856,984]],
      "spans": {"cols10_heroCard16x9":[242,1678],"cols8_heroWithOrbit":[388,1532],"cols6_uiPanel":[534,1386],"cols1to5_textColumn":[96,802],"cols7to12_media":[972,1824],"cols5to8_dualDeliveryHedge":[680,1240]},
      "marginVariants": {"60":128,"72":126,"96":122,"120":118},
      "marginVariantsNote": "column width for other film text margins with the same 24 px gutter: col = (1920 - 2m - 264) / 12",
      "centreInGutter": [948,972],
      "thirdsLines": {"x":[640,1280],"y":[360,720]},
      "keylinesOverrideRows": true
    },
    "9x16": {
      "ev": "A+I+E",
      "source": "Bible §2.7; grid-composition §12",
      "columns": 6,
      "marginX": 72,
      "gutter": 24,
      "column": 136,
      "columnStarts": [72,232,392,552,712,872],
      "lastColumnEnd": 1008,
      "rows": 6,
      "rowTop": 288,
      "rowBottom": 672,
      "rowGutter": 24,
      "row": 140,
      "rowRanges": [[288,428],[452,592],[616,756],[780,920],[944,1084],[1108,1248]],
      "rowsOrganic": [[240,420],[444,624],[648,828],[852,1032],[1056,1236],[1260,1440]],
      "rowsNote": "rows (ads) = 6 x 140 from y288 to y1248; rows (organic) = 6 x 180 from y240 to y1440",
      "centreInGutter": [528,552]
    },
    "1x1": {
      "ev": "E",
      "source": "derived: same 6-col module as 9:16 so assets port 1:1",
      "columns": 6,
      "marginX": 72,
      "gutter": 24,
      "column": 136,
      "columnStarts": [72,232,392,552,712,872],
      "lastColumnEnd": 1008,
      "rows": 6,
      "rowTop": 72,
      "rowBottom": 72,
      "rowGutter": 24,
      "row": 136,
      "rowRanges": [[72,208],[232,368],[392,528],[552,688],[712,848],[872,1008]],
      "centreInGutter": [528,552]
    },
    "4x5": {
      "ev": "E",
      "source": "derived: same 6-col module as 9:16; 180 px rows = 9:16 organic row",
      "columns": 6,
      "marginX": 72,
      "gutter": 24,
      "column": 136,
      "columnStarts": [72,232,392,552,712,872],
      "lastColumnEnd": 1008,
      "rows": 6,
      "rowTop": 75,
      "rowBottom": 75,
      "rowGutter": 24,
      "row": 180,
      "rowRanges": [[75,255],[279,459],[483,663],[687,867],[891,1071],[1095,1275]],
      "centreInGutter": [528,552],
      "nineBySixteenWindow": {"y":[285,1635],"note":"a 4:5 deliverable is the y285-1635 window of a 9:16 master designed to house-safe"}
    }
  },
  "composition": {
    "archetypes": {
      "centre": "… сокращено (ключи: name, axisFamily, definition, when, geometry, density, ev, motion, formats, avoid); полностью — в файле данных",
      "thirds": "… сокращено (ключи: name, axisFamily, definition, when, geometry, density, ev, motion, formats, avoid); полностью — в файле данных",
      "zCorner": "… сокращено (ключи: name, axisFamily, definition, when, geometry, density, ev, motion, formats, avoid); полностью — в файле данных",
      "editorialSplit": "… сокращено (ключи: name, axisFamily, definition, when, geometry, density, ev, motion, formats, avoid); полностью — в файле данных",
      "fullBleed": "… сокращено (ключи: name, axisFamily, definition, when, geometry, density, ev, motion, formats, avoid); полностью — в файле данных",
      "orbit": "… сокращено (ключи: name, axisFamily, definition, when, geometry, density, ev, motion, formats, avoid); полностью — в файле данных",
      "explodedStack": "… сокращено (ключи: name, axisFamily, definition, when, geometry, density, ev, motion, formats, avoid); полностью — в файле данных",
      "macro": "… сокращено (ключи: name, axisFamily, definition, when, geometry, density, ev, motion, formats, avoid); полностью — в файле данных",
      "wall": "… сокращено (ключи: name, axisFamily, definition, when, geometry, density, ev, motion, formats, avoid); полностью — в файле данных"
    },
    "decisionTable": [
      {"beat":"hook","roles":1,"content":"media","use":"fullBleed","alt":["macro"],"avoid":["centre type slate"]},
      {"beat":"hook","roles":1,"content":"object","use":"macro","alt":["fullBleed"],"avoid":["wall"]},
      {"beat":"name/title","roles":1,"content":"type","use":"centre","alt":["editorialSplit (light, reading)"],"avoid":["thirds"]},
      {"beat":"intent (prompt/input)","roles":1,"content":"ui","use":"centre","alt":["editorialSplit (keynote)"],"avoid":["fullBleed"]},
      {"beat":"action (press/click)","roles":1,"content":"object","use":"macro","alt":["centre"],"avoid":["wall","orbit"]},
      {"beat":"result/payoff","roles":1,"content":"media","use":"fullBleed","alt":["centre (framed card)"],"avoid":["editorialSplit with >1 text block"]},
      "… ещё 11 элементов (полный список — в файле данных)"
    ],
    "modifiers": [
      {"if":"the subject has a direction (gaze, motion)","then":"thirds with the subject facing inward; text on the opposite third"},
      {"if":"two roles of equal importance (claim + proof, input + output)","then":"editorialSplit or zCorner; never two centres"},
      {"if":"must-read words > 8 or dense UI","then":"editorialSplit on the light scheme (dark = spectacle, light = reading)"},
      {"if":"the previous frame was a density peak (wall/orbit)","then":"centre or fullBleed with <= 1 line (sparse after dense)"},
      {"if":"3 consecutive centred beats","then":"the next non-type beat uses the film's off-axis family"},
      {"if":"composition axis = keynote-left-axis","then":"editorialSplit (5/7) for every explain beat; centre only for name and end"},
      "… ещё 2 элементов (полный список — в файле данных)"
    ],
    "axisPolicy": {
      "primaryAxis": "centre (x = W/2, y = H/2) or one declared left axis for keynote films",
      "offAxisFamilies": ["zCorner","thirds (incl. lower-left anchor)","editorialSplit","symmetric flanks/triptych"],
      "offAxisFamiliesPerFilm": 1,
      "offAxisEveryBeats": [2,4],
      "centredShareMax": 0.75,
      "ev": "A (AV5 5/5 alternate) + T (client: centre only where ideal)"
    },
    "balance": {"lever":"counter an off-centre mass with a smaller, higher-contrast element farther out on the opposite side (Arnheim)","upperHalfReadsHeavier":true,"check":"blur test on a 25% thumbnail","ev":"I (craft)"},
    "proportion": {"cards":"column/row spans and native media ratios (16:9, 9:16, 1:1, 4:5); never golden-ratio layouts","ev":"I (Markowsky 1992)"},
    "layoutPatterns": {
      "centeredHero": {"heroAnchor":[0.5,0.5],"archetype":"centre"},
      "split": {"landscapeColumns":[0.42,0.58],"portrait":"stack","archetype":"editorialSplit (5/7 = 0,417 / 0,583 — совпадает)"},
      "editorial": {"axis":"leading edge of the safe region (RTL-aware)","archetype":"editorialSplit / keynote-left-axis"},
      "fullBleed": {"contentCoversCanvas":true,"archetype":"fullBleed"},
      "modularGrid": {"gridSource":"active delivery profile","archetype":"wall (bento)"},
      "lowerThird": {"anchor":"lower leading safe corner","archetype":"zCorner (payoff corner)","use":"имя, роль, пояснение поверх действия"},
      "freeform": {"archetype":"orbit / explodedStack / свободная постановка","use":"персонажи, абстракция, коллаж, пространство"},
      "rule": "не совмещать несовместимые схемы; при смене формата сохранить смысл и порядок внимания, позиции пересобрать",
      "ev": "[стартовая настройка] tokens_universal.json (2026-10-08)"
    }
  },
  "density": {
    "maxGroups": 4,
    "maxGroupsIncludesFocal": true,
    "maxTextBlocks": 3,
    "focalPoints": 1,
    "mustReadWordsPerFrameMax": [12,15],
    "frameTypes": {
      "titleBrand": {"elements":[1,3],"textBlocks":[1,2],"negativeSpacePct":[60,85],"mustReadWords":6,"archetypes":["centre","macro"],"colourCardNegativeSpacePctMin":70},
      "keynoteUiPrompt": {"elements":[3,5],"textBlocks":[1,3],"negativeSpacePct":[40,75],"negativeSpaceMedianPct":[45,55],"mustReadWords":15,"controlsMax":5,"archetypes":["centre","editorialSplit","explodedStack"]},
      "collageFanBeforeAfter": {"elements":"1 hero + <= 5 satellites","textBlocks":[0,2],"negativeSpacePct":[30,55],"mustReadWords":8,"archetypes":["orbit","editorialSplit","zCorner","thirds"]},
      "wallGridTunnel": {"elements":[14,150],"textBlocks":[0,1],"negativeSpacePct":[0,10],"mustReadWords":6,"note":"rhythm peak only; never two in a row","archetypes":["wall"]},
      "fullBleedPayoff": {"elements":"1 + <= 1 chrome","textBlocks":[0,1],"negativeSpacePct":null,"mustReadWords":4,"archetypes":["fullBleed"]}
    },
    "densityAxisMapping": {
      "sparse": "upper bound of negativeSpacePct, lower bound of elements",
      "balanced": "median",
      "rich": "lower bound of negativeSpacePct, upper bound of elements",
      "rule": "the density axis moves INSIDE these ranges; it can never exceed maxGroups, maxTextBlocks or mustReadWords"
    },
    "grouping": {
      "innerGapMaxRatioOfOuter": 0.5,
      "labelToChip": [12,16],
      "chipToChip": [16,24],
      "groupToGroup": [48,64],
      "labelToReferentMax": 24,
      "headlineToSubGapEm": [0.25,0.4],
      "commonRegion": "related UI sits in one container",
      "ev": "I (Kubovy 1998 ratio) + E (px values)"
    },
    "complexity": {
      "textAndBrandZones": "low pixel (feature) complexity: scrim or darken media behind type",
      "interestFrom": "arrangement (design complexity), not more objects",
      "test": "JPEG at fixed quality: the text/brand crop is among the lightest crops of the frame",
      "ev": "I (Pieters, Wedel & Batra 2010)"
    },
    "tests": {"blurTestPx":[20,30],"thumbnailPct":25,"filmstripPct":10}
  },
  "hierarchy": {
    "levelsPerFrameMax": 3,
    "adjacentScaleStepMin": 1.333,
    "coPresentLevelStepMin": 2,
    "heroAreaVsNextMin": 2,
    "heroToSatelliteScale": [3,5],
    "ratios": {
      "headlineToMeta": {"value":4,"ev":"A (88/22)"},
      "numberToQualifier": {"value":[2.1,2.3],"ev":"A"},
      "kickerToKeyword": {"value":[1.8,3.8],"ev":"A"},
      "displayToUi": {"value":[3.5,4.5],"ev":"A"},
      "inlineVersionToWord": {"value":[0.69,0.79],"note":"same level (capsule \"4.0\" beside the word)","ev":"A"},
      "qualifierToWord": {"value":[0.2,0.55],"note":"a lower level (word in a pill under the word)","ev":"A"},
      "markHeightToWordCapHeight": {"value":[0.4,0.6],"ev":"A"},
      "scaleJumpAsEmphasisMin": {"value":2.5,"ev":"A"}
    },
    "titleStack": {
      "universal": {"order":"mark -> WORD -> qualifier in a container","wordCapHeightPctH16x9":[11,15],"stackHeightPctH":[27,35],"stackCentreY16x9":[490,540],"groupWidthPctW":[50,83],"gaps":{"markToWord":[30,51],"wordToQualifier":[18,54]},"ev":"A"},
      "higgsfield": {"scope":"higgsfield","word":"Space Grotesk Bold CAPS 170-235 px (cap 118-165), tracking -3% chrome/iridescent ... -6% flat","mark":"squiggle + wordmark 340-470 px wide","qualifier":"capsule / pearl plaque / glossy pill","ev":"A"}
    },
    "readingOrder": ["focal (the thing that will move)","headline (same axis or own column)","support (sub, chips, brand pill)","chrome/meta"],
    "emphasis": {
      "devicesPerFrame": 1,
      "wordsPerDevice": [1,2],
      "neverStack": "accent colour + large + glow on one element",
      "allowedDevices": ["colour/material change","container","material on type","scale jump >= 2.5x","grey tail (2nd clause at 50%)","one-word accent font","object instead of word"],
      "forbidden": ["weight change mid-line","faux italic / faux bold","> 3 accent words per frame"]
    },
    "narrativeTextStylesPerFilmMax": 5
  },
  "typography": {
    "familiesPerFilm": {"narrative":2,"accentMax":1,"accentUse":"one word or one title only","mono":"optional, data/code only","ev":"A + I"},
    "source": "Google Fonts only (licence + web availability); verify family name, axes and script subsets",
    "trackingBySize": {
      "unit": "em (store as %, emit px = em x fontSize for DTCG/AE; AE tracking = em x 1000)",
      "caps": [{"px":[200,9999],"em":[-0.07,-0.03]},{"px":[120,200],"em":[-0.06,-0.03]},{"px":[80,120],"em":[-0.04,-0.02]},{"px":[48,80],"em":[-0.04,-0.02]},{"px":[20,48],"em":[0.04,0.12]}],
      "mixed": [{"px":[200,9999],"em":[-0.08,-0.04]},{"px":[120,200],"em":[-0.04,-0.03]},{"px":[80,120],"em":[-0.04,-0.02]},{"px":[48,80],"em":[-0.02,-0.01]},{"px":[20,48],"em":[-0.02,0]}],
      "opticalSizeCorrection": "display/opsz cuts set tighter: relax 0.01 em when moving a value from a text cut to its display cut",
      "irradiation": "light caps on dark at 96-130 px: relax 0.01 em or one weight step down if counters close",
      "neverBelow": {"px":48,"em":-0.02,"note":"-6% on 43 px merges letters"},
      "ev": "A (archive -2...-6%, median -4%) + I (Bringhurst +5-10% caps small; Andersson dynamic metrics)"
    },
    "lineHeight": {"capsHeadline":[0.88,1],"capsSingleLine":[0.8,0.9],"colourCard":0.96,"mixedDisplay":[1,1.11],"body":[1.3,1.4],"prompt":[1.4,1.55],"log":[1.2,1.65],"subtitle":1.2,"rule":"line height never clips ascenders/descenders"},
    "case": {"capsFor":["names","labels","claims","offers","titles"],"sentenceFor":"voice lines (with full stop)","never":"a CAPS hero and a sentence-case hero in one frame"},
    "lineBreaks": "phrase boundaries only; never orphan an article/adjective from its noun",
    "openType": {"tnum":"every changing number","case":"caps with punctuation","liveTextInAE":"stylistic sets may drop in AE: outline copies or fixed-width boxes"},
    "charsPerLine": {
      "rule": "maxChars = usableWidth / (fontSize x avgCapAdvanceEm)",
      "avgCapAdvanceEm": {"Space Grotesk Bold":0.551,"Inter Display Bold":0.584,"Barlow Condensed":0.421,"Special Gothic Expanded One":0.72},
      "headlineMaxWords": 7,
      "headlineLines": 2,
      "headline16x9CapsCharsAt152px": 20,
      "headline9x16CapsCharsAt96px": [12,14]
    },
    "scriptFallback": {
      "rule": "every typeVoice declares a fallback per script; never set a script the face lacks (no synthetic glyphs)",
      "capHeightMatch": "fallbackSize = size x capHeight(primary) / capHeight(fallback)   e.g. Space Grotesk -> Inter: x 0.70/0.727 = 0.96",
      "scripts": ["Latn","Cyrl","Grek","Jpan","Kore","Hans","Hant","Arab","Deva"],
      "defaults": {"Cyrl":"Inter / Inter Display (same weight)","Grek":"Inter","Jpan":"Noto Sans JP","Kore":"Noto Sans KR","Hans":"Noto Sans SC","Hant":"Noto Sans TC","Arab":"Noto Sans Arabic","Deva":"Noto Sans Devanagari"},
      "ev": "I (Google Fonts subsets) + A"
    },
    "glyphs": "brand glyphs (stars, marks) are vector instances, never typed characters",
    "typeScaleAnchors": {
      "note": "INFORMATIVE reference ranges in px for an Inter-like face (x 0.546 / cap 0.728); validation uses floors (legibility) and ratios (hierarchy), not these ranges",
      "derivation": "base = type.body = round(floorX / xHeight(text face)); steps = base x ratio^k (ratio >= 1.333, by mood); headline = first step whose letter height reaches comfort and whose 18-char line fits the live width; display = hea…",
      "framePairs": "two text levels in ONE frame differ >= 2x: resolve() publishes policy.type.framePairs = every token pair with ratio >= 2 (e.g. display + body, headline + label); with ratio 1.333 the headline pairs with label/ui, not wit…",
      "16x9": {"mega":[300,680],"display":[170,235],"headline":[128,160],"subhead":[88,112],"body":[64,72],"label":[48,64],"caption":[56,64],"ui":[20,36],"code":[28,40]},
      "9x16": {"mega":[360,480],"display":[160,220],"headline":[96,150],"subhead":[72,88],"body":[40,56],"label":[36,44],"caption":[52,60],"ui":[22,36],"code":[28,36]},
      "1x1": {"mega":[280,400],"display":[140,200],"headline":[96,128],"subhead":[64,80],"body":[40,52],"label":[36,40],"caption":[48,56],"ui":[22,32],"code":[26,32]},
      "4x5": {"mega":[300,440],"display":[150,210],"headline":[96,140],"subhead":[64,84],"body":[40,52],"label":[36,40],"caption":[48,56],"ui":[20,32],"code":[26,32]},
      "ev": "A (16:9, 9:16 from Bible scale) + E (1:1, 4:5 derived at the same px/pt as 9:16)"
    },
    "kinetics": "design the settled frame; animated captions are liked but not better understood (Rashid 2008); never deform product names"
  },
  "legibility": {
    "law": "legibility is a LETTER HEIGHT in frame px, not a font size: floor (error below), target (house must-read, warn below), comfort = 2 x floor for the key message of the frame",
    "rationale": "fluent reading starts at an x-height of ~0.2 deg (Legge & Bigelow 2011) at a 32-36 cm phone distance; inset 16:9 feeds sit at that threshold, full-screen phones get the Bible floors (0.18-0.25 deg); comfort ~0.4 deg",
    "formula": {"angleToPx":"letterHeightPx = 2 * d_mm * tan(theta/2) / mmPerFramePx","fontSizePx":"round(letterHeightPx / r_font), never below the absolute floor","r_font":"xHeight/em (mixed case) or capHeight/em (CAPS) of the ACTUAL face"},
    "roles": {
      "type.body / type.headline / type.display": "mixed: floorX; CAPS: floorCap",
      "type.label (CAPS, carries meaning)": "floorCap",
      "type.caption": "subtitle rules (accessibility.subtitles)",
      "type.ui": "absolute floor only (texture)",
      "secondary text": "secondaryX"
    },
    "referenceFaces": {
      "Inter": {"xHeight":0.546,"capHeight":0.728},
      "Space Grotesk": {"xHeight":0.486,"capHeight":0.7},
      "Geist": {"xHeight":0.53,"capHeight":0.71},
      "Archivo": {"xHeight":0.526,"capHeight":0.686},
      "Bricolage Grotesque": {"xHeight":0.517,"capHeight":0.66},
      "Plus Jakarta Sans": {"xHeight":0.536,"capHeight":0.745},
      "Mona Sans": {"xHeight":0.525,"capHeight":0.729},
      "Unbounded": {"xHeight":0.566,"capHeight":0.75},
      "Sofia Sans Extra Condensed": {"xHeight":0.486,"capHeight":0.655},
      "Fraunces": {"xHeight":0.482,"capHeight":0.7},
      "Playfair": {"xHeight":0.414,"capHeight":0.571},
      "Martian Mono": {"xHeight":0.6,"capHeight":0.8},
      "Doto": {"xHeight":0.5,"capHeight":0.7}
    },
    "absoluteFloorPx": 20,
    "absoluteFloorScale": "x shortSide/1080",
    "contexts": {
      "feed16x9": {"format":"16x9","note":"16:9 inside a portrait social feed at x0.2 (X, LinkedIn, Instagram feed). THE binding case for a 16:9 master shipped to social","viewingDistanceMm":340,"mmPerFramePx":0.034,"letterHeightPx":{"floorX":35,"floorCap":35,"targetX":35,"secondaryX":20,"comfortX":70},"angleDeg":{"floorX":0.201,"targetX":0.201,"comfortX":0.401},"interPx":{"floorMixed":64,"floorCaps":48,"targetMixed":64,"secondaryMixed":37,"comfortMixed":128,"comfortCaps":96},"ev":"A+I (Legge & Bigelow 0.2 deg; Bababekova 32-36 cm; Bible: mixed >= 64, CAPS >= 48)"},
      "full16x9": {"format":"16x9","note":"16:9 full-screen, landscape phone","viewingDistanceMm":340,"mmPerFramePx":0.0766,"letterHeightPx":{"floorX":25.5,"floorCap":25.5,"targetX":25.5,"secondaryX":16.4,"comfortX":51},"angleDeg":{"floorX":0.329,"targetX":0.329,"comfortX":0.658},"interPx":{"floorMixed":47,"floorCaps":35,"targetMixed":47,"secondaryMixed":30,"comfortMixed":93,"comfortCaps":70},"ev":"A+I (Bible: >= 47 px; Apple 17 pt at ~2.75 px/pt)"},
      "full9x16": {"format":"9x16","note":"9:16 full-screen phone (Reels/TikTok/Shorts)","viewingDistanceMm":340,"mmPerFramePx":0.0662,"letterHeightPx":{"floorX":22,"floorCap":26,"targetX":26.2,"secondaryX":17.5,"comfortX":44},"angleDeg":{"floorX":0.245,"targetX":0.292,"comfortX":0.491},"interPx":{"floorMixed":40,"floorCaps":36,"targetMixed":48,"secondaryMixed":32,"comfortMixed":81,"comfortCaps":60},"ev":"A (Bible 9:16: must-read >= 40-48 px, captions >= 36-40, subtitles >= 52)","extra":{"headlinePx":[96,150],"subtitlePxMin":52}},
      "feed1x1": {"format":"1x1","note":"1:1 at full feed width on a phone (same px/pt as 9:16)","viewingDistanceMm":340,"mmPerFramePx":0.0662,"letterHeightPx":{"floorX":22,"floorCap":26,"targetX":26.2,"secondaryX":17.5,"comfortX":44},"angleDeg":{"floorX":0.245,"targetX":0.292,"comfortX":0.491},"interPx":{"floorMixed":40,"floorCaps":36,"targetMixed":48,"secondaryMixed":32,"comfortMixed":81,"comfortCaps":60},"ev":"E (same px/pt as 9:16)"},
      "feed4x5": {"format":"4x5","note":"4:5 at full feed width on a phone (same px/pt as 9:16)","viewingDistanceMm":340,"mmPerFramePx":0.0662,"letterHeightPx":{"floorX":22,"floorCap":26,"targetX":26.2,"secondaryX":17.5,"comfortX":44},"angleDeg":{"floorX":0.245,"targetX":0.292,"comfortX":0.491},"interPx":{"floorMixed":40,"floorCaps":36,"targetMixed":48,"secondaryMixed":32,"comfortMixed":81,"comfortCaps":60},"ev":"E (same px/pt as 9:16)"},
      "desktop16x9": {"format":"16x9","note":"16:9 on a 24-inch monitor at 60 cm; the 20 px absolute floor binds first","viewingDistanceMm":600,"mmPerFramePx":0.2766,"letterHeightPx":{"floorX":10.9,"floorCap":14.5,"targetX":10.9,"secondaryX":10.9,"comfortX":21.8},"angleDeg":{"floorX":0.288,"targetX":0.288,"comfortX":0.576},"interPx":{"floorMixed":20,"floorCaps":20,"targetMixed":20,"secondaryMixed":20,"comfortMixed":40,"comfortCaps":30},"ev":"E (never binding next to social contexts)"},
      "tv16x9": {"format":"16x9","note":"16:9 on a 55-inch TV at 2.7 m, or an event screen","viewingDistanceMm":2700,"mmPerFramePx":0.6302,"letterHeightPx":{"floorX":15,"floorCap":15,"targetX":22.9,"secondaryX":15,"comfortX":30},"angleDeg":{"floorX":0.201,"targetX":0.306,"comfortX":0.401},"interPx":{"floorMixed":27,"floorCaps":21,"targetMixed":42,"secondaryMixed":27,"comfortMixed":55,"comfortCaps":41},"ev":"S (BBC subtitle line 7-8% H) + E","extra":{"subtitleLinePctH":[7,8]}}
    },
    "darkSceneUplift": {"transientTextUnder1_5sMinPx":40,"chipsMinPx":24,"socialHeadline16x9MinPx":120,"ev":"I (Piepenbrock 2014; Dobres 2017) + E"},
    "targetRule": "a deliverable passes the strictest context it ships to; a 16:9 master that ships to social must pass feed16x9",
    "effectiveFloor": "floorPx(font, case, ctx) = max(absoluteFloorPx, round(letterHeightPx[ctx] / r_font)); validation tolerance 2%; error below floor, warning below target",
    "worked": {"Inter mixed feed16x9":64,"Inter CAPS feed16x9":48,"Space Grotesk CAPS feed16x9":50,"Inter mixed full9x16 floor / target":[40,48],"Playfair mixed feed16x9 (x 0.414)":85,"Playfair CAPS feed16x9 (cap 0.571)":61},
    "pushedUi": "UI text may be below the floor only if a push brings it to >= mustRead in the approved B-rest state",
    "ev": "I (Legge & Bigelow 2011; Bababekova 2011; BBC) + A + E"
  },
  "reading": {
    "holdFormula": {"expr":"hold_s = max(1.0, 0.35 * words + 0.5)","examples":{"2 words":1.2,"4 words":1.9,"10 words":4},"ev":"E (Brysbaert 238 wpm; BBC 160-180 wpm, 0.3 s/word; +0.5 s to find text after a cut)"},
    "holdFormulaChars": {"expr":"hold_s = max(1.0, chars / cpsDesign[script] + 0.5)","use":"scripts without word spaces (Jpan, Hans, Hant) or when words are long"},
    "cpsSubtitleMax": {"Latn/en":20,"Arab":20,"Kore":12,"Hans":9,"Jpan":4,"otherDefault":17,"ev":"S (Netflix Timed Text Style Guides, adult; Jpan subtitles 4 cps)"},
    "cpsDesign": {"Latn":15,"Arab":15,"Kore":9,"Hans":6.75,"Jpan":3,"other":12.75,"rule":"designed on-screen text = 0.75 x subtitle maximum (competes with imagery)","ev":"E"},
    "typing": {"maxCps":20,"verbatimCps":15,"perFrameMax24fps":1,"holdAfterLastCharS":0.5,"countsAsReading":true,"ev":"E (Netflix 20 cps direction)"},
    "absoluteMinFrames": 20,
    "subtitleEventMaxS": 7,
    "assemblyMaxS": 0.6,
    "overMovingImagery": {"holdMultiplier":1.3,"alternatives":["freeze/slow the plate during the hold","scrim 40-70%"],"ev":"I (Vital 2022) + E"},
    "mustReadWordsPerFrame": [12,15],
    "headlineWords": [2,7],
    "overflowRule": "if the copy does not fit, split it across frames; never shrink below the legibility floor",
    "voDuplication": "design text uses keywords, not the VO transcript (Mayer redundancy); subtitles are a separate accessibility layer",
    "finalRule": "hold_ms = max(1000, 350 · words + 500) × k (k = 1 по умолчанию; 1,2–1,5 для чисел, данных и терминов; × 1,3 поверх движущегося изображения). Вариант tokens_universal max(1200, (500 + 300 · words) · k) — консервативный по…",
    "complexityK": {"default":1,"numbersOrData":1.3,"newTerms":1.2,"ev":"[стартовая настройка] tokens_universal.json (2026-10-08)"},
    "typingCpsDefault": 15,
    "afterTypingHoldMs": {"ours":500,"tokensUniversal":600,"use":500},
    "unreadableAppearanceDoesNotCount": true,
    "decorativeFastTextNotStretched": true,
    "helper": "HFT.readTime(text, {script, k, typing, overImagery, fps})"
  },
  "focalContinuity": {
    "law": "the next frame's focal point starts within 9% of the frame diagonal of the previous focal point, or at the format's focal home",
    "preferredPctDiag": 9.08,
    "maxUncuedPctDiag": 21.79,
    "byFormat": {
      "16x9": {"diagonal":2203,"preferredPx":200,"maxUncuedPx":480},
      "9x16": {"diagonal":2203,"preferredPx":200,"maxUncuedPx":480},
      "1x1": {"diagonal":1527,"preferredPx":139,"maxUncuedPx":333},
      "4x5": {"diagonal":1729,"preferredPx":157,"maxUncuedPx":377}
    },
    "home": {"16x9":[960,540],"9x16":{"ads":[540,760],"organic":[540,840]},"1x1":[540,540],"4x5":[540,660]},
    "cueTypes": ["motion toward the new position before the cut","character gaze","cursor travel","light sweep / wipe edge pointing to B focal","zoom out-then-in"],
    "cutOnMotionOnset": true,
    "afterHardCut": "focal in the middle third of the frame (centre bias peaks after a cut)",
    "persistentAnchor": "at least one element survives every cut at identical coordinates (check with a 50% overlay)",
    "polarityFlipAccentDelayS": 0.3,
    "oneFastMoverPerBeat": true,
    "peripheryDriftPxPerS": [8,16],
    "ev": "I (Smith 2012 cueing; Tseng 2009; Smith & Henderson 2008) + E (px thresholds)"
  },
  "rhythm": {
    "formula": {"framesPerBeat":"fps * 60 / bpm","framesPerBar4_4":"4 * fps * 60 / bpm","beatSeconds":"60 / bpm"},
    "rule": "pick fps first (native fps of the footage/generations), then a BPM that gives an integer (ideally even) frames-per-beat; record both in the passport before production",
    "recommendedPairs": [
      {"fps":24,"bpm":120,"framesPerBeat":12,"note":"house default; most AI video is 24 fps"},
      {"fps":24,"bpm":90,"framesPerBeat":16,"note":"calm / luxury"},
      {"fps":24,"bpm":144,"framesPerBeat":10,"note":"energetic"},
      {"fps":25,"bpm":125,"framesPerBeat":12,"note":"PAL / platforms requiring 25"},
      {"fps":25,"bpm":100,"framesPerBeat":15,"note":"calm (odd frames per beat: eighths fall between frames)"},
      {"fps":30,"bpm":120,"framesPerBeat":15,"note":"UI films; eighth notes fall between frames: cut on beats only"},
      "… ещё 3 элементов (полный список — в файле данных)"
    ],
    "avoid": [{"fps":25,"bpm":120,"why":"12.5 frames per beat: cuts cannot land on every beat"},{"fps":30,"bpm":128,"why":"14.06 frames per beat"},{"mix":"24 and 30 fps sources in one comp","why":"judder"}],
    "integerTempoTable": {
      "24": "… сокращено (ключи: msPerFrame, integerBeatTempos); полностью — в файле данных",
      "25": {"msPerFrame":40,"integerBeatTempos":[{"bpm":60,"framesPerBeat":25,"framesPerEighth":null,"framesPerBar4_4":100},{"bpm":75,"framesPerBeat":20,"framesPerEighth":10,"framesPerBar4_4":80},{"bpm":100,"framesPerBeat":15,"framesPerEighth":null,"framesPerBar4_4":60},{"bpm":125,"framesPerBeat":12,"framesPerEighth":6,"framesPerBar4_4":48},{"bpm":150,"framesPerBeat":10,"framesPerEighth":5,"framesPerBar4_4":40}]},
      "30": "… сокращено (ключи: msPerFrame, integerBeatTempos); полностью — в файле данных",
      "60": "… сокращено (ключи: msPerFrame, integerBeatTempos); полностью — в файле данных"
    },
    "cutPhrasing": {"rule":"vary shot lengths in phrases, not a metronome","examplePhraseBeats":[2,2,1,1,4],"ev":"I (Cutting 2010, 1/f-like shot lengths) + E"},
    "syncPolicy": "cuts and graphic hits on beats / bar lines; the single action (press) on the strongest accent; craft norm, not a proven lever (Lipscomb 2013)",
    "beatDurations": {"graphicBeatS":[1.5,3],"heroOrDataBeatS":[3,4],"logoBeatS":[2,3]},
    "durations": {
      "chipPop": {"seconds":[0.24,0.32],"note":"chip / sparkle / badge pop","ev":"E","frames":{"24":[6,8],"25":[6,8],"30":[7,10],"60":[14,19]}},
      "cardSlide200to400px": {"seconds":[0.4,0.56],"note":"card slide of 200-400 px (scale with distance: +40 ms per +100 px)","ev":"E","frames":{"24":[10,13],"25":[10,14],"30":[12,17],"60":[24,34]}},
      "headlineMaskUp": {"seconds":[0.48,0.72],"note":"one headline line rising out of its mask","ev":"E","frames":{"24":[12,17],"25":[12,18],"30":[14,22],"60":[29,43]}},
      "heroReveal": {"seconds":[0.7,1.2],"note":"hero reveal / scale-in","ev":"E","frames":{"24":[17,29],"25":[18,30],"30":[21,36],"60":[42,72]}},
      "frameAssemblyMax": {"seconds":0.6,"note":"a frame finishes assembling within 0.6 s, then holds","ev":"A","frames":{"24":14,"25":15,"30":18,"60":36}},
      "cameraPush": {"seconds":[1,2],"note":"camera push / pull / pan through UI","ev":"E","frames":{"24":[24,48],"25":[25,50],"30":[30,60],"60":[60,120]}},
      "exit": {"seconds":[0.2,0.3],"note":"exits: 50-100 ms shorter than the matching entrance","ev":"I","frames":{"24":[5,7],"25":[5,8],"30":[6,9],"60":[12,18]}},
      "cursorTravel600to1200px": {"seconds":[0.5,0.9],"note":"bell-shaped speed (minimum jerk)","ev":"I","frames":{"24":[12,22],"25":[13,23],"30":[15,27],"60":[30,54]}},
      "cursorDwellBeforeClick": {"seconds":[0.15,0.25],"note":"","ev":"E","frames":{"24":[4,6],"25":[4,6],"30":[5,8],"60":[9,15]}},
      "cursorPress": {"seconds":0.1,"note":"press: cursor scale 0.85, target dips to 0.94","ev":"E","frames":{"24":2,"25":3,"30":3,"60":6}},
      "cursorRelease": {"seconds":0.22,"note":"","ev":"E","frames":{"24":5,"25":6,"30":7,"60":13}},
      "clickRipple": {"seconds":[0.4,0.5],"note":"","ev":"E","frames":{"24":[10,12],"25":[10,13],"30":[12,15],"60":[24,30]}},
      "accentHitMin": {"seconds":0.16,"note":"any full-colour flash / hit lasts >= 4 frames at 24-25 fps","ev":"E","frames":{"24":4,"25":4,"30":5,"60":10}},
      "lightSweep": {"seconds":[0.5,0.75],"note":"30-45 deg band across a lockup (12-18 f @24)","ev":"E","frames":{"24":[12,18],"25":[13,19],"30":[15,23],"60":[30,45]}},
      "signatureSweep": {"seconds":[0.75,1],"note":"brand signature sweep (18-24 f @24)","ev":"A","frames":{"24":[18,24],"25":[19,25],"30":[23,30],"60":[45,60]}},
      "whipBlur": {"seconds":[0.167,0.333],"note":"whip-pan blur, 4-8 f @24","ev":"I","frames":{"24":[4,8],"25":[4,8],"30":[5,10],"60":[10,20]}},
      "maskWipe": {"seconds":[0.5,0.75],"note":"mask / wipe across the frame","ev":"E","frames":{"24":[12,18],"25":[13,19],"30":[15,23],"60":[30,45]}},
      "morph": {"seconds":[0.5,1],"note":"shape morph inside one radius family","ev":"E","frames":{"24":[12,24],"25":[13,25],"30":[15,30],"60":[30,60]}},
      "freezeDim": {"seconds":[0.25,0.5],"note":"freeze, dim to 40%, then claim","ev":"E","frames":{"24":[6,12],"25":[6,13],"30":[8,15],"60":[15,30]}},
      "textOnScreenMin": {"seconds":null,"note":"any text is on screen >= 20 frames (Netflix TTSG)","ev":"S","frames":{"24":20,"25":20,"30":20,"60":20}},
      "endCardMin": {"seconds":2,"note":"designed end card held >= 2 s","ev":"A","frames":{"24":48,"25":50,"30":60,"60":120}},
      "finalLockupMin": {"seconds":1.5,"note":"final held brand lockup (preferred 2 s)","ev":"I","frames":{"24":36,"25":38,"30":45,"60":90}},
      "generationHold": {"seconds":[1.5,3],"note":"hold for generated / footage media","ev":"E","frames":{"24":[36,72],"25":[38,75],"30":[45,90],"60":[90,180]}},
      "heroRevealHoldMin": {"seconds":2,"note":"hero payoff held >= 2 s","ev":"E","frames":{"24":48,"25":50,"30":60,"60":120}},
      "photoBurst": {"seconds":[0.4,0.45],"note":"photo bursts in series of 2-3 (wide, mid, close)","ev":"A","frames":{"24":[10,11],"25":[10,11],"30":[12,14],"60":[24,27]}}
    },
    "durationScaling": {
      "m": "m = 2^((0.5 - energy) x 1.2) x durMul(personality), clamped to [0.5, 1.8]",
      "energyRange": [0,1],
      "tokenBounds": {"dur.chip":{"base":0.28,"min":"max(5 f, 0.2 s)","max":0.6},"dur.ui":{"base":0.4,"min":"max(5 f, 0.2 s)","max":0.9},"dur.headline":{"base":0.6,"min":0.4,"max":1.2},"dur.hero":{"base":0.95,"min":0.6,"max":2},"dur.camera":{"base":1.5,"min":1,"max":3},"dur.exit":{"base":"min(0.25 x m, dur.ui - 2 f)","min":"5 f","max":0.5}},
      "quantise": "frames = round(s x fps), then s = frames / fps (times are always whole frames)",
      "rule": "personalities scale motion durations only; reading holds, text minimums (20 f), accent hits (>= 4 f) and flash limits are never scaled",
      "exitShorterThanEnterMs": [50,100]
    },
    "stagger": {
      "cascadeFormula": "cascade = clamp(round(3 x m x staggerMul), 1, 8) frames",
      "cascadeFrames24Default": [2,4],
      "separateEventsFrames": "max(6, 2 x cascade)",
      "line2Delay": "cascade + 1 (default 3-4 f)",
      "accentAfterTextFrames24": [4,6],
      "followThrough": "2-4 x cascade (default 6-12 f)",
      "readsAs": {"<= 4 f":"one cascade",">= 6 f":"separate events (use deliberately, e.g. luxury)"},
      "rule": "one group = one direction, one easing, one beat; different groups on different beats",
      "ev": "A (AV5 P2 expo-out 0.6 s, stagger 2-4 f) + I (Heer & Robertson 2007)"
    },
    "overshoot": {
      "maxScaleHard": 0.12,
      "maxScaleDefault": 0.08,
      "allowedOn": ["chips","pills","sparkles","stickers","small cards"],
      "never": ["logo","headline","product name","hero media"],
      "expressiveMomentsPer30s": {"default":3,"hardMax":6},
      "byPersonality": {"productive":0,"expressive":0.06,"luxury-slow":0,"playful-bouncy":0.12,"cinematic":0,"glitch-tech":0},
      "ev": "A (Bible 5-8%, <= 3 per 30 s as the default) + E (playful ceiling)"
    },
    "easingShape": {
      "enter": "lands softly: end slope (1 - y2) / (1 - x2) <= 0.5",
      "exit": "leaves softly: start slope y1 / x1 <= 0.5",
      "move": "soft at both ends",
      "camera": "symmetric in-out",
      "bounds": "x1, x2 in [0, 1]; y may leave [0, 1] (overshoot / anticipation) only within the overshoot cap",
      "steps": "stepped easing (glitch) allowed: steps(n), n 2-6"
    },
    "tempoFromEnergy": {
      "framesPerBeat": "round(15 - 6 x energy) at 24 fps-equivalent; BPM = 60 x fps / framesPerBeat (BPM may be fractional; frames per beat never are)",
      "examples24fps": {"technical (0.55)":[12,120],"luxury (0.15)":[14,102.86],"energetic (0.9)":[10,144]}
    },
    "motionBlurShutterDeg": 180,
    "twinkleMaxHz": 3
  },
  "narrative": {
    "universalSpine": {
      "value": "COVER/HOOK -> NAME -> MECHANIC (intent -> action) -> RESULT -> PROOF -> [mechanic/result 2-4x] -> END CARD (mirror of cover)",
      "ev": "A",
      "scope": "universal",
      "hfInstance": "COVER -> HOOK -> PRODUCT MECHANIC (prompt -> Generate ✦ n) -> GENERATION -> NUMBER PROOF -> ... -> END CARD"
    },
    "beatUnit": "one beat = one VO line = one key frame (A/B/C states)",
    "medianBeats": {"15s":7,"30s":13,"60s":[15,22]},
    "runtimeShares": {"openAndName":[10,15],"intent":[8,12],"demoOrAgentUi":[20,40],"generationOrAction":[10,15],"resultsAndProof":[20,30],"ctaAndEnd":[10,20],"ev":"A (AV1 rows) + I (Teixeira: last 15-20% held lockup)"},
    "firstSeconds": {"surpriseBy":2,"productOrPropositionBy":3,"brandMarkBy":5,"ev":"S (TikTok 2025, Google ABCD vendor guidance)"},
    "frame01": "never a logo slate",
    "proofEveryBeats": [2,3],
    "sparseDenseAlternation": "alternate every 1-2 cuts; after a wall/peak always a one-line frame",
    "densityRampBeforePayoff": "accelerate counts/cuts, then cut to one full-bleed result",
    "polarity": {"flipAt":["act boundary","chapter schedule every 5-6 s","key beat"],"never":"mid-shot","via":["maskWipe","flash","dip"],"ev":"A + I (Cutting 2016, analogy)"},
    "brandPulses": {"count":[2,4],"maxSeconds":1,"position":"off-centre","window":"first 80% of runtime","finalLockup":{"lastPct":[15,20],"minSeconds":[1.5,2]},"ev":"I (Teixeira, Wedel & Pieters 2010; TV data) -> E on social"},
    "bookend": "end card mirrors the cover (same object or lockup, larger): a goal, not an observed invariant",
    "triads": "3 features, 3 corner captions, 3 hooks read as complete",
    "templates": {
      "6s": "… сокращено (ключи: use, beats, totalWordsMax, genres); полностью — в файле данных",
      "15s": "… сокращено (ключи: use, beats, totalWordsMax, genres); полностью — в файле данных",
      "30s": "… сокращено (ключи: use, beats, totalWordsMax, genres); полностью — в файле данных",
      "60s": "… сокращено (ключи: use, beats, totalWordsMax, genres); полностью — в файле данных"
    },
    "templateRules": [
      "Windows are seconds on a 120 BPM grid (0.5 s = 1 beat). At another tempo, keep the beat counts and recompute seconds.",
      "Every window must hold its text: dur >= assembly (<= 0.6 s) + max(1.0, 0.35 w + 0.5). mustReadWordsMax = min(roleWordCap, timeWordCap); copy over budget is split across beats, never shrunk.",
      "Action beats (1 s) carry only a UI label (texture), never must-read copy.",
      "In templates < 20 s, CTA and end card merge into one held lockup.",
      "A beat role may be swapped for another of the same function (proof <-> scale) but never removed: hook, name, result, end are mandatory in all lengths."
    ],
    "weighted": {
      "changeAndResult": "… сокращено (ключи: purposeRu, suitableGenres, beats, fixedDuration, noteRu); полностью — в файле данных",
      "explainInSteps": "… сокращено (ключи: purposeRu, suitableGenres, beats, fixedDuration, noteRu); полностью — в файле данных",
      "questionEvidenceConclusion": "… сокращено (ключи: purposeRu, suitableGenres, beats, fixedDuration, noteRu); полностью — в файле данных",
      "themeVariationReturn": "… сокращено (ключи: purposeRu, suitableGenres, beats, fixedDuration, noteRu); полностью — в файле данных",
      "parallelComparison": "… сокращено (ключи: purposeRu, suitableGenres, beats, fixedDuration, noteRu); полностью — в файле данных",
      "modularSequence": "… сокращено (ключи: purposeRu, suitableGenres, beats, fixedDuration, noteRu); полностью — в файле данных"
    },
    "helper": "HFT.timeline(id, durationMs, fps, bpm?) — веса → кадры с накопленным округлением; с bpm — привязка границ к долям"
  },
  "transitions": {
    "countRule": {"maxCountedTypesPerFilm":2,"notCounted":["hardCut","the brand signature transition (declared in brands.*)"],"whipMaxPerFilm":1,"ev":"A + I (Uber Base, Carbon)"},
    "grammar": {
      "hardCut": {"duration":"0 f","allowedWhen":"always; on a beat or on motion onset; next focal within 9% diag or at focal home","counts":false},
      "matchCut": {"duration":"0 f (+2-4 f motion continuation)","allowedWhen":"last frame of A and first frame of B share a silhouette (size within +/-10%) at a position within 9% diag; verify with a 50% overlay","default":true,"counts":true},
      "push": {"aka":"zoomThrough","duration":[1,2],"ease":"camera","allowedWhen":"B is literally contained in A (card, screen, window): scale = W_frame / W_container, aspect preserved; source headroom >= scale","forbiddenWhen":"B is unrelated to the container; scale > 4.6 without a separately rendered target","counts":true},
      "pullBack": {"duration":[1,2],"ease":"camera","allowedWhen":"the film's single motivated reverse: one -> many, or the deliverables reveal; max 2.6x","counts":"as part of push family"},
      "maskWipe": {"duration":[0.5,0.75],"ease":"move","allowedWhen":"reveal within an act; before -> after on the same position; polarity flip at an act boundary","geometry":"bar 6% W (120 px @1920) or a 25-35 deg divider with a handle; leading edge points at B focal","counts":true},
      "lightSweep": {"duration":[0.5,0.75],"allowedWhen":"across a lockup, pill or end card as a brand gesture","geometry":"30-45 deg band, accent -> transparent, Screen/Add","counts":"not counted only if it is the declared signature"},
      "flash": {"duration":">= 4 f @24-25 (>= 160 ms)","allowedWhen":"on a strong beat at an act/chapter boundary or a polarity flip; as the press impact","forbiddenWhen":"> 3 flashes in any 1 s; saturated red flashes; flash area > 25% of a 10 deg field when frequent","counts":true},
      "whip": {"duration":[0.167,0.333],"allowedWhen":"max once per film; target lands at frame centre; with a whoosh","forbiddenWhen":"a second whip; B focal off-centre; reading frame right after","counts":true,"why":"whip pans scatter gaze (Smith 2012)"},
      "morph": {"duration":[0.5,1],"ease":"move","allowedWhen":"A and B are the same object class inside one radius family (pill -> card -> frame) or a semantically linked shape (orb -> pill -> chip)","counts":true},
      "freezeDim": {"duration":[0.25,0.5],"allowedWhen":"emphasis on a payoff: freeze, dim to 40%, then the claim","counts":true},
      "dip": {"duration":[0.25,0.5],"allowedWhen":"chapter boundary (dip to ground colour)","counts":true},
      "crossDissolve": {"duration":[0.5,0.75],"allowedWhen":"luxury-slow / cinematic personalities: between plates of the same act; otherwise only time passing inside one plate","forbiddenWhen":"between UI states or onto type","counts":true},
      "pop": {"duration":[0.24,0.32],"allowedWhen":"playful personality: B elements pop in on the cut (scale 0.8 -> 1 with overshoot <= cap)","forbiddenWhen":"logo, headline, product name","counts":true},
      "slice": {"duration":[0.08,0.25],"allowedWhen":"glitch-tech personality: 2-6 horizontal slices displaced for 2-6 frames on a beat","forbiddenWhen":"more than 3 per second (flash rule); over must-read text","counts":true}
    },
    "decisionTable": [
      {"relation":"same object, same position","use":["matchCut","hardCut"]},
      {"relation":"B is inside A (container -> content)","use":["push"]},
      {"relation":"B is many of A","use":["pullBack","morph (scale-down into a slot)"]},
      {"relation":"same position, changed state (before -> after)","use":["maskWipe","morph"]},
      {"relation":"new scene, same act, focal within 9% diag","use":["hardCut on beat or motion onset"]},
      {"relation":"new scene, focal > 22% diag away","use":["cue then hardCut","whip (if unused)","zoom out-then-in"]},
      "… ещё 3 элементов (полный список — в файле данных)"
    ],
    "continuityDevicePerFilmMin": 1,
    "continuityDevices": ["persistent object","fixed chrome","travelling object (morphs across cuts)","dashed next-shot crop","zoom-through","radius-family morph","type-on -> slot","blur -> CTA","clean plate between type frames"]
  },
  "camera": {
    "rules": {
      "dominantVerbsPerFilm": 1,
      "motivatedReverseMax": 1,
      "ease": [0.65,0,0.35,1],
      "landOn": ["frame centre","a third line"],
      "longJump": "zoom out, then in (van Wijk & Nuij 2003, rho ~ 1.42), never a flat pan across far regions",
      "textAfterZoomPx16x9": [60,120],
      "motionBlurShutterDeg": 180,
      "ev": "A + I"
    },
    "verbs": {
      "static": {"use":"type-led and reading frames; default","params":{}},
      "drift": {"use":"keep plates alive","params":{"pxPerS":[8,16],"scalePerBeat":[1,1.03],"overscanPct":[101,111]}},
      "pushIn": {"use":"focus, enter UI, reveal detail","params":{"scale":[1.14,4.6],"readableUiScale":[1.35,2.4],"macroScale":[2.6,4.6],"durS":[1,2],"headroom":"source width >= frame width x max scale"}},
      "pullBack": {"use":"one -> many, deliverables reveal (the one reverse)","params":{"scaleMax":2.6,"durS":[1,2]}},
      "truck": {"use":"lateral reveal along a row; parallax showcase","params":{"midPlanePxPerS16x9":[120,240],"parallaxRatios":[0.5,1,1.3]},"ev":"E"},
      "pedestal": {"use":"vertical reveal (9:16 stacks)","params":{"midPlanePxPerS9x16":[120,240]},"ev":"E"},
      "orbit": {"use":"object or exploded stack; 3D scenes","params":{"arcDeg":[15,30],"durS":[2,4],"fovDeg":[24,35],"fovDefault":28},"ev":"E (three3d: 25 deg arc, FOV 28)"},
      "zoomThrough": {"use":"push where the container exactly fills the frame","params":{"scale":"W_frame / W_container"}},
      "rackFocus": {"use":"move attention between depth planes in 3D/2.5D","params":{"durFrames24":[12,24]},"rule":"type is never out of focus at rest"},
      "whip": {"use":"single energetic jump","params":{"blurFrames24":[4,8],"maxPerFilm":1}}
    },
    "speedByPersonality": "motion personality sets cameraSpeed in [0.6, 1.6]; magnitude limits above never change",
    "headroomTable": [{"push":"<= 1.1","sourceWidthMin16x9":2112},{"push":"1.1-1.5","sourceWidthMin16x9":[2112,2880]},{"push":"> 1.5","sourceWidthMin16x9":">= 2880 or a separately rendered target frame"}]
  },
  "depth": {
    "planes": [
      {"z":0,"id":"ground","layer":"00_BG","parallax":0,"blurPx":0,"opacity":1,"overscanPct":[110,120],"content":"scene ground colour / texture"},
      {"z":1,"id":"atmosphere","layer":"01_ATMOS","parallax":0.25,"blurPx":[200,600],"opacity":[0.06,0.6],"overscanPct":[110,120],"content":"glow pools, blooms, vignette, texture grid"},
      {"z":2,"id":"far","layer":"02_FAR","parallax":0.5,"scale":[0.6,0.9],"blurPx":[2,8],"blurPxBackgroundUi":[12,24],"opacity":[0.28,0.6],"shadow":null,"content":"far cards, blurred source plate (40-80 px, 35%)"},
      {"z":3,"id":"hero","layer":"03_HERO","parallax":1,"scale":1,"blurPx":0,"opacity":1,"shadow":"shadow.mid","overscanPct":[101,111],"content":"hero media/object + its mask"},
      {"z":4,"id":"near","layer":"04_NEAR_UI","parallax":1.3,"scale":[1.05,1.3],"blurPx":[0,4],"opacity":1,"shadow":"shadow.near","content":"near UI cards, chips (farthest near chip may take 2-4 px)"},
      {"z":5,"id":"type","layer":"05_TYPE","parallax":1,"blurPx":0,"content":"live text, one line per layer; never blurred, never in DOF"},
      "… ещё 4 элементов (полный список — в файле данных)"
    ],
    "tiersMax": 3,
    "tiersNote": "far / hero / near (+ ground, atmosphere, overlays)",
    "shadowByTier": {"mid":{"y":9,"blur":20,"alpha":0.09},"near":{"y":18,"blur":35,"alpha":0.17},"rule":"offset and blur roughly double from mid to near; one light direction (top or top-left)"},
    "overscanRule": "overscan_pct >= 100 + 200 * parallax * maxDriftPx / frameWidth",
    "dof": {
      "neverOnText": true,
      "blurGrowsWith": "|z - zFocus|",
      "twoD": {"farPx":[2,8],"backgroundUiPx":[12,24],"satelliteIconsPx":24,"plateBehindModalPx":[40,80]},
      "threeD": {"maxCocPxAt1080":34,"maxCocPctH":3.1,"nearFarAsymmetry":"near blur stronger than far (three3d near 440 / far 680 scale)","focusPull":"rack focus 12-24 f"},
      "ev": "I (Kosara 2001 semantic DOF) + E"
    },
    "perspective": {"tiltDegMax":12,"vanishingDirections":1,"overlapPx":[30,100],"stickerOverlapPx":[30,60],"fovDeg3D":[24,35],"fovDefault3D":28},
    "threeD": {
      "taste": "simple modern materials; no detailed old-fashioned 3D, no device renders, no hardware frames",
      "tonemap": "hue-preserving neutral shoulder (ACES shifts saturated accents)",
      "bloom": {"threshold":1.15,"strength":[0.15,0.3]},
      "ev": "T + E (three3d)"
    }
  },
  "color": {
    "areaBudget": {
      "neutralsPct": [85,95],
      "accentPrimaryMin": 0,
      "salienceWeight": "weight = sqrt(|Lc(action, bg)| / 96) x (0.75 + 0.25 x sqrt(C / 0.222)); x1.2 if H in [320, 40] or [250, 300] (H-K); clamp 0.5-1.6; ext = clamp(1 / weight, 0.6, 1.2)",
      "byMood": {"calm":{"target":3,"max":6,"objects":1,"echoes":0,"secondaryMax":0},"luxury":{"target":2,"max":4,"objects":1,"echoes":0,"secondaryMax":0},"energetic":{"target":7,"max":12,"objects":1,"echoes":2,"secondaryMax":5},"playful":{"target":8,"max":14,"objects":2,"echoes":1,"secondaryMax":6},"technical":{"target":4,"max":8,"objects":1,"echoes":1,"secondaryMax":3},"editorial":{"target":3,"max":6,"objects":1,"echoes":1,"secondaryMax":0}},
      "formula": "targetPct = moodTarget x ext; maxPct = moodMax x ext",
      "caps": {"fillOnlyOnLightPctMax":8,"hardCeilingPct":18,"secondaryPctMax":6,"secondaryHeroFeaturePctMax":15},
      "singleAccentIdentityDefault": {"target":4,"max":8,"objects":1,"echoes":1,"note":"neon accent on near-black (weight 1.0); = the Higgsfield archive norm"},
      "floodException": "a full-frame accent flood: energetic / playful <= 1 per 15 s (bumpers); other moods only on the end card",
      "appliesTo": "the accent fill and its text (glow pools are not counted)",
      "ev": "A (archive <= 8%) + I (Itten contrast of extension; High 2023 H-K) + E (weights, moods; reconciled with DERIVE.md section 5)"
    },
    "accentCounting": {
      "rule": "accent objects and echoes per frame follow the mood (default 1 object + 1 echo; never more than 2 + 2); the FOCAL point is still one",
      "object": "a connected accent element with its own glow",
      "setOfIdenticalChips": "one object",
      "echo": "a smaller element with the same meaning (line 2, progress bar, active subtitle word)",
      "notCounted": ["typing caret","accent tokens inside UI text","accent inside the generated media"]
    },
    "secondAccent": {"perFilm":1,"meaningsPerColour":1,"hueDistanceMinDeg":90,"neverOn":["logo","primary CTA","brand glyph"],"stateHueSeparationDeg":35,"ev":"E"},
    "helmholtzKohlrausch": {"rule":"magenta/blue/red accents read brighter than their L: give them 20-30% less area than an equal-L cyan/yellow-green","ev":"I (High 2023; Corney 2009) + E"},
    "gradients": {
      "space": "OKLCH (or OKLab); never sRGB for hue-to-hue",
      "midpointRule": "a gradient between two hues is allowed only if its OKLCH midpoint hue is within 30 deg of a palette hue or its chroma < 0.05; otherwise separate the hues spatially with a neutral",
      "bandingCodesMin": 20,
      "darkGradientDither": {"sigmaPct":[1,1.5],"grainPx":[1,2]},
      "ev": "I (Ottosson 2020; Tandon 2021) + E"
    },
    "polarity": {"dark":"spectacle: hero media, one headline, glowing accents","light":"reading: dense UI, prompts, multi-line text","ev":"I (Piepenbrock 2013-14)"},
    "lightScene": {
      "accentWithContrastBelow": 3,
      "thenAccentIs": "fill only (never text, never stroke < 12 px)",
      "glow": "additive glow clips on light grounds: use a coloured soft shadow (y 12, blur 40, 25-35%)",
      "cardOnPaper": "ink shadow 6-14%, blur 48-96, y 16-32 + 1 px stroke (a white card alone is 1.11:1)"
    },
    "neutralsNearAccent": {"rule":"greys adjacent to a large accent area take chroma 0.006-0.008 at the accent hue (simultaneous contrast)","ev":"I (Albers) + E"},
    "luma": {
      "rec709FloorY": 32,
      "distinctFromGroundDeltaYMin": 7,
      "colouredTextMinPx": 40,
      "colouredStrokeMinPx": [3,4],
      "accentStrokeMinPx": 2,
      "lowLumaDeltaText": {"deltaYBelow":60,"thenMinPx":64,"weight":"bold"},
      "why": "4:2:0 chroma subsampling: edges must be carried by luma",
      "ev": "S (BT.709) + E"
    },
    "light": {
      "modelsPerFilm": 1,
      "keyDirection": "top or top-left (azimuth -45..0 deg from vertical)",
      "perFrameMin": "one light source + one tactile object, unless material axis = flat or the frame is full-bleed media",
      "emitter": "hot core (L 0.98) + multi-scale halo (blur 4/12/32/96/240, gain 0.8/0.5/0.3/0.18/0.10); background 200 px from the source <= OKLCH L 0.30",
      "linearVsGamma": "cut glow gain 2-3x in linear-light comps",
      "ev": "I (Spencer 1995; Jimenez 2014) + E"
    },
    "glass": {"onlyOver":"imagery (never over a flat ground)","neverGlassOnGlass":true,"maxPerFrame":2,"smallTextScrimPct":[20,30],"ev":"I (Apple Liquid Glass; NN/g)"},
    "grain": {"onUi":false,"lightScenePctMax":5,"insidePlates":"allowed","ornamentKits":"halftone / dot screens only as the film's ornament kit"},
    "successiveContrast": "after a dark -> light cut the paper reads brighter and the accent dimmer for ~6-10 frames: introduce the key accent ~0.3 s after the cut",
    "hfInstance": {"scope":"higgsfield","accent":"#D1FE17 lime = Higgsfield acts; <= 8% (10%); never text or thin line on light grounds (1.06-1.17:1)","second":"magenta #ED1572 / pink #FF005B / lilac #E571FF, one per film"}
  },
  "accessibility": {
    "contrast": {
      "standards": ["WCAG 2.x (normative)","APCA (draft)"],
      "policy": "check both; the stricter verdict wins",
      "roles": "… сокращено (ключи: fg.primary on bg.base, bg.raised, bg.overlay, fg.muted on bg.base, bg.raised, fg.subtle on bg.base, accent.text, accent.secondaryText, state.* on bg.base, fg.onAccent on accent.action, accent.action, line.focus (non-text) on bg.base, fg.inverse on bg.inverse); полностью — в файле данных",
      "severity": "below floor = error; between floor and target = warning (on the role's primary surface)",
      "archiveNote": "Higgsfield keeps its archive grey #A2A2A2 on #131313 (7.3:1, Lc 51) as a brand override: it passes the dark muted floor (Lc 50), not the target (Lc 60)",
      "overImagery": "sample the worst pixel behind the glyphs; if below target add a scrim of the ground colour at 40-70%",
      "videoMargin": "keep a margin above minimums: compression and phone screens reduce contrast",
      "ev": "S (WCAG 2.2 1.4.3, 1.4.11; APCA Bronze)"
    },
    "flash": {
      "maxFlashesPerSecond": 3,
      "flashDefinition": "a pair of opposing luminance changes of >= 10% where the darker state is below 0.80 relative luminance",
      "areaRuleIfMoreFrequent": {"pctOf10DegField":25,"wcagRect1024x768":[341,256],"equivalentRect":{"16x9":[640,360],"9x16":[360,640],"1x1":[360,360],"4x5":[360,450]}},
      "redFlash": "no saturated red flashes",
      "broadcast": "Ofcom / ITU-R BT.1702: <= 25% of screen area for frequent flashes",
      "accentHitMinFrames": {"24":4,"25":4,"30":5,"60":10},
      "twinkleMaxHz": 3,
      "qa": "final render through a PSE analyser (Harding FPA or PEAT)",
      "ev": "S (WCAG 2.3.1) + E (hit length)"
    },
    "subtitles": {
      "when": "every voiced beat; every beat whose proof is sound",
      "slot": "one fixed position per film, outside the focal zone",
      "16x9": {"boxY":[880,980],"bottomEdgeMaxY":1000,"sizePx":{"mixed":[56,64],"caps":48,"min":48},"lines":2,"charsPerLine":32},
      "9x16": {"boxY":[1150,1250],"xRange":[72,888],"sizePxMin":52,"lines":2,"charsPerLine":[22,26]},
      "1x1": {"boxY":[860,960],"sizePxMin":48,"lines":2,"charsPerLine":[24,28],"ev":"E"},
      "4x5": {"boxY":[1080,1180],"sizePxMin":48,"lines":2,"charsPerLine":[24,28],"ev":"E"},
      "backing": "pill of the ground colour at 60%, radius = height/2, padding 24/14; or a 40-60% scrim",
      "timing": {"cpsMax":"see reading.cpsSubtitleMax","minFrames":20,"maxSeconds":7},
      "deliverables": "burned-in + SRT/VTT per language",
      "activeWordHighlight": "optional; counts as the frame's accent echo",
      "ev": "S (Netflix TTSG, BBC) + A"
    },
    "soundOff": "every beat reads without sound (feeds autoplay muted)",
    "colourIndependence": "never encode meaning by hue alone: pair state colours with shape, label, position or a luminance difference of >= 0.15 OKLCH L (e.g. selected vs rejected)",
    "reducedMotion": "interactive/web loops honour prefers-reduced-motion: show the B-rest frame, drop parallax and camera moves",
    "vestibular": "large zooms (> 2x) and fast lateral parallax are the riskiest moves: keep them eased (camera curve), <= 1 per beat, and never looped",
    "legibilityFloors": "see legibility",
    "loudness": {"socialLufs":-14,"truePeakDbtp":-1,"broadcastLufs":-23,"ev":"E / S (EBU R128)"}
  },
  "shape": {
    "law": "one radius formula per container class for the whole film; radius = fraction x the element's SHORT side (so it scales with the container and is never copied from the hero); nested radii are concentric (inner = outer - pa…",
    "families": {
      "note": "fraction of the short side; 0.5 = full pill; canonical sizes: card 600x400, control 360x96, chip 200x48, media 1280x720, window 1440x900; caps: card 64, media 72, window 56 px",
      "sharp": {"card":0,"control":0,"chip":0,"media":0,"window":0,"strokes":[1,2,3]},
      "soft": {"card":0.045,"control":0.25,"chip":0.25,"media":0.03,"window":0.025,"strokes":[1.5,2,3]},
      "round": {"card":0.06,"control":0.5,"chip":0.5,"media":0.045,"window":0.028,"strokes":[1.5,2,3]},
      "pill": {"card":0.12,"control":0.5,"chip":0.5,"media":0.08,"window":0.05,"strokes":[2,3,4]},
      "strokesOrder": "hairline / strong / accent px",
      "ev": "E (reconciled with DERIVE.md section 7)"
    },
    "archiveRoundFamily": {
      "scope": "higgsfield",
      "ev": "A",
      "values": {"chip":"full","keyPill":"23-29% of height","card9x16":"6% of width (5-7%)","cardSmall16x9":"3-5% of width (<= 700 px)","heroMedia16x9":"2-3% of width (860-1440 px)","fullScreenCard":"40-44 px at 1800-1840 wide","window":"22-26 px","panel":"28-32 px","composer":"0.2 x height, <= 48","plaque":"7.6% of height","iconTile":"16.7-27% of size","phoneScreenFrameless":"36-43 px at 390-500 wide"},
      "note": "the Higgsfield archive is the `round` family"
    },
    "strokes": {"hairlinePx":[1,2],"accentPx":[2,4.5],"colouredChromaOnlyMinPx":[3,4],"dash":[18,12],"onMovingElementsMinPx":2,"ev":"A + I (shimmer under motion/compression; 4:2:0)"},
    "tilt": {"cardsDegMax":12,"stickerSkewDeg":7.4,"oneVanishingDirection":true}
  },
  "unity": {
    "law": "a film reads as ONE motion when every passport row has exactly one value for the whole film",
    "passportRows": [
      "register/style + ground",
      "scene mode (dark/light/schedule)",
      "accents (primary + <= 1 secondary, one meaning each)",
      "display voice",
      "type scale (<= 5 narrative styles)",
      "text margin + primary axis + one off-axis family",
      "… ещё 10 элементов (полный список — в файле данных)"
    ],
    "heroMotifPresencePctBeatsMin": 60,
    "radiusRule": "one formula per container class; nested radii concentric: inner = outer - padding; inside a fan radius scales with each card",
    "doseRule": {"perNewPiece":"change 1 primary + <= 1 secondary lever vs the identity default; differ from each of the last 3 pieces in >= 1 lever","ev":"I (MAYA, Hekkert 2003; Post 2016) + E"},
    "tests": ["filmstrip at 10%: one family","logo-off: brand still nameable","line-up with last 3 pieces: family, not duplicate","blur 20-30 px","JPEG complexity of text zones"],
    "keyframes": {
      "states": {"A":"entry: every element where it comes from","B":"rest: the approved hero state (after any push)","C":"exit = A of the next frame"},
      "layerStack": ["00_BG","01_ATMOS","02_FAR","03_HERO","04_NEAR_UI","05_TYPE","06_BRAND","07_FX","08_CAPTIONS","99_NOTES"],
      "workFrame16x9": {"w":2304,"h":1296,"safeChildCentre":[1152,648],"overscanPct":120},
      "naming": "FILM_sNN_{A-in|B-rest|C-out}_{16x9|9x16|1x1|4x5}_vNN [DRAFT|REVIEW|APPROVED|FINAL]"
    },
    "ev": "A + I (Gerstner programmes; Keller/Kapferer kernel vs periphery)"
  },
  "semanticContract": {"tokens":"176 токенов — таблица «Семантический контракт»","policy":"→ таблица «Политика темы»","aliases":"→ таблица «Алиасы имён токенов»"},
  "units": {
    "designUnit": "du",
    "du": "min(w, h) / 1080 px",
    "referenceShortEdgePx": 1080,
    "note": "всем 4 форматам (16:9, 9:16, 1:1, 4:5) короткая сторона = 1080, поэтому наши px = du. Для 4K, LED-стен и нестандартных экранов умножайте на HFT.du()",
    "position": "normalised x/y: доля ширины / высоты, 0 — левый / верхний край; за кадром — только осознанный вход / выход",
    "time": "ms — основная единица; кадры — только после ms2f()",
    "null": "null = «не задано / не применяется», не ноль и не разрешение придумывать данные",
    "opacity": "0..1",
    "rotation": "degrees",
    "scale": "multiplier",
    "tracking": "em",
    "lineHeight": "multiplier of font size",
    "world3d": "meters (отдельно от du)",
    "color": "sRGB hex для 2D-образцов; рабочее пространство и HDR задаются в production.color",
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08)"
  },
  "timing": {
    "positiveDuration": "frames = max(1, round(ms · fps / 1000))",
    "minimumHold": "frames = ceil(ms · fps / 1000) (чтение, удержание)",
    "cut": "0 кадров (склейка и нулевая задержка остаются 0)",
    "timeline": "сначала общая длина в кадрах, затем КУМУЛЯТИВНЫЕ границы: последняя граница = общая длина; независимое округление сцен запрещено (дыры / наложения)",
    "beat": "доля = 60000 / BPM мс; дробное число кадров на долю допустимо (25 fps @ 120 BPM = 12,5): округляются накопленные границы",
    "helpers": ["HFT.ms2f(ms, fps, {hold})","HFT.beatGrid(bpm, fps, n)","HFT.timeline(id, durationMs, fps, bpm?)"],
    "houseRule": "наш дом: выбрать fps первым, затем целое число кадров на долю (§3.11); дробная доля — только когда музыка задана извне",
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08)"
  },
  "overrideOrder": {
    "lowToHigh": ["core","style preset","brand","project","delivery-specific","documented shot exception"],
    "rules": [
      "каждое исключение записывается с причиной (HFT.theme({exceptions:[{token, value, reason}]}); без reason — ошибка V24)",
      "переопределения не отменяют достоверность данных, ссылок и требования сдачи",
      "бренд может только ужесточать законы core; locks бренда проект не меняет",
      "после любого переопределения тема валидируется заново"
    ],
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08) + ARCHITECTURE §1.4"
  },
  "principles": {
    "must": [
      "одна цель кадра: прочесть, сравнить, почувствовать ритм, заметить действие или рассмотреть образ",
      "не искажать обязательный текст, данные и реальные свойства продукта ради красивого перехода",
      "проверять важное в итоговом размере просмотра и в реальной среде (законы читаемости §3.8)",
      "один цвет / одна форма / одно повторяющееся движение = один смысл на весь фильм; смену смысла показывать явно",
      "время текста и действия — по формулам чтения (§3.9), но формула не заменяет просмотр",
      "требования конкретного носителя проверяются перед сдачей; пресеты не подтверждают соответствие площадке",
      "… ещё 2 элементов (полный список — в файле данных)"
    ],
    "should": [
      "один фокус в информационном кадре (§3.5)",
      "плотность и темп по задаче; паузы для значимого результата",
      "движение связывает, раскрывает или акцентирует",
      "число шрифтов, цветов и переходов — по стилю, система узнаваема (§3.18)"
    ],
    "may": [
      "коллаж, танец, музыкальный монтаж и абстракция могут намеренно иметь несколько центров внимания",
      "буквы как текстура не обязаны читаться, но обязательный смысл отделён от текстуры",
      "логотип, хук, UI, речь, кульминация и CTA — только там, где их требует жанр"
    ],
    "tags": {"must":"[обязательно]","should":"[по умолчанию]","may":"[исключение]"},
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08) + Bible §0, §10"
  },
  "delivery": {
    "profiles": {
      "landscape": {"format":"16x9","w":1920,"h":1080,"gridColumns":12,"gutterDu":24,"houseInsetFraction":{"x":0.05,"y":0.06},"layout":"горизонтальные группы, две колонки"},
      "portrait": {"format":"9x16","w":1080,"h":1920,"gridColumns":6,"gutterDu":24,"houseInsetFraction":{"x":0.067,"y":0.06},"layout":"пересобрать группы по вертикали; переносы, крупность героя и подписи заново"},
      "square": {"format":"1x1","w":1080,"h":1080,"gridColumns":6,"gutterDu":24,"houseInsetFraction":{"x":0.06,"y":0.06},"layout":"баланс центра и краёв; не кропать 16:9 без новой компоновки"},
      "portrait4x5": {"format":"4x5","w":1080,"h":1350,"gridColumns":6,"gutterDu":24,"houseInsetFraction":{"x":0.067,"y":0.06},"layout":"отдельная компоновка; = окно y285–1635 мастера 9:16"},
      "custom": {"format":null,"w":null,"h":null,"gridColumns":null,"gutterDu":null,"houseInsetFraction":null,"layout":"сцена, LED, эфир, инсталляция: задать геометрию, дистанцию просмотра и карту экранов"}
    },
    "reconcile": "houseInsetFraction — эстетические поля, НЕ платформенная safe zone. Наши измеренные safeAreas (§3.2) остаются: 16:9 текст ≥ 60 px (title-safe 90 % для ТВ), 9:16 must-read x72–888 / y240–1440 (organic) или y288–1248 (ads)…",
    "config": {
      "platformName": null,
      "specificationUrl": null,
      "specificationCheckedOn": null,
      "overlayAsset": null,
      "forbiddenRegionsNormalized": [],
      "requiredSafeRegionNormalized": null,
      "cropVariants": [],
      "pixelAspectRatio": 1,
      "scanMode": "progressive",
      "alphaRequired": false,
      "hdrRequired": false,
      "noteRu": "houseInsetFraction задаёт эстетические поля, а не гарантированную safe zone. Размеры, частоту кадров, перекрытия платформы, область титров и параметры экспорта подтвердить для конкретной сдачи. Для эфирных и нестандартны…"
    },
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08)"
  },
  "localization": {
    "rules": [
      "проверить каждую нужную письменность в выбранном шрифте (HFT.fonts[family].scripts); нет глифов → fallback по typography.scriptFallback, кегль по cap/x-height",
      "RTL: зеркалить порядок чтения и UI, но никогда механически логотипы и графики; редакционная ось = ведущий край (leading edge) с учётом RTL",
      "после перевода пересобрать переносы и пересчитать время чтения (HFT.readTime с script)",
      "никогда не ужимать обязательный текст под старую рамку: делить на кадры",
      "письменности без пробелов (Jpan, Hans, Hant, Thai) — формула по знакам (reading.holdFormulaChars)"
    ],
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08) + core 3.7.5"
  },
  "motion": {
    "scalars": {
      "scaleEnterFrom": 0.96,
      "pressScale": 0.96,
      "overshootOptionalScale": 1.04,
      "expressiveTiltMaxDeg": 4,
      "subduedOpacity": 0.45,
      "travelDu": {"small":24,"medium":80,"large":240},
      "ev": "[стартовая настройка] tokens_universal.json (2026-10-08)",
      "note": "overshoot по-прежнему ограничен личностью (§3.11.2: productive 0, expressive 0,06, playful 0,12)"
    },
    "patterns": {
      "enter": {"options":["position","opacity","mask","scale"],"duration":"dur.headline | dur.ui | dur.hero","ease":"ease.enter","rule":"свойства по действию; не все сразу"},
      "exit": {"duration":"dur.exit (на 50–100 мс короче входа)","ease":"ease.exit"},
      "reposition": {"duration":"dur.ui","ease":"ease.move","rule":"связь стартовой и конечной позиции видна"},
      "reveal": {"options":["cut","mask","occlusion","focus","light","assembly"],"rule":"один механизм раскрытия под материал; свечение и искры не обязательны"},
      "stagger": {"delay":"stagger (2–4 кадра @24 = один каскад; ≥ 6 = отдельные события)","rule":"проверять ОБЩЕЕ время группы: задержки складываются"},
      "emphasis": {"options":["hold","scale","contrast","isolation","sound","direction change"],"rule":"пауза — тоже акцент; один приём на кадр (§3.6.17)"},
      "transform": {"options":["shape_morph","match_cut","shared_element","replacement"],"rule":"выбрать, что связывает формы: смысл, контур, позиция или движение; не подменять факты плавной трансформацией"},
      "hold": {"duration":"по содержанию (reading.finalRule)","rule":"фоновое движение не мешает главному (periphery drift 8–16 px/s)"},
      "cut": {"durationMs":0,"rule":"прямая склейка допустима без промежуточной анимации"}
    },
    "byPersonality": {
      "productive": {"reveal":"mask","emphasis":"contrast","transform":"match_cut"},
      "expressive": {"reveal":"assembly","emphasis":"scale","transform":"shape_morph"},
      "luxury-slow": {"reveal":"light","emphasis":"hold","transform":"replacement"},
      "playful-bouncy": {"reveal":"assembly","emphasis":"scale","transform":"shape_morph"},
      "cinematic": {"reveal":"focus","emphasis":"hold","transform":"match_cut"},
      "glitch-tech": {"reveal":"cut","emphasis":"isolation","transform":"replacement"}
    },
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08) + core 3.11, 3.13"
  },
  "components": {
    "number": {"tabularFigures":true,"unitWhenMeaningNeedsIt":true,"sourceRequiredForFactualClaim":true,"size":"type.number / type.display","ratioToQualifier":[2.1,2.3]},
    "progress": {"mode":"indeterminate until real progress exists","rule":"никакого вымышленного %"},
    "comparison": {"sameConditionsAndScale":true,"labelsWhenAmbiguous":true},
    "imagePanel": {"focalPointNormalized":[0.5,0.5],"fit":"contain | crop по смыслу; проверить на всех форматах","nativeRatioOnly":true},
    "lowerThird": {"name":"type.headline | type.subhead","secondary":"type.label","hold":"по контенту или по событию"},
    "button": {"states":["idle","focused","pressed","disabled"],"paddingDu":[32,20],"fill":"accent.action","text":"fg.onAccent","pressScale":0.96,"note":"для демо реального UI брать размеры и состояния продукта"},
    "badge": {"paddingDu":[16,8],"radius":"radius.chip","type":"type.label"},
    "card": {"paddingDu":24,"radius":"radius.card","fill":"bg.raised","border":"line.hairline (декоративная) / line.essential (несёт смысл)"},
    "caption": {"type":"type.caption","linesMax":2,"slot":"один фиксированный на фильм (accessibility.subtitles)"},
    "logo": {"rule":"никогда не придумывать пропорции чужого знака; свой знак — только инстансом","clearSpace":"brand.logoClearSpaceDu"},
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08)"
  },
  "quality": {
    "reviewStages": ["key_frame","motion_sample","rough_cut","final_render","delivery_test"],
    "content": [
      "Обязательные слова и цифры совпадают с брифом.",
      "Фактические утверждения имеют источник или обозначены как условный пример.",
      "Демо показывает заявленную функцию без скрытой подмены результата.",
      "График сохраняет данные, единицы и смысл шкалы."
    ],
    "visual": [
      "Проверены переносы, пропавшие символы, обрезки и перекрытия.",
      "Важный текст читается в реальном размере просмотра.",
      "Проверены все требуемые форматы, safe zones и интерфейсные перекрытия.",
      "Проверены временные артефакты: дрожание, мерцание, полосы, ступеньки и ошибки масок.",
      "Проверены движение, трекинг, контакты, циклы и альфа-канал для включённых модулей.",
      "Сильные вспышки и резкие полноэкранные изменения требуют отдельной проверки финального видео по условиям размещения; число в конфиге не доказывает безопасность."
    ],
    "audio": ["Речь и значимые звуки различимы.","Нет случайного клиппинга, щелчков на склейках и пропавших каналов.","Субтитры соответствуют речи, когда они нужны.","Уровни и формат совпадают с требованиями сдачи."],
    "scope": "проверять только включённые модули и реальные требования проекта; HFT.validate() — проверка токенов, НЕ проверка видео",
    "flash": "вспышки и резкие полноэкранные смены — только на финальном видео (PSE-анализатор: Harding FPA / PEAT)",
    "frameChecklist": "Bible §10.1 (композиция, цвет, типографика, материал и свет, генерации, фильм, копирайт, тесты)",
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08) + Bible §10"
  },
  "production": {
    "assetManifestFields": ["id","kind","source","local_or_remote_reference","usage_rights","version","dimensions","fps_if_video","duration_if_timed","color_space","alpha_mode","used_in_shots"],
    "shotManifestFields": ["id","purpose","start_frame","end_frame_exclusive","layout","assets","required_text","motion","audio","exceptions","status"],
    "naming": {"shot":"PROJECT_SHOT_FORMAT_VERSION (v001, v002 …)","frame":"FILM_sNN_{A-in|B-rest|C-out}_{16x9|9x16|1x1|4x5}_vNN [DRAFT|REVIEW|APPROVED|FINAL]","layer":"00_BG … 99_NOTES (core.depth)"},
    "color": {"workingSpace":null,"viewTransform":null,"outputSpace":"Rec.709 / sRGB","bitDepth":null,"rule":"явно задать преобразования между графикой, 3D, видео и файлом; проверять градиенты и свечение после экспорта"},
    "export": {
      "masterContainer": null,
      "masterCodec": null,
      "deliveryContainer": null,
      "deliveryCodec": null,
      "bitrate": null,
      "fps": null,
      "audioFormat": null,
      "alphaMode": null,
      "captionFormats": [],
      "coverAsset": null,
      "noteRu": "Параметры выбираются по содержимому, инструменту и спецификации получателя; единого обязательного кодека или битрейта нет."
    },
    "handoff": [
      "Передать согласованные исходники и финальные версии.",
      "Зафиксировать используемые шрифты, плагины и версии инструментов, если это влияет на воспроизведение.",
      "Для переноса между приложениями проверить один кадр и короткое движение: blur, easing, glow и режимы смешивания могут отличаться.",
      "Сохранить список материалов и настройки экспорта.",
      "Отметить, какие версии и проверки действительно выполнены."
    ],
    "ev": "[стартовая настройка] tokens_universal.json (2026-10-08) + Bible §13"
  }
}
```

### axes

```json
{
  "typeVoice": {
    "neo-grotesk": {
      "label": "Нео-гротеск",
      "character": "нейтральный, точный, продуктовый; голос интерфейса и keynote",
      "families": {"display":[{"family":"Inter","weights":[500,600,700],"axes":{"opsz":32}},{"family":"Inter Tight","weights":[600,700,800]},{"family":"Geist","weights":[600,700]}],"text":[{"family":"Inter","weights":[400,500,600],"axes":{"opsz":"auto"}},{"family":"Geist","weights":[400,500]}],"mono":[{"family":"JetBrains Mono","weights":[400,500]},{"family":"Geist Mono","weights":[400,500]}],"accent":[{"family":"Instrument Serif","style":"italic","weights":[400]}]},
      "tracking": [[200,-0.04,-0.055],[120,-0.03,-0.04],[80,-0.02,-0.03],[48,-0.01,-0.02],[20,0.06,-0.005]],
      "lineHeight": {"display1":1,"display2":1.04,"caps":0.92,"body":1.35,"ui":1.2},
      "case": {"display":"sentence (утверждение с точкой допустимо)","label":"CAPS только ≤36 px"},
      "scaleRatio": 1.5,
      "rules": ["opsz = 32 для всего ≥32 px (font-optical-sizing:auto); ниже — opsz по кеглю","'case' на CAPS с пунктуацией, 'tnum' на всех меняющихся числах","вес не меняется внутри строки; акцент — цветом, контейнером или материалом"],
      "params": {"display":"Inter","text":"Inter","mono":"JetBrains Mono","accent":"Instrument Serif","w":{"display":700,"headline":600,"body":500,"label":600,"code":500},"displayCase":"sentence","labelCase":"caps","ratio":1.5,"lh":{"display1":1,"display2":1.04,"caps":0.92,"body":1.35,"ui":1.2},"tracking":[[200,-0.04,-0.055],[120,-0.03,-0.04],[80,-0.02,-0.03],[48,-0.01,-0.02],[20,0.06,-0.005]]}
    },
    "grotesk-tech": {
      "label": "Тех-гротеск",
      "character": "системный, «космический», инженерный; голос тегов, чисел, титульного СЛОВА",
      "families": {"display":[{"family":"Space Grotesk","weights":[500,600,700]}],"text":[{"family":"Inter","weights":[400,500,600]}],"mono":[{"family":"Space Mono","weights":[400,700]},{"family":"JetBrains Mono","weights":[400,500]}],"accent":[{"family":"Doto","weights":[800],"axes":{"ROND":0}}]},
      "tracking": [[200,-0.04,-0.05],[120,-0.04,-0.04],[80,-0.03,-0.03],[48,-0.02,-0.02],[20,0.12,0]],
      "lineHeight": {"display1":0.9,"display2":0.95,"caps":0.92,"body":1.35,"ui":1.2},
      "case": {"display":"CAPS","label":"CAPS +0.12…+0.16 em на 15–28 px (HUD, теги)"},
      "scaleRatio": 1.333,
      "rules": ["Space Grotesk никогда не наклоняется (italic нет); «слово скорости» — Inter Bold Italic","ширина почти не меняется с весом (300→700 <1%): вес можно анимировать без переразбивки","кириллица и греческий → Inter тем же весом, кегль ×0,96 (капитель 0,70 / 0,728)"],
      "params": {"display":"Space Grotesk","text":"Inter","mono":"Space Mono","accent":"Doto","w":{"display":700,"headline":700,"body":500,"label":600,"code":400},"displayCase":"caps","labelCase":"caps","ratio":1.333,"lh":{"display1":0.9,"display2":0.95,"caps":0.92,"body":1.35,"ui":1.2},"tracking":[[200,-0.04,-0.05],[120,-0.04,-0.04],[80,-0.03,-0.03],[48,-0.02,-0.02],[20,0.12,0]]}
    },
    "humanist": {
      "label": "Гуманист",
      "character": "тёплый, разговорный, читаемый; рукописная логика штриха",
      "families": {"display":[{"family":"Commissioner","weights":[500,600,700],"axes":{"FLAR":30,"VOLM":0}}],"text":[{"family":"Commissioner","weights":[400,500],"axes":{"FLAR":0,"VOLM":0}},{"family":"Source Sans 3","weights":[400,600]}],"mono":[{"family":"IBM Plex Mono","weights":[400,500]}],"accent":[{"family":"Literata","style":"italic","weights":[400],"axes":{"opsz":72}}]},
      "tracking": [[200,-0.02,-0.035],[120,-0.015,-0.025],[80,-0.01,-0.02],[48,0,-0.01],[20,0.06,0]],
      "lineHeight": {"display1":1.04,"display2":1.1,"caps":0.96,"body":1.42,"ui":1.25},
      "case": {"display":"sentence","label":"CAPS +0.08 em ≤32 px"},
      "scaleRatio": 1.333,
      "rules": ["FLAR (вспышка на концах штрихов) 0–40: выше 40 читается как декоративный шрифт","VOLM держать 0 на тексте, до 40 только на дисплее ≥120 px"],
      "params": {"display":"Commissioner","text":"Commissioner","mono":"IBM Plex Mono","accent":"Literata","w":{"display":600,"headline":600,"body":500,"label":600,"code":400},"displayCase":"sentence","labelCase":"caps","ratio":1.333,"lh":{"display1":1.04,"display2":1.1,"caps":0.96,"body":1.42,"ui":1.25},"tracking":[[200,-0.02,-0.035],[120,-0.015,-0.025],[80,-0.01,-0.02],[48,0,-0.01],[20,0.06,0]]}
    },
    "geometric": {
      "label": "Геометрический",
      "character": "дружелюбный, чистый, «софтовый»; круглые чаши, открытая апертура",
      "families": {"display":[{"family":"Plus Jakarta Sans","weights":[700,800]},{"family":"Manrope","weights":[700,800]},{"family":"Jost","weights":[500,600]}],"text":[{"family":"Plus Jakarta Sans","weights":[400,500,600]},{"family":"Manrope","weights":[400,500,600]}],"mono":[{"family":"DM Mono","weights":[400,500]}],"accent":[{"family":"Instrument Serif","style":"italic","weights":[400]}]},
      "tracking": [[200,-0.03,-0.045],[120,-0.02,-0.035],[80,-0.01,-0.025],[48,0.02,-0.015],[20,0.12,0]],
      "lineHeight": {"display1":1.04,"display2":1.08,"caps":1,"body":1.45,"ui":1.25},
      "case": {"display":"sentence","label":"CAPS +0.10…+0.16 em (геометрическим капителям нужен воздух)"},
      "scaleRatio": 1.333,
      "rules": ["CAPS-дисплей ≥120 px не используем (круглые O/C/G разваливают ритм)","Plus Jakarta Sans не отдаёт базовую кириллицу (только cyrillic-ext) → кириллица в Manrope"],
      "params": {"display":"Plus Jakarta Sans","text":"Plus Jakarta Sans","mono":"DM Mono","accent":"Instrument Serif","w":{"display":800,"headline":700,"body":500,"label":600,"code":400},"displayCase":"sentence","labelCase":"caps","ratio":1.333,"lh":{"display1":1.04,"display2":1.08,"caps":1,"body":1.45,"ui":1.25},"tracking":[[200,-0.03,-0.045],[120,-0.02,-0.035],[80,-0.01,-0.025],[48,0.02,-0.015],[20,0.12,0]]}
    },
    "editorial-serif": {
      "label": "Редакционная антиква",
      "character": "литературный, тёплый, авторский; контраст роман/италик",
      "families": {"display":[{"family":"Fraunces","weights":[300,400,500],"axes":{"opsz":144,"SOFT":50,"WONK":0}},{"family":"Literata","weights":[300,400,500],"axes":{"opsz":72}}],"text":[{"family":"Commissioner","weights":[400,500],"axes":{"FLAR":20}}],"mono":[{"family":"DM Mono","weights":[400]}],"accent":[{"family":"Fraunces","style":"italic","weights":[400],"axes":{"opsz":144,"SOFT":100,"WONK":1}}]},
      "tracking": [[200,-0.02,-0.03],[120,-0.015,-0.02],[80,-0.01,-0.015],[48,0,-0.01],[20,0.1,0]],
      "lineHeight": {"display1":1.02,"display2":1.08,"caps":1,"body":1.48,"ui":1.3},
      "case": {"display":"sentence + одно слово италиком","label":"CAPS +0.10 em, набор в гротеске текста"},
      "scaleRatio": 1.5,
      "rules": ["на ≥120 px вес 300–400: контраст даёт opsz, а не жирность","италик того же семейства = акцент; другой серифный шрифт рядом запрещён","Fraunces без кириллицы → Literata (opsz 72) тем же весом"],
      "params": {"display":"Fraunces","text":"Commissioner","mono":"DM Mono","accent":"Fraunces","w":{"display":400,"headline":400,"body":500,"label":600,"code":400},"displayCase":"sentence","labelCase":"caps","ratio":1.5,"lh":{"display1":1.02,"display2":1.08,"caps":1,"body":1.48,"ui":1.3},"tracking":[[200,-0.02,-0.03],[120,-0.015,-0.02],[80,-0.01,-0.015],[48,0,-0.01],[20,0.1,0]]}
    },
    "didone-luxury": {
      "label": "Дидона / люкс",
      "character": "кутюрный, тихий, дорогой; волосяные засечки и разреженные капители",
      "families": {"display":[{"family":"Playfair","weights":[400,500],"axes":{"opsz":"auto","wdth":100}},{"family":"Bodoni Moda","weights":[400,500],"axes":{"opsz":96}}],"text":[{"family":"Jost","weights":[300,400,500]}],"mono":[{"family":"DM Mono","weights":[300,400]}],"accent":[{"family":"Playfair","style":"italic","weights":[400],"axes":{"opsz":"auto"}}]},
      "tracking": [[200,0.04,-0.02],[120,0.05,-0.015],[80,0.06,-0.01],[48,0.12,0],[20,0.22,0.01]],
      "lineHeight": {"display1":1.02,"display2":1.1,"caps":1.05,"body":1.5,"ui":1.3},
      "case": {"display":"sentence или разреженные CAPS (+0.04…+0.08 em)","label":"Jost 500 CAPS +0.20…+0.28 em"},
      "scaleRatio": 1.618,
      "rules": ["Playfair: капитель 0,571 em (файл шрифта) → для равной капители с Inter кегль ×1,27","дисплей не жирнее 600: волосяные штрихи на 4:2:0 должны быть ≥2 px → Playfair ≥120 px","opsz = кегль (font-optical-sizing:auto) — на больших кеглях контраст растёт сам","Bodoni Moda только латиница → для кириллицы Playfair"],
      "params": {"display":"Playfair","text":"Jost","mono":"DM Mono","accent":"Playfair","w":{"display":500,"headline":400,"body":500,"label":500,"code":400},"displayCase":"sentence","labelCase":"caps","ratio":1.618,"lh":{"display1":1.02,"display2":1.1,"caps":1.05,"body":1.5,"ui":1.3},"tracking":[[200,0.04,-0.02],[120,0.05,-0.015],[80,0.06,-0.01],[48,0.12,0],[20,0.22,0.01]]}
    },
    "condensed-display": {
      "label": "Узкий дисплей",
      "character": "кинематографичный, плакатный, вертикальный; титры и постеры",
      "families": {"display":[{"family":"Sofia Sans Extra Condensed","weights":[300,700,800]},{"family":"Big Shoulders","weights":[700,800,900],"axes":{"opsz":72}},{"family":"Barlow Condensed","weights":[700,800]}],"text":[{"family":"Sofia Sans","weights":[300,400,500]}],"mono":[{"family":"IBM Plex Mono","weights":[400]}],"accent":[{"family":"Cormorant","style":"italic","weights":[500]}]},
      "tracking": [[200,-0.01,-0.02],[120,0,-0.01],[80,0.01,0],[48,0.04,0],[20,0.14,0.01]],
      "trackingCredits": "веса 200–400 CAPS: +0.18…+0.30 em (титровый набор)",
      "lineHeight": {"display1":0.88,"display2":0.92,"caps":0.88,"body":1.38,"ui":1.25},
      "case": {"display":"CAPS","label":"CAPS широкий трекинг"},
      "scaleRatio": 1.618,
      "rules": ["узкий только CAPS-дисплей; текст — в нормальной ширине того же семейства","Sofia Sans Extra Condensed: средняя ширина знака 0,27 em → ≈45% уже Inter, ≤30 знаков на строку при 152 px","«Big Shoulders Display» из старых документов теперь «Big Shoulders» (opsz 10–72)"],
      "params": {"display":"Sofia Sans Extra Condensed","text":"Sofia Sans","mono":"IBM Plex Mono","accent":"Cormorant","w":{"display":800,"headline":700,"body":500,"label":700,"code":400},"displayCase":"caps","labelCase":"caps","ratio":1.618,"lh":{"display1":0.88,"display2":0.92,"caps":0.88,"body":1.38,"ui":1.25},"tracking":[[200,-0.01,-0.02],[120,0,-0.01],[80,0.01,0],[48,0.04,0],[20,0.14,0.01]]}
    },
    "expanded-display": {
      "label": "Широкий дисплей",
      "character": "громкий, футуристичный, «модный»; одно слово на кадр",
      "families": {"display":[{"family":"Unbounded","weights":[600,700,800,900]},{"family":"Archivo","weights":[800,900],"axes":{"wdth":125}},{"family":"Mona Sans","weights":[800,900],"axes":{"wdth":125}}],"text":[{"family":"Manrope","weights":[400,500,600]}],"mono":[{"family":"Geist Mono","weights":[400,500]}],"accent":[{"family":"Syne","weights":[800]}]},
      "tracking": [[200,-0.02,-0.04],[120,-0.01,-0.03],[80,0,-0.02],[48,0.02,-0.01],[20,0.08,0]],
      "lineHeight": {"display1":0.96,"display2":1,"caps":0.95,"body":1.42,"ui":1.25},
      "case": {"display":"CAPS или sentence; 1–3 слова","label":"CAPS +0.08 em"},
      "scaleRatio": 1.5,
      "rules": ["≤8–10 знаков на строку при 200 px (Unbounded ≈0,6 em/знак)","широкий шрифт не ставим в длинные строки и субтитры"],
      "params": {"display":"Unbounded","text":"Manrope","mono":"Geist Mono","accent":"Syne","w":{"display":700,"headline":600,"body":500,"label":600,"code":400},"displayCase":"caps","labelCase":"caps","ratio":1.5,"lh":{"display1":0.96,"display2":1,"caps":0.95,"body":1.42,"ui":1.25},"tracking":[[200,-0.02,-0.04],[120,-0.01,-0.03],[80,0,-0.02],[48,0.02,-0.01],[20,0.08,0]]}
    },
    "mono-terminal": {
      "label": "Моно / терминал",
      "character": "инженерный, честный, «сделано в коде»",
      "families": {"display":[{"family":"Martian Mono","weights":[500,600,700,800],"axes":{"wdth":100}},{"family":"JetBrains Mono","weights":[700,800]}],"text":[{"family":"IBM Plex Sans","weights":[400,500],"axes":{"wdth":100}}],"mono":[{"family":"IBM Plex Mono","weights":[400,500]},{"family":"JetBrains Mono","weights":[400,500]}],"accent":[{"family":"Doto","weights":[800],"axes":{"ROND":0}}]},
      "tracking": [[200,-0.05,-0.05],[120,-0.04,-0.04],[80,-0.03,-0.03],[48,-0.02,-0.02],[20,0.04,0]],
      "lineHeight": {"display1":1.04,"display2":1.1,"caps":1,"body":1.45,"ui":1.5},
      "case": {"display":"lowercase-команды, `>`/`$`, [скобки] для лейблов","label":"CAPS +0.04 em"},
      "scaleRatio": 1.5,
      "rules": ["моноширинный дисплей «рыхлый» — трекинг сильнее, чем у гротеска на тот же кегль","tnum встроен; счётчики не дрожат","Martian Mono: капитель 0,80 em (файл шрифта) → кегль ×0,91 к Inter для равной капители"],
      "params": {"display":"Martian Mono","text":"IBM Plex Sans","mono":"IBM Plex Mono","accent":"Doto","w":{"display":600,"headline":500,"body":500,"label":500,"code":400},"displayCase":"sentence","labelCase":"caps","ratio":1.5,"lh":{"display1":1.04,"display2":1.1,"caps":1,"body":1.45,"ui":1.5},"tracking":[[200,-0.05,-0.05],[120,-0.04,-0.04],[80,-0.03,-0.03],[48,-0.02,-0.02],[20,0.04,0]]}
    },
    "rounded-friendly": {
      "label": "Скруглённый",
      "character": "мягкий, доброжелательный, тактильный",
      "families": {"display":[{"family":"Rubik","weights":[700,800,900]},{"family":"Nunito","weights":[800,900]},{"family":"M PLUS Rounded 1c","weights":[800]}],"text":[{"family":"Rubik","weights":[400,500]},{"family":"Nunito","weights":[500,600]}],"mono":[{"family":"DM Mono","weights":[400,500]}],"accent":[]},
      "tracking": [[200,-0.02,-0.035],[120,-0.015,-0.025],[80,-0.01,-0.02],[48,0.02,-0.01],[20,0.08,0]],
      "lineHeight": {"display1":1.02,"display2":1.06,"caps":1,"body":1.45,"ui":1.25},
      "case": {"display":"sentence","label":"sentence"},
      "scaleRatio": 1.333,
      "rules": ["Rubik отдаёт арабский и иврит — один шрифт на три письменности","CAPS-дисплей не используем: скругления читаются как «детский» шрифт"],
      "params": {"display":"Rubik","text":"Rubik","mono":"DM Mono","accent":null,"w":{"display":800,"headline":700,"body":500,"label":600,"code":400},"displayCase":"sentence","labelCase":"sentence","ratio":1.333,"lh":{"display1":1.02,"display2":1.06,"caps":1,"body":1.45,"ui":1.25},"tracking":[[200,-0.02,-0.035],[120,-0.015,-0.025],[80,-0.01,-0.02],[48,0.02,-0.01],[20,0.08,0]]}
    },
    "quirky-grotesk": {
      "label": "Характерный гротеск",
      "character": "дерзкий, современный, с «живыми» деталями (ink traps, переменная ширина)",
      "families": {"display":[{"family":"Bricolage Grotesque","weights":[700,800],"axes":{"opsz":96,"wdth":85}},{"family":"Familjen Grotesk","weights":[600,700]},{"family":"Syne","weights":[700,800]}],"text":[{"family":"Rubik","weights":[400,500]},{"family":"Onest","weights":[400,500]}],"mono":[{"family":"DM Mono","weights":[400,500]}],"accent":[{"family":"Bricolage Grotesque","weights":[800],"axes":{"opsz":12,"wdth":75}}]},
      "tracking": [[200,-0.03,-0.05],[120,-0.02,-0.04],[80,-0.01,-0.03],[48,0.02,-0.02],[20,0.08,0]],
      "lineHeight": {"display1":0.96,"display2":1,"caps":0.95,"body":1.42,"ui":1.25},
      "case": {"display":"sentence или lowercase","label":"sentence"},
      "scaleRatio": 1.5,
      "rules": ["opsz 96 на дисплее (детали тоньше), opsz 12 — «грубый» акцент того же семейства","wdth 75↔100 можно анимировать на ударной доле","Bricolage без кириллицы → Rubik 800 (капитель 0,70 против 0,66: кегль ×0,94)"],
      "params": {"display":"Bricolage Grotesque","text":"Rubik","mono":"DM Mono","accent":"Bricolage Grotesque","w":{"display":800,"headline":700,"body":500,"label":600,"code":400},"displayCase":"sentence","labelCase":"sentence","ratio":1.5,"lh":{"display1":0.96,"display2":1,"caps":0.95,"body":1.42,"ui":1.25},"tracking":[[200,-0.03,-0.05],[120,-0.02,-0.04],[80,-0.01,-0.03],[48,0.02,-0.02],[20,0.08,0]]}
    },
    "variable-kinetic": {
      "label": "Вариативный кинетический",
      "character": "ритмичный, музыкальный; ширина и вес — это движение",
      "families": {"display":[{"family":"Mona Sans","weights":[200,900],"axes":{"wdth":[75,125],"wght":[200,900]}},{"family":"Roboto Flex","weights":[100,1000],"axes":{"wdth":[25,151],"opsz":144}},{"family":"Anybody","weights":[100,900],"axes":{"wdth":[50,150]}}],"text":[{"family":"Mona Sans","weights":[400,500],"axes":{"wdth":100}}],"mono":[{"family":"JetBrains Mono","weights":[500]}],"accent":[{"family":"Anybody","weights":[900],"axes":{"wdth":150}}]},
      "tracking": [[200,-0.02,-0.04],[120,-0.01,-0.03],[80,0,-0.02],[48,0.02,-0.01],[20,0.08,0]],
      "trackingByWidth": "трекинг = базовый − 0,02 × (wdth − 100) / 25 (на wdth 125 ещё −0,02 em; на 75 — +0,02 em)",
      "lineHeight": {"display1":0.9,"display2":0.94,"caps":0.88,"body":1.4,"ui":1.25},
      "case": {"display":"CAPS 1–3 слова","label":"CAPS +0.08 em"},
      "scaleRatio": 2,
      "rules": ["анимируем wdth/wght, а не scale: капитель постоянна, ритм строк не прыгает","переносы планируем по самому широкому состоянию (+25% длины строки)","Mona Sans без кириллицы → Roboto Flex (те же оси wdth/wght)"],
      "params": {"display":"Mona Sans","text":"Mona Sans","mono":"JetBrains Mono","accent":"Anybody","w":{"display":900,"headline":700,"body":500,"label":600,"code":500},"displayCase":"caps","labelCase":"caps","ratio":2,"lh":{"display1":0.9,"display2":0.94,"caps":0.88,"body":1.4,"ui":1.25},"tracking":[[200,-0.02,-0.04],[120,-0.01,-0.03],[80,0,-0.02],[48,0.02,-0.01],[20,0.08,0]]}
    },
    "pixel": {
      "label": "Пиксель / точечная матрица",
      "character": "цифровой, приборный, «машина думает»",
      "families": {"display":[{"family":"Doto","weights":[700,800,900],"axes":{"ROND":100}},{"family":"Pixelify Sans","weights":[500,700]},{"family":"Tiny5","weights":[400]}],"text":[{"family":"Onest","weights":[400,500]}],"mono":[{"family":"Geist Mono","weights":[400,500]}],"accent":[]},
      "tracking": [[200,0.02,0.02],[120,0.02,0.02],[80,0.02,0.02],[48,0.03,0.02],[20,0.06,0.02]],
      "lineHeight": {"display1":1,"display2":1.12,"caps":1,"body":1.4,"ui":1.3},
      "case": {"display":"CAPS или цифры","label":"CAPS"},
      "scaleRatio": 2,
      "rules": ["отрицательный трекинг запрещён: точки/пиксели слипаются","Doto только ≥96 px (на меньших кеглях точки сливаются в 4:2:0)","Tiny5: кегль кратен 8 px, чтобы пиксель шрифта = целому числу px","Doto без кириллицы → DotGothic16 (пиксельная готика, тоже кириллица и японский)"],
      "params": {"display":"Doto","text":"Onest","mono":"Geist Mono","accent":null,"w":{"display":800,"headline":700,"body":500,"label":600,"code":400},"displayCase":"caps","labelCase":"caps","ratio":2,"lh":{"display1":1,"display2":1.12,"caps":1,"body":1.4,"ui":1.3},"tracking":[[200,0.02,0.02],[120,0.02,0.02],[80,0.02,0.02],[48,0.03,0.02],[20,0.06,0.02]],"minDisplayPx":96}
    }
  },
  "palette": {
    "modes": {
      "signal": {"label":"Сигнал","neutralChroma":0.004,"accentChromaCap":0.4,"desc":"почти ахроматичные нейтрали + один насыщенный акцент на пределе охвата sRGB; второй акцент ≥90° по тону, ≤3–5%"},
      "tonal": {"label":"Тональный","neutralChroma":0.012,"accentChromaCap":0.14,"desc":"нейтрали подкрашены тоном сида (C 0,010–0,025), акцент средней насыщенности; цвет как атмосфера"},
      "duotone": {"label":"Дуотон","neutralChroma":0.01,"accentChromaCap":0.4,"desc":"два сида работают полями (колор-блоки 10–35%), текст — тёмный инк на светлых полях"},
      "pastel": {"label":"Пастель","neutralChroma":0.008,"accentChromaCap":0.18,"desc":"акценты в светлых полях (L 0,80–0,92, C 0,06–0,12) + одна насыщенная ступень для действия; mesh-градиенты из ≤2 тонов"},
      "mono": {"label":"Монохром","neutralChroma":0,"accentChromaCap":0.4,"desc":"ахроматика; акцент — инверсия ч/б, свечение или размер; цветная точка-статус ≤0,5% площади"},
      "spectral": {"label":"Спектральный","neutralChroma":0.01,"accentChromaCap":0.2,"desc":"холодные «хромовые» нейтрали + иридесцентный переход между двумя сидами по короткой дуге OKLCH (≤12% площади)"}
    },
    "accentAreaByMood": {"calm":{"target":[1,4],"max":6},"luxury":{"target":[1,3],"max":4},"editorial":{"target":[2,6],"max":8},"technical":{"target":[2,8],"max":10},"energetic":{"target":[6,15],"max":25},"playful":{"target":[12,30],"max":40}},
    "rampL": {"50":0.97,"100":0.935,"200":0.88,"300":0.82,"400":0.75,"500":0.68,"600":0.6,"700":0.52,"800":0.44,"900":0.36,"950":0.28},
    "rampTaper": {"50":0.35,"100":0.6,"200":0.85,"300":1,"400":1,"500":1,"600":1,"700":1,"800":0.9,"900":0.8,"950":0.7},
    "neutralL": {"0":0.13,"25":0.145,"50":0.16,"75":0.18,"100":0.2,"150":0.235,"200":0.27,"300":0.34,"400":0.45,"500":0.56,"600":0.66,"700":0.75,"800":0.85,"900":0.93,"925":0.955,"950":0.97,"975":0.985,"1000":1},
    "algorithm": [
      "1. seed → OKLCH (Ls, Cs, Hs). Нейтрали: hue = neutralHue (или seed), chroma = mode.neutralChroma (signal 0,004 … tonal 0,012–0,014; mono 0).",
      "2. Ramp акцента: L = rampL[k], C = min(Cs × taper[k], mode.accentChromaCap, maxChroma_sRGB(L, Hs)); ключ 'seed' = точный hex.",
      "3. Тёмная схема: bg.base L = darkBaseL (0,13–0,18); sunken −0,045 (≥0,10); raised +0,04; card +0,06; overlay +0,08; input +0,10; fg.primary L 0,95 (C×0,6); fg.muted 0,76; fg.subtle 0,60. Линии — альфа fg.primary поверх b…",
      "4. Светлая схема: bg.base L = lightBaseL (0,93–0,99); raised/card = +0,025 (белый при ≥0,995); sunken и input −0,035; overlay −0,06; fg.primary L 0,20 (inkHue); fg.muted 0,47; fg.subtle 0,60; линии — так же альфой.",
      "5. accent.action — тёмная: seed, если ≥3:1 к bg, иначе светлее по ramp; светлая: pastel → первая ступень с белым текстом ≥4,5:1; seed L ≥0,80 → «маркер» (seed заливкой + край A700 + инк-текст); иначе seed или темнее до ≥…",
      "6. accent.onAction — из {белый/fg.primary, инк}: оставить пары с WCAG ≥3:1 и |Lc| ≥45, выбрать максимум |Lc| (APCA точнее для насыщенных средних тонов: белый на красном #E4321B — Lc 74 при WCAG 4,4).",
      "7. accent.text — первая ступень от seed в сторону контраста с WCAG ≥4,5:1 и |Lc| ≥60; accent.core = A50; accent.subtle = OKLab-микс bg→seed 12–14%; accent.glow = seed 30% (тёмная) / цветная тень A600 35% (светлая).",
      "8. accent2/accent3 — тот же алгоритм; второй акцент ≥90° по тону от первого (кроме пресетов, где он — свет/статус).",
      "… ещё 2 элементов (полный список — в файле данных)"
    ]
  },
  "material": {
    "flat": {
      "label": "Плоский",
      "idea": "разделение планов значением (ΔL ≥0,045 на тёмном) и хейрлайном, без теней",
      "css": {"dark":{"surface":"bg.raised (сплошной)","border":"inset 0 0 0 1px rgba(255,255,255,.08)","shadowRest":"none","shadowFloat":"none","highlight":"none","glow":"none","backdrop":"none"},"light":{"surface":"#FFFFFF на bg.base","border":"inset 0 0 0 1px rgba(0,0,0,.08)","shadowRest":"none","shadowFloat":"0 1px 0 rgba(0,0,0,.06)","highlight":"none","glow":"none","backdrop":"none"}},
      "three": {"material":"MeshStandardMaterial","params":{"roughness":1,"metalness":0},"lights":[{"type":"HemisphereLight","intensity":1},{"type":"DirectionalLight","intensity":0.6,"position":[3,5,4]}],"renderer":{"toneMapping":"NoToneMapping","exposure":1},"bloom":null,"env":"none"},
      "rules": ["градиенты на поверхностях ≤ΔL 0,03 (кроме световых пулов фона)","хейрлайны 1 px только на неподвижных объектах"]
    },
    "soft-shadow": {
      "label": "Мягкие тени",
      "idea": "многослойная тень с реальным спадом (5 слоёв), предметы «парят» над бумагой",
      "css": {"dark":{"surface":"bg.raised","border":"inset 0 0 0 1px rgba(255,255,255,.06)","shadowRest":"0 2px 4px rgba(0,0,0,.25), 0 8px 16px rgba(0,0,0,.25)","shadowFloat":"0 2px 4px rgba(0,0,0,.25), 0 12px 24px rgba(0,0,0,.30), 0 32px 64px rgba(0,0,0,.40)","highlight":"inset 0 1px 0 rgba(255,255,255,.06)","glow":"none","backdrop":"none"},"light":{"surface":"#FFFFFF","border":"inset 0 0 0 1px rgba(INK,.05)","shadowRest":"0 1px 2px rgba(INK,.06), 0 4px 12px rgba(INK,.05)","shadowFloat":"0 1px 1px rgba(INK,.04), 0 2px 4px rgba(INK,.04), 0 8px 16px rgba(INK,.05), 0 24px 48px rgba(INK,.07), 0 56px 112px rgba(INK,.08)","highlight":"none","glow":"цветная тень под акцентом: 0 12px 32px -8px rgba(ACCENT_600,.35)","backdrop":"none"}},
      "three": {"material":"MeshPhysicalMaterial","params":{"roughness":0.55,"metalness":0,"clearcoat":0,"sheen":0.2,"sheenRoughness":0.8},"lights":[{"type":"RectAreaLight","intensity":3,"size":[4,4],"position":[2,4,3]},{"type":"HemisphereLight","intensity":0.6}],"contactShadow":{"opacity":0.35,"blur":2.5},"renderer":{"toneMapping":"AgXToneMapping","exposure":1},"bloom":null,"env":"RoomEnvironment (PMREM)"},
      "rules": ["одна формула тени на фильм","INK = fg.primary светлой схемы (тонированная тень), не чистый #000"]
    },
    "glass-modern": {
      "label": "Современное стекло",
      "idea": "плоские стеклянные панели с верхним бликом и внутренней глубиной; стекло только поверх изображения",
      "css": {"dark":{"surface":"linear-gradient(180deg,rgba(255,255,255,.09),rgba(255,255,255,.03))","border":"inset 0 0 0 1.5px rgba(255,255,255,.15)","shadowRest":"0 1px 1px rgba(0,0,0,.2), 0 3px 6px rgba(0,0,0,.22), 0 10px 20px rgba(0,0,0,.25)","shadowFloat":"0 1px 1px rgba(0,0,0,.2), 0 3px 6px rgba(0,0,0,.22), 0 10px 20px rgba(0,0,0,.25), 0 24px 48px rgba(0,0,0,.3), 0 48px 96px rgba(0,0,0,.35)","highlight":"inset 0 2px 0 rgba(255,255,255,.16), inset 0 -14px 24px rgba(0,0,0,.28)","glow":"none","backdrop":"blur(30px) saturate(140%)"},"light":{"surface":"linear-gradient(180deg,rgba(255,255,255,.72),rgba(255,255,255,.48))","border":"inset 0 0 0 1px rgba(255,255,255,.9)","shadowRest":"0 1px 1px rgba(INK,.04), 0 8px 20px rgba(INK,.08)","shadowFloat":"0 1px 1px rgba(INK,.04), 0 16px 34px rgba(INK,.10), 0 40px 80px rgba(INK,.06)","highlight":"inset 0 1px 0 #FFFFFF","glow":"none","backdrop":"blur(24px) saturate(160%)"}},
      "three": {"material":"MeshPhysicalMaterial","params":{"transmission":1,"thickness":0.8,"roughness":0.22,"ior":1.45,"metalness":0,"clearcoat":1,"clearcoatRoughness":0.08,"attenuationDistance":2.5,"specularIntensity":1,"envMapIntensity":1},"geometry":"только плоские скруглённые плиты (RoundedBox, глубина ≤4% ширины)","lights":[{"type":"env","intensity":1}],"renderer":{"toneMapping":"AgXToneMapping","exposure":1},"bloom":{"strength":0.15,"radius":0.3,"threshold":0.9},"env":"RoomEnvironment (PMREM)"},
      "rules": ["≤2 стеклянных объекта на кадр, никогда стекло на стекле","на плоском фоне стекло читается как серый прямоугольник — нужен образ или градиент под ним","текст на стекле ≥4,5:1 к худшему пикселю фона; иначе скрим 20–30%","запрещено: стеклянные трубки, пузыри, мениск (клиент: «старомодно»)"]
    },
    "clay": {
      "label": "Глина / мягкий пластик",
      "idea": "матовые надутые формы, сатиновый sheen, мягкая цветная тень",
      "css": {"dark":{"surface":"сплошной цвет объекта","border":"none","shadowRest":"0 10px 24px -10px rgba(0,0,0,.5)","shadowFloat":"0 20px 40px -12px rgba(0,0,0,.55)","highlight":"inset 0 2px 1px rgba(255,255,255,.18), inset 0 -10px 18px rgba(0,0,0,.35)","glow":"none","backdrop":"none"},"light":{"surface":"сплошной цвет объекта","border":"none","shadowRest":"0 2px 4px rgba(INK,.08), 0 10px 20px -8px rgba(ACCENT_700,.30)","shadowFloat":"0 2px 4px rgba(INK,.08), 0 18px 36px -12px rgba(ACCENT_700,.38)","highlight":"inset 0 2px 1px rgba(255,255,255,.55), inset 0 -8px 16px rgba(INK,.10)","glow":"none","backdrop":"none"}},
      "three": {"material":"MeshPhysicalMaterial","params":{"roughness":0.62,"metalness":0,"clearcoat":0.08,"clearcoatRoughness":0.6,"sheen":0.6,"sheenRoughness":0.5,"sheenColor":"base→white 50%","envMapIntensity":0.75},"geometry":"RoundedBox radius = 0,2 × меньшей стороны, segments 6; капсулы, сферы, «подушки»","lights":[{"type":"RectAreaLight","intensity":4,"position":[2,4,3]},{"type":"HemisphereLight","intensity":0.7},{"type":"DirectionalLight","intensity":0.8,"role":"rim","position":[-3,2,-4]}],"contactShadow":{"opacity":0.4,"blur":3},"renderer":{"toneMapping":"AgXToneMapping","exposure":1.05},"bloom":null,"env":"мягкая студия: 2 софтбокса"},
      "rules": ["без глянца: clearcoat ≤0,1","без микродеталей и фасок — форма читается силуэтом"]
    },
    "metallic-subtle": {
      "label": "Сатиновый металл",
      "idea": "матовый/сатиновый металл и «фольга» в типографике; никогда зеркальный хром",
      "css": {"dark":{"surface":"linear-gradient(100deg, N300, N400 40%, N200 60%, N300)","border":"inset 0 0 0 1px rgba(255,255,255,.10)","shadowRest":"0 8px 24px rgba(0,0,0,.45)","shadowFloat":"0 2px 4px rgba(0,0,0,.4), 0 24px 56px rgba(0,0,0,.55)","highlight":"inset 0 1px 0 rgba(255,255,255,.22), inset 0 -1px 0 rgba(0,0,0,.4)","glow":"none","backdrop":"none","textFoil":"linear-gradient(180deg, A50 0%, A200 46%, A500 54%, A100 100%) + background-clip:text"},"light":{"surface":"linear-gradient(100deg, N900, N950 40%, N800 60%, N900)","border":"inset 0 0 0 1px rgba(INK,.10)","shadowRest":"0 6px 18px rgba(INK,.12)","shadowFloat":"0 2px 4px rgba(INK,.10), 0 20px 48px rgba(INK,.14)","highlight":"inset 0 1px 0 #FFFFFF","glow":"none","backdrop":"none","textFoil":"linear-gradient(180deg, A700 0%, A500 46%, A800 54%, A600 100%) + background-clip:text"}},
      "three": {"material":"MeshPhysicalMaterial","params":{"metalness":0.9,"roughness":0.32,"anisotropy":0.5,"clearcoat":0.25,"clearcoatRoughness":0.3,"envMapIntensity":1.2},"geometry":"простые тела вращения, плиты, монограммы; без экструдированного хром-текста","lights":[{"type":"env","intensity":1.2},{"type":"DirectionalLight","intensity":1.5,"role":"rim"}],"renderer":{"toneMapping":"ACESFilmicToneMapping","exposure":0.95},"bloom":{"strength":0.1,"radius":0.3,"threshold":0.9},"env":"мягкая градиентная студия (2 больших софтбокса), без высокочастотных HDRI"},
      "rules": ["roughness никогда <0,18 — зеркальный хром читается старомодно","блик-свип (specular sweep) шириной 12–18% объекта, 400–600 px/с, один на кадр"]
    },
    "paper-grain": {
      "label": "Бумага / зерно",
      "idea": "печатная поверхность, вырезанная бумага, тени «бумага на бумаге»",
      "css": {"dark":{"surface":"N150 + зерно multiply/overlay 6%","border":"none","shadowRest":"0 1px 0 rgba(0,0,0,.4), 0 8px 18px -8px rgba(0,0,0,.6)","shadowFloat":"0 1px 0 rgba(0,0,0,.4), 0 12px 28px -10px rgba(0,0,0,.65)","highlight":"inset 0 1px 0 rgba(255,255,255,.04)","glow":"none","backdrop":"none"},"light":{"surface":"N950 + зерно multiply 8%","border":"none","shadowRest":"0 1px 0 rgba(INK,.06), 0 6px 14px -6px rgba(INK,.18)","shadowFloat":"0 1px 0 rgba(INK,.06), 0 6px 14px -6px rgba(INK,.18), 0 18px 40px -16px rgba(INK,.14)","highlight":"none","glow":"none","backdrop":"none"}},
      "three": {"material":"MeshStandardMaterial","params":{"roughness":0.92,"metalness":0,"normalScale":0.15},"geometry":"тонкие плиты (бумага 0,5–2% ширины), процедурная normal-карта шума","lights":[{"type":"DirectionalLight","intensity":1.6,"color":"#FFE7C7","role":"тёплый ключ ~3500 K"},{"type":"HemisphereLight","intensity":0.5}],"renderer":{"toneMapping":"AgXToneMapping","exposure":1},"bloom":null,"env":"none"},
      "rules": ["зерно — свойство поверхности, не UI-текста ≤36 px","смещённые слои «стопки бумаги» 2–4 px"]
    },
    "neon-light": {
      "label": "Свет / неон",
      "idea": "эмиттер с горячим ядром и многомасштабным ореолом; только на тёмной сцене",
      "css": {"dark":{"surface":"сплошной акцент, ядро A50 на внутренних 20–30%","border":"none","shadowRest":"none","shadowFloat":"none","highlight":"none","glow":"0 0 4px rgba(A,.8), 0 0 12px rgba(A,.5), 0 0 32px rgba(A,.3), 0 0 96px rgba(A,.18), 0 0 240px rgba(A,.10)","backdrop":"none"},"light":{"surface":"акцент заливкой","border":"none","shadowRest":"0 6px 20px -6px rgba(A400,.35)","shadowFloat":"0 12px 40px -8px rgba(A400,.30)","highlight":"none","glow":"не работает (аддитивный свет клипуется) → цветная мягкая тень","backdrop":"none"}},
      "three": {"material":"MeshStandardMaterial","params":{"emissiveIntensity":2.5,"roughness":0.6,"metalness":0,"toneMapped":true},"geometry":"линии, плоскости, точки, капсулы; без стеклянных трубок","lights":[{"type":"AmbientLight","intensity":0.1}],"renderer":{"toneMapping":"ACESFilmicToneMapping","exposure":1},"bloom":{"strength":0.75,"radius":0.35,"threshold":0.75},"env":"none (тёмная сцена)"},
      "rules": ["1 эмиттер + 1 эхо на кадр","фон в 200 px от источника ≤ OKLCH L 0,30","яркие ядра — через A50, а не «больше акцента» (стопка в Add клипуется в жёлтый)"]
    }
  },
  "shape": {
    "sharp": {
      "label": "Острый",
      "radii": {"chip":2,"button":2,"card":0,"panel":0,"image":0,"tile":2,"prompt":2},
      "strokes": {"hairline":1.5,"ui":2,"accent":4,"rule":[2,4]},
      "notes": "линейки и рамки — главный графический приём; скругление только на точках",
      "params": {"card":0,"cardSmall":0,"control":0,"chip":0,"pill":0,"media":0,"panel":0,"window":0,"tile":0,"strokes":[1,2,3]}
    },
    "soft": {
      "label": "Мягкий",
      "radii": {"chip":10,"button":14,"card":"clamp(12, 2% ширины, 28)","panel":20,"image":18,"tile":16,"prompt":20},
      "strokes": {"hairline":1,"ui":1.5,"accent":3},
      "notes": "вложенные радиусы концентричны: r_внутр = r_внешн − паддинг",
      "params": {"card":0.045,"cardSmall":0.045,"control":0.25,"chip":0.25,"pill":0.26,"media":0.03,"panel":0.035,"window":0.025,"tile":0.15,"strokes":[1.5,2,3]}
    },
    "round": {
      "label": "Круглый",
      "radii": {"chip":999,"button":"999 (h ≤96) иначе 0,5h","card":"clamp(24, 3,5% ширины, 48)","panel":32,"image":32,"tile":"24% размера (squircle)","prompt":"0,33h"},
      "strokes": {"hairline":1,"ui":1.5,"accent":3},
      "notes": "squircle (corner smoothing 60%) на тайлах и иконках",
      "params": {"card":0.06,"cardSmall":0.06,"control":0.5,"chip":0.5,"pill":0.5,"media":0.045,"panel":0.05,"window":0.028,"tile":0.22,"strokes":[1.5,2,3]}
    },
    "pill": {
      "label": "Капсула",
      "radii": {"chip":999,"button":999,"card":"min(0,5h, 6% ширины)","panel":48,"image":40,"tile":"50% (круг) или 27% (squircle)","prompt":"0,33h (HF) … 0,5h","bar":"w/2 (капсула)"},
      "strokes": {"hairline":1,"ui":1.5,"accent":3},
      "notes": "капсулы и орбы — герой-форма; карточки остаются прямоугольниками с крупным радиусом",
      "params": {"card":0.12,"cardSmall":0.12,"control":0.5,"chip":0.5,"pill":0.5,"media":0.08,"panel":0.08,"window":0.05,"tile":0.3,"strokes":[2,3,4]}
    }
  },
  "motionPersonality": {
    "productive": {
      "label": "Продуктивный (= Higgsfield house)",
      "ease": {"enter":[0.05,0.7,0.1,1],"exit":[0.3,0,0.8,0.15],"move":[0.2,0,0,1],"ui":[0.2,0,0.38,0.9],"emphasis":[0.4,0.14,0.3,1],"camera":[0.65,0,0.35,1],"loop":"linear"},
      "durMult": 1,
      "staggerFrames": {"default":3,"range":[2,4]},
      "overshoot": {"maxScalePct":6,"allowedOn":["chip","pill","sparkle","sticker"],"never":["logo","headline","body"]},
      "spring": null,
      "camera": {"verbs":["push-in"],"pushPerShot":[1.14,1.6],"idleDriftPctPerSec":[1,2],"whipMax15s":1,"orbitDegPerSec":4},
      "transitions": ["match-cut","push","mask"],
      "textReveal": "маска строки снизу вверх; строка 2 через 3–4 кадра; подсветка ещё через 4–6",
      "holdMult": 1,
      "motionBlurDeg": 180,
      "bpm": [110,125],
      "fps": 24,
      "params": {"ease":{"enter":[0.05,0.7,0.1,1],"exit":[0.3,0,0.8,0.15],"move":[0.2,0,0,1],"ui":[0.2,0,0.38,0.9],"expressive":[0.4,0.14,0.3,1],"camera":[0.65,0,0.35,1]},"durMul":1,"staggerMul":1,"holdMult":1,"shutter":180,"cameraSpeed":1,"verbs":["pushIn"],"transitions":["matchCut","push","maskWipe"]}
    },
    "expressive": {
      "label": "Экспрессивный",
      "ease": {"enter":[0.16,1,0.3,1],"exit":[0.7,0,0.84,0],"move":[0.83,0,0.17,1],"ui":[0.2,0,0,1],"emphasis":[0.34,1.56,0.64,1],"camera":[0.76,0,0.24,1],"loop":"linear"},
      "durMult": 0.85,
      "staggerFrames": {"default":2,"range":[2,3]},
      "overshoot": {"maxScalePct":10,"allowedOn":["chip","pill","card","object","sticker"],"never":["logo","body"]},
      "spring": null,
      "camera": {"verbs":["push-in","whip"],"pushPerShot":[1.2,2],"idleDriftPctPerSec":[2,4],"whipMax15s":1,"orbitDegPerSec":10},
      "transitions": ["whip","morph","match-cut","flash"],
      "textReveal": "по словам: scale 0,9→1 + blur 8→0 px, шаг 2 кадра",
      "holdMult": 0.9,
      "motionBlurDeg": 180,
      "bpm": [120,140],
      "fps": 24,
      "params": {"ease":{"enter":[0.16,1,0.3,1],"exit":[0.7,0,0.84,0],"move":[0.83,0,0.17,1],"ui":[0.2,0,0,1],"expressive":[0.34,1.56,0.64,1],"camera":[0.76,0,0.24,1]},"durMul":0.85,"staggerMul":0.667,"holdMult":0.9,"shutter":180,"cameraSpeed":1.2,"verbs":["pushIn","whip"],"transitions":["whip","morph","matchCut","flash"]}
    },
    "luxury-slow": {
      "label": "Люкс, медленный",
      "ease": {"enter":[0.19,1,0.22,1],"exit":[0.45,0,0.55,1],"move":[0.45,0,0.55,1],"ui":[0.25,0.1,0.25,1],"emphasis":[0.19,1,0.22,1],"camera":[0.37,0,0.63,1],"loop":"linear"},
      "durMult": 1.6,
      "staggerFrames": {"default":6,"range":[5,8]},
      "overshoot": {"maxScalePct":0,"allowedOn":[],"never":["всё"]},
      "spring": null,
      "camera": {"verbs":["slow push-in","slow orbit"],"pushPerShot":[1.03,1.1],"idleDriftPctPerSec":[0.5,1.5],"whipMax15s":0,"orbitDegPerSec":3},
      "transitions": ["dissolve","mask","match-cut","dip"],
      "textReveal": "opacity 0→1 + y +12→0 px + трекинг +0,06 em → целевой за 1,2 с; строки через 8 кадров",
      "holdMult": 1.3,
      "motionBlurDeg": 180,
      "bpm": [70,96],
      "fps": 24,
      "params": {"ease":{"enter":[0.19,1,0.22,1],"exit":[0.45,0,0.55,1],"move":[0.45,0,0.55,1],"ui":[0.25,0.1,0.25,1],"expressive":[0.19,1,0.22,1],"camera":[0.37,0,0.63,1]},"durMul":1.6,"staggerMul":2,"holdMult":1.3,"shutter":180,"cameraSpeed":0.6,"verbs":["pushIn","orbit"],"transitions":["crossDissolve","maskWipe","matchCut","dip"]}
    },
    "playful-bouncy": {
      "label": "Игривый, пружинный",
      "ease": {"enter":[0.34,1.56,0.64,1],"exit":[0.36,0,0.66,-0.56],"move":[0.68,-0.6,0.32,1.6],"ui":[0.175,0.885,0.32,1.275],"emphasis":[0.34,1.56,0.64,1],"camera":[0.65,0,0.35,1],"loop":"linear"},
      "durMult": 0.9,
      "staggerFrames": {"default":3,"range":[2,4]},
      "overshoot": {"maxScalePct":15,"allowedOn":["chip","pill","card","object","sticker","word"],"never":["logo","body"],"squashStretchPct":8},
      "spring": {"freqHz":2,"damping":0.6,"overshootPct":9.5,"settle2pctSec":0.53,"formula":"x(t)=1−e^(−ζωt)(cos ω_d t + ζω/ω_d · sin ω_d t), ω=2πf, ω_d=ω√(1−ζ²)"},
      "camera": {"verbs":["locked","bouncy dolly"],"pushPerShot":[1.05,1.3],"idleDriftPctPerSec":[0,1],"whipMax15s":1,"orbitDegPerSec":6},
      "transitions": ["morph","push","mask"],
      "textReveal": "по словам: pop scale 0→1,08→1 (back-out), шаг 2 кадра; заголовок ≤6% overshoot",
      "holdMult": 1,
      "motionBlurDeg": 180,
      "bpm": [110,128],
      "fps": 24,
      "params": {"ease":{"enter":[0.34,1.56,0.64,1],"exit":[0.36,0,0.66,-0.56],"move":[0.68,-0.6,0.32,1.6],"ui":[0.175,0.885,0.32,1.275],"expressive":[0.34,1.56,0.64,1],"camera":[0.65,0,0.35,1]},"durMul":0.9,"staggerMul":1,"holdMult":1,"shutter":180,"cameraSpeed":1,"verbs":["static","truck"],"transitions":["morph","push","maskWipe"]}
    },
    "cinematic": {
      "label": "Кинематографичный",
      "ease": {"enter":[0.25,0.46,0.45,0.94],"exit":[0.55,0.06,0.68,0.19],"move":[0.65,0,0.35,1],"ui":[0.33,0,0.2,1],"emphasis":[0.7,0,0.2,1],"camera":[0.45,0,0.55,1],"loop":"linear"},
      "durMult": 1.35,
      "staggerFrames": {"default":4,"range":[4,6]},
      "overshoot": {"maxScalePct":0,"allowedOn":[],"never":["всё"]},
      "spring": null,
      "camera": {"verbs":["dolly","truck","slow orbit"],"pushPerShot":[1.05,1.25],"idleDriftPctPerSec":[1,3],"whipMax15s":0,"orbitDegPerSec":8,"rackFocusFrames":[12,18],"parallax":[1,0.6,0.3]},
      "transitions": ["match-cut","dissolve","dip","mask"],
      "textReveal": "blur 12→0 + opacity за 18 кадров; трекинг дрейфует −0,01 em за шот",
      "holdMult": 1.2,
      "motionBlurDeg": 216,
      "bpm": [80,110],
      "fps": 24,
      "params": {"ease":{"enter":[0.25,0.46,0.45,0.94],"exit":[0.55,0.06,0.68,0.19],"move":[0.65,0,0.35,1],"ui":[0.33,0,0.2,1],"expressive":[0.7,0,0.2,1],"camera":[0.45,0,0.55,1]},"durMul":1.35,"staggerMul":1.333,"holdMult":1.2,"shutter":216,"cameraSpeed":0.75,"verbs":["truck","orbit","pushIn"],"transitions":["matchCut","crossDissolve","dip","maskWipe"]}
    },
    "glitch-tech": {
      "label": "Глитч / тех",
      "ease": {"enter":{"steps":4,"position":"end"},"exit":{"steps":3,"position":"start"},"move":[0.9,0,0.1,1],"ui":[0.2,0,0,1],"emphasis":{"steps":6,"position":"end"},"camera":"linear","loop":"linear","position":[0.2,0,0,1]},
      "durMult": 0.7,
      "staggerFrames": {"default":1,"range":[1,2]},
      "overshoot": {"maxScalePct":0,"allowedOn":[],"never":["всё"],"jitterPx":[2,6],"jitterFrames":[1,2]},
      "spring": null,
      "camera": {"verbs":["locked","snap-zoom"],"pushPerShot":[1.25,1.25],"snapZoomFrames":2,"idleDriftPctPerSec":[0,0],"whipMax15s":0,"orbitDegPerSec":0},
      "transitions": ["hard-cut","glitch-slice","mask","flash"],
      "textReveal": "type-on 24–40 знаков/с с кареткой (12 кадров вкл / 12 выкл) или scramble 8–12 кадров на слово",
      "holdMult": 1,
      "motionBlurDeg": 0,
      "bpm": [120,140],
      "fps": 24,
      "safety": "RGB-сдвиг ≤4 px на 1–2 кадра; вспышки ≤3/с (WCAG 2.3.1), площадь мигания ≤25% кадра",
      "params": {"ease":{"enter":{"steps":4,"position":"end"},"exit":{"steps":3,"position":"start"},"move":[0.9,0,0.1,1],"ui":[0.2,0,0,1],"expressive":{"steps":6,"position":"end"},"camera":"linear"},"durMul":0.7,"staggerMul":0.333,"holdMult":1,"shutter":0,"cameraSpeed":1.4,"verbs":["static","pushIn"],"transitions":["hardCut","slice","maskWipe","flash"]}
    }
  },
  "composition": {
    "minimal-centred": {
      "label": "Минимальный, центр",
      "axis": "x960 / y540; стек титула центрирован на y490–540",
      "grid": "12 кол. как направляющие (поля 96, гаттер 24, колонка 122)",
      "negativeSpace": [60,85],
      "maxGroups": 3,
      "heroToNextArea": 3,
      "focal": [[0.5,0.48]],
      "archetypes": ["centre","macro","orbit","full-bleed (payoff)","Z / угловая пара (≤1 off-axis семья на фильм)"],
      "align": "center",
      "nine16": "тот же центр; стек по вертикали, зона титула y620–1000",
      "params": {"primaryAxis":"centre","offAxisFamily":"thirds","archetypesPreferred":["centre","fullBleed","macro"],"centredShareMax":0.75}
    },
    "editorial-asymmetric": {
      "label": "Редакционная асимметрия",
      "axis": "левая ось = начало 2-й колонки (x242); текстовый блок 5 кол. (706 px)",
      "grid": "12 кол.; сплиты 5/7, 4/8, 7/5; флаш-лефт, рваный правый край",
      "negativeSpace": [45,65],
      "maxGroups": 4,
      "heroToNextArea": 2.5,
      "focal": [[0.333,0.333],[0.667,0.667]],
      "archetypes": ["thirds","editorial split","full-bleed с краем","индекс-номер"],
      "align": "left",
      "nine16": "киккер + заголовок в верхней трети (y220–700), медиа ниже",
      "params": {"primaryAxis":"leftAxis","offAxisFamily":"editorialSplit","archetypesPreferred":["editorialSplit","thirds","fullBleed"],"centredShareMax":0.4}
    },
    "maximal-collage": {
      "label": "Контролируемый коллаж",
      "axis": "одна главная фигура + 2 глубинных плана",
      "grid": "3 плана глубины с параллаксом 1 / 0,6 / 0,3",
      "negativeSpace": [25,45],
      "maxGroups": 4,
      "heroToNextArea": 4,
      "focal": [[0.5,0.5],[0.4,0.45]],
      "archetypes": ["exploded stack","коллаж-фан","стикеры (поворот ±2…8°)","перекрытие 10–30%"],
      "align": "free",
      "nine16": "коллаж собирается заново: герой сверху, 2 спутника, текст в спокойной зоне ≥20% кадра",
      "params": {"primaryAxis":"centre","offAxisFamily":"flanks","archetypesPreferred":["orbit","explodedStack","centre"],"centredShareMax":0.6}
    },
    "keynote-left-axis": {
      "label": "Keynote, левая ось",
      "axis": "единая левая ось x144 (96–160) для всего текста",
      "grid": "текст 6–7 кол. слева, медиа справа (x1000–1824) или full-bleed со скримом 0→60% слева",
      "negativeSpace": [40,60],
      "maxGroups": 3,
      "heroToNextArea": 2,
      "focal": [[0.25,0.45],[0.72,0.5]],
      "archetypes": ["step-слайд","split","UI-демо справа"],
      "align": "left",
      "nine16": "ось x72; текст сверху, медиа снизу; базовая линия одна на всю серию",
      "params": {"primaryAxis":"leftAxis","offAxisFamily":"zCorner","archetypesPreferred":["thirds","zCorner","centre"],"centredShareMax":0.5}
    },
    "poster-type-led": {
      "label": "Плакат, ведёт шрифт",
      "axis": "шрифт = изображение: 60–95% ширины кадра",
      "grid": "4–6 кол. плаката; строки выравниваются по ширине кеглем",
      "negativeSpace": [20,50],
      "maxGroups": 2,
      "heroToNextArea": 5,
      "focal": [[0.5,0.5]],
      "archetypes": ["мега-слово (кроп ≤15%, кроме имени продукта)","вертикальный стек 2–4 слов","один поддерживающий элемент"],
      "align": "left или justified-by-size",
      "nine16": "стек 3–5 строк по ширине x72–1008",
      "params": {"primaryAxis":"centre","offAxisFamily":"thirds","archetypesPreferred":["centre","macro","fullBleed"],"centredShareMax":0.75}
    }
  },
  "density": {
    "sparse": {"maxGroups":2,"maxElements":4,"maxTextBlocks":2,"maxWords":8,"negativeSpace":[65,85],"beatsPer15s":[5,6],"avgShotSec":[2.5,3],"params":{"maxGroups":2,"maxElements":4,"maxTextBlocks":2,"maxWords":8,"negativeSpacePct":[65,85]}},
    "balanced": {"maxGroups":4,"maxElements":8,"maxTextBlocks":3,"maxWords":15,"negativeSpace":[45,65],"beatsPer15s":[7,7],"avgShotSec":[2,2.2],"params":{"maxGroups":4,"maxElements":8,"maxTextBlocks":3,"maxWords":15,"negativeSpacePct":[45,65]}},
    "rich": {
      "maxGroups": 4,
      "maxElements": 14,
      "maxTextBlocks": 4,
      "maxWords": 20,
      "negativeSpace": [25,45],
      "beatsPer15s": [9,10],
      "avgShotSec": [1.5,1.7],
      "note": "только на пике ритма, чередовать со sparse; групп всё равно ≤4",
      "params": {"maxGroups":4,"maxElements":14,"maxTextBlocks":4,"maxWords":20,"negativeSpacePct":[25,45]}
    }
  },
  "texture": {
    "none": {"css":null,"note":"чистая поверхность; при больших тёмных градиентах всё равно дизер на экспорте σ≈1–1,5%","params":{"kind":"none","amount":0}},
    "grain": {
      "css": "<svg><filter id=g><feTurbulence type=fractalNoise baseFrequency=.9 numOctaves=2 stitchTiles=stitch/></filter><rect width=100% height=100% filter=url(#g)/></svg> mix-blend-mode:overlay",
      "opacity": {"dark":[0.05,0.08],"light":[0.03,0.05]},
      "animate": "пересев seed каждые 2 кадра (12 к/с) или статично",
      "note": "зерно стоит битрейта: ≤8% на тёмном, проверить загрузкой в соцсеть",
      "params": {"kind":"grain","amount":0.03}
    },
    "dot-grid": {
      "css": "radial-gradient(circle, FG 1px, transparent 1.2px) 0 0 / 28px 28px; маска radial 100%→0 к краям",
      "opacity": {"dark":[0.05,0.08],"light":[0.06,0.1]},
      "animate": "параллакс 0,3× камеры",
      "note": "шаг 24–32 px, точка 2 px",
      "params": {"kind":"dotGrid","amount":0.04}
    },
    "halftone": {
      "css": "radial-gradient(circle, ACCENT 40%, transparent 41%) 0 0 / 12px 12px, поворот 45°; маска линейная 0→100%",
      "opacity": {"dark":[0.12,0.25],"light":[0.15,0.35]},
      "animate": "scale ≤1,05 (иначе муар)",
      "note": "ячейка 8–14 px; только как орнамент/тень, ≤15–20% площади кадра",
      "params": {"kind":"halftone","amount":0.04}
    },
    "scanlines": {
      "css": "repeating-linear-gradient(0deg, rgba(0,0,0,.35) 0 1px, transparent 1px 4px)",
      "opacity": {"dark":[0.04,0.08],"light":null},
      "animate": "медленный сдвиг 20 px/с (опц.)",
      "note": "только на тёмном; не поверх смыслового текста <64 px",
      "params": {"kind":"scanlines","amount":0.03}
    }
  },
  "compatibility": [
    "neon-light только на тёмной сцене; на светлой он автоматически становится цветной мягкой тенью (derive делает это сам).",
    "glass-modern требует изображения или градиента под стеклом; с texture: none и плоским фоном не используется.",
    "luxury-slow и cinematic несовместимы с density: rich (длинные холды + много элементов = перегруз).",
    "playful-bouncy не сочетается с didone-luxury и condensed-display: пружина ломает тон шрифта.",
    "pixel и mono-terminal — только shape: sharp или round; pill спорит с сеткой символов.",
    "palette: mono + motion: glitch-tech + flash: следить за правилом ≤ 3 смен полярности в секунду.",
    "pastel никогда не даёт цвет текста; текст — инк, действие — насыщенная ступень с белым текстом."
  ]
}
```

### styles (без разрешённых значений)

```json
{
  "higgsfield": {
    "name": "Higgsfield",
    "status": "approved-current",
    "mood": ["уверенный","точный","минимальный, но творческий","технологичный","кинематографичный"],
    "axes": {"typeVoice":"neo-grotesk","typeVoiceSecondary":"grotesk-tech","palette":"signal","material":"flat","materialSecondary":"glass-modern","shape":"pill","motion":"productive","composition":"minimal-centred","density":"sparse","texture":"grain"},
    "seeds": {"accent":"#D1FE17","accent2":"#ED1572"},
    "paletteMode": "signal",
    "radii": {"chip":999,"button":999,"card":"min(0,5h, 6% ширины)","panel":48,"image":40,"tile":"50% (круг) или 27% (squircle)","prompt":"0,33h (HF) … 0,5h","bar":"w/2 (капсула)"},
    "strokes": {"hairline":1,"ui":1.5,"accent":3},
    "density": {"base":"sparse","maxGroups":2,"maxElements":4,"maxTextBlocks":2,"maxWords":8,"negativeSpace":[65,85],"beatsPer15s":[5,6],"avgShotSec":[2.5,3]},
    "do": ["одна идея на бит, центр — только когда он идеален","лайм как свет и действие; ≤8% площади","генерации — плейсхолдер plate() «✦ GENERATION» + описание шота","партнёр — простой текст («Claude»)","дисплей с отрицательным трекингом (−3…−6%)","expo-out ~0,6 с, stagger 2–4 кадра"],
    "dont": ["детальный старомодный 3D: стеклянные трубки, мениск, пузыри, хром","клаттер: HUD, счётчики, угловые метки, сателлиты","странные или неясные идеи","лайм текстом/линией на светлом","Space Grotesk для кириллицы и italic","overshoot на логотипе и заголовке"]
  },
  "swiss-editorial": {
    "name": "Swiss Editorial",
    "status": "preset",
    "mood": ["рациональный","уверенный","редакционный","чистый","интернациональный"],
    "axes": {"typeVoice":"neo-grotesk","palette":"signal","material":"flat","shape":"sharp","motion":"productive","composition":"editorial-asymmetric","density":"balanced","texture":"none"},
    "seeds": {"accent":"#E4321B"},
    "paletteMode": "signal",
    "radii": {"chip":2,"button":2,"card":0,"panel":0,"image":0,"tile":2,"prompt":2},
    "strokes": {"hairline":1.5,"ui":2,"accent":4,"rule":[2,4]},
    "density": {"base":"balanced","maxGroups":4,"maxElements":8,"maxTextBlocks":3,"maxWords":15,"negativeSpace":[45,65],"beatsPer15s":[7,7],"avgShotSec":[2,2.2]},
    "do": ["одна гарнитура, контраст масштабом ≥2,5×","строгая сетка: каждый край — по колонке","числа как главные объекты (tnum)"],
    "dont": ["тени, стекло, свечения","центрированный текст в длинных блоках","больше одного акцентного цвета","диагональные движения"]
  },
  "luxury-serif": {
    "name": "Luxury Serif",
    "status": "preset",
    "mood": ["тихий","роскошный","медленный","кутюрный","интимный"],
    "axes": {"typeVoice":"didone-luxury","palette":"tonal","material":"metallic-subtle","shape":"sharp","motion":"luxury-slow","composition":"minimal-centred","density":"sparse","texture":"none"},
    "seeds": {"accent":"#C9AE7C","accent2":"#5E1A22"},
    "paletteMode": "tonal",
    "radii": {"chip":2,"button":2,"card":0,"panel":0,"image":0,"tile":2,"prompt":2},
    "strokes": {"hairline":1.5,"ui":2,"accent":4,"rule":[2,4]},
    "density": {"base":"sparse","maxGroups":2,"maxElements":4,"maxTextBlocks":2,"maxWords":8,"negativeSpace":[65,85],"beatsPer15s":[5,6],"avgShotSec":[2.5,3]},
    "do": ["медленные растворения и дыхание камеры ≤2%/с","контраст: огромный кегль заголовка — крошечные разреженные капители","один металл на фильм"],
    "dont": ["overshoot, пружины, whip","жирнее 600 на дисплее","больше двух цветов кроме нейтралей","мелкий Playfair <120 px в движении (волосяные штрихи мерцают)"]
  },
  "playful-pop": {
    "name": "Playful Pop",
    "status": "preset",
    "mood": ["радостный","смелый","«конфетный»","пружинистый","дружелюбный"],
    "axes": {"typeVoice":"quirky-grotesk","palette":"duotone","material":"clay","shape":"round","motion":"playful-bouncy","composition":"maximal-collage","density":"balanced","texture":"halftone"},
    "seeds": {"accent":"#FF5FA2","accent2":"#2ED3A0","accent3":"#FFD23F"},
    "paletteMode": "duotone",
    "radii": {"chip":999,"button":"999 (h ≤96) иначе 0,5h","card":"clamp(24, 3,5% ширины, 48)","panel":32,"image":32,"tile":"24% размера (squircle)","prompt":"0,33h"},
    "strokes": {"hairline":1,"ui":1.5,"accent":3},
    "density": {"base":"balanced","maxGroups":4,"maxElements":8,"maxTextBlocks":3,"maxWords":15,"negativeSpace":[45,65],"beatsPer15s":[7,7],"avgShotSec":[2,2.2]},
    "do": ["пружина на объектах и стикерах (overshoot до 15%)","крупные цветовые поля вместо мелких деталей","мягкие цветные тени под объектами"],
    "dont": ["белый текст на пастельных полях","больше 3 цветов","пружина на логотипе и длинном тексте","одновременно двигать >1 героя"]
  },
  "cinematic-noir": {
    "name": "Cinematic Noir",
    "status": "preset",
    "mood": ["мрачный","драматичный","загадочный","плёночный","сдержанный"],
    "axes": {"typeVoice":"condensed-display","palette":"mono","material":"metallic-subtle","shape":"sharp","motion":"cinematic","composition":"editorial-asymmetric","density":"sparse","texture":"grain"},
    "seeds": {"accent":"#E9A04A","accent2":"#5E9FAD"},
    "paletteMode": "mono",
    "radii": {"chip":2,"button":2,"card":0,"panel":0,"image":0,"tile":2,"prompt":2},
    "strokes": {"hairline":1.5,"ui":2,"accent":4,"rule":[2,4]},
    "density": {"base":"sparse","maxGroups":2,"maxElements":4,"maxTextBlocks":2,"maxWords":8,"negativeSpace":[65,85],"beatsPer15s":[5,6],"avgShotSec":[2.5,3]},
    "do": ["длинные планы, одно непрерывное движение камеры на шот","rack focus между планами","тьма как пространство: 70–85% кадра"],
    "dont": ["яркие насыщенные заливки","пружины и overshoot","мелкий текст <48 px на смысловых битах","вспышки чаще 1 в 3 с"]
  },
  "soft-pastel-ui": {
    "name": "Soft Pastel UI",
    "status": "preset",
    "mood": ["спокойный","доступный","воздушный","оптимистичный","мягкий"],
    "axes": {"typeVoice":"geometric","palette":"pastel","material":"soft-shadow","materialSecondary":"glass-modern","shape":"round","motion":"productive","composition":"minimal-centred","density":"balanced","texture":"grain"},
    "seeds": {"accent":"#9D8CFF","accent2":"#FFB199"},
    "paletteMode": "pastel",
    "radii": {"chip":999,"button":"999 (h ≤96) иначе 0,5h","card":"clamp(24, 3,5% ширины, 48)","panel":32,"image":32,"tile":"24% размера (squircle)","prompt":"0,33h"},
    "strokes": {"hairline":1,"ui":1.5,"accent":3},
    "density": {"base":"balanced","maxGroups":4,"maxElements":8,"maxTextBlocks":3,"maxWords":15,"negativeSpace":[45,65],"beatsPer15s":[7,7],"avgShotSec":[2,2.2]},
    "do": ["мягкие 5-слойные тени","одна насыщенная ступень для кнопки действия","крупный UI ×1,5–2,4 без мелочи"],
    "dont": ["неон и аддитивные свечения","чёрный #000 текст (только тонированный инк)","больше двух пастельных тонов","резкие whip и вспышки"]
  },
  "tech-terminal": {
    "name": "Tech Terminal",
    "status": "preset",
    "mood": ["точный","инженерный","«гиковский»","быстрый","честный"],
    "axes": {"typeVoice":"mono-terminal","palette":"signal","material":"flat","shape":"sharp","motion":"glitch-tech","composition":"keynote-left-axis","density":"balanced","texture":"scanlines"},
    "seeds": {"accent":"#2BD9FF","accent2":"#FFB224"},
    "paletteMode": "signal",
    "radii": {"chip":2,"button":2,"card":0,"panel":0,"image":0,"tile":2,"prompt":2},
    "strokes": {"hairline":1.5,"ui":2,"accent":4,"rule":[2,4]},
    "density": {"base":"balanced","maxGroups":4,"maxElements":8,"maxTextBlocks":3,"maxWords":15,"negativeSpace":[45,65],"beatsPer15s":[7,7],"avgShotSec":[2,2.2]},
    "do": ["type-on с реальной скоростью 24–40 зн/с","состояния [ RUN ] → [ OK ] вместо иконок","данные таблицей с tnum"],
    "dont": ["RGB-сдвиг дольше 2 кадров","зелёный фосфор","скевоморфные CRT-рамки","вспышки >3/с"]
  },
  "brutalist-raw": {
    "name": "Brutalist Raw",
    "status": "preset",
    "mood": ["сырой","громкий","честный","дерзкий","структурный"],
    "axes": {"typeVoice":"expanded-display","palette":"signal","material":"flat","shape":"sharp","motion":"glitch-tech","composition":"poster-type-led","density":"rich","texture":"halftone"},
    "seeds": {"accent":"#FFD500"},
    "paletteMode": "signal",
    "radii": {"chip":2,"button":2,"card":0,"panel":0,"image":0,"tile":2,"prompt":2},
    "strokes": {"hairline":1.5,"ui":2,"accent":4,"rule":[2,4]},
    "density": {"base":"rich","maxGroups":4,"maxElements":14,"maxTextBlocks":4,"maxWords":20,"negativeSpace":[25,45],"beatsPer15s":[9,10],"avgShotSec":[1.5,1.7],"note":"только на пике ритма, чередовать со sparse; групп всё равно ≤4"},
    "do": ["огромный кегль, плотный стек, видимая сетка","одна сигнальная жёлтая плита в чёрной рамке","моно-аннотации со стрелками","ксерокс-полутон в фотографиях"],
    "dont": ["размытые тени, стекло, градиенты","скругления","пружины","больше одного цвета кроме ч/б"]
  },
  "organic-editorial": {
    "name": "Organic Editorial",
    "status": "preset",
    "mood": ["тёплый","человечный","природный","вдумчивый","рукотворный"],
    "axes": {"typeVoice":"editorial-serif","palette":"tonal","material":"paper-grain","shape":"soft","motion":"luxury-slow","composition":"editorial-asymmetric","density":"balanced","texture":"grain"},
    "seeds": {"accent":"#C2643F","accent2":"#6F8F5E"},
    "paletteMode": "tonal",
    "radii": {"chip":10,"button":14,"card":"clamp(12, 2% ширины, 28)","panel":20,"image":18,"tile":16,"prompt":20},
    "strokes": {"hairline":1,"ui":1.5,"accent":3},
    "density": {"base":"balanced","maxGroups":4,"maxElements":8,"maxTextBlocks":3,"maxWords":15,"negativeSpace":[45,65],"beatsPer15s":[7,7],"avgShotSec":[2,2.2]},
    "do": ["тёплый ключевой свет","медленное «дыхание» (scale 1→1,02 за 4 с)","фото — главный носитель цвета"],
    "dont": ["неон, глянец, хром","холодные синие нейтрали","больше двух земляных акцентов","жёсткие вспышки"]
  },
  "y2k-chrome-modern": {
    "name": "Y2K Chrome Modern",
    "status": "preset",
    "mood": ["футуристичный","глянцевый","эйфоричный","цифровая мода","оптимистичный"],
    "axes": {"typeVoice":"expanded-display","palette":"spectral","material":"metallic-subtle","materialSecondary":"glass-modern","shape":"pill","motion":"expressive","composition":"minimal-centred","density":"balanced","texture":"none"},
    "seeds": {"accent":"#8FE3FF","accent2":"#D58BFF"},
    "paletteMode": "spectral",
    "radii": {"chip":999,"button":999,"card":"min(0,5h, 6% ширины)","panel":48,"image":40,"tile":"50% (круг) или 27% (squircle)","prompt":"0,33h (HF) … 0,5h","bar":"w/2 (капсула)"},
    "strokes": {"hairline":1,"ui":1.5,"accent":3},
    "density": {"base":"balanced","maxGroups":4,"maxElements":8,"maxTextBlocks":3,"maxWords":15,"negativeSpace":[45,65],"beatsPer15s":[7,7],"avgShotSec":[2,2.2]},
    "do": ["одна глянцевая героиня-форма","блик-свип по шрифту один раз на шот","холодные хромовые нейтрали"],
    "dont": ["зеркальный хром и экструдированный 3D-текст (старомодно)","стразы, звёзды-блёстки повсюду","зелёные оттенки в градиенте","больше двух стеклянных панелей"]
  },
  "kinetic-type": {
    "name": "Kinetic Type",
    "status": "preset",
    "mood": ["ритмичный","энергичный","смелый","музыкальный","типографический"],
    "axes": {"typeVoice":"variable-kinetic","palette":"mono","material":"flat","shape":"sharp","motion":"expressive","composition":"poster-type-led","density":"sparse","texture":"none"},
    "seeds": {"accent":"#3346FF"},
    "paletteMode": "mono",
    "radii": {"chip":2,"button":2,"card":0,"panel":0,"image":0,"tile":2,"prompt":2},
    "strokes": {"hairline":1.5,"ui":2,"accent":4,"rule":[2,4]},
    "density": {"base":"sparse","maxGroups":2,"maxElements":4,"maxTextBlocks":2,"maxWords":8,"negativeSpace":[65,85],"beatsPer15s":[5,6],"avgShotSec":[2.5,3]},
    "do": ["анимировать оси, а не масштаб","каждое слово держится ≥20 кадров","одна ультрамариновая доля на фразу"],
    "dont": ["больше 3 слов в кадре","мерцающие инверсии чаще 3/с","декоративные объекты рядом со шрифтом","кернинговые дыры при wdth 125 (трекинг −0,04)"]
  },
  "dot-matrix": {
    "name": "Dot Matrix",
    "status": "preset",
    "mood": ["минимальный","цифровой","приборный","модерн-ретро","холодный"],
    "axes": {"typeVoice":"pixel","palette":"mono","material":"neon-light","shape":"round","motion":"glitch-tech","composition":"minimal-centred","density":"sparse","texture":"dot-grid"},
    "seeds": {"accent":"#F4F4F0","accent2":"#FF3B30"},
    "paletteMode": "mono",
    "radii": {"chip":999,"button":"999 (h ≤96) иначе 0,5h","card":"clamp(24, 3,5% ширины, 48)","panel":32,"image":32,"tile":"24% размера (squircle)","prompt":"0,33h"},
    "strokes": {"hairline":1,"ui":1.5,"accent":3},
    "density": {"base":"sparse","maxGroups":2,"maxElements":4,"maxTextBlocks":2,"maxWords":8,"negativeSpace":[65,85],"beatsPer15s":[5,6],"avgShotSec":[2.5,3]},
    "do": ["числа и короткие слова","мягкое LED-свечение точек на тёмном","чистая тьма вокруг"],
    "dont": ["Doto меньше 96 px","отрицательный трекинг","цветные заливки","глитч-эффекты (это не glitch, а прибор)"]
  }
}
```
