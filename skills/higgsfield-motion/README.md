# higgsfield-motion — vendored motion-design skill

A large (~2.7MB), detailed Claude skill for designing motion-graphics key
frames and code-rendered films (HTML/CSS/SVG/WebGL → PNG stills, MP4 with
music/SFX) in any brand identity, via a token system (`scripts/hf-tokens.js`)
and a ~1.3MB handbook of frame/motion/production rules (`references/parts/`,
in Russian).

**Source:** published as a free download by `@adilinthewildtempo` on their
Higgsfield.ai blog post ["I Tested Claude Motion at 3 Difficulty
Levels"](https://higgsfield.ai/@adilinthewildtempo/blogs/i-tested-claude-motion-at-3-difficulty-levels-can-it-make-a-higgsfield-style-launch-video)
(Oct 2026), explicitly for readers to download and use. Registered as
`higgsfield-motion` in `config/capability-registry.yaml`, trust tier T3.

**Honest provenance note:** no formal open-source license file ships with
this skill — the author distributes it directly from their blog as a
`.skill` download, not a licensed GitHub repo. The distribution intent is
unambiguous (the blog post's explicit purpose is "download our two Claude
skills, then copy a brief below"), which is why it's vendored here at all,
but treat it as the author's own freely-shared work rather than a formally
licensed OSS project.

**Removed before vendoring:** a stray precompiled `scripts/encode` arm64
Mach-O binary that was bundled in the original `.skill` zip — the skill's
own `scripts/setup.sh` recompiles this from `encode.swift` on first use into
a cache directory outside the skill folder, so the bundled binary was a
redundant, unverified build artifact. Never ship precompiled binaries of
unknown provenance into this repo; let the skill's own setup step build it
locally instead.

**References/client-taste.md and references/production-lessons.md** are the
author's own iterative design notes from developing and testing this skill
(appears to be the author's own self-directed test sessions rather than a
third party's confidential client data — the blog post itself is literally
titled "I Tested Claude Motion..."). Read with that context: the "client"
feedback recorded there is the author's own accumulated taste from testing,
not live client-confidentiality material.

Static vendored copy — there's no git repo to re-sync from; re-download
from the blog post above if the author updates it.
