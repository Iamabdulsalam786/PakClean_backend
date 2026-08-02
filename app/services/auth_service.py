from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppHTTPException
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    generate_reset_token,
    get_refresh_expiry,
    get_reset_token_expiry,
    hash_password,
    hash_value,
    verify_password,
    verify_value,
)
from app.models.user import OtpPurpose, PasswordResetToken, RefreshToken, User, UserRole, UserStatus
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshTokenResponse,
    RegisterRequest,
    RegisterResponse,
    ResendOtpRequest,
    ResendOtpResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    UserPublic,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from app.services.otp_service import OtpService


def _resolve_next_step(user: User) -> str:
    if not user.is_email_verified:
        return "verify_email"
    if user.role == UserRole.cleaner and not user.is_onboarding_complete:
        return "agreement"
    return "home"


def _to_user_public(user: User) -> UserPublic:
    return UserPublic(
        id=str(user.id),
        fullName=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role.value,
        isEmailVerified=user.is_email_verified,
        isOnboardingComplete=user.is_onboarding_complete,
        profileImageUrl=user.profile_image_url,
    )


async def _issue_tokens(
    db: AsyncSession,
    *,
    user: User,
    remember_me: bool = False,
) -> tuple[str, str, int]:
    access_token = create_access_token(user_id=user.id, email=user.email, role=user.role.value)
    refresh_token = generate_refresh_token()
    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_value(refresh_token),
        remember_me=remember_me,
        expires_at=get_refresh_expiry(remember_me=remember_me),
    )
    db.add(refresh_record)
    await db.flush()
    return access_token, refresh_token, settings.jwt_access_expires_minutes * 60


