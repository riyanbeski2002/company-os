# ADR-006 — Goals above projects, and outcomes distinct from "done"

- **Status**: proposed — design only, for Riyan's review before Phase 3
  implementation starts (`tasks/todo.md`, Phase 3, item 1)
- **Date**: 2026-10-21
- **Decided by**: pending Riyan. Requested by the 2026-10-21 master prompt
  §7.1/§7.2 ("organizations … goals, projects, programs, tasks, milestones,
  budgets … evidence artifacts"; "a task completing does not automatically
  mean its parent business objective was achieved"), and constrained by
  Phase 3's own line: "as events + projections … never a second source of
  truth."
- **Commits**: none yet

## Context

Grounded in what the code does today, not in the master prompt's framing.

**Most of the requested hierarchy already exists. Only the top and the
bottom are missing.** Here is the master prompt's chain, Mission → Strategic
Objective → Key Result → Program → Project → Milestone → Task → Evidence →
Outcome, checked one rung at a time against the code:

| Rung | Exists today? | Where |
|---|---|---|
| Mission / Objective / Key Result | **No** | nothing above `project` exists anywhere |
| Program | **No, and does not need to** | see below |
| Project | Yes, as a namespace | the required `project` string on every event (`eventlog.validate`), which scopes `status`, `costs`, `baseline.latest`, and `lessons.fold` |
| Milestone | **Yes, under another name** | `gate_group`. ADR-005 made the milestone/PR boundary the gating unit, and `gate_group` is how a milestone is tagged at plan time |
| Task | Yes | `taskstate.fold()` |
| Evidence | Yes | `evidence` on facts (`REQUIRES_EVIDENCE`), plus gate verdicts bound to the trusted `WORKER_STARTED` launch |
| Outcome | **No** | the system has no idea at all of a result beyond "the task is DONE/MERGED" |

So the real gap is two things, not seventeen entities:

1. **No record of why the work exists.** A project is a string label. It
   has no definition event and no statement of intent. The closest thing to
   a business objective is the plan spec's `request` field, and that is not
   recorded in the log at all. `cmd_staff` copies each *task's* fields into
   `TASK_CREATED.data`, but the plan-level `request` stays behind in
   `.company/projects/<project>.json`, and the next `company plan` for that
   project overwrites that file. Check the current log: none of its 12
   `TASK_CREATED` events carries a request or objective field. The record
   of what Riyan asked for disappears once the next plan is made.
2. **"Done" is the end of the line.** `render.report()` headlines a
   project as "**N% complete** — X of Y work items delivered". That is
   accurate as a statement about activity, and it is the only success
   statement the system can make. Suppose every task under an intent is
   MERGED and the intent still failed: the feature shipped and nobody used
   it, or the fix landed and the metric did not move. That case cannot be
   expressed today. It looks the same as success.

**Why there is no Program layer.** A program, as the master prompt uses
the word, is a set of projects pursuing one objective. Once an objective
exists and tasks link to it, "the projects serving this objective" is a
*derived* set: the distinct `project` values of its linked tasks. A
`PROGRAM_CREATED` event would be a second, hand-maintained record of
something the log can already compute. That is the exact failure this repo
exists to prevent. If this one-person company ever needs a portfolio
grouping that cuts across objectives, that is a new ADR with a real
use case behind it.

**One structural fact constrains scope.** Every onboarded repo has its
*own* event log: `find_repo_root()/.company`, and 10 repos are onboarded
under `~/dev` today (finos, growfin, resolve-os, ht-workspace, …). "One
organization" therefore spans ten independent authoritative logs. This ADR
designs for a single log and leaves cross-log rollup for later
(see "What this does NOT do"). The v1 choices here are made so that
cross-log rollup can be added later without changes to v1.

**The migration surface is small.** The company-os log has 620 events, but
only 12 are `TASK_CREATED`. 278 of the 620 are `LESSON_RECORDED` events
under project `p` with patterns `"x"` and `"a repeated pattern"`. They look
like test fixtures that leaked into the real log. That is a separate
test-isolation defect, flagged here and not fixed by this ADR. Every
existing event predates this ADR, and none carries a goal.

## Decision

### 1. One entity, `goal`, with three levels

`level ∈ {mission, objective, key_result}`. There is one goal entity, not
three. The levels differ only in validation:

- `mission`: no parent. At most one open mission per log. This is the
  organization's statement of purpose, so **no separate `ORG_CREATED`**.
  For a single operator the organization *is* the installation, and its
  only property worth recording is the mission. A name, if wanted, is the
  mission's `title`.
- `objective`: its parent is the mission.
- `key_result`: its parent is an objective, and it **must** carry a
  `measure`. A key result without a number is just a second objective.

Tasks may link to an `objective` or a `key_result`, never to the `mission`.
Everything serves the mission, so a mission link carries no information.

### 2. Four new event types, each with its one-line reason

`eventlog.py` asks for a stated reason for every new type, because the set
is permanent. Each one below records a fact that no existing event can
carry:

| Event | Why it can't be an existing event | Evidence required? |
|---|---|---|
| `GOAL_DEFINED` | No event records business intent. `request` never reaches the log at all | No. Defining intent is a decision, not a factual claim (same reasoning as `ADVISORY_RESOLVED`) |
| `GOAL_LINKED` | A task's goal must be correctable after `TASK_CREATED`, and events are immutable | No. Classification is a decision |
| `OUTCOME_ASSESSED` | Nothing records whether intent was *achieved*. That is the core ask | **Yes**, added to `REQUIRES_EVIDENCE` |
| `GOAL_CLOSED` | An abandoned goal would otherwise sit "unassessed" forever and bury the real gaps (the `ESCALATION_RESOLVED`/`ADVISORY_RESOLVED` pairing pattern) | No |

**Rejected:** `ORG_CREATED` (the mission covers it), `PROGRAM_CREATED`
(derived, see Context), `MILESTONE_*` (`gate_group` already is the
milestone), and `GOAL_STATUS_CHANGED` (goal status is derived, never set
by hand; see §5).

All four use `make_event` unchanged. Goal events are not project-scoped,
because an objective can span projects. `validate()` still requires a
non-empty `project`, so they carry the reserved value **`project: "_org"`**.
Nothing that filters by project today (`_project_tasks`,
`costs.aggregate`, `baseline.latest`, `lessons.fold`) reads these events,
so the sentinel affects nothing existing. None of the four carries a
top-level `task` field. That is deliberate (§3).

Data shapes:

```jsonc
// GOAL_DEFINED — first emission defines, a later one with the same id revises (last wins)
{"event":"GOAL_DEFINED","actor":"riyan","project":"_org","data":{
  "id":"G-004",                    // assigned like escalations.next_id(): G-NNN
  "level":"key_result",
  "title":"Month-end close runs without manual paise correction",
  "parent":"G-002",
  "measure":{                      // required for key_result, optional otherwise
    "metric":"manual corrections per close", "unit":"count",
    "baseline":14, "target":0, "direction":"decrease",
    "how":"count of correction journal entries in the close export"},
  "budget":{"output_tokens":3000000},   // optional, see §7
  "reason":"target lowered after Q3 review"   // required iff this id is already defined
}}

// GOAL_LINKED — no top-level `task`; members in data.tasks (the group WORKER_STARTED shape)
{"event":"GOAL_LINKED","actor":"company-pm","project":"_org","data":{
  "goal":"G-004",                  // null = unlink
  "tasks":["MONEY-PAISE-M1","MONEY-PAISE-M2"],
  "reason":"retro-link: historical tasks predating ADR-006"}}

// OUTCOME_ASSESSED
{"event":"OUTCOME_ASSESSED","actor":"riyan","project":"_org","data":{
  "goal":"G-004",
  "verdict":"not_achieved",        // achieved | not_achieved | inconclusive
  "measured":{"value":3,"as_of":"2026-11-30"},  // required for a key_result unless inconclusive
  "method":"ran the November close, counted correction entries"},
 "evidence":{"log":"reports/close-2026-11.csv"}}

// GOAL_CLOSED
{"event":"GOAL_CLOSED","actor":"riyan","project":"_org","data":{
  "goal":"G-004","disposition":"superseded",   // abandoned | superseded
  "superseded_by":"G-009","reason":"..."}}
```

Validation at append time follows the existing `validate()` pattern:
level/parent rules, `measure` on key results, `verdict` in its set, and
`measured.value` on a key-result verdict. One rule is new and specific to
`OUTCOME_ASSESSED`: **evidence consisting only of `{"commit": sha}` is
refused.** A commit proves a deliverable exists. This event exists to
record something different from that, and accepting a merge SHA as proof
of an outcome would let the conflation back in through the side door.

### 3. Task → goal linking: one derivation, inside `taskstate.fold()`

There are two ways to set a link, and exactly one place resolves it:

- **At creation.** A `goal` field on a task in the plan spec, plus an
  optional spec-level `goal` that `cmd_plan` copies onto every task that
  lacks one, the same way it already stamps `project`. `cmd_staff` already
  passes every task field into `TASK_CREATED.data`, so this needs no new
  plumbing. The only change is adding `"goal"` to `FIELDS_FROM_DATA`.
- **After creation.** `GOAL_LINKED`, for retro-linking historical tasks and
  for correcting a wrong link.

`taskstate.fold()` handles `GOAL_LINKED` in its existing no-`task` branch,
alongside the group-`WORKER_STARTED` case. For each member already in
`tasks` it sets `task["goal"]`, and later events win in `seq` order. It
**does not touch `updated_at`**: relinking is classification, not work, and
bumping it would silently reset the clocks in `detect_stale_tasks` and
`detect_resting_tasks`. Because the event has no top-level `task`, it can
never create a phantom DRAFT task for a misspelled id. Unknown ids show up
in the goal projection as `unknown_tasks`.

**Task state and goal state cannot disagree, because only one of them
computes the link.** The goal projection does not re-read link events. It
takes `taskstate.fold()`'s output as input:

```
goals.fold(events, tasks=taskstate.fold(events)) -> {goal_id: view}
```

`goals.fold` reads only `GOAL_DEFINED`, `OUTCOME_ASSESSED` and
`GOAL_CLOSED` from the log. Membership comes from `task.get("goal")`. One
log, one link derivation, two views over it.

This is a new module, `tools/company/goals.py`, rather than an extension of
`taskstate.fold()`. The repo already has that precedent: `escalations.py`,
`advise.py` and `lessons.py` each keep their own pure `fold()` over the
same log for their own entity family. Folding goals into the task fold
would turn a 160-line function, the one that holds the Evidence Rule's
inputs, into two jobs.

### 4. "Outcome achieved" as its own axis, never derived from tasks

The goal view keeps **two independent fields**, `delivery` and `outcome`.
It never collapses them into one status. Together they cover the master
prompt's four required distinctions:

| Distinction | Field | Derived from |
|---|---|---|
| Activity performed | `activity` | worker runs and spend on linked tasks (`costs.aggregate`'s existing `by_task`, summed) |
| Deliverables produced | `delivery` | linked task statuses: `none` / `in_progress` / `delivered`, with **DONE and MERGED counted separately**. MERGED is shipped but not verified by the Evidence Rule, and the goal view must not blur that line, as `IMPLIED_STATUS` already refuses to |
| Outcome achieved | `outcome.state = achieved` | the latest qualifying `OUTCOME_ASSESSED` |
| Outcome not yet verified | `outcome.state = unassessed`, or `self_assessed`/`stale` set | no qualifying assessment exists |

Rules, all deterministic and all computed in the fold:

- **No task event ever changes `outcome`.** If every linked task is DONE,
  the result is `delivery: delivered, outcome: unassessed`. The projection
  flags this as `awaiting_assessment`. That is the gap made visible.
  `delivery: delivered, outcome: not_achieved` is a first-class, expected
  state ("we shipped it and it didn't work"). `achieved` with tasks still
  open is also legitimate.
- **`meets_target` is computed, not asserted.** When a key result's
  `measure` has a numeric `target`/`direction` and the assessment has a
  numeric `measured.value`, the fold computes the comparison itself. A
  verdict that contradicts it (e.g. "achieved" at 3 against a target of 0,
  decreasing) is flagged `assessment_inconsistent`. Deterministic beats
  model-judged wherever a number exists.
- **Self-assessment doesn't count.** An `OUTCOME_ASSESSED` whose actor is
  the `owner` of any linked task is recorded and shown, but it is marked
  `self_assessed` and never moves `outcome.state`. This is the same
  principle as `check_done()` refusing a self-certified gate.
- **Staleness is checked by sequence, not by clock.** If a linked task
  reaches MERGED/DONE at a higher `seq` than the latest assessment, the
  outcome is flagged `stale`. New work landed after the measurement, so
  the measurement no longer covers it.
- **Parents never inherit.** An objective whose key results are all
  `achieved` shows `children: 3/3 achieved`, but its own `outcome` stays
  `unassessed` until it is assessed itself. This applies the master
  prompt's "task done ≠ objective achieved" rule at every level, not only
  at the bottom.
- **`GOAL_CLOSED` removes a goal from the gap lists.** The goal and its
  history stay readable.

Views are written to `.company/goals/G-NNN.json` with `canonical()`, and
`company rebuild` / `rebuild --verify` cover that directory under the same
rules as `tasks/`: byte-identical replay, and a stray file is a mismatch.

### 5. CLI: one new group, `company goal`

This follows the existing `company task …` / `company session …` /
`company team …` shape. No changes to existing verbs, except that
`company plan` accepts `goal`.

| Command | What it does |
|---|---|
| `company goal define` | Appends `GOAL_DEFINED` with level, title, parent, measure and budget. With an existing `--id` it revises, and `--reason` is required |
| `company goal link <goal> --tasks …` | Appends `GOAL_LINKED`. `--unlink` sets null. `--reason` is required for any task that is already terminal (retro-linking) |
| `company goal assess <goal> --verdict … --evidence …` | Appends `OUTCOME_ASSESSED` and enforces §2's validation |
| `company goal close <goal> --disposition …` | Appends `GOAL_CLOSED` |
| `company goal tree [--json]` | Shows the mission → objectives → key results tree, each node with `delivery` / `outcome` / spend |
| `company goal show <goal>` | One goal: linked tasks with status, assessment history, flags, budget vs. spend |
| `company goal gaps` | The discipline view: ungoaled tasks per project, `awaiting_assessment`, `stale`, `self_assessed`, `assessment_inconsistent`, key results with no assessment, `unknown_tasks` |

Two guards, both mechanical:

- The four goal events are refused through raw `company event`. They go
  only through `company goal`, which owns their validation. This works like
  `LAUNCHER_ONLY_EVENTS`.
- `company goal define|link|assess|close` refuse to run when
  `$COMPANY_ACTOR` is set, i.e. from inside a launched Tier-2 worker. A
  worker defining its own objective, or grading its own outcome, is
  self-certification. This is the one actor boundary the system can
  enforce today without a human-identity mechanism it doesn't have.

Who defines what is a PM-prompt rule, not code: Riyan sets the mission and
objectives, and the PM proposes them via `company escalate --kind decision`.
The PM may define key results under an objective Riyan approved. It may
link tasks without asking, because classification is delegated work.

### 6. Risk triggers and staffing: unchanged, on purpose

- **Goal text is never an input to `staffing.evaluate()`.** `cmd_plan`
  keeps evaluating `request` + task title + owned paths only. Appending
  goal titles would make "Objective: grow payments revenue" fire the
  `payments` trigger on every task under it. That is the same
  keyword-only false positive `presentational_paths` was added to stop.
  A goal can never add or subtract a gate. The risk table stays a pure
  function of the work itself.
- **`check_done()` and the Evidence Rule are untouched.** An outcome
  assessment has no bearing on whether a task may reach DONE, and the
  reverse holds too.
- **Staffing** gains no goal-driven rules. In `agents/company-pm.md`,
  staffing step 1 ("what outcome is requested, in business terms?") gets
  one concrete instruction: name the goal id, or say explicitly that the
  work is ungoaled.

### 7. Budgets: per-goal amounts in the log, the policy in `budgets.yaml`

`config/budgets.yaml` today is concurrency and wall-clock policy only. No
spend budget exists anywhere. A per-goal budget is a fact about one goal
that gets revised over time, so it lives on `GOAL_DEFINED.data.budget`. A
YAML row keyed by `G-004` would be a second place a goal's facts live.
`budgets.yaml` gets the *policy* half, following its existing pattern:

```yaml
goal_budgets:
  unit: output_tokens      # what a goal budget is denominated in
  warn_at_ratio: 0.8       # `goal show`/`gaps` flag spend at 80% of budget
  enforce: false           # v1 is report-only, no launch is ever refused
```

v1 is report-only. Spend is `costs.aggregate()`'s existing `by_task`,
summed over linked tasks, so per-goal attribution comes for free from the
by-task split shipped 2026-10-19. That split includes its labeled
even-split estimate for gate-group runs. This closes the Phase 2 item
deferred "until Phase 3's org/budget work makes it load-bearing", using
attribution that already exists. Enforcement (refusing `company run` on an
over-budget goal) is a later decision that should rest on real spend data,
not be built ahead of it.

## What this deliberately does NOT do

**Not needed yet (no current use case; do not build ahead of one):**

- **No department, role, permission or RBAC model.** There is one human.
  "AI employees" already exist as `agents/*.md` with frontmatter tool
  grants, and that is the real permission system. `department` already
  exists as a task field (`FIELDS_FROM_DATA`, shown by `render.status`),
  yet zero of the 12 tasks in this log set it. A field nobody fills in is
  evidence against building a department entity, not for it.
- **No humans or reporting-relationships entity.** There is one operator,
  and `actor` strings plus `$COMPANY_ACTOR` already identify who did what.
- **No multi-tenant isolation.** `doc/GOAL.md` rules this out explicitly
  ("no multi-tenant concept"), as does the 2026-10-19 lesson on
  paperclip's multi-org surface ("solving a different company's problem").
- **No web dashboard or API.** Phase 5 sequences these until after the
  state they would display is trustworthy, and `cmd-center` is the
  separate read-only companion.
- **No federation or remote execution.**
- **No automatic outcome measurement** (pulling metrics from external
  systems). An assessment is a human or PM act with evidence attached.
  Automating it means trusting a new category of input, which needs its
  own design and threat model.
- **No auto-linking of historical tasks** by project name, title
  similarity or `gate_group`. Inferring a link would turn a guess into
  something that looks like a recorded fact. This is the same reasoning
  `IMPLIED_STATUS` uses to refuse back-dating DONE onto MERGED work.

**Needed later, sequenced after this ADR:**

- **Cross-repo rollup** (one org tree over ten repos' logs). The shape that
  keeps a single source of truth: org-level goal events live in one
  designated log (company-os's own, resolved through `$CLAUDE_PLUGIN_ROOT`
  the way the capability registry already is). A task in another repo
  links with a qualified id. A read-only aggregator folds several logs
  side by side, and each log stays authoritative only for its own facts,
  with nothing copied between them. This needs its own ADR, because it
  introduces the first cross-log reference and has to decide how a
  qualified id is validated at append time. v1's log-local `G-NNN` ids
  leave room for a later `<repo>:G-NNN` qualifier.
- **Budget enforcement**, once report-only spend data shows where limits
  belong.
- **An `Outcomes` section in `company report`**, once real goals exist to
  show. Until then `report`'s output stays byte-identical.

## Consequences

**What becomes possible:**

- "Did we achieve what we set out to do?" gets an answer the log can back
  up, separate from "did we ship it?". "Shipped, didn't work" becomes a
  recorded state instead of something that looks like success.
- Work with no stated purpose becomes a visible count. `company goal gaps`
  lists ungoaled tasks per project, so a task without a goal link is now a
  visible gap instead of an invisible one.
- Cost per objective comes from attribution that already exists.

**Operational discipline it demands:**

- The PM names a goal (or explicitly "ungoaled") at plan time, and Riyan
  owns the mission and objectives. Most small work will rightly stay
  ungoaled. The gaps view is information, not a gate, and nothing refuses
  an ungoaled task.
- Someone has to *assess*, with evidence, on purpose. The system will
  show `awaiting_assessment` indefinitely rather than guess. If this
  becomes noise, the answer is to close or assess goals, not to have the
  fold infer outcomes.
- Implementation touches `taskstate.py` and `eventlog.py`, the files that
  hold the Evidence Rule. `governance-mechanism` in
  `config/risk-triggers.yaml` does **not** cover either file today (its
  paths are `hooks/**`, the three gate/risk/staffing YAMLs, `worker.py`,
  `staffing.py` and `cli.py`), so this work would ship with baseline review
  only. The implementation plan should add `security` with a recorded
  `gate_reason`. Separately, Riyan should decide whether to extend the
  trigger to those two files. That is a real gap of the same kind ADR-002
  closed for `staffing.py`.

**Migration — the existing log keeps working unchanged:**

- No existing event carries `goal`, and none is a goal event. `goals.fold`
  returns `{}` and `.company/goals/` stays empty.
- `taskstate.fold()` must not add a default `goal: null` key. Absence means
  ungoaled. With that rule, every existing `.company/tasks/*.json` replays
  byte-identical and `company rebuild --verify` passes without a rewrite.
  Implementation should include a golden test asserting exactly this
  against a copy of the current log.
- `company status`, `costs`, `report`, `plan` and `staff` do not read goal
  views in v1, so their output on the existing log is unchanged.
- Historical tasks appear in `goal gaps` as ungoaled. Linking any of them
  is an explicit, reasoned `GOAL_LINKED`. Here that means 12 tasks, a
  manual and optional pass. In larger repos such as finos (218 tasks at
  last measure), retro-linking is a deliberate per-objective decision,
  not a migration step.
