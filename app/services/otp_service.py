"""
Email OTP business logic aligned with sign-up → verify → login flow.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.integrations.email import deliver_otp_email
from app.models.otp import OtpChallenge
from app.models.user import User
from app.schemas.otp import OtpRequestResponse
from app.services.user_queries import get_user_by_email

logger = logging.getLogger(__name__)

OTP_EXPIRE_SECONDS = 300
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60


class OtpError(Exception):
    def __init__(self, message: str, *, code: str = "otp_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def _generate_otp_code() -> str:
    """Cryptographically secure 6-digit OTP (000000–999999)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _latest_active_challenge(db: Session, email: str) -> OtpChallenge | None:
    statement = (
        select(OtpChallenge)
        .where(
            OtpChallenge.email == email,
            OtpChallenge.consumed_at.is_(None),
        )
        .order_by(OtpChallenge.created_at.desc())
        .limit(1)
    )
    return db.scalar(statement)


def request_email_otp(db: Session, email: str) -> OtpRequestResponse:
    normalized = email.lower().strip()
    now = datetime.now(timezone.utc)

    existing = _latest_active_challenge(db, normalized)
    if existing is not None:
        age = (now - existing.created_at).total_seconds()
        if age < OTP_RESEND_COOLDOWN_SECONDS:
            raise OtpError(
                "Please wait before requesting another code",
                code="otp_cooldown",
            )

    code = _generate_otp_code()
    challenge = OtpChallenge(
        email=normalized,
        code_hash=hash_password(code),
        expires_at=now + timedelta(seconds=OTP_EXPIRE_SECONDS),
        attempt_count=0,
    )
    db.add(challenge)
    db.commit()

    expires_minutes = OTP_EXPIRE_SECONDS // 60
    delivery = deliver_otp_email(
        to_email=normalized,
        code=code,
        expires_minutes=expires_minutes,
    )

    show_dev_code = settings.debug and not delivery.delivered

    return OtpRequestResponse(
        expires_in_seconds=OTP_EXPIRE_SECONDS,
        email_delivered=delivery.delivered,
        delivery_provider=delivery.provider if delivery.delivered else None,
        dev_code=code if show_dev_code else None,
        message=(
            "Verification code sent to your email."
            if delivery.delivered
            else "Verification code generated. Check the app or backend logs (email not configured)."
        ),
    )


def verify_email_otp(db: Session, email: str, code: str):
    """Verify OTP, mark email verified, return JWT + user."""
    from app.services.auth_service import build_session_response

    normalized = email.lower().strip()
    now = datetime.now(timezone.utc)

    challenge = _latest_active_challenge(db, normalized)
    if challenge is None:
        raise OtpError("Invalid or expired code", code="otp_invalid")

    if challenge.expires_at < now:
        raise OtpError("Invalid or expired code", code="otp_invalid")

    if challenge.attempt_count >= OTP_MAX_ATTEMPTS:
        raise OtpError("Too many attempts. Request a new code.", code="otp_locked")

    if not verify_password(code, challenge.code_hash):
        challenge.attempt_count += 1
        db.add(challenge)
        db.commit()
        raise OtpError("Invalid or expired code", code="otp_invalid")

    user = get_user_by_email(db, normalized)
    if user is None:
        raise OtpError(
            "No account found for this email. Please sign up first.",
            code="otp_no_account",
        )

    if not user.is_active:
        raise OtpError("Inactive user", code="inactive_user")

    if user.is_email_verified:
        raise OtpError("Email already verified. Please sign in.", code="otp_already_verified")

    user.is_email_verified = True
    challenge.consumed_at = now
    db.add(user)
    db.add(challenge)
    db.commit()
    db.refresh(user)

    return build_session_response(user)
