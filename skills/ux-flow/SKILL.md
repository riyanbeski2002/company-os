---
name: ux-flow
description: Use before frontend implementation starts on a customer-facing screen or flow with real ambiguity — a new page, a materially different interaction, a permission-gated view nobody has designed yet. Produces the states/edge-case/information-architecture contract frontend builds against. Triggers on - design the UX for, what should this screen do, is this ready for frontend to build, staff a product designer.
---

# UX Flow

A frontend implementation is only as good as the contract it was given. "Build
the settings page" hides a dozen unmade decisions; each one guessed
differently by frontend, QA, and Riyan produces rework, not a shipped screen.
This skill is how those decisions get made once, on paper, before code.

## Who runs this
`product-designer`, staffed by `company-pm` when a task is customer-facing
**and** genuinely ambiguous — not for every UI change. A copy fix or a new
field on an existing form does not need this; a new page or a materially
different interaction does.

## What the output must cover

1. **Screens and states.** For each screen: loading, empty, error,
   unauthorized, disabled — not just the happy path. A screen with only a
   happy-path spec is not specified.
2. **Information architecture.** What groups with what. What's primary vs.
   secondary. Where does this fit in navigation.
3. **Edge cases.** Slow network, partial failure, a permission the user
   doesn't have, an empty result set, a result set of one vs. a thousand.
4. **Explicit non-goals.** What this task does NOT cover — as load-bearing as
   what it does. Scope creep during implementation usually traces back to a
   handoff that didn't say what was out.
5. **Existing pattern first.** If this product already has an answer for
   something similar, defer to it and say so. Never invent a second pattern
   for something the product already solved.

## What this is NOT
Not a visual design system. Not colors, spacing tokens, or component code —
that's `frontend-engineer`'s job, guided by its own taste standard. This
skill decides what the screen has to do; the frontend engineer decides what
it looks like while doing it.

## The handoff

```
company handoff <TASK_ID> --from product-designer --to frontend --stdin
```

Frontend builds against this the same way it would build against a published
API contract — not against a guess about what product probably meant.

## When to skip this entirely

- The pattern already exists in this product; point frontend at the existing
  screen instead of re-deriving it.
- The change is small enough that ambiguity isn't the risk (a field, a copy
  change, a state that already has a pattern).
- Staffing a designer here would be tier inflation for a two-line change —
  the same discipline that applies to Tier 2 workers applies to adding roles.
