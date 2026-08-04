"""
OTP codes model — email verification secrets for registration.

Why a dedicated table (not columns on users)?
  - OTPs are short-lived; users are long-lived
  - Resend creates many codes over time; we invalidate old ones
  - Hash, expiry, attempts, and used-flag belong to the code lifecycle

This replaces the older otp_challenges shape for the new auth flow.
Alembic will create the otp_codes table in a later migration file.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OtpCode(Base):
    """
    One row per OTP issued to a user.

    Lifecycle:
      register/resend → insert (code_hash, expires_at, is_used=False)
      verify success  → is_used=True
      resend          → mark previous active rows invalidated/used, insert new
    """

    __tablename__ = "otp_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Owner of this OTP. CASCADE: delete user → delete their OTPs.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Denormalized for lookup/logging; always store lowercased email.
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # Hash of the 6-digit OTP — NEVER store the raw code.
    code_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # created_at + OTP_EXPIRE_MINUTES (default 5).
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # True after successful verify OR when superseded by resend.
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    # Wrong verify attempts against THIS code.
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Used with attempt_count; can also read max from Settings in the service.
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default="5",
    )

    # Also drives the 60-second resend cooldown (latest row per email/user).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Optional ORM navigation: otp.user → User (lazy select by default).
    user = relationship("User", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<OtpCode id={self.id} user_id={self.user_id} "
            f"used={self.is_used} attempts={self.attempt_count}>"
        )
