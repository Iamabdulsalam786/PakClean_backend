"""
User model — identity for customers, providers, and admins.

Auth redesign:
  - Register creates users with is_verified=False until email OTP succeeds
  - Login must reject unverified accounts
  - role supports the mobile signup toggle (customer | provider)
  - Passwords are stored hashed only (never plaintext)
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, enum.Enum):
    """
    Application roles.

    Inheriting from str makes JSON / Pydantic serialization use the value
    ("customer") instead of "UserRole.CUSTOMER".
    """

    CUSTOMER = "customer"
    PROVIDER = "provider"
    ADMIN = "admin"


class User(Base):
    """ORM mapping for the users table."""

    __tablename__ = "users"

    # UUID primary key: safe to expose in APIs; avoids sequential ID guessing.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    # Required on the mobile signup form; nullable in DB for legacy/OTP-only rows.
    # Uniqueness still enforced when phone is present (Postgres allows multiple NULLs).
    phone: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=True,
    )

    # Nullable until we add social-only login; email/password users must set it.
    hashed_password: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    full_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=UserRole.CUSTOMER,
        index=True,
    )

    # False until POST /auth/verify-otp succeeds. Login must check this flag.
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<User id={self.id} email={self.email!r} "
            f"role={self.role} verified={self.is_verified}>"
        )
