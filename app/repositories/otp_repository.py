"""
OtpRepository — database access for the otp_codes table.

Handles persistence only:
  - create OTP rows
  - find latest active OTP
  - invalidate previous OTPs (resend)
  - bump attempt counters / mark used

Business rules (expiry window, cooldown seconds, max attempts) live in the service.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.otp_code import OtpCode


class OtpRepository:
    """Thin data-access layer around OtpCode rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def add(
        self,
        *,
        user_id: UUID,
        email: str,
        code_hash: str,
        expires_at: datetime,
        max_attempts: int = 5,
    ) -> OtpCode:
        """
        Insert a new OTP row (not committed).

        Caller must pass an already-hashed code — never plaintext.
        """
        row = OtpCode(
            user_id=user_id,
            email=email,
            code_hash=code_hash,
            expires_at=expires_at,
            is_used=False,
            attempt_count=0,
            max_attempts=max_attempts,
        )
        self._db.add(row)
        return row

    def get_latest_for_email(self, email: str) -> OtpCode | None:
        """
        Newest OTP for this email (any status).

        Used for resend cooldown: compare created_at to now.
        """
        statement = (
            select(OtpCode)
            .where(OtpCode.email == email)
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
        return self._db.scalar(statement)

    def get_latest_active_for_email(self, email: str) -> OtpCode | None:
        """
        Newest unused OTP for verify flow.

        Service still must check expires_at and attempt_count.
        """
        statement = (
            select(OtpCode)
            .where(
                OtpCode.email == email,
                OtpCode.is_used.is_(False),
            )
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
        return self._db.scalar(statement)

    def invalidate_active_for_user(self, user_id: UUID) -> int:
        """
        Mark all unused OTPs for this user as used (resend / supersede).

        Returns number of rows updated.
        """
        statement = (
            update(OtpCode)
            .where(
                OtpCode.user_id == user_id,
                OtpCode.is_used.is_(False),
            )
            .values(is_used=True)
        )
        result = self._db.execute(statement)
        return result.rowcount or 0

    def save(self, otp: OtpCode) -> OtpCode:
        """Persist in-memory changes (attempt_count, is_used, etc.)."""
        self._db.add(otp)
        return otp
