"""Client-facing view layer for expenses.

Renders what a given user is allowed to see and do. Approval controls are not
implemented — that is the work Scenario B asks Company OS to staff.
"""

from __future__ import annotations


def render_expense_row(expense, viewer) -> str:
    """One line per expense, as the viewer sees it."""
    amount = f"{expense.amount_cents / 100:.2f}"
    return f"[{expense.id}] {amount} — {expense.description} ({expense.status})"


def render_expense_list(expenses, viewer) -> list[str]:
    return [render_expense_row(e, viewer) for e in expenses]


def available_actions(expense, viewer) -> list[str]:
    """Actions the viewer may take on this expense.

    Currently everyone gets the same list: submitters can do nothing further.
    """
    return []
