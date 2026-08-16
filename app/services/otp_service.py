"""
Email OTP business logic: request and verify.

Delivery is intentionally dumb for now (log + optional dev_code).
Later swap in Resend/SendGrid without changing these rules.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.otp import OtpChallenge
from app.models.user import User, UserRole
from app.schemas.auth import PUBLIC_ROLES
from app.schemas.otp import OtpRequestResponse, OtpVerifyResponse

logger = logging.getLogger(__name__)

OTP_EXPIRE_SECONDS = 300  # 5 minutes
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60


class OtpError(Exception):
    """Domain error for OTP failures — routes map codes to HTTP status."""

    def __init__(self, message: str, *, code: str = "otp_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def _generate_otp_code() -> str:
    """Cryptographically strong 6-digit code (000000–999999)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _latest_active_challenge(db: Session, email: str) -> OtpChallenge | None:
    """Newest non-consumed challenge for this email (may still be expired)."""
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
    """
    Create an OTP challenge and "send" it.

    Always returns a generic success message (anti user-enumeration).
    """
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

    # Dev "email provider": log the code. Replace with real SMTP/API later.
    logger.info("OTP for %s: %s (expires in %ss)", normalized, code, OTP_EXPIRE_SECONDS)

    return OtpRequestResponse(
        expires_in_seconds=OTP_EXPIRE_SECONDS,
        dev_code=code if settings.debug else None,
    )


def verify_email_otp(
    db: Session,
    email: str,
    code: str,
    *,
    role: UserRole = UserRole.CUSTOMER,
) -> OtpVerifyResponse:
    """
    Validate OTP, create user if needed (customer or provider), return access token.

    `role` is used only when creating a new account; existing users keep their role.
    """
    if role not in PUBLIC_ROLES:
        raise OtpError("Invalid role for registration", code="invalid_role")

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

    user = db.scalar(select(User).where(User.email == normalized))
    is_new_user = False
    if user is None:
        # OTP can onboard customer or provider without a password.
        local_part = normalized.split("@", maxsplit=1)[0] or "User"
        user = User(
            email=normalized,
            full_name=local_part[:150],
            hashed_password=None,
            role=role,
            is_active=True,
        )
        db.add(user)
        is_new_user = True
    elif not user.is_active:
        raise OtpError("Inactive user", code="inactive_user")

    # Success — consume so the code cannot be reused.
    challenge.consumed_at = now
    db.add(challenge)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value},
    )
    return OtpVerifyResponse(
        access_token=token,
        role=user.role,
        is_new_user=is_new_user,
    )
