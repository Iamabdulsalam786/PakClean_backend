"""
UserRepository — database access for the users table.

Why repositories exist (Clean Architecture):
  - Services contain BUSINESS rules (verify OTP, block unverified login).
  - Repositories contain DATA access (SQLAlchemy queries only).
  - Benefit: you can unit-test AuthService with a fake repository,
    and you can change SQL without rewriting auth rules.

Beginner mistake: putting select/insert logic directly inside FastAPI routes.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole


class UserRepository:
    """Thin data-access layer around User rows."""

    def __init__(self, db: Session) -> None:
        # One repository instance per request/session is typical.
        self._db = db

    def get_by_id(self, user_id: UUID) -> User | None:
        """Primary-key lookup (used by /auth/me and JWT sub resolution)."""
        return self._db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        """
        Login / register / OTP flows look up by email.

        Email must already be normalized to lowercase by the service layer.
        """
        statement = select(User).where(User.email == email)
        return self._db.scalar(statement)

    def get_by_phone(self, phone: str) -> User | None:
        """Duplicate-phone checks during registration."""
        statement = select(User).where(User.phone == phone)
        return self._db.scalar(statement)

    def add(
        self,
        *,
        full_name: str,
        email: str,
        phone: str | None,
        hashed_password: str,
        role: UserRole,
        is_verified: bool = False,
        is_active: bool = True,
    ) -> User:
        """
        Create a user row in memory and add it to the session.

        Does NOT commit — the service decides transaction boundaries
        (e.g. create user + OTP in one commit).
        """
        user = User(
            full_name=full_name,
            email=email,
            phone=phone,
            hashed_password=hashed_password,
            role=role,
            is_verified=is_verified,
            is_active=is_active,
        )
        self._db.add(user)
        return user

    def save(self, user: User) -> User:
        """
        Persist pending changes for an existing user instance.

        Example: set is_verified=True after OTP success, then save.
        Still does not commit by itself.
        """
        self._db.add(user)
        return user
