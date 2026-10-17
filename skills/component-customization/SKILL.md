---
name: component-customization
description: Use before building any UI component, hero section, scroll effect, or animated interaction from scratch — check the registered component libraries first, then restyle/restructure what you find to this product's actual tokens and taste, rather than shipping it verbatim or ignoring it and hand-rolling one. Triggers on - build a hero section, add a scroll animation, I need a component for X, this looks generic/templated.
---

# Component customization: reuse the structure, never the skin

This repo has 15+ registered component/animation/scroll libraries
(react-bits, tailark-blocks, shadcn-ui, serafimcloud/21st, bklit-ui,
uiverse-io-galaxy, themesberg-neumorphism-ui-free,
nextlevelbuilder-ui-ux-pro-max-skill, darkroomengineering-lenis,
greensock-gsap-skills, claudedesignskills, and more) — registered, cloned,
and then mostly left unused beyond the initial clone. That's the actual gap
this skill closes: **check the library before building from scratch, then
customize what you find before shipping it** — neither step is optional.

## Step 1 — Check before you build

Before writing a hero section, card grid, scroll effect, nav, pricing table,
or any other common UI pattern from zero, search what's already registered:

```
python3 $CLAUDE_PLUGIN_ROOT/tools/capability.py search <pattern keyword>
```

Then pick by job, not by whichever you remember:

| Need | Reach for |
|---|---|
| An animated/interactive React component (hover states, reveals, cursors) | `react-bits` |
| A marketing-page block (hero, pricing, CTA) | `tailark-blocks` — marketing sites only, wrong density for dashboards |
| An accessible baseline primitive (button, dialog, select) | `shadcn-ui` |
| A broader community component gallery | `serafimcloud/21st` |
| A chart/data-viz component | `bklit-ui` (its `studio` package is separate and proprietary — the components themselves are MIT) |
| A CSS-only visual effect, no React needed | `uiverse-io-galaxy` |
| Neumorphism specifically | `themesberg-neumorphism-ui-free` (free tier only) |
| A whole design system from scratch | `nextlevelbuilder-ui-ux-pro-max-skill` |
| Smooth/inertial scroll physics | `darkroomengineering-lenis` — pair with GSAP ScrollTrigger for what happens *as* it scrolls, Lenis is just the scroll feel itself |
| Scroll-triggered animation sequencing | `greensock-gsap-skills` (ScrollTrigger) or this repo's own `scroll-animation` |
| 3D/WebGL (Three.js, React Three Fiber, GSAP) | `skills/claudedesignskills/` |
| Rebuilding a 3D object from a reference photo | `img2threejs-img2threejs` — code-only reconstruction, no mesh downloads |

Not finding a fit after checking the table and a search is the actual
signal to build from scratch — not skipping the check because building
feels faster.

## Step 2 — Never ship it verbatim

A component pulled from a library and shipped with its default colors,
type, spacing, and copy reads as generic AI-slop — this is the complaint
that keeps coming up. Every component you pull in must be restyled to this
product's actual tokens before it ships:

- **Tokens, not defaults.** Palette, type scale, radius, shadow, motion
  timing — pull from this product's real design tokens (or `motion-vocabulary`'s
  defaults if none exist yet), never the library's demo values.
- **Structure can stay, skin cannot.** The DOM shape, the interaction
  pattern, the accessibility semantics — keep those, they're the actual
  engineering value of reusing a library. The visual identity on top of
  that structure is what must change.
- **Copy is never a placeholder.** "Lorem ipsum" or the library's demo copy
  shipping to production is an incomplete task, not a detail to fix later.
- **One deliberate deviation, minimum.** If a component looks identical to
  its library demo except for color, that's still a photocopy with a
  different coat of paint — change at least one structural or interaction
  detail (layout, reveal order, a micro-interaction) so it reads as
  genuinely built for this product, not dropped in.

## Step 3 — Taste-check before calling it done

Run the result past `Leonxlnx/taste-skill` or `pbakaus/impeccable`'s
deterministic anti-pattern check before marking the task done — the same
gate `frontend-engineer` already holds all UI work to. A customized
component that still reads as "a react-bits demo with new colors" hasn't
cleared step 2 yet.
