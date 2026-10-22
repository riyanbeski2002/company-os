# The `company` CLI's JSON output, as a contract

company-os has no server and no API (`doc/GOAL.md`). A read-only consumer
like `cmd-center` (GUI-01 blocked-agent alerts, GUI-02 cost analytics,
GUI-03 budget alerts, GUI-04 cross-repo overview) reads state by running
`company ... ` and parsing stdout. This doc pins down the shapes it can rely
on. `tests/test_cli_json_contract.py` asserts every key set listed here
against a real fixture log, so a drift fails CI before it reaches a consumer.

Every shape below is written by `cli.emit()`: `json.dumps(sort_keys=True,
indent=2)` plus a trailing newline (`eventlog.canonical()`), derived purely
by replaying `.company/events/events.jsonl`. Nothing here is cached or
estimated, and none of these commands writes to the log.

## Calling it

```sh
company --root ~/dev/<repo>/.company status --json
```

`--root` (or `COMPANY_ROOT`) points at one repo's `.company/`. There is no
multi-repo command: a cross-repo overview (GUI-04) is one call per repo.
Exit 0 means stdout is one JSON document. A non-zero exit means an error
message on stderr and nothing to parse (e.g. `goal show` on an unknown id).

Every command below accepts `--json`, so a consumer can pass it uniformly.
On `status` and `goal tree` it switches from text to JSON; on `costs`,
`goal show`, `goal gaps` and `escalate --list` it is a no-op, because they
are always JSON.

"Always" means the key is always there. "Optional" means the key is
sometimes missing entirely. A key that is present but can hold `null` is
written as `T | null`.

## `company status --json`: tasks, blockers, stalls (GUI-01, GUI-04)

Without `--json` you get text. `--project P` narrows the output to one
project; leave it out and you get every project in this `.company/`.

