# claudedesignskills — vendored 3D/animation/web skills

22 Claude Code skills for 3D graphics, animation, and interactive web
development (Three.js, GSAP, React Three Fiber, Babylon.js, Framer Motion,
and more), each with its own `SKILL.md`, `references/`, `scripts/`, and
`assets/`.

**Source:** https://github.com/freshtechbro/claudedesignskills (MIT,
registered as `freshtechbro-claudedesignskills` in
`config/capability-registry.yaml`, trust tier T2). Vendored here directly
(not left in `external/`) per Riyan's explicit instruction — this is meant to
be used as actual first-class skill content for `frontend-engineer`, same
tier as `Leonxlnx/taste-skill`, `pbakaus/impeccable`, `emilkowalski/skills`,
and `nextlevelbuilder/ui-ux-pro-max-skill`.

To refresh from upstream, re-run:
```bash
rsync -a --exclude='*.zip' external/freshtechbro-claudedesignskills/.claude/skills/ skills/claudedesignskills/
```
(after `tools/sync_external_capabilities.py freshtechbro-claudedesignskills` pulls the latest).
