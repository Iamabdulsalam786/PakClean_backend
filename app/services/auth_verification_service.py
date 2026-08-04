"""
Auth verification use-cases: register, verify OTP, resend, login, refresh.

Layering:
  API route → this service → repositories + EmailSender + security helpers

This module owns business rules. It does not import FastAPI.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.auth_exceptions import (
    AuthDomainError,
    EmailDeliveryError,
    EmailNotVerifiedError,
    EmailTakenError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidOtpError,
    InvalidRefreshTokenError,
    OtpAttemptsExceededError,
    OtpResendCooldownError,
    PhoneTakenError,
)
from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_otp_code,
    generate_refresh_token,
    hash_otp_code,
    hash_password,
    hash_refresh_token,
    verify_otp_code,
    verify_password,
)
from app.models.user import User, UserRole
from app.repositories.otp_repository import OtpRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    RefreshResponse,
    RegisterResponse,
    TokenPair,
    UserLogin,
    UserRegister,
)
from app.services.email_factory import build_email_sender
from app.services.email_sender import EmailMessage, EmailSendError, EmailSender

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthVerificationService:
    """Application service for email-verified authentication."""

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
        # Lazy/default wiring keeps tests able to inject a fake sender.
        self._email_sender = email_sender

    def _sender(self) -> EmailSender:
        if self._email_sender is None:
            self._email_sender = build_email_sender()
        return self._email_sender

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    def register(self, data: UserRegister) -> RegisterResponse:
        """
        Create unverified user, store hashed OTP, send real email.

        Transaction strategy:
          1) Validate uniqueness
          2) Insert user + OTP
          3) Commit
          4) Send email (outside DB transaction)
          5) If email fails → EmailDeliveryError (client should call resend-otp)
        """
        email = str(data.email).lower().strip()
        phone = data.phone.strip()

        if self._users.get_by_email(email) is not None:
            raise EmailTakenError()
        if self._users.get_by_phone(phone) is not None:
            raise PhoneTakenError()

        if data.role not in {UserRole.CUSTOMER, UserRole.PROVIDER}:
            raise AuthDomainError("Invalid role", code="invalid_role")

        user = self._users.add(
            full_name=data.full_name.strip(),
            email=email,
            phone=phone,
            hashed_password=hash_password(data.password),
            role=data.role,
            is_verified=False,
            is_active=True,
        )
        self._db.flush()  # assign user.id before OTP insert

        plain_otp = generate_otp_code(6)
        expires_at = _utcnow() + timedelta(minutes=settings.otp_expire_minutes)
        self._otps.add(
            user_id=user.id,
            email=email,
            code_hash=hash_otp_code(plain_otp),
            expires_at=expires_at,
            max_attempts=settings.otp_max_attempts,
        )
        self._db.commit()
        self._db.refresh(user)

        try:
            self._send_otp_email(to_email=email, code=plain_otp, full_name=user.full_name)
        except EmailSendError as exc:
            logger.exception("OTP email failed after register email_domain=%s", email.split("@")[-1])
            raise EmailDeliveryError(
                "Account created but failed to send verification email. Please use resend-otp."
            ) from exc

        # Never log or return plain_otp.
        return RegisterResponse(email=email, user_id=user.id)

    # ------------------------------------------------------------------
    # Verify OTP
    # ------------------------------------------------------------------

    def verify_otp(self, *, email: str, code: str) -> TokenPair:
        """Mark OTP used, set is_verified=True, issue access + refresh tokens."""
        normalized = email.lower().strip()
        user = self._users.get_by_email(normalized)
        otp = self._otps.get_latest_active_for_email(normalized)

        # Generic failure path reduces account enumeration.
        if user is None or otp is None:
            raise InvalidOtpError()

        if not user.is_active:
            raise InactiveUserError()

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

        otp.is_used = True
        self._otps.save(otp)

        user.is_verified = True
        self._users.save(user)
        self._db.commit()
        self._db.refresh(user)

        return self._issue_token_pair(user)

    # ------------------------------------------------------------------
    # Resend OTP
    # ------------------------------------------------------------------

    def resend_otp(self, *, email: str) -> str:
        """
        Invalidate old OTPs, create a new one, send email.

        Always returns a generic message when possible to reduce enumeration.
        Still enforces cooldown when an unverified user exists.
        """
        normalized = email.lower().strip()
        generic = "If an unverified account exists for this email, a new OTP has been sent."

        user = self._users.get_by_email(normalized)
        if user is None or user.is_verified or not user.is_active:
            # Do not reveal which case matched.
            return generic

        latest = self._otps.get_latest_for_email(normalized)
        if latest is not None:
            elapsed = (_utcnow() - latest.created_at).total_seconds()
            cooldown = settings.otp_resend_cooldown_seconds
            if elapsed < cooldown:
                raise OtpResendCooldownError(int(cooldown - elapsed) or 1)

        self._otps.invalidate_active_for_user(user.id)

        plain_otp = generate_otp_code(6)
        expires_at = _utcnow() + timedelta(minutes=settings.otp_expire_minutes)
        self._otps.add(
            user_id=user.id,
            email=normalized,
            code_hash=hash_otp_code(plain_otp),
            expires_at=expires_at,
            max_attempts=settings.otp_max_attempts,
        )
        self._db.commit()

        try:
            self._send_otp_email(
                to_email=normalized,
                code=plain_otp,
                full_name=user.full_name,
            )
        except EmailSendError as exc:
            logger.exception("OTP resend email failed domain=%s", normalized.split("@")[-1])
            raise EmailDeliveryError() from exc

        return generic

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self, data: UserLogin) -> TokenPair:
        """Password login — blocked until email is verified."""
        email = str(data.email).lower().strip()
        user = self._users.get_by_email(email)

        if user is None or not user.hashed_password:
            raise InvalidCredentialsError()

        if not verify_password(data.password, user.hashed_password):
            raise InvalidCredentialsError()

        if not user.is_active:
            raise InactiveUserError()

        if not user.is_verified:
            raise EmailNotVerifiedError()

        return self._issue_token_pair(user)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self, raw_refresh_token: str) -> RefreshResponse:
        """Rotate refresh token: revoke old, issue new access + refresh."""
        token_hash = hash_refresh_token(raw_refresh_token)
        row = self._refresh.get_by_token_hash(token_hash)

        if row is None or row.revoked_at is not None:
            raise InvalidRefreshTokenError()

        if row.expires_at <= _utcnow():
            raise InvalidRefreshTokenError()

        user = self._users.get_by_id(row.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError()
        if not user.is_verified:
            raise EmailNotVerifiedError()

        self._refresh.revoke(row, revoked_at=_utcnow())
        pair = self._issue_token_pair(user)
        return RefreshResponse(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _issue_token_pair(self, user: User) -> TokenPair:
        access = create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.value},
        )
        raw_refresh = generate_refresh_token()
        refresh_expires = _utcnow() + timedelta(days=settings.refresh_token_expire_days)
        self._refresh.add(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_expires,
        )
        self._db.commit()
        return TokenPair(
            access_token=access,
            refresh_token=raw_refresh,
            role=user.role,
        )

    def _send_otp_email(self, *, to_email: str, code: str, full_name: str) -> None:
        """Send the OTP via EmailSender. Must never be logged by callers."""
        minutes = settings.otp_expire_minutes
        body = (
            f"Hi {full_name},\n\n"
            f"Your Pak Clean verification code is: {code}\n\n"
            f"This code expires in {minutes} minutes.\n"
            f"If you did not create an account, ignore this email.\n"
        )
        self._sender().send(
            EmailMessage(
                to_email=to_email,
                subject="Pak Clean — Email verification code",
                body_text=body,
            )
        )
