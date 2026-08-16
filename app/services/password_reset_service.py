"""
PasswordResetService — forgot-password / verify-reset-otp / reset-password.

Layering:
  API route → this service → repositories + EmailSender + security helpers

Owns business rules for password recovery. Does not import FastAPI.

Security rules encoded here:
  - Anti-enumeration: forgot-password always returns the same success message
  - Purpose isolation: only PASSWORD_RESET OTPs
  - Cooldown 60s + hourly cap (5) on issue
  - Approach B: verify-reset-otp does not consume; reset-password re-checks + consumes
  - On successful reset: hash new password, mark OTP used, revoke ALL refresh tokens
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.auth_exceptions import (
    AuthDomainError,
    EmailDeliveryError,
    InactiveUserError,
    InvalidOtpError,
    OtpAttemptsExceededError,
    OtpResendCooldownError,
)
from app.core.config import settings
from app.core.security import (
    generate_otp_code,
    hash_otp_code,
    hash_password,
    verify_otp_code,
)
from app.models.otp_code import OtpCode
from app.models.otp_purpose import OtpPurpose
from app.models.user import User
from app.repositories.otp_repository import OtpRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    VerifyResetOtpRequest,
    VerifyResetOtpResponse,
)
from app.services.email_factory import build_email_sender
from app.services.email_sender import EmailMessage, EmailSendError, EmailSender

logger = logging.getLogger(__name__)

# Max password-reset OTP issues per email per rolling hour.
_PASSWORD_RESET_HOURLY_LIMIT = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PasswordResetService:
    """Application service for password recovery."""

    def __init__(
        self,
        db: Session,
        *,
        email_sender: EmailSender | None = None,
    ) -> None:
        self._db = db
        self._users = UserRepository(db)
        self._otps = OtpRepository(db)
        self._refresh = RefreshTokenRepository(db)
        self._email_sender = email_sender

    def _sender(self) -> EmailSender:
        if self._email_sender is None:
            self._email_sender = build_email_sender()
        return self._email_sender

    # ------------------------------------------------------------------
    # Forgot password
    # ------------------------------------------------------------------

    def forgot_password(self, *, email: str) -> ForgotPasswordResponse:
        """
        Issue a PASSWORD_RESET OTP if a resettable account exists.

        Always returns the same response body (anti-enumeration).
        Still enforces cooldown / hourly limits when an eligible user exists
        so attackers cannot hammer SMTP for known inboxes.
        """
        normalized = email.lower().strip()
        response = ForgotPasswordResponse()
        domain = normalized.split("@")[-1] if "@" in normalized else "unknown"

        user = self._users.get_by_email(normalized)
        if not self._is_resettable(user):
            logger.info("password_reset_forgot skipped domain=%s reason=ineligible", domain)
            return response

        assert user is not None  # for type checkers; gated by _is_resettable

        latest = self._otps.get_latest_for_email(
            normalized,
            purpose=OtpPurpose.PASSWORD_RESET,
        )
        if latest is not None:
            elapsed = (_utcnow() - latest.created_at).total_seconds()
            cooldown = settings.otp_resend_cooldown_seconds
            if elapsed < cooldown:
                raise OtpResendCooldownError(int(cooldown - elapsed) or 1)

        since = _utcnow() - timedelta(hours=1)
        issued_last_hour = self._otps.count_created_since(
            normalized,
            purpose=OtpPurpose.PASSWORD_RESET,
            since=since,
        )
        if issued_last_hour >= _PASSWORD_RESET_HOURLY_LIMIT:
            raise AuthDomainError(
                "Too many password reset requests. Please try again later.",
                code="otp_rate_limit",
            )

        self._otps.invalidate_active_for_user(
            user.id,
            purpose=OtpPurpose.PASSWORD_RESET,
        )

        plain_otp = generate_otp_code(6)
        expires_at = _utcnow() + timedelta(minutes=settings.otp_expire_minutes)
        self._otps.add(
            user_id=user.id,
            email=normalized,
            purpose=OtpPurpose.PASSWORD_RESET,
            code_hash=hash_otp_code(plain_otp),
            expires_at=expires_at,
            max_attempts=settings.otp_max_attempts,
        )
        self._db.commit()

        try:
            self._send_reset_email(
                to_email=normalized,
                code=plain_otp,
                full_name=user.full_name,
            )
        except EmailSendError as exc:
            logger.exception("password_reset_email_failed domain=%s", domain)
            raise EmailDeliveryError(
                "Failed to send password reset email. Please try again."
            ) from exc

        logger.info("password_reset_otp_issued domain=%s", domain)
        return response

    # ------------------------------------------------------------------
    # Verify reset OTP (does not consume)
    # ------------------------------------------------------------------

    def verify_reset_otp(self, data: VerifyResetOtpRequest) -> VerifyResetOtpResponse:
        """
        Check that the PASSWORD_RESET OTP is valid.

        Does NOT mark the OTP used — Approach B: final consume is in reset_password.
        Still increments attempt_count on wrong codes.
        """
        normalized = str(data.email).lower().strip()
        user = self._users.get_by_email(normalized)
        otp = self._otps.get_latest_active_for_email(
            normalized,
            purpose=OtpPurpose.PASSWORD_RESET,
        )

        self._assert_otp_matches(user=user, otp=otp, code=data.code, consume=False)

        return VerifyResetOtpResponse(email=normalized)

    # ------------------------------------------------------------------
    # Reset password (re-check OTP + consume)
    # ------------------------------------------------------------------

    def reset_password(self, data: ResetPasswordRequest) -> ResetPasswordResponse:
        """
        Re-validate OTP, set new password hash, consume OTP, revoke all sessions.
        """
        normalized = str(data.email).lower().strip()
        domain = normalized.split("@")[-1] if "@" in normalized else "unknown"

        user = self._users.get_by_email(normalized)
        otp = self._otps.get_latest_active_for_email(
            normalized,
            purpose=OtpPurpose.PASSWORD_RESET,
        )

        self._assert_otp_matches(user=user, otp=otp, code=data.code, consume=True)

        assert user is not None and otp is not None

        if not user.is_active:
            raise InactiveUserError()

        user.hashed_password = hash_password(data.new_password)
        self._users.save(user)

        otp.is_used = True
        self._otps.save(otp)

        revoked = self._refresh.revoke_all_for_user(user.id, revoked_at=_utcnow())
        self._db.commit()

        logger.info(
            "password_reset_success domain=%s sessions_revoked=%s",
            domain,
            revoked,
        )
        return ResetPasswordResponse()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_resettable(user: User | None) -> bool:
        """
        Only verified, active accounts with a password may reset.

        Unverified / missing / inactive → treat like "no account" for responses.
        """
        if user is None:
            return False
        if not user.is_active or not user.is_verified:
            return False
        if not user.hashed_password:
            return False
        return True

    def _assert_otp_matches(
        self,
        *,
        user: User | None,
        otp: OtpCode | None,
        code: str,
        consume: bool,
    ) -> None:
        """
        Shared OTP checks for verify-reset-otp and reset-password.

        `consume` is reserved for clarity at call sites; marking used happens
        in reset_password after this returns (Approach B).
        """
        _ = consume  # documented intent; consume is applied by caller

        if user is None or otp is None or not self._is_resettable(user):
            raise InvalidOtpError()

        if otp.attempt_count >= otp.max_attempts:
            raise OtpAttemptsExceededError()

        if otp.expires_at <= _utcnow():
            raise InvalidOtpError()

        if not verify_otp_code(code, otp.code_hash):
            otp.attempt_count += 1
            self._otps.save(otp)
            self._db.commit()
            if otp.attempt_count >= otp.max_attempts:
                raise OtpAttemptsExceededError()
            raise InvalidOtpError()

    def _send_reset_email(self, *, to_email: str, code: str, full_name: str) -> None:
        """Send password-reset OTP. Never log the code."""
        minutes = settings.otp_expire_minutes
        body = (
            f"Hi {full_name},\n\n"
            f"Your Pak Clean password reset code is: {code}\n\n"
            f"This code expires in {minutes} minutes.\n"
            f"If you did not request a password reset, ignore this email.\n"
        )
        self._sender().send(
            EmailMessage(
                to_email=to_email,
                subject="Pak Clean — Password reset code",
                body_text=body,
            )
        )
