---
name: voice-commanded-editing
description: Use when editing an existing raw video where the creator spoke their own edit instructions out loud while filming (e.g. "zoom in here," "add a caption," "cut to black," "remove it") — find each spoken order with word-level timestamps and apply the effect at the exact synced moment, output frame-accurate to the original. Triggers on - edit this video, I narrated the edits, sync effects to what I said, self-commentary edit.
category: "media.video-production"
---

# Voice-commanded self-edit

A distinct workflow from `motion-graphics-video` (which builds a composition
from scratch): here the raw footage and its cut are already final — the job
is applying effects/captions/grading *on top of* unchanged footage, synced
to spoken commentary the creator gave themselves while filming. Adapted from
a free public prompt (thegrowthengine.net/prompt/edit, no license stated,
offered openly) — reorganized and generalized here rather than reproduced
verbatim.

## The core idea

The creator's spoken lines during filming are literally edit orders, not
just narration. Transcribe the raw video with **word-level timestamps**
(a local Whisper model — free, runs on-device, no API dependency) and treat
every spoken instruction as a direct command: find it, apply the effect at
that exact timestamp.

- **Sync to the frame, not just the word.** A spoken "watch this" paired
  with a snap or a point should land the effect on the gesture, not an
  arbitrary offset from when the word was transcribed — check the actual
  video frames around the timestamp, not only the transcript.
- **Effects persist until explicitly reversed.** "Add a zoom" stays active
  until the creator says "remove it" / "back to normal" — don't auto-revert
  after one beat.
- **Intro and CTA get special treatment.** The first spoken lines are the
  hook/intro, the last is the call to action — these carry the most weight
  and deserve the most polish, not just whatever effect was literally named.
- **If given a style reference**, match its look (grading, caption style,
  graphic-card treatment) first, then push further — denser, faster, more
  surprises than the reference — rather than only matching it 1:1.

## Hard constraints — this is an overlay pass, not a re-cut

- **Frame 1 of the output is frame 1 of the input.** Same length, same
  timing, same resolution, same frame rate. No re-cutting, no speed
  changes — this skill adds effects/captions/grading on top of an
  already-final edit, it doesn't change the edit itself.
- **Grade very lightly and naturally** when asked to "make me look good":
  correct skin tone (pull out colored spill from screens/LED strips), never
  push contrast/saturation or crush shadows, no beauty-filter smoothing, no
  vignette unless explicitly asked.
- **Captions**: short bursts (1-3 words), bold sans, legible at phone size,
  never placed over a face or hands — check this per-frame, not just as a
  static safe-zone assumption, since hands/face move.
- **Audio**: clean the voice track, add music bed and SFX strictly under
  the voice level, master to **-14 LUFS** (the same loudness target used
  elsewhere in this repo's video-editor tooling — keep it consistent).
- **Use free, local tools** — this workflow is specifically meant to run
  without a paid API dependency (local Whisper for transcription, local
  video-processing tools for the effects pass). `hiteshk03-davinci-resolve-mcp`
  (already registered) ships local Whisper transcription if DaVinci Resolve
  is the placement target anyway — no need for a separate standalone
  Whisper install if so.

## Verify before claiming done

Check every frame of the output, specifically for: an effect landing early
or late relative to its spoken trigger, broken cutout/matte edges, caption
text sitting on a face or hands, typos, blank/dropped frames, and audio
drifting out of sync. Fix, re-render, re-check — repeat until a full pass
finds nothing, the same verify-loop discipline as `motion-graphics-video`.

## Leave a record

Write an edit log (one line per spoken order: its timestamp, what was
applied, which tool did it) alongside the output — this is what lets
someone (or a later session) audit what happened without re-watching the
whole video, and it's the evidence that each spoken instruction was
actually found and executed, not skipped.
