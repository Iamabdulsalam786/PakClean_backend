"""
User model — identity for customers, providers, and admins.

Phase 1 design:
  - One users table; role decides permissions
  - Providers get a separate ProviderProfile later (skills, verification, location)
  - Passwords are stored hashed only (see app.core.security later)
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

    # Optional in Phase 1; phone OTP / unique constraint can tighten later.
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

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    is_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    is_onboarding_complete: Mapped[bool] = mapped_column(
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
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
