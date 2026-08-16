"""Task packet rendering (§5).

A Tier-2 worker receives exactly this and nothing else: no CEO conversation, no
company history, no other worker's reasoning, no PM deliberation. The role
definition already lives in the agent file — this does not re-teach the worker
what a senior backend engineer is.

Budget: ~2k tokens. Over budget means the task is too big or the scoping was
lazy, so `render` raises rather than quietly shipping a bloated packet.
"""

from __future__ import annotations

from pathlib import Path

TOKEN_BUDGET = 2000
CHARS_PER_TOKEN = 4  # rough, deliberately conservative


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
           verify: str | None = None, baseline: dict | None = None) -> str:
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
