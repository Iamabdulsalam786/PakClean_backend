"""
OTP challenge model — email one-time passwords for login/register.

Interview talking points:
  - Store a hash of the code, never the plain OTP (same idea as passwords).
  - Expiry + attempt limits reduce brute-force risk.
  - Delivery (console / Resend / SendGrid) is outside this table — provider layer.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OtpChallenge(Base):
    """
    One row per OTP send attempt for an email address.

    Lifecycle:
      request → create row (hashed code, expires_at)
      verify  → check hash/expiry/attempts → set consumed_at
    """

    __tablename__ = "otp_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Normalized lowercase email this OTP was sent to.
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # bcrypt/sha256 hash of the 6-digit code — never store plain "123456".
    code_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # How many wrong verify attempts so far (lock after N).
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Set when verify succeeds — row cannot be reused.
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<OtpChallenge id={self.id} email={self.email!r}>"
