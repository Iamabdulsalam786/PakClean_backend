"""
OTP codes model — short-lived secrets for email verification AND password reset.

Why a dedicated table (not columns on users)?
  - OTPs are short-lived; users are long-lived
  - Resend / forgot-password create many codes over time; we invalidate old ones
  - Hash, expiry, attempts, used-flag, and purpose belong to the code lifecycle

purpose (OtpPurpose):
  - email_verification → register / resend-otp
  - password_reset → forgot-password flow
  Lookups and invalidation MUST filter by purpose to prevent cross-flow abuse.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.otp_purpose import OtpPurpose


class OtpCode(Base):
    """
    One row per OTP issued to a user for a specific purpose.

    Lifecycle:
      issue   → insert (code_hash, expires_at, is_used=False, purpose=...)
      verify  → check hash/expiry/attempts; mark is_used on success (or on reset)
      resend / new forgot-password → invalidate previous unused rows of SAME purpose
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

    # Why this OTP exists — registration verify vs password reset.
    # values_callable stores enum .value strings in Postgres (not names).
    purpose: Mapped[OtpPurpose] = mapped_column(
        Enum(
            OtpPurpose,
            name="otp_purpose",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=OtpPurpose.EMAIL_VERIFICATION,
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

    # True after successful consume OR when superseded by a newer OTP of same purpose.
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

    # Cap for attempt_count; service may also read Settings.otp_max_attempts.
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default="5",
    )

    # Drives 60s cooldown and hourly rate-limit counts.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    user = relationship("User", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<OtpCode id={self.id} purpose={self.purpose} "
            f"used={self.is_used} attempts={self.attempt_count}>"
        )
