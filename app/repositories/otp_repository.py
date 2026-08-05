"""
OtpRepository — database access for the otp_codes table.

Handles persistence only:
  - create OTP rows (always with a purpose)
  - find latest OTP scoped by email + purpose
  - invalidate unused OTPs for user + purpose (resend / new forgot)
  - count recent issues (hourly rate limit)
  - bump attempt counters / mark used

Business rules (expiry window, cooldown seconds, max attempts) live in the service.

CRITICAL: every lookup/invalidate MUST filter by purpose so a signup OTP
cannot be used (or invalidated) by the password-reset flow, and vice versa.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.otp_code import OtpCode
from app.models.otp_purpose import OtpPurpose


class OtpRepository:
    """Thin data-access layer around OtpCode rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def add(
        self,
        *,
        user_id: UUID,
        email: str,
        purpose: OtpPurpose,
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
            purpose=purpose,
            code_hash=code_hash,
            expires_at=expires_at,
            is_used=False,
            attempt_count=0,
            max_attempts=max_attempts,
        )
        self._db.add(row)
        return row

    def get_latest_for_email(
        self,
        email: str,
        *,
        purpose: OtpPurpose,
    ) -> OtpCode | None:
        """
        Newest OTP for this email + purpose (any status).

        Used for resend / forgot-password cooldown: compare created_at to now.
        """
        statement = (
            select(OtpCode)
            .where(
                OtpCode.email == email,
                OtpCode.purpose == purpose,
            )
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
        return self._db.scalar(statement)

    def get_latest_active_for_email(
        self,
        email: str,
        *,
        purpose: OtpPurpose,
    ) -> OtpCode | None:
        """
        Newest unused OTP for this email + purpose.

        Service still must check expires_at and attempt_count.
        """
        statement = (
            select(OtpCode)
            .where(
                OtpCode.email == email,
                OtpCode.purpose == purpose,
                OtpCode.is_used.is_(False),
            )
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
        return self._db.scalar(statement)

    def invalidate_active_for_user(
        self,
        user_id: UUID,
        *,
        purpose: OtpPurpose,
    ) -> int:
        """
        Mark unused OTPs for this user + purpose as used (resend / supersede).

        Does NOT touch OTPs of other purposes.
        Returns number of rows updated.
        """
        statement = (
            update(OtpCode)
            .where(
                OtpCode.user_id == user_id,
                OtpCode.purpose == purpose,
                OtpCode.is_used.is_(False),
            )
            .values(is_used=True)
        )
        result = self._db.execute(statement)
        return result.rowcount or 0

    def count_created_since(
        self,
        email: str,
        *,
        purpose: OtpPurpose,
        since: datetime,
    ) -> int:
        """
        How many OTPs were issued for email + purpose since `since`.

        Used for hourly rate limits (e.g. max 5 forgot-password OTPs / hour).
        """
        statement = (
            select(func.count())
            .select_from(OtpCode)
            .where(
                OtpCode.email == email,
                OtpCode.purpose == purpose,
                OtpCode.created_at >= since,
            )
        )
        return int(self._db.scalar(statement) or 0)

    def save(self, otp: OtpCode) -> OtpCode:
        """Persist in-memory changes (attempt_count, is_used, etc.)."""
        self._db.add(otp)
        return otp
