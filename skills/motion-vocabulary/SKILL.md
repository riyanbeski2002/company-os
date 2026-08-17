---
name: motion-vocabulary
description: Use when specifying, implementing, or reviewing any UI motion — enter/exit animation, transition, gesture feedback, scroll effect, loading state. Gives frontend-engineer the precise vocabulary and defaults to justify a motion choice concretely instead of by taste alone. Triggers on - how should this animate, what easing should I use, is this transition too slow/fast, does this need a spring, review this animation.
---

# Motion Vocabulary

`frontend-engineer`'s taste standard says "never add motion without a reason
specific to this screen." This skill is the vocabulary that makes "a reason"
concrete instead of a feeling — precise terms for what an animation is doing,
sane defaults for the common cases, and the failure modes to name when
reviewing one. Adapted from the public animation-terminology references at
animations.dev and motion-vocabulary.vercel.app; reorganized here around
"when to reach for this" rather than as a general glossary.

## Enter/exit — how something appears or leaves
- **Fade** — opacity only. Safest default; use when position doesn't matter.
- **Slide in** — enters from off-screen. Use to imply *where it came from*
  (a side panel, a bottom sheet) — not as a default fade replacement.
- **Scale in** — grows from smaller, usually with fade. Reads as "this just
  came into existence here" (a popover, a new card). Overusing it everywhere
  reads as generic AI-slop polish, not intent.
- **Pop in** — scale-in with slight overshoot. Reserve for genuinely delightful
  moments (a like button, a confetti trigger) — never for routine UI.
- **Reveal** — content uncovered via clip-path/mask rather than faded in.
  Use when the *shape* of the reveal carries meaning (an image loading in).

## Timing — sequencing multiple things
- **Stagger** — list items animate with small sequential delays. Use for
  lists/grids appearing together; keep the per-item delay small (≤50ms) or it
  reads as slow, not polished.
- **Orchestration** — several distinct animations timed to work together
  (exit-then-enter, not simultaneous). Use when two elements are swapping.
- **Duration / delay** — state the actual number when reviewing, not "feels
  slow" — UI enter/exit is normally 150–300ms; longer reads as sluggish.

## Easing — how speed changes over the animation
- **Ease-out** (fast start, slow finish) — **the default for anything entering
  or responding to user action.** If you didn't choose an easing deliberately,
  this is the one that should be there.
- **Ease-in** (slow start, fast finish) — usually wrong for UI; it makes the
  interface feel like it's hesitating before responding. Reserve for exits
  where the element is leaving attention, not arriving.
- **Ease-in-out** — for animations that both start and end at rest (a toggle
  moving between two fixed states).
- **Linear** — constant speed. Correct only for continuous/ambient motion
  (a loading spinner, a marquee) — using it for enter/exit reads as robotic.
- **Cubic-bezier** — a custom curve. Only justify this over a named easing
  when the built-in ones were tried and didn't fit; don't reach for it first.

## Spring — physics-driven motion
- **Spring** (stiffness, damping, mass) — use for anything that should feel
  physically responsive to interruption (drag-released elements, gesture
  feedback) — not for routine page-level enter/exit, where a fixed-duration
  ease-out is simpler and equally correct.
- **Stiffness** — higher = snappier. **Damping** — lower = more bounce/
  overshoot. **Mass** — higher = slower to start and stop.
- **Interruptible** — a spring worth using for drag/gesture-driven motion
  specifically because it can be smoothly redirected mid-flight; a
  fixed-duration tween cannot.

## Transforms — what's actually moving
Translate, scale, rotate, skew, 3D tilt. Prefer **transform + opacity** over
animating layout properties (width, height, top, left) — the former is
GPU-composited and won't cause layout thrashing; the latter forces the browser
to recompute layout on every frame. If a review finds an animation on
`width`/`height`/`top`/`left`, that's a performance finding, not a style
preference.

## Transitions — state changes
- **Layout animation** — size/position changes animate instead of snapping.
  Use when a change happens *while the user is looking at it* (an accordion,
  a list reorder) — never for changes that happen off-screen.
