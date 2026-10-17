# higgsfield-motion-saas — vendored SaaS/app launch-motion skill

A Claude skill specifically for SaaS/app/product launch motion — code-based
(HTML/CSS/Canvas → headless-Chromium capture → sub-frame motion blur →
H.264) or via an After Effects ExtendScript path, with a library of
transitions tuned to hide cuts at peak motion speed (needle zoom,
fly-through, UI morph, mockup hand-off, object carry, etc.).

**Source:** published as a free download by `@adilinthewildtempo` alongside
`higgsfield-motion` on the same
[Higgsfield.ai blog post](https://higgsfield.ai/@adilinthewildtempo/blogs/i-tested-claude-motion-at-3-difficulty-levels-can-it-make-a-higgsfield-style-launch-video)
(Oct 2026). Registered as `higgsfield-motion-saas` in
`config/capability-registry.yaml`, trust tier T3.

**Honest provenance note, two parts:**
1. Same as `higgsfield-motion`'s README — no formal license file, but
   explicit public-distribution intent from the author's own blog post.
2. `SKILL.md` discloses, in its own words, that its After Effects technique
   library was built by "a frame-by-frame study of MahdiEdits' SaaS
   tutorials" and is "reproduced... within a few percent." This is the
   author's own stated derivation of another creator's (MahdiEdits')
   technique library, not hidden — flagged here so anyone using this skill's
   AE path knows the lineage of those specific numbers/recipes.

Static vendored copy — there's no git repo to re-sync from; re-download
from the blog post above if the author updates it.
