"""Task packet rendering (§5).

A Tier-2 worker receives exactly this and nothing else: no CEO conversation, no
company history, no other worker's reasoning, no PM deliberation. The role
definition already lives in the agent file — this does not re-teach the worker
what a senior backend engineer is.

Budget: ~3.5k tokens. Over budget means the task is too big or the scoping was
lazy, so `render` raises rather than quietly shipping a bloated packet.
"""

from __future__ import annotations

from pathlib import Path

# RAISED 2000 -> 3500 on 5 Sep 2026 by Riyan's explicit decision, after the
# budget blocked TWO finished Wave 7 tasks from being gated at all:
# TASK-MERCHANT-RULE-BUILD rendered ~3002 tokens and TASK-IAM-VOCABULARY-DESIGN
# ~2818, both with one-line briefs. Neither was blocked by a fat brief — the
# packet embeds the task's DIFF and its accumulated gates_failed history, so a
# long design document and a task with ten rounds of recorded findings both
# exceed the cap no matter how tersely the PM writes.
#
# Riyan was offered three options (ship the three already-gated tasks; split
# the two blocked ones; raise the budget) and chose to raise it.
#
# HONEST COST, recorded so this is not mistaken for drift: 2000 was doing real
# work. It flagged TASK-MERCHANT-RULE-BUILD as oversized hours before nine gate
# rounds proved it, and the PM worked around it once instead of splitting —
# which a fable root-cause analysis later identified as a genuine contributing
# factor. Raising the ceiling removes that early warning for every task, not
# just these two. If a task approaches 3500, treat it as the same signal 2000
# used to give and split it rather than raising this again.
# RESTORED to 3500 on 10 Sep 2026. It was raised to 4000 on 8 Sep as
# an explicit loan — Riyan: "raise it but once done bring it back again" — to
# unblock sep08d/sep08e. Those groups are gated and gone, so the loan is repaid.
# The measurements below are kept because they explain what the ceiling is FOR;
# they are the argument for a future exception, not for leaving it raised.
#
# WHY, with measurements rather than assertion. Riyan first chose to SPLIT the
# oversized tasks rather than raise this, which was the right instinct. The
# split was done and measured:
#   9-file task, full brief ......... 3787
#   6-file half, full brief ......... 3853
#   6-file half, TWELVE-WORD brief .. 3644
# Stripping the brief to nothing saved ~200 tokens; the embedded diff alone is
# ~3400. So a half-sized task with an empty brief STILL does not fit. Splitting
# further would work at ~3 files, but that turns five near-identical mechanical
# edits ("stop building IN-lists, page instead") into three separate reviews —
# and a reviewer wants them together precisely to confirm the pattern was
# applied consistently.
#
# That is the distinction this budget could not previously express: it catches
# a task doing too many DIFFERENT things, but a mechanical sweep across N files
# is one thing done N times. 3500 admits that case and still refuses genuinely
# fat ones.
TOKEN_BUDGET = 3500
CHARS_PER_TOKEN = 4  # rough, deliberately conservative

# A GROUP packet is not a task packet. TOKEN_BUDGET caps one task's brief,
# and 2000 is the right discipline there: if a single task cannot be
# described in 2k tokens it is too big or was scoped lazily. A group packet
# describes N tasks reviewed as one unit, so a fixed cap punishes exactly the
# batching the group gate exists to enable — measured 2026-09-02, a 5-task
# group with real acceptance criteria renders ~2528 tokens and was refused,
# making "one gate for all tasks" structurally impossible past ~3 tasks.
# The packet's fixed scaffolding (instructions, verdict lines, verify, diff
# stat) is roughly constant; only the per-task criteria block scales. So the
# budget scales the same way. This bounds the packet - it does not uncap it.
GROUP_TOKEN_BUDGET_BASE = 1200
# 700 -> 1100 for the same reason and by the same decision: a 2-task group
# rendered ~3226 tokens against a 2600 cap, which made Riyan's standing "gate
# everything as one group" instruction impossible for tasks carrying real
# diffs. Scales with task count as before; this bounds the packet, it does not
# uncap it.
GROUP_TOKEN_PER_TASK = 1100


def group_token_budget(n_tasks: int) -> int:
    return GROUP_TOKEN_BUDGET_BASE + GROUP_TOKEN_PER_TASK * max(1, n_tasks)


