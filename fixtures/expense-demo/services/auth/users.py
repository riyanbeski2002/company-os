"""User and role registry for the expense demo.

Deliberately small and dependency-free: the point of this fixture is to give
Company OS a real repo with real tests, not to be a real product.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ROLES = ("employee", "manager", "finance")


@dataclass(frozen=True)
class User:
    id: str
    name: str
    roles: tuple[str, ...] = field(default=("employee",))

    def has_role(self, role: str) -> bool:
        return role in self.roles


class UserStore:
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def add(self, user: User) -> User:
        for role in user.roles:
            if role not in ROLES:
                raise ValueError(f"unknown role {role!r}; known roles are {ROLES}")
        self._users[user.id] = user
        return user

    def get(self, user_id: str) -> User:
        if user_id not in self._users:
            raise KeyError(f"no such user {user_id!r}")
        return self._users[user_id]

    def __len__(self) -> int:
        return len(self._users)
