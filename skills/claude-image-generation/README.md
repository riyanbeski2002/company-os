# claude-image-generation — vendored image-generation skills

8 Claude Code skills for generating website/app images without depending on
a hosted model like Nano Banana or ChatGPT image generation:

- **`level-1-image-generator`** — Pillow/numpy code-based design engine.
  Posters, logos, quote cards, geometric/Bauhaus art, carousel slides. Zero
  API, zero cost, fully local, crisp text (no AI artifacts).
- **`level-2-image-generator`** — real Three.js 3D scene rendered headlessly
  (headless-gl under Xvfb) to one frame. Product shots, 3D backgrounds. Zero
  API, zero cost, local.
- **`level-3-image-generator`** — Cloudflare Workers AI (`flux-1-schnell`).
  The only tier needing a key, and it's Cloudflare, not Nano Banana/ChatGPT —
  nearly free, for photographic/freeform looks levels 1-2 can't produce.
- **`scene-splitter`, `story-illustrator`, `story-narrator`,
  `story-html-publisher`, `storybook-pipeline`** — a composed app chaining
  the above into an AI Storybook pipeline (plain-English story -> a
  self-contained illustrated, narrated HTML book).

**Source:** https://github.com/hassancs91/claude-image-generation (MIT,
registered as `hassancs91-claude-image-generation` in
`config/capability-registry.yaml`, trust tier T2). Vendored here directly
(not left in `external/`), same treatment as `claudedesignskills` — this is
the real answer to Riyan's explicit ask: stop depending on Nano Banana/
ChatGPT for website images on projects like eden. Reach for Level 1 or 2
first (free, local, deterministic); Level 3 only when a photographic/
freeform look is genuinely needed.

To refresh from upstream, re-run:
```bash
rsync -a --exclude='*.zip' external/hassancs91-claude-image-generation/.claude/skills/ skills/claude-image-generation/
```
(after `tools/sync_external_capabilities.py hassancs91-claude-image-generation` pulls the latest).
