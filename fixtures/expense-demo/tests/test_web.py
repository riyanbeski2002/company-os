import unittest

from api.approvals.expenses import ExpenseStore
from services.auth.users import User
from web.client import available_actions, render_expense_list, render_expense_row


class TestClient(unittest.TestCase):
    def setUp(self):
        self.store = ExpenseStore()
        self.viewer = User("u1", "Asha", ("employee",))
        self.expense = self.store.submit("u1", 4200, "Taxi")

    def test_render_row_includes_amount_and_status(self):
        row = render_expense_row(self.expense, self.viewer)
        self.assertIn("42.00", row)
        self.assertIn("submitted", row)

    def test_render_list_one_row_each(self):
        self.store.submit("u1", 100, "Coffee")
        rows = render_expense_list(self.store.for_owner("u1"), self.viewer)
        self.assertEqual(len(rows), 2)

    def test_employee_has_no_actions(self):
        self.assertEqual(available_actions(self.expense, self.viewer), [])


if __name__ == "__main__":
    unittest.main()
