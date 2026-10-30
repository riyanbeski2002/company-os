# Agent roster — non-default picks

Reference, not steps: read this when staffing a role that isn't the obvious
default (most tasks are still `frontend-engineer`/`backend-engineer` plus
`code-reviewer`/`qa-engineer`). Disclosed out of `agents/company-pm.md`
(retro finding #3, `mattpocock/skills`' `retro`, 2026-10-30) so it isn't
always-loaded context for every session regardless of whether the goal ever
touches finance, legal, or video.

## `finance-analyst` / `legal-analyst`

Both Tier 1, no worktree — they exist for real business deliverables, not
code: a DCF, an LBO, a comps set, a contract review, NDA triage. Their actual
methodology comes from official Anthropic plugins (T1,
`$CLAUDE_PLUGIN_ROOT/config/capability-registry.yaml`), not reimplementation;
if the plugin isn't installed, they say so rather than improvise. Most tasks
don't need them — but when Riyan asks for a financial model or a contract
read, staff the role built for it instead of `cfo-advisor` (a different job:
it audits this repo's own token spend) or a generalist attempt.

`legal-analyst`'s own job — contract/NDA review — has a dedicated playbook
kind (`legal_review` in `config/playbooks.yaml`, routed via `capability-map.yaml`'s
`legal_review` tag, not `confirm`-gated: it's a first-party T0 agent doing
exactly what it's built for). `finance-analyst`'s is `finance_deliverable`.

## `video-editor`

Tier 2, worktree. Exists for rendered video/motion-graphics work — launch
videos, logo animations, overlay cards on footage, channel intros — built
from code (HyperFrames/Remotion) rather than hand keyframing. Staff it when
the outcome is genuinely a video deliverable, not a static image (that's
`frontend-engineer` reaching for `skills/claude-image-generation/`) and not a
UI screen.

Reachable from `video_recreate`/`content_engine` via `capability-map.yaml`
(`video_build`/`video_quality_check`/`audio_quality_check`/`video_render_alt`/
`video_placement`), all `confirm: true` — `explain()` surfaces it in
`needs_confirmation`, never silently staffs it; ask Riyan once. Its
registered renderers and the Premiere/Resolve placement tools have real
machine requirements (see `agents/video-editor.md`) — don't assume a step is
available just because it's registered; check before staffing a handoff that
depends on it.