class PacketTooLarge(ValueError):
    pass


def _bullets(items, empty="(none)") -> str:
    items = list(items or [])
    if not items:
        return f"  {empty}"
    return "\n".join(f"  - {i}" for i in items)


def render(task: dict, *, why: str, contracts: list[dict] | None = None,
           architecture: list[str] | None = None, decisions: list[str] | None = None,
           handoff_target: str = "pm", max_turns: int = 60,
           timeout_s: int = 1800, enforce_budget: bool = True,
           verify: str | None = None, baseline: dict | None = None,
           diff_summary: str | None = None) -> str:
    contracts = contracts or []
    verify = verify or task.get("test_command")
    if not verify:
        raise ValueError(
            f"no verify command for {task['id']}. The Evidence Rule needs a command "
            f"that produces a real exit code — run `company detect --write` or set "
            f"`verify:` in .company/config/project.yaml."
        )

    # On a brownfield repo the suite may already be red. Say so plainly, or the
    # worker will waste its budget chasing failures it did not cause.
    if baseline and not baseline.get("green"):
        base_note = (
            f"  ⚠ This repo was ALREADY RED before your task: exit "
            f"{baseline.get('exit_code')}"
            + (f", {baseline['failures']} failures" if baseline.get("failures") is not None else "")
            + ".\n"
            "  Do NOT try to fix pre-existing failures — they are out of scope and\n"
            "  will burn your budget. You must simply not add any. Report the real\n"
            "  exit code and failure count either way."
        )
    else:
        base_note = "  The repo is green at baseline. Any failure you report is yours to fix."

    contract_text = "  (none — nothing downstream depends on your interface)"
    if contracts:
        contract_text = "\n".join(
            f"  - {c.get('name')}: {c.get('summary')}" for c in contracts)

    # CFO audit, 2026-08-24: a gate role (review/qa/security) is launched
    # against this same task after implementation, and previously received
    # this identical packet with no record of what actually changed — it had
    # to rediscover the diff itself via Bash (git log/diff, then read whole
    # files) before it could review anything, every single time. Riyan,
    # 2026-08-24: the fix isn't complete until a gate is actually HANDED the
    # change, not just told where to go look for it — so this carries the
    # real patch content (bounded — see cli.py's cap), not just a file list.
    # A gate still has full Read/Grep/Bash if it genuinely needs more
    # surrounding context; this just means it no longer has to start blind.
    diff_section = ""
    if diff_summary:
        diff_section = f"\nCHANGES SO FAR (what to review — full patch unless noted otherwise)\n{diff_summary}\n"

    packet = f"""TASK {task['id']} — {task.get('title', 'untitled')}
TIER {task.get('tier', 2)}

OBJECTIVE
  {task.get('title', '')}

WHY IT MATTERS
  {why}

OWNERSHIP (enforced by a PreToolUse hook — writes outside this are blocked)
  owned:
{_bullets(task.get('owned_globs'))}
  forbidden:
{_bullets(task.get('forbidden_globs'))}

BRANCH    {task.get('branch')}
WORKTREE  you are already in it; this is your entire working copy

DEPENDENCIES
{_bullets(task.get('depends_on'), empty='(none)')}

CONTRACTS PUBLISHED BY YOUR DEPENDENCIES (build against these, not guesses)
{contract_text}
{diff_section}
RELEVANT ARCHITECTURE (pointers, read them if you need them)
{_bullets(architecture, empty='(nothing beyond the files in your owned globs)')}

RELEVANT DECISIONS
{_bullets(decisions, empty='(none)')}

ACCEPTANCE CRITERIA
{_bullets(task.get('acceptance_criteria'))}

REQUIRED VERIFICATION
  Run: {verify}
{base_note}
  Report the REAL exit code via a TEST_RUN event, including when it fails, and
  include a failure count when the runner prints one:
    --data '{{"cmd":"...","exit_code":N,"failures":N}}'

BUDGET
  max turns: {max_turns}   wall clock: {timeout_s}s

HOW TO REPORT
  company event {task['id']} TEST_RUN --data '{{"cmd":"...","exit_code":N}}' --evidence <log-path>
  company event {task['id']} IMPLEMENTATION_READY --evidence <commit-sha>
  company event {task['id']} CONTRACT_PUBLISHED --data '{{"name":"...","summary":"..."}}' --evidence <path>
  company handoff {task['id']} --from {task.get('department', 'engineering')} --to {handoff_target} --stdin

  Commit your work before emitting IMPLEMENTATION_READY — the SHA is the evidence.
  A task cannot reach DONE without a diff, a green test run, and a review by
  someone other than you. Do not attempt to certify your own work.
"""
    if enforce_budget:
        estimate = len(packet) // CHARS_PER_TOKEN
        if estimate > TOKEN_BUDGET:
            raise PacketTooLarge(
                f"packet for {task['id']} is ~{estimate} tokens, over the "
                f"{TOKEN_BUDGET} budget. The task is too big or the scoping is "
                f"lazy — split it rather than raising the budget."
            )
    return packet