- **Morph** — one shape becomes another. **Shared element transition** — an
  element visually travels between two states/screens (a thumbnail becoming
  a detail view). Both are expensive to build correctly; only worth it when
  the continuity itself is the point, not decoration.
- **Crossfade** — one element fades out as another fades in, same position.
  The default for swapping content in place without motion implying direction.

## Scroll
- **Scroll reveal** — elements animate in as they enter the viewport. Use
  sparingly on content pages; overusing it on every section is a common
  AI-generated-site tell, not polish.
- **Parallax** — background/foreground move at different rates. High cost,
  easy to make nauseating — needs a specific reason, not "it looks nice."
- **View/page transition** — animation between routes. Only worth building
  custom if it preserves user orientation (what moved where); otherwise a
  plain crossfade is more honest than a flashy transition with no meaning.

## Gestures — direct manipulation feedback
- **Press/tap** — subtle scale-down (e.g. 0.97) on click. Cheap, expected,
  almost always correct to include on anything tappable.
- **Drag** with elastic constraints, **rubber-banding** (resistance + snap-back
  past a boundary), **swipe to dismiss**, **hold to confirm** (progress fill
  while held) — all exist to make direct manipulation feel physically
  grounded. Missing rubber-banding on a draggable/scrollable boundary is a
  correctness finding (the UI feels broken at the edge), not a nice-to-have.
- **Shake/wiggle** — quick jitter signaling error. Reserve for genuine
  rejection (invalid input) — using it decoratively trains users to ignore it.

## Ambient — continuous, resting-state motion
Marquee, loop, orbit, pulse, float, idle animation. All should be **subtle and
literally ignorable** — ambient motion competing for attention is a defect,
not liveliness. If it would be distracting on a second monitor while you work,
it's too much.

## Polish & feedback
- **Skeleton/shimmer** — placeholder with moving sheen during load. Use
  instead of a spinner when the final layout is known ahead of the data.
- **Number ticker**, **typewriter**, **text morph** — all read as delightful
  in isolation and exhausting when applied to every number/heading on a dense
  page. Reserve for the one or two moments meant to be noticed.
- **Confetti/particles** — genuine success moments only (checkout complete,
  goal achieved) — never routine confirmations. This is the single most
  common "unearned" motion violation in frontend-engineer's own taste rules.

## Principles — the underlying physical logic
- **Anticipation** — a small wind-up opposite the main direction before
  moving, borrowed from traditional animation. Rarely needed in UI; mostly
  relevant to character/illustration motion, not interface elements.
- **Follow-through** — loose parts keep moving briefly after the main element
  stops (a stagger on child elements after a parent settles).
- **Squash & stretch** — deforming an element to convey weight/speed on
  impact. Playful contexts only; wrong for dense, operational UI.

## Performance vocabulary — for naming what's actually wrong
- **Compositing** — GPU moves/fades an element with no layout recalculation.
  This is why transform/opacity animate cheaply and width/height don't.
- **Jank** / **dropped frame** — visible stutter from missed frame deadlines.
  60fps is the baseline; if an animation visibly stutters, name the frame
  budget being missed, not just "it feels laggy."
- **Layout thrashing** — animating a property that forces repeated layout
  recalculation every frame (see Transforms above).
- **Reduced motion** — `prefers-reduced-motion` must be respected for any
  ambient, autoplaying, or large-scale motion. Treat missing support for it
  as a correctness gap, on the same level as a missing empty/error state.

## When reviewing an animation, ask
1. Does it have a specific purpose (orient, give feedback, show a
   relationship) — can you name it in one sentence?
2. Is the easing/duration a deliberate choice or whatever the library
   defaulted to?
3. Is it animating transform/opacity, or something that causes layout
   thrashing?
4. Would it survive `prefers-reduced-motion` being on?
5. If you removed it entirely, would anything actually get worse? If not,
   it's decoration, not motion with a reason.
