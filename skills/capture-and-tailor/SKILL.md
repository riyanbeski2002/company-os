---
name: capture-and-tailor
description: Use whenever a reference is handed over — a website/section, a video/reel, a live app, or an image of an object — and the goal is a tailored, original version for this product, not a copy of it. Routes to the right capture tool by reference type, enforces grammar-only extraction (never the reference's actual content/assets), and runs a deliberate-difference check so the result doesn't read as a photocopy. Triggers on - recreate this, make something like this reference, I want this style for our product, clone the vibe not the content.
---

# Capture and tailor: reference in, original out

The common failure mode this skill exists to prevent: pointing an agent at
a reference and getting back either (a) a near-identical copy — a real IP/
impersonation risk and a dead giveaway to anyone who's seen the original —
or (b) something so loosely "inspired" it doesn't actually capture what made
the reference work. The fix is the same in both directions: extract the
reference's *structure/grammar*, never its *content*, then deliberately
diverge on specific, named dimensions before shipping.

## Step 1 — Route by reference type

| Reference is... | Use |
|---|---|
| A live website or app (UI/UX, interaction patterns) | `morluto-rea` (reverse-engineering agent) — **own-site or explicit-permission only**, same restriction as `JCodesMore/ai-website-cloner-template`. Never point this at a site you don't own or have written permission for. |
| A video or reel (editing rhythm, shots, transitions, camera moves) | `edenfunf-reelmimic` — built specifically for this: breaks down the reference's edit grammar, produces a new video, explicitly never carries over the original footage/characters/assets. |
| An object in a photo/image, wanted as a 3D asset | `img2threejs-img2threejs` — code-only procedural reconstruction, not mesh extraction from the source image. |
| A design style/mood (palette, type, composition) for key frames or a film | `higgsfield-motion`'s `HFT.derive()` — generates a new, validated identity from seed colors/moods rather than copying a specific brand's tokens. |
| A UI pattern you want adapted, not pixel-cloned | `component-customization` (this repo's own skill) — check the library table there before capturing anything bespoke. |

If the reference doesn't fit any row above (e.g. a strategy doc, a brand
voice, a product's feature set), that's ordinary research, not a capture
job — just read it and build from the brief.

## Step 2 — Grammar only, never content (non-negotiable)

Whichever tool does the capture, the output must never include: the
reference's actual logo, copyrighted characters, real footage/photos of
people from it, its literal copy/text, or any asset pulled directly from
it. What transfers is structural: shot lengths and cut rhythm, a layout's
information hierarchy, a component's interaction pattern, a palette's
*relationships* (not its exact hex values unless the task is explicitly
"use this exact brand"), timing/pacing. This is the same rule already
enforced for `ai-website-cloner-template` (own-site-only) and built into
`edenfunf-reelmimic`'s own design (no original footage/characters carried
over) — applied here as one consistent policy across every capture path.

## Step 3 — Deliberately diverge before shipping

After capturing the grammar, change at least these before calling it done —
this is what separates "inspired by" from "looks like a photocopy":

1. **Palette or type**, not both reused as-is from the reference.
2. **At least one structural beat** — a different opening shot, a
   reordered section, a component laid out differently — not just a
   recolor of the exact same sequence.
3. **Real content specific to this product** — never the reference's
   actual copy, product names, or placeholder text standing in for it.
4. **One genuinely new idea** the reference didn't have — a transition it
   didn't use, a micro-interaction it lacked, a beat it skipped. If nothing
   was added, the build only subtracted from the reference, which still
   reads as a weaker copy of it.

## Step 4 — Verify by comparing, specifically for over-similarity

Most verify loops check "does this match the brief." This one adds the
opposite check too: **does this look too much like the reference specifically**
— side by side, at the same moments/sections, would someone who's seen the
original immediately recognize it as a copy rather than something new that
drew on it? If yes, go back to step 3 and diverge further before delivery,
not after a complaint.
