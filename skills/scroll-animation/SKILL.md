---
name: scroll-animation
description: Use when a landing/hero/product page needs a scroll-driven narrative — an element that transforms, assembles/disassembles, or tells a story as the user scrolls, not just a fade-in. Covers researching multiple production pipelines (frame-sequenced video, CSS scroll-timeline, JS scroll-linked libraries, Lottie, WebGL, SVG morph), presenting them as real options, and splitting delegated work into what this skill builds itself vs. what needs Riyan specifically. Triggers on - scroll story, scroll-driven animation, as I scroll, scrollytelling, animated hero section, immersive scroll experience.
---

# Scroll Animation

A "scroll story" — an element that visibly transforms, builds, or narrates as
the user scrolls past it — is not one technique. It's a category with real
production tradeoffs. This skill's job: research which pipeline actually fits
the ask, present the real options, and split the work into what gets built
autonomously vs. what genuinely needs Riyan (usually: the creative concept
and any AI-generated source footage).

**This is a specific instance of the wider pattern**: research → present real
options → get a direction → build against it. Don't default to the first
pipeline that comes to mind, and don't default to only the pipeline described
in any one example — brainstorm what else would achieve the brief.

## Who runs this
`product-designer` for the narrative/concept brainstorm and pipeline
recommendation; `frontend-engineer` for implementation once a pipeline and
concept are chosen. Reference `motion-vocabulary`'s Immersive & Cinematic
profile for the vocabulary this category of motion draws on.

## Six production pipelines — research which fits, don't assume one

| Pipeline | What it actually is | Best for | Cost/complexity | Needs Riyan for |
|---|---|---|---|---|
| **Frame-sequenced video** | Pre-render a video (AI-generated or filmed), extract N frames/sec, draw the frame matching scroll progress onto a canvas | Photoreal or highly art-directed sequences no code can express (a laptop disassembling with mechanical arms) | High: video-gen cost, frame storage/bandwidth, needs careful compression | The concept prompt and the generated footage itself — this is inherently a creative-direction step, not an engineering one |
| **Native CSS scroll-timeline** | `animation-timeline: scroll()` / `view-timeline` — the browser ties keyframes directly to scroll position, no JS | Property-level transforms (move, scale, rotate, opacity, clip-path) on real DOM/SVG elements | Low: no library, no assets, best performance, but limited browser support and to CSS-animatable properties | Nothing — fully buildable end to end once a concept is chosen |
| **JS scroll-linked (GSAP ScrollTrigger, Framer Motion's `useScroll`)** | A library ties arbitrary JS/DOM changes to scroll progress — more control than CSS, still no pre-rendered assets | Choreographed multi-element sequences (things entering, leaving, swapping) where CSS alone can't express the logic | Medium: a real dependency, more code, but no asset pipeline | Nothing — fully buildable end to end |
| **Lottie (After Effects export)** | A vector animation authored in After Effects, exported as JSON, scrubbed frame-by-frame via `lottie-web`'s `goToAndStop(frame)` tied to scroll | Illustrated/vector narratives — smaller payload than raster video for the same visual complexity, crisp at any size | Medium: needs an After Effects source (or a motion designer), but the runtime is lightweight | The AE source file/motion design — this skill can wire up the scroll-scrub, not author vector animation from scratch |
| **WebGL/3D (Three.js, Spline)** | A real 3D scene; camera or object transforms are driven by scroll progress | Genuinely three-dimensional narratives — orbiting, exploded-view, depth | High: real 3D asset creation, GPU cost, steepest learning curve | The 3D model/scene, unless a tool like Spline is used for lower-code scene building |
| **SVG path morph/draw** | Vector paths that morph between shapes or draw themselves in, driven by scroll | Schematic, diagrammatic, or line-art storytelling (exploded diagrams, flowcharts building themselves) | Low–medium: no video pipeline, but path authoring/morphing takes real design care | The path artwork, unless generated programmatically from existing icons/diagrams |

**Present 2–4 of these as concrete options**, not the full table — pick the
ones that plausibly fit the brief, describe the *felt result* of each in one
line, and let Riyan choose before building anything. "Immersive" alone
doesn't tell you which of these six is right; the content (is there real
footage-worthy content, or is it DOM elements that can transform themselves)
usually does.

