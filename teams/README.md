# Team bundles

A team bundle is a starter pack for staffing a new kind of project: which
roles it usually needs, which already-approved capability-registry skills
pair well with it, and a short list of first tasks a project like this
typically needs before anything else. `company team show <name>` prints one
for a human to read and act on manually.

Donor review, 2026-10-19 (`tasks/lessons.md`): paperclip's teams-catalog
bundles agents + projects + tasks + skills + extensions as one importable
unit with per-dependency resolution tracking. company-os's version is
deliberately read-only and advisory rather than an importable/installable
artifact: `company team show` never creates a task, loads a skill, or writes
to the event log on its own — staffing a real project is still `company-pm`'s
judgment call (`agents/company-pm.md`'s "Staffing, in this order"), informed
by the bundle, not automated by it. A bundle that auto-created
`TASK_CREATED` events from a template would be staffing without the
judgment the risk table and `company-pm` are supposed to apply — the exact
thing `config/capability-registry.yaml`'s own header warns against for
skill adoption ("a proposal that could silently become an adoption is not a
proposal") generalized to task staffing.

## Format

```yaml
name: web-app
description: one line — what kind of project this is for
roles:
  - product-designer   # must be a real agents/<role>.md
  - frontend-engineer
suggested_skills:
  - id: motion-vocabulary   # must be a real capability-registry.yaml entry id
    why: one line — why this pairs with this kind of project
seed_tasks:
  - title: a short task title
    notes: what it covers and why it's usually one of the first things done
```

## Adding a new bundle

Write `teams/<name>.yaml` in this shape, then `company team show <name>` —
it validates every role against `agents/*.md` and every suggested skill
against `config/capability-registry.yaml`, and prints a clear warning for
anything that doesn't resolve, rather than silently printing a bundle that
references something that no longer exists.