| key | type | meaning |
|---|---|---|
| `project` | string \| null | the `--project` filter, or `COMPANY_PROJECT`; `null` = all projects |
| `progress` | string | **a string, not a number**: `"42%"` (mean of known per-task progress) or `"unknown"`. Kept for compatibility; prefer `progress_pct` |
| `progress_pct` | int \| null | the same figure as a number, 0-100; `null` exactly when `progress` is `"unknown"` (no task's progress can be computed). Never a stand-in number |
| `tasks` | list | task views from `taskstate.fold()` (below) |
| `escalations` | list | **open** escalations only; blocking ones come first, then sorted by id |
| `stalled` | object | task id -> reason string. Critical: stale (48h+), worker gone with no terminal event, resting, or a gate that exited with no verdict |
| `early_warning` | object | task id -> reason string. "Suspicious" (1-2 days silent), never also in `stalled` |

**Task view.** Always: `id`, `project`, `status` (`DRAFT`, `PLANNED`, ...,
`DONE`, `MERGED`, `ABANDONED`), `evidence` (object), `criteria_met` (list),
`created_at`, `updated_at` (UTC `YYYY-MM-DDTHH:MM:SSZ`). Optional: whatever
the task's events supplied, such as `title`, `owner`, `tier`, `goal`,
`depends_on`, `gates`, `branch`, `worktree`, `worker_roles`. Treat the task
view as open: read the keys you need and ignore the rest.

**Escalation.** Always: `id`, `kind`, `need`, `blocking` (bool), `raised_by`,
`raised_at`, `task` (string \| null), `project`. Optional: `detail`,
`options`, `commands`.

What counts as a "blocked agent" for GUI-01: a task with an open escalation
where `blocking: true`, or a task listed in `stalled`.

## `company escalate --list open|resolved|all`: the escalation audit trail

`--project` is optional here, and `--json` is accepted but changes nothing.

| key | type | meaning |
|---|---|---|
| `ok` | bool | always `true` |
| `filter` | string | the value passed to `--list` |
| `count` | int | `len(escalations)` |
| `escalations` | list | escalation objects (above) plus `status` (`open`/`resolved`); a resolved one also has `resolution`, `resolved_by`, `resolved_at` |

## `company costs`: tokens and spend (GUI-02)

Always JSON (`--json` is accepted and changes nothing). `--project P`
narrows the output.
On a subscription the dollar figure is an **estimate, not a bill**.

| key | type | meaning |
|---|---|---|
| `project` | string \| null | the filter, `null` = all |
| `billed_to` | string | a fixed human label |
| `worker_runs` | int | `WORKER_EXITED` runs that reported a cost or tokens |
| `tasks_delivered` | int | tasks now `DONE` or `MERGED` |
| `tokens` | object | `input`, `output`, `cache_read`, `cache_creation`, all ints |
| `tokens_per_delivered_task` | object \| null | `tokens` divided by `tasks_delivered`; `null` when nothing has been delivered |
| `wall_clock_minutes` | number | total worker run time |
| `api_equivalent_usd` | number | the client-side API-price estimate |
| `by_actor` | list | one object per actor, **most output tokens first**: `actor` (string), `runs`, `output_tokens`, `cache_read_tokens`, `seconds`, `usd_equivalent`, `tasks` (list), `turns`, `runs_missing_turns`, `runs_with_unestimated_cost`; plus `avg_cache_read_per_turn`, `avg_output_per_turn` **only** once one of its runs reported a turn count |
| `by_task` | list | one object per task, **most cache-read tokens first**: `task` (string, the task id), `runs`, `output_tokens`, `cache_read_tokens`, `seconds`, `usd_equivalent`, `actors` (list), `split_across_tasks` (int; >1 means a gate-group run's cost was split evenly, so the figure is an estimate) |
| `untasked` | object | the same five totals for runs with no task (e.g. advisors) |
| `runs_with_unestimated_cost` | int | runs with tokens but no dollar figure (e.g. codex). `api_equivalent_usd` undercounts by this many runs |
| `runs_with_backfilled_tokens` | int | runs whose tokens were rebuilt by `company backfill-tokens` |
| `notes` | list of strings | caveats for humans. The wording can change at any time; don't parse it |

`by_actor` and `by_task` are lists so the ranking survives serialization:
`sort_keys` reorders the keys inside each entry, never the entries. Ties
keep log order. To look an entry up by id, index it yourself (e.g.
`{e["actor"]: e for e in out["by_actor"]}`).

## `company goal tree --json` / `goal show <id>` / `goal gaps` (GUI-03)

**`goal tree --json`** returns `{"goals": [node, ...]}`, one node per root
goal (one whose parent isn't defined). Each node always has: `id`, `level`
(`mission`/`objective`/`key_result`), `title`, `status` (`open`/`closed`),
`delivery`, `outcome`, `flags`, `activity`, and `children` (a list of nodes,
recursive).

- `delivery`: `state` (`none`/`in_progress`/`delivered`), plus int counts
  `total`, `done`, `merged`, `abandoned`, `open`. This axis covers what was
  shipped.
- `outcome`: `state` (`unassessed`/`achieved`/`not_achieved`/`inconclusive`),
  `assessed_seq` (int \| null), `stale`, `self_assessed`, `inconsistent`
  (bools). This axis covers whether the shipped work achieved its intent. It
  never moves when a task does.
- `flags`: a list drawn from `awaiting_assessment`, `stale`, `self_assessed`,
  `assessment_inconsistent`, `unknown_tasks`.
- `activity`: summed over the linked tasks' `by_task` entries: `runs`,
  `output_tokens`, `cache_read_tokens`, `seconds`, `usd_equivalent`,
  `includes_split_estimate` (bool).

**`goal show <id>`** is always JSON (`--json` is accepted). It returns the full goal view, which
has everything a tree node has except that `children` is a list of **ids**,
plus:
- always: `defined_by`, `defined_at`, `revisions` (list), `tasks` (ids),
  `projects`, `unknown_tasks`, `assessments` (list of `seq`, `by`, `at`,
  `verdict`, `measured`, `method`, `evidence`, `self_assessed`,
  `meets_target`, `inconsistent`), `children_achieved` (`achieved`,
  `total`), `linked_tasks` (list of `id`, `status`, `project`, `title`), and
  `budget_status` (object \| null).
- optional, present only if the goal defines them: `parent`, `measure`,
  `budget`, `closed`.

`budget_status` is `null` when the goal has no budget in the configured
unit. Otherwise it has `unit`, `budget`, `spent`, `ratio` (number \| null),
`warn` (bool; true at or above `warn_at_ratio`, default 0.8, from
`budgets.yaml`) and `enforced` (bool). This is the GUI-03 signal.
company-os only reports budgets and never enforces them.

**`goal gaps`** is always JSON (`--json` is accepted) and only covers open
goals:

| key | type | meaning |
|---|---|---|
| `ungoaled_tasks` | object | project -> task ids with no goal |
| `awaiting_assessment`, `stale`, `self_assessed`, `assessment_inconsistent`, `key_results_unassessed` | lists of goal ids | goals carrying that flag (the last list: key results with no outcome) |
| `unknown_tasks` | object | goal id -> linked ids that aren't tasks |
| `tasks_linked_to_undefined_goal` | object | goal id -> task ids |
| `budget_warnings` | list | `{"goal": id, ...budget_status}` for each goal whose `warn` is true |

## `company report`: text only

There is no JSON mode. It prints a Markdown summary, and it also **writes**
`.company/reports/<project|all>.md`. A strictly read-only consumer (GUI-05)
should build its view from `status --json` and not call `report`.

## Stability policy

- Adding a key, or a new value of an existing enum, is **non-breaking**.
  Consumers must ignore keys they don't know.
- **Breaking:** removing a key, renaming a key, changing a key's type (e.g.
  making `progress` a number), turning an always-present key into an
  optional one, or turning a JSON command into a text-only one.
- A breaking change ships in the same commit as an updated
  `tests/test_cli_json_contract.py` and an entry in the changelog below. The
  commit message starts with `BREAKING:` and names the command and key.
- Not covered: reason strings, `notes`, `billed_to`, the text (non-`--json`)
  output, and anything this doc doesn't list.

## Findings (current behaviour, deliberately not changed)

1. `company report` writes a file as a side effect (see above).

## Changelog

- v2 — 2026-10-22
  - **BREAKING:** `costs`: `by_actor` and `by_task` changed from objects
    (id -> entry) to lists of entries in cost-rank order, each entry
    carrying its id as `actor` / `task`. As objects, `sort_keys` re-sorted
    them alphabetically and the ranking `costs.aggregate()` builds never
    reached the JSON (v1 Finding 1). Migrate with
    `{e["actor"]: e for e in out["by_actor"]}` if you need the old lookup.
  - `status --json`: new `progress_pct` (int \| null). `progress` is
    unchanged (v1 Finding 2). Additive.
  - `costs`, `goal show`, `goal gaps`, `escalate`: accept `--json` as a
    no-op, so passing `--json` to every command no longer fails argparse on
    some of them. Additive.
- v1 — 2026-10-21 — initial documented contract.