## The frame-sequenced video pipeline, worked in full

This is the pipeline Riyan described directly — building it end to end since
it has the most non-obvious steps and the clearest human/automation split.

**1. Concept → detailed scene description (needs Riyan).**
A good AI-video-gen prompt is specific about: subject, camera behavior,
lighting/mood, the sequence of distinct beats (not just "cool animation"),
and duration. Draft the detailed prompt for Riyan to review/edit — don't
generate it blind and hope; this is the one step where his taste is the
actual spec.

**2. Generate the footage (needs Riyan).**
Riyan runs the prompt through an AI video tool (Google Flow, Stitch, or
equivalent) and supplies the resulting video file. This skill does not have
a way to generate video itself — say so plainly rather than attempting a
worse substitute.

**3. Extract frames (autonomous).**
```bash
ffmpeg -i input.mp4 -vf fps=30 out/frame-%03d.png
```
30fps for a smooth scrub; consider fewer if payload size matters more than
buttery scrubbing — a scroll-driven sequence rarely needs cinema-grade
smoothness since the user controls the pace, not real time. Optimize each
frame (WebP, appropriate resolution for the largest render size) before
shipping — a 150-frame PNG sequence at full resolution is a real payload
problem, not a detail to skip.

**4. Preload and index (autonomous).**
Preload all frames before the sequence is scroll-reachable (a loading state
is expected here — treat "sequence not yet loaded" as a real state, same
discipline as any other loading/empty/error state).

**5. Build the scroll-driven sequencer (autonomous).**
Canvas approach — map scroll progress within the element's scroll range to a
frame index, draw only that frame:
```js
function render() {
  const progress = getScrollProgress(sectionEl); // 0 to 1
  const frame = Math.min(frames.length - 1, Math.floor(progress * frames.length));
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(frames[frame], 0, 0);
}
```
Drive `render()` from a scroll listener throttled to `requestAnimationFrame`,
never on every raw scroll event — an unthrottled per-pixel redraw is a real
performance defect, not a style choice. Pin the section's scroll height to
however many frames of "scroll distance" the sequence should occupy (a
common pattern: a tall wrapper with a `position: sticky` canvas inside it, so
the canvas stays in view while the wrapper's extra height drives progress).

**6. Verify it, the same standard as any other motion.** Does it survive
`prefers-reduced-motion` (fall back to a static frame or a short static video,
never force the full scrub on someone who opted out)? Does it stay performant
on the actual target device, not just a dev machine?

## What this skill always does itself vs. always hands to Riyan

**Autonomous, every pipeline:** frame/asset extraction and optimization,
sequencer/choreography code, performance tuning, accessibility fallback,
integration into the page.

**Always needs Riyan:** the creative concept and direction choice (which of
the presented options), and any step that requires an external creative tool
this skill has no access to (AI video generation, a motion designer's AE
file, a 3D artist's scene). Name the exact external step and what's needed
from it — "generate a 5-second video of X, Y, Z, roughly this shot list" —
rather than a vague "please provide assets."

## Anti-patterns
- Never default to the frame-sequenced-video pipeline just because it was
  the first example anyone gave you — it's the most expensive option on the
  table and often the wrong one for what CSS/JS scroll-linking could do at a
  fraction of the cost.
- Never build a scroll narrative nobody asked to see twice — this category is
  expensive to get wrong, so the "present options first" step matters more
  here than almost anywhere else in frontend work.
- Never ship a frame sequence with no loading state or reduced-motion
  fallback — treat both as correctness gaps, not polish.
