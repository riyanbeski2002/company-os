"""Expense submission and listing.

Approval is intentionally NOT implemented here — that is the work Scenario B
asks Company OS to staff and deliver.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count

_ids = count(1)

STATUSES = ("submitted", "approved", "rejected")


@dataclass
class Expense:
    id: int
    owner_id: str
    amount_cents: int
    description: str
    status: str = "submitted"


class ExpenseStore:
    def __init__(self) -> None:
        self._expenses: dict[int, Expense] = {}

    def submit(self, owner_id: str, amount_cents: int, description: str) -> Expense:
        if amount_cents <= 0:
            raise ValueError("amount must be positive")
        if not description.strip():
            raise ValueError("description is required")
        expense = Expense(next(_ids), owner_id, amount_cents, description)
        self._expenses[expense.id] = expense
        return expense

    def get(self, expense_id: int) -> Expense:
        if expense_id not in self._expenses:
            raise KeyError(f"no such expense {expense_id}")
        return self._expenses[expense_id]

    def for_owner(self, owner_id: str) -> list[Expense]:
        return [e for e in self._expenses.values() if e.owner_id == owner_id]

    def all(self) -> list[Expense]:
        return list(self._expenses.values())
