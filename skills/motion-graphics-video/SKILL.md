---
name: motion-graphics-video
description: Use when building a rendered motion-graphics video or overlay (launch video, logo animation, SaaS-overlay card on talking-head footage, channel intro) with Claude writing real HTML/CSS/SVG/GSAP and a code-to-video renderer, instead of hand-keyframing in After Effects. Triggers on - make a launch video, animate this logo, build a motion graphic overlay, create an intro/explainer video, review this motion-graphics render.
---

# Motion-graphics video, built from code

Claude cannot generate video the way a diffusion/video model can — it writes
code that draws each frame, then a renderer stitches the frames into an MP4.
Which renderer and how precisely you brief it determines whether the result
looks like a template or like a studio reel. Distilled from public
discussion of HyperFrames/Remotion-based workflows (a YouTube walkthrough and
two creators' write-ups of their own build process); reorganized here around
company-os's own registered tools rather than reproduced verbatim — the
original write-ups are personal lead-magnet documents, not open-source
repos, so they aren't vendored into this repo.

## Pick the renderer, name it explicitly in the brief

Never let Claude fall back to building its own ad hoc rendering tool from
scratch — results are inconsistent. Name one of the registered renderers up
front:

- **`heygen-com-hyperframes`** (`external/heygen-com-hyperframes`) — HTML
  file with `data-start`/`data-duration` timing, GSAP drives motion,
  `npx hyperframes check/snapshot/render` is the verify loop. Default choice.
- **`remotion-dev-skills`** (`external/remotion-dev-skills`) — React-based
  alternative; reach for it when the task is already a React codebase and
  Remotion's component model is a more natural fit than raw HTML/GSAP.
- **`diffusionstudio-core`/`diffusionstudio-editor`** (`external/diffusionstudio-*`)
  — browser-based WebCodecs compositing engine; reach for this when the task
  wants captions/effects/transitions as first-class timeline operations
  rather than hand-written HTML/GSAP.
- **`latent-spaces-brag`** (`external/latent-spaces-brag`) — one-command
  launch video for a *finished project*, not a from-scratch brief. Pairs
  with hyperframes/remotion for the render step.

Tested side by side, the *same* brief produces materially better, more
consistent output with a named framework than without one — this single
line is the second-highest-leverage thing in the whole brief, after the
QUALITY CHECK loop below.

**If the renderer is HyperFrames, naming it is not enough — name the
workflow too.** HyperFrames routes "make me a product video" requests to
different workflows (`/product-launch-video`, `/general-video` companion
mode, `/faceless-explainer`, etc.) with materially different defaults for
pacing and structure. Picking the wrong one produces a video that's well
executed but the wrong *genre* — e.g. `/general-video` companion mode
defaulting to a slow narrative vignette when the brief actually wanted a
launch reel. If a reviewed draft comes back as "boring" or "doesn't feel
like X," check whether the workflow itself matches the intent before
reworking pacing, color, or cuts — a slow film made faster is still a film.

**Showing real content is not a story by itself.** Pulling in real product
UI/data (as REAL CONTENT below requires) stops invented filler, but it
doesn't by itself assert why any of it matters. Every beat still needs a
stated headline — a claim, not just a visual — or the result reads as a
sequence of screenshots with good typography.

**Budget screen time proportional to the product's real breadth.** Don't
let the single easiest-to-dramatize mechanic (one feature, one flow, one
error state) consume most of the runtime just because it animates well —
if it's a fraction of what the product does, keep it to a fraction of the
video, and use the remaining time on other real capabilities.

## Structure every brief the same way

A one-line prompt ("add motion graphics to my clip") produces generic,
centered, default-colored output. A brief that's actually structured
produces the opposite. Use these sections every time, in order:

```
Create a [length] second [type of video] for [product/brand/topic], using
<renderer>.

PRODUCT   — what it is, who it's for, one line. The promise. Features/points
            in the order they should appear.
STORY     — the structure (hook, N points, close). One visual thread that
            runs through the whole thing (a line, a shape, a recurring
            color). How each scene becomes the next — prefer a transform
            over a hard cut or fade when the brief calls for polish.
FORMAT    — exact resolution, aspect ratio, fps, exact duration, export
            format.
LOOK      — exact hex colors (not "blue," the actual hex), named fonts for
            headline vs. body, the named style (see the style list below),
            what to explicitly avoid (gradients, stock icons, anything that
            reads as a template, unless the style calls for exactly that).
MOTION    — camera/elements never sit fully static; real depth (soft
            shadows, blur on distant elements); real motion blur on fast
            moves (render extra in-between frames and blend them, don't
            fake it with a CSS blur filter).
SOUND     — generate every sound and music cue in code, not stock files;
            tempo in BPM; scene changes land on the beat; every sound effect
            sits on the exact frame of the action it belongs to.
QUALITY CHECK — render, look at a frame from every half-second, critique it
            like a senior motion designer would (story, layout, spacing,
            type, timing, depth, readability, does the sound match the
            picture), fix everything found, render again, repeat. At least
            3-4 full rounds before considering it done — this single
            instruction is the biggest quality lever in the whole brief.
RULES     — whether Claude should stop and ask or make every call itself;
            what counts as "done" (final file, confirm it has sound, list
            what changed each round).
```

If the user hasn't fixed on a specific look yet, ask Claude to *propose* the
LOOK/MOTION/SOUND sections from a short style name instead of leaving them
blank — "particles," "liquid morph," "holographic," "glassmorphism,"
"kinetic typography," "isometric," "clay 3D," "wireframe 3D," "ASCII art,"
"gradient mesh," "comic book," "split-flap," "retro VHS," "halftone,"
"Bauhaus," "pixel art," "blueprint," "art deco," "neo-brutalism" are all real
distinguishable directions a renderer can execute — naming one changes the
result far more than tuning parameters inside a generic template.

## Build native DOM, never a flattened image

An AI image model (e.g. the `claude-image-generation` skill, or a
diffusion model) is fine for *locking a visual direction* — generate one
reference frame, get sign-off, then discard the image. The shipped
composition stays real HTML/CSS/SVG text, logos, and icons, because only
real DOM elements can be independently timed, letter-split, and
re-ordered. A card baked into one PNG can only ever fade in as a single
block — it can't be word-synced or partially revealed.

## Reusable patterns worth knowing by name

- **Fanned-card stack** (2-4 short items overlapping like a hand of
  playing cards): tilt them -8°/0°/8°, ascending z-index front-to-back, and
  make every overlapping card **opaque** — a translucent card lets the one
  behind it bleed through at the overlap edge, the single most common visual
  bug in this kind of build.
- **Letter-level kinetic type**: word-level stagger reads as flat once
  you've seen letter-level. Split text into per-letter spans once,
  deterministically, before building the animation timeline (a fixed DOM
  transform, not per-frame logic, so it stays seek-safe), then stagger each
  letter ~30ms apart with a small 3D barrel-roll rather than a flat rise.
  Set 3D perspective per letter, not on an ancestor — it won't render
  correctly otherwise.
- **Zoom-cut transition**: a brief diagonal light-streak sweep plus a
  synchronized camera scale-punch (`1 → ~1.09 → 1`) on every hard cut reads
  as a polished product-launch edit instead of a slideshow. Keep something
  in frame permanently drifting (camera sway, a slow background rotation,
  idle float on held elements) so no frame is ever fully static — use a
  large finite repeat count for any looping drift, never an infinite
  repeat, so the render stays seekable.
- **Word-synced overlays on real footage**: when overlaying graphics on
  talking-head footage, time every reveal to the exact word being spoken
  (from a word-level transcript with per-word start/end), not an even
  stagger — this is what makes an overlay read as "listening to the
  voiceover" rather than "playing alongside it."
- **Beat-synced motion**: for a showreel/launch video that should feel
  scored rather than illustrated, measure a real beat grid from the audio
  (don't guess a tempo) and land every cut, pop-in, and sound effect on a
  beat or downbeat. `sunwood-ai-labs-hyperframes-motion-reel-skill` and
  `abubakrchan-product-launch-motion` are two independently-vetted skills
  built specifically for this — reach for one instead of reinventing beat
  measurement from scratch.
- **Scoring instead of a single pass/fail critique**: for a longer or
  higher-stakes build, score each dimension that matters (story, layout,
  depth, timing, readability, sound-sync) numerically — e.g. 1-10 — after
  every render, fix whatever scored lowest, and keep looping until every
  dimension clears a stated bar (e.g. 8+). This is a more structured version
  of the QUALITY CHECK loop above for a build worth the extra rounds; don't
  bother with it for a short, simple overlay where a plain critique pass is
  enough.
- **Narration/voiceover**: `fishaudio-fish-audio-plugin` gives free-tier TTS
  with voice cloning via a remote MCP connector — real voice audio generated
  in seconds instead of a flat default TTS voice. Cloud service, not local;
  check current free-tier terms before depending on it for anything beyond
  a draft.

## Verify before claiming done — this is not optional

Lint passing is necessary but not sufficient; invisible elements, corrupted
gradient text, and oversized SVG strokes have each been lint-clean and still
visually broken. After every non-trivial edit:

1. Run the renderer's own check command (e.g. `npx hyperframes check
   <project>`) — must be clean.
2. Snapshot the exact timestamp just touched and **actually read the
   resulting image** — don't trust the check alone.
3. Only render the full clip once the targeted snapshot looks right — a
   full render is the expensive step, spend it last.
4. A static `file://` open of the raw composition is not a valid check for
   a JS-driven renderer — scripts are disabled there, so nothing animates
   and every element renders at its raw default state simultaneously. That
   looks like total chaos and is not a bug; don't debug it as one. Trust
   only the renderer's own live preview or an actual rendered frame/video.
5. The builder's own "check passed" / "render verified" is not the last
   word — it has shipped a real layout bug (a closing element overflowing
   both edges of the canvas) while reporting a clean check. Whoever reviews
   the delivered file should independently ffprobe it, run `volumedetect` on
   the audio, and extract + actually look at frames from several beats
   (especially the very last frame) before accepting the claim.

## Common gotchas (each one otherwise costs a full debug cycle)

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| A timed video element never renders / render hangs | A `<video>` with its own start/duration timing sits inside another element that *also* carries timing | Make the ancestor a plain untimed wrapper; only the `<video>` itself should carry timing. |
| An element never appears even though its parent fades in | `opacity:0` set on both parent and child, but only the parent gets animated back | Give the timed base state to exactly one level. |
| Gradient text renders corrupted or doubled | `background-clip:text` declared on a wrapper with no direct text node | Declare the gradient-clip on the actual leaf element holding the glyphs. |
| An SVG ring/outline renders as a solid blob | `stroke-width` sized in screen-pixel units inside a small `viewBox` | Scale stroke-width to the viewBox's own units (often 0.15-0.25 on a small icon). |
| Render hangs forever with zero frames and no error | Rendering onto a network/removable volume instead of local disk | Render to local disk; stage from a network volume first if needed. |

## Placing the result

Once rendered, hand the clip to whichever placement path the project
actually has available — don't assume one is wired up:

- **`hetpatel-11-adobe-premiere-pro-mcp`** (`external/hetpatel-11-adobe-premiere-pro-mcp`)
  — places the rendered clip directly onto a *new* Premiere sequence (never
  touch the user's existing edit) via a local MCP bridge. Real requirement:
  needs a licensed local Adobe Premiere Pro install and the CEP bridge panel
  running on the *same machine* as the MCP client — check this is actually
  true on the machine in use before assuming the tool is available.
- No Premiere on this machine: hand back the rendered file directly (MP4,
  optionally a second transparent-alpha export for overlay use) and say so
  plainly rather than claiming a placement step that didn't happen.
