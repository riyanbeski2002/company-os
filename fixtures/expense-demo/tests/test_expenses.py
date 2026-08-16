import unittest

from api.approvals.expenses import ExpenseStore
from services.auth.users import ROLES, User, UserStore


class TestUsers(unittest.TestCase):
    def test_add_and_get(self):
        store = UserStore()
        store.add(User("u1", "Asha", ("employee",)))
        self.assertEqual(store.get("u1").name, "Asha")

    def test_unknown_role_rejected(self):
        store = UserStore()
        with self.assertRaises(ValueError):
            store.add(User("u2", "Bo", ("wizard",)))

    def test_has_role(self):
        user = User("u3", "Cy", ("employee", "manager"))
        self.assertTrue(user.has_role("manager"))
        self.assertFalse(user.has_role("finance"))

    def test_known_roles(self):
        self.assertEqual(ROLES, ("employee", "manager", "finance"))

    def test_missing_user(self):
        with self.assertRaises(KeyError):
            UserStore().get("nope")


class TestExpenses(unittest.TestCase):
    def setUp(self):
        self.store = ExpenseStore()

    def test_submit(self):
        e = self.store.submit("u1", 4200, "Taxi to client site")
        self.assertEqual(e.status, "submitted")
        self.assertEqual(e.amount_cents, 4200)

    def test_rejects_zero_amount(self):
        with self.assertRaises(ValueError):
            self.store.submit("u1", 0, "Nothing")

    def test_rejects_blank_description(self):
        with self.assertRaises(ValueError):
            self.store.submit("u1", 100, "   ")

    def test_for_owner(self):
        self.store.submit("u1", 100, "One")
        self.store.submit("u2", 200, "Two")
        self.assertEqual(len(self.store.for_owner("u1")), 1)

    def test_missing_expense(self):
        with self.assertRaises(KeyError):
            self.store.get(9999)


if __name__ == "__main__":
    unittest.main()
