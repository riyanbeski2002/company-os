# external/ — locally-cloned capability-registry forks

Every entry in `config/capability-registry.yaml` that carries a `forked_to:`
field has been forked to `github.com/riyanbeski2002/<name>` and, once synced,
has a shallow local clone here at `external/<id>/`.

This directory is **gitignored** (see `.gitignore`) — the fork on GitHub is
the durable copy of record; a clone here is a disposable working copy any
agent or skill can read, run, or build on top of directly, and re-sync at any
time with no data loss.

## Sync

```bash
python3 tools/sync_external_capabilities.py          # clone anything missing, pull anything present
python3 tools/sync_external_capabilities.py --check   # report only, clone/pull nothing
python3 tools/sync_external_capabilities.py <id>      # sync one entry by its registry id
```

## Using one

- Read/import/vendor-copy directly from `external/<id>/` — no `npx skills add`
  or ad hoc `git clone` needed first, it's already there.
- To change it, commit inside `external/<id>/` itself (it's its own git repo,
  pointed at your fork) and `git push` — company-os's own history never sees
  the diff, only the fork does.
- `tools/sync_external_capabilities.py` only ever fast-forwards from the
  fork's `HEAD`; it will not overwrite local commits that haven't been pushed.

## Making a skill actually loadable (not just readable)

`tools/build_capability_index.py` scans every `external/<id>/` for real
`SKILL.md` files (deduping per-tool copies — some repos ship the same skill
under `.cursor/`, `.kiro/`, `docs/`, etc.) and classifies each repo as
`skill` / `tool` / `reference`, writing the curated catalog to
`config/capability-index.yaml`. A repo can yield many units — e.g.
`google-skills` is 164 real skills, `freshtechbro-claudedesignskills` is 23.

`tools/capability.py` is the loader, "at command":
```bash
tools/capability.py list                              # browse the catalog
tools/capability.py show <unit_id>                     # one unit's detail + pairs_with
tools/capability.py load <unit_id>                     # symlinks a skill into skills/ (live — picked up next session)
tools/capability.py unload <unit_id>
```
A loaded skill behaves exactly like a native one (`skills/motion-vocabulary`,
etc.) — same `SKILL.md` frontmatter, same invocation path. It does **not**
make every skill fire automatically on every task; an agent still decides
relevance per-task, same as any skill. `load` the specific unit(s) a task
actually needs, not the whole catalog.

`pairs_with` (hand-curated in `tools/build_capability_index.py`, not
auto-derived) surfaces complementary units at load time — e.g. loading
`threejs-webgl` prints that `react-three-fiber` and `greensock-gsap-skills`
pair with it, so related capabilities are visible without loading all 1,100+
units "just in case."

**Graphify** (`graphify-labs-graphify`, installed globally via
`uv tool install graphifyy && graphify install --platform claude`) maps any
one repo's structure into a queryable knowledge graph on demand
(`/graphify external/<id>`) — tree-sitter based, local, no LLM call for code.
It's interactive/on-demand by design, not a batch-extraction CLI, so it is
**not** pre-run across all of `external/` — that would be slow and mostly
wasted. Run it against a specific repo only when a task actually needs its
structure mapped.

## Not every registry entry is here

Entries without a `forked_to:` field are either already wired in a different
way (`motion-vocabulary`, `scroll-animation` are original skills written in
this repo; `sqlmapproject-sqlmap` clones straight into
`skills/pen_test/engines/` via that skill's own `update_engines.sh`, same
reasoning — a single owning skill, no need for a second copy here) or are
plugin installs (`anthropics-financial-services-plugins`,
`anthropics-knowledge-work-plugins-legal` — `/plugin install`, not a clone).