class AuthService:
    @staticmethod
    async def register(db: AsyncSession, payload: RegisterRequest) -> RegisterResponse:
        if payload.password != payload.confirmPassword:
            raise AppHTTPException(
                status_code=400,
                message="Passwords do not match",
                code="VALIDATION_ERROR",
                errors={"confirmPassword": ["Passwords do not match"]},
            )

        email = payload.email.lower()
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            raise AppHTTPException(
                status_code=409,
                message="Email is already registered",
                code="EMAIL_EXISTS",
                errors={"email": ["Email is already registered"]},
            )

        user = User(
            full_name=payload.fullName.strip(),
            email=email,
            phone=payload.phone.strip(),
            password_hash=hash_password(payload.password),
            role=UserRole(payload.role),
            status=UserStatus.pending,
            is_email_verified=False,
            is_onboarding_complete=payload.role == "customer",
        )
        db.add(user)
        await db.flush()

        await OtpService.create_and_send(
            db,
            email=email,
            purpose=OtpPurpose.email_verification,
            user=user,
        )

        return RegisterResponse(
            userId=str(user.id),
            email=user.email,
            role=user.role.value,
            otpSent=True,
            expiresIn=settings.otp_expires_minutes * 60,
            nextStep="verify_email",
        )

    @staticmethod
    async def verify_otp(db: AsyncSession, payload: VerifyOtpRequest) -> VerifyOtpResponse:
        purpose = OtpPurpose(payload.purpose)
        await OtpService.verify(db, email=payload.email, otp=payload.otp, purpose=purpose)

        if purpose == OtpPurpose.email_verification:
            result = await db.execute(select(User).where(User.email == payload.email.lower()))
            user = result.scalar_one_or_none()
            if not user:
                raise AppHTTPException(status_code=404, message="User not found", code="NOT_FOUND")

            user.is_email_verified = True
            user.status = UserStatus.active
            await db.flush()

            access, refresh, expires_in = await _issue_tokens(db, user=user)
            return VerifyOtpResponse(
                user=_to_user_public(user),
                accessToken=access,
                refreshToken=refresh,
                expiresIn=expires_in,
                nextStep=_resolve_next_step(user),
            )

        reset_token = generate_reset_token()
        result = await db.execute(select(User).where(User.email == payload.email.lower()))
        user = result.scalar_one_or_none()
        if not user:
            raise AppHTTPException(status_code=404, message="User not found", code="NOT_FOUND")

        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_value(reset_token),
                expires_at=get_reset_token_expiry(),
            )
        )
        await db.flush()

        return VerifyOtpResponse(
            resetToken=reset_token,
            expiresIn=900,
            nextStep="reset_password",
        )

    @staticmethod
    async def resend_otp(db: AsyncSession, payload: ResendOtpRequest) -> ResendOtpResponse:
        purpose = OtpPurpose(payload.purpose)
        email = payload.email.lower()

        user = None
        if purpose == OtpPurpose.email_verification:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                raise AppHTTPException(status_code=404, message="User not found", code="NOT_FOUND")
            if user.is_email_verified:
                raise AppHTTPException(status_code=400, message="Email already verified", code="ALREADY_VERIFIED")

        await OtpService.create_and_send(db, email=email, purpose=purpose, user=user)
        return ResendOtpResponse(
            expiresIn=settings.otp_expires_minutes * 60,
            retryAfter=settings.otp_resend_cooldown_seconds,
        )

    @staticmethod
    async def login(db: AsyncSession, payload: LoginRequest) -> LoginResponse:
        result = await db.execute(select(User).where(User.email == payload.email.lower()))
        user = result.scalar_one_or_none()

        if not user or not verify_password(payload.password, user.password_hash):
            raise AppHTTPException(status_code=401, message="Invalid email or password", code="INVALID_CREDENTIALS")

        if not user.is_email_verified:
            raise AppHTTPException(
                status_code=403,
                message="Please verify your email before logging in",
                code="EMAIL_NOT_VERIFIED",
            )

        if user.status == UserStatus.suspended:
            raise AppHTTPException(status_code=403, message="Account is suspended", code="ACCOUNT_SUSPENDED")

        user.last_login_at = datetime.now(UTC)
        access, refresh, expires_in = await _issue_tokens(db, user=user, remember_me=payload.rememberMe)

        return LoginResponse(
            user=_to_user_public(user),
            accessToken=access,
            refreshToken=refresh,
            expiresIn=expires_in,
            nextStep=_resolve_next_step(user),
        )

    @staticmethod
    async def forgot_password(db: AsyncSession, payload: ForgotPasswordRequest) -> dict[str, str]:
        email = payload.email.lower()
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            await OtpService.create_and_send(
                db,
                email=email,
                purpose=OtpPurpose.password_reset,
                user=user,
            )

        return {
            "message": "If an account exists with this email, a verification code has been sent",
        }

    @staticmethod
    async def reset_password(db: AsyncSession, payload: ResetPasswordRequest) -> ResetPasswordResponse:
        if payload.newPassword != payload.confirmPassword:
            raise AppHTTPException(
                status_code=400,
                message="Passwords do not match",
                code="VALIDATION_ERROR",
                errors={"confirmPassword": ["Passwords do not match"]},
            )

        result = await db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.is_used.is_(False))
            .order_by(PasswordResetToken.created_at.desc())
        )
        tokens = result.scalars().all()
        matched: PasswordResetToken | None = None

        for token in tokens:
            if verify_value(payload.resetToken, token.token_hash):
                matched = token
                break

        if not matched or matched.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise AppHTTPException(status_code=400, message="Invalid or expired reset token", code="INVALID_RESET_TOKEN")

        user_result = await db.execute(select(User).where(User.id == matched.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise AppHTTPException(status_code=404, message="User not found", code="NOT_FOUND")

        user.password_hash = hash_password(payload.newPassword)
        matched.is_used = True

        refresh_result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        for refresh in refresh_result.scalars().all():
            refresh.revoked_at = datetime.now(UTC)

        await db.flush()
        return ResetPasswordResponse(nextStep="login")

    @staticmethod
    async def refresh_token(db: AsyncSession, refresh_token: str) -> RefreshTokenResponse:
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.revoked_at.is_(None)).order_by(RefreshToken.created_at.desc())
        )
        records = result.scalars().all()
        matched: RefreshToken | None = None

        for record in records:
            if verify_value(refresh_token, record.token_hash):
                matched = record
                break

        if not matched or matched.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise AppHTTPException(status_code=401, message="Invalid or expired refresh token", code="INVALID_REFRESH_TOKEN")

        user_result = await db.execute(select(User).where(User.id == matched.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise AppHTTPException(status_code=401, message="Invalid refresh token", code="INVALID_REFRESH_TOKEN")

        matched.revoked_at = datetime.now(UTC)
        access, new_refresh, expires_in = await _issue_tokens(db, user=user, remember_me=matched.remember_me)

        return RefreshTokenResponse(
            accessToken=access,
            refreshToken=new_refresh,
            expiresIn=expires_in,
        )

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.revoked_at.is_(None))
        )
        for record in result.scalars().all():
            if verify_value(refresh_token, record.token_hash):
                record.revoked_at = datetime.now(UTC)

    @staticmethod
    async def get_me(db: AsyncSession, user_id: UUID) -> UserPublic:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise AppHTTPException(status_code=404, message="User not found", code="NOT_FOUND")
        return _to_user_public(user)