def estimate_tokens(packet: str) -> int:
    return len(packet) // CHARS_PER_TOKEN


def render_group(tasks: list[dict], *, group_id: str, why: str,
                 diff_summary: str | None, verify: str, baseline: dict | None = None,
                 max_turns: int = 60, timeout_s: int = 1800,
                 enforce_budget: bool = True) -> str:
    """Grouped gate packet (efficiency addendum, 2026-08-24): several tasks
    that touch the same core get ONE gate launch instead of one each — this
    is that launch's packet. It does not change what a gate must verify or
    the Evidence Rule's per-task bookkeeping: the worker is instructed to
    emit its own verdict event for EVERY task listed below, individually,
    with the same evidence. `cli.py`'s `cmd_gate_group` then checks each task
    actually got one — a task that doesn't is unreviewed, exactly like a
    solo gate that exits with no verdict, never silently passed through
    because a sibling in the group was reviewed.
    """
    if baseline and not baseline.get("green"):
        base_note = (
            f"  ⚠ This repo was ALREADY RED before this group's work: exit "
            f"{baseline.get('exit_code')}"
            + (f", {baseline['failures']} failures" if baseline.get("failures") is not None else "")
            + ".\n  Pre-existing failures are out of scope — do not fail the group over them."
        )
    else:
        base_note = "  The repo is green at baseline. Any new failure is this group's to explain."

    task_lines = []
    for t in tasks:
        task_lines.append(
            f"  {t['id']} — {t.get('title', 'untitled')}\n"
            f"    owned: {', '.join(t.get('owned_globs') or []) or '(none declared)'}\n"
            f"    acceptance criteria:\n"
            + "\n".join(f"      - {c}" for c in (t.get('acceptance_criteria') or ['(none declared)']))
        )
    tasks_text = "\n".join(task_lines)
    verdict_lines = "\n".join(
        f"    company event {t['id']} <PASS_OR_FAIL_EVENT> --evidence <sha-or-log-path>"
        for t in tasks)

    diff_section = ""
    if diff_summary:
        diff_section = f"\nCOMBINED CHANGES (what to review — full patch unless noted otherwise)\n{diff_summary}\n"

    packet = f"""GATE GROUP {group_id} — {len(tasks)} tasks reviewed together, one pass
These tasks touch the same core and are being reviewed as one unit instead of
{len(tasks)} separate passes. Review them together — the combined diff below
is the real unit of change; do not review each task's slice in isolation.

TASKS IN THIS GROUP
{tasks_text}

WHY IT MATTERS
  {why}
{diff_section}
REQUIRED VERIFICATION
  Run: {verify}
{base_note}

BUDGET
  max turns: {max_turns}   wall clock: {timeout_s}s

HOW TO REPORT
  You MUST emit one verdict event for EVERY task above, individually — not
  one combined event, not just the last task. A task with no verdict event
  from you is treated as unreviewed, the same as a solo gate exiting silently:
{verdict_lines}

  Do not certify a task you did not actually examine. If the group's diff
  reveals that one task is fine and another is not, FAIL that one task and
  PASS the rest — a group review is still an independent judgment per task,
  not a single verdict rubber-stamped across all of them.
"""
    if enforce_budget:
        estimate = len(packet) // CHARS_PER_TOKEN
        budget = group_token_budget(len(tasks))
        if estimate > budget:
            raise PacketTooLarge(
                f"group packet for {group_id} is ~{estimate} tokens, over the "
                f"{budget} budget for {len(tasks)} tasks. Split the group, or "
                f"drop the embedded patch (a large combined diff pushes this "
                f"over on its own)."
            )
    return packet
