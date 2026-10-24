---
name: motion-as-code
description: Use when making motion graphics as CODE driven by a voiceover — every frame a deterministic function of time, re-rendered on edit, instead of hand-keyframed in After Effects. An alternative render path to HyperFrames for voiceover-locked explainers. Triggers on - motion as code, code-driven animation, voiceover-synced explainer, render motion graphics from code, three.js motion graphic, procedural motion video.
---

# Motion as Code

Make motion graphics from code, driven by a voiceover, without opening After
Effects. Nothing is keyframed by hand: each scene (a "plate") is a file that
draws every frame as a function of time, and word-level voiceover timings tell
each plate when to animate, so the picture is locked to the voice. Because it is
all code, you ask the model to change an animation and re-render, instead of
moving hundreds of keyframes.

Original write-up of the workflow from the "Motion as Code" starter kit (visual
engine: pdoom-video by mexicat, MIT). Stack in the reference kit: TypeScript +
three.js, bun + Vite, headless Chrome + ffmpeg. No code vendored here.

## The core rule

**Everything is a deterministic function of time.** The engine calls
`render(f, out)` once per frame with `f.t` (song time), `f.lt` (time since the
plate started), `f.p` (0→1 progress through the plate), and `f.a` (audio
features at that moment). Because every frame is pure, the live browser preview
and the exported MP4 are identical, and re-timing is free: change the voiceover,
re-run alignment, and each plate finds its words by content.

## The pipeline (six stages)

1. **Voiceover** — the narration (e.g. ElevenLabs `voiceover.mp3`).
2. **Align** — forced alignment (wav2vec2 / ONNX) produces word-level timings;
   refined against the audio's silences.
3. **Scenes** — one TypeScript file per plate, plus a timeline saying when each
   plate plays (cuts sit in the pause just before each line).
4. **Preview** — Vite dev server, hot-reload; scrub to the moment you changed
   (space play/pause, `[`/`]` prev/next plate, `,`/`.` step a frame, `?t=35` to
   start at 35s).
5. **Render** — headless Chrome → raw frames → ffmpeg, with motion blur
   (sub-frames), e.g. CRF 17; `--samples` and `--scale` flags trade speed for
   quality/resolution.
6. **Sound** — effects cue sheet derived from the same word timings, ducked
   under the voice and normalised (e.g. -14 LUFS); rebuild the mix and mux with
   ffmpeg, no re-render needed.

## Writing a plate

A plate extends `Scene` and exports as default; add it to the timeline with a
start time derived from the script (a cut lands ~0.18s before its line's first
word). Stateful plates reset on `f.seeked` after a scrub. To change the piece,
edit a plate and re-render — e.g. "slow the pipeline plate 20% without changing
the voiceover timing", "add a plate between frames and pipeline showing a
loading bar".

## When to use this vs. HyperFrames

- **Motion as code**: a voiceover-locked explainer where you want each frame as
  procedural code and tight word-sync, on the three.js/bun render path.
- **HyperFrames** (the repo's default video framework): most video, animation,
  captioned-clip, title-card and multi-scene work — reach for it first unless
  the user specifically wants this code-as-frames, voiceover-aligned approach.

## Requirements / gaps

Needs bun, headless Chrome, and ffmpeg with libx264 present. Re-alignment needs
Python + an ONNX model. Check your ElevenLabs licence before publishing audio
you generated.
