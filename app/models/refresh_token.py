"""
Refresh token model — revocable long-lived session credentials.

Why this table exists:
  - Access JWTs are short-lived and cannot be revoked until they expire.
  - Refresh tokens in the DB can be revoked (logout, theft, rotation).
  - We store only a HASH of the token (same idea as OTP / password).

Used by:
  POST /auth/verify-otp  → issue access + refresh
  POST /auth/login       → issue access + refresh
  POST /auth/refresh     → rotate: revoke old, issue new pair
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RefreshToken(Base):
    """ORM mapping for the refresh_tokens table."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Session owner. CASCADE: deleting a user removes their sessions.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hash of the opaque refresh token string sent to the client.
    # If the DB leaks, attackers still cannot reuse tokens without the raw value.
    token_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    # Absolute expiry (e.g. now + REFRESH_TOKEN_EXPIRE_DAYS).
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # NULL = active. Set on logout, rotation, or admin revoke.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Optional device fingerprinting later (not required for Phase 1).
    user_agent: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    user = relationship("User", lazy="joined")

    def __repr__(self) -> str:
        active = self.revoked_at is None
        return f"<RefreshToken id={self.id} user_id={self.user_id} active={active}>"
