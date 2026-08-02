from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_otp, get_otp_expiry, hash_value, verify_value
from app.models.user import OtpCode, OtpPurpose, User
from app.services.email_service import send_otp_email


class OtpService:
    @staticmethod
    async def _get_recent_otp(
        db: AsyncSession,
        *,
        email: str,
        purpose: OtpPurpose,
    ) -> OtpCode | None:
        result = await db.execute(
            select(OtpCode)
            .where(
                OtpCode.email == email.lower(),
                OtpCode.purpose == purpose,
                OtpCode.is_used.is_(False),
            )
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_and_send(
        db: AsyncSession,
        *,
        email: str,
        purpose: OtpPurpose,
        user: User | None = None,
    ) -> str:
        email = email.lower()
        recent = await OtpService._get_recent_otp(db, email=email, purpose=purpose)

        if recent:
            cooldown_until = recent.created_at.replace(tzinfo=UTC) + timedelta(
                seconds=settings.otp_resend_cooldown_seconds
            )
            if datetime.now(UTC) < cooldown_until:
                remaining = int((cooldown_until - datetime.now(UTC)).total_seconds())
                from app.core.exceptions import AppHTTPException

                raise AppHTTPException(
                    status_code=429,
                    message=f"Please wait {remaining} seconds before requesting a new code",
                    code="OTP_COOLDOWN",
                )

        otp = generate_otp()
        record = OtpCode(
            user_id=user.id if user else None,
            email=email,
            code_hash=hash_value(otp),
            purpose=purpose,
            expires_at=get_otp_expiry(),
        )
        db.add(record)
        await db.flush()

        await send_otp_email(to_email=email, otp=otp, purpose=purpose.value)
        return otp

    @staticmethod
    async def verify(
        db: AsyncSession,
        *,
        email: str,
        otp: str,
        purpose: OtpPurpose,
    ) -> OtpCode:
        from app.core.exceptions import AppHTTPException

        email = email.lower()
        result = await db.execute(
            select(OtpCode)
            .where(
                OtpCode.email == email,
                OtpCode.purpose == purpose,
                OtpCode.is_used.is_(False),
            )
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()

        if not record:
            raise AppHTTPException(status_code=400, message="Invalid or expired OTP", code="INVALID_OTP")

        if record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise AppHTTPException(status_code=400, message="OTP has expired", code="OTP_EXPIRED")

        if record.attempts >= settings.otp_max_attempts:
            raise AppHTTPException(status_code=429, message="Too many OTP attempts", code="OTP_MAX_ATTEMPTS")

        if not verify_value(otp, record.code_hash):
            record.attempts += 1
            await db.flush()
            raise AppHTTPException(status_code=400, message="Invalid OTP code", code="INVALID_OTP")

        record.is_used = True
        await db.flush()
        return record
