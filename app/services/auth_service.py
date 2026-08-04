"""
Auth business logic: sign-up, login, and session responses.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import (
    AuthSessionResponse,
    SignupRole,
    UserRead,
    UserRegister,
)
from app.services.user_queries import get_user_by_email
from app.schemas.otp import OtpRequestResponse


class AuthError(Exception):
    """Domain error for auth failures."""

    def __init__(self, message: str, *, code: str = "auth_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def map_signup_role(role: SignupRole) -> UserRole:
    if role == SignupRole.CLEANER:
        return UserRole.PROVIDER
    return UserRole.CUSTOMER


def map_user_role_to_signup(role: UserRole) -> SignupRole:
    if role == UserRole.PROVIDER:
        return SignupRole.CLEANER
    return SignupRole.CUSTOMER


def resolve_next_step(user: User) -> str:
    if user.role == UserRole.PROVIDER and not user.is_onboarding_complete:
        return "agreement"
    return "home"


def build_session_response(user: User) -> AuthSessionResponse:
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value},
    )
    return AuthSessionResponse(
        access_token=token,
        user=UserRead.model_validate(user),
        next_step=resolve_next_step(user),
    )


def signup_user(db: Session, data: UserRegister) -> tuple[User, OtpRequestResponse]:
    """
    Sign-up step 1: create unverified account and send email OTP.

    No JWT is issued until OTP verification succeeds.
    """
    existing = get_user_by_email(db, data.email)
    if existing is not None:
        raise AuthError("Email already registered", code="email_taken")

    if data.phone:
        phone_taken = db.scalar(select(User).where(User.phone == data.phone))
        if phone_taken is not None:
            raise AuthError("Phone already registered", code="phone_taken")

    db_role = map_signup_role(data.role)
    user = User(
        email=data.email.lower(),
        phone=data.phone,
        full_name=data.full_name.strip(),
        hashed_password=hash_password(data.password),
        role=db_role,
        is_active=True,
        is_email_verified=False,
        is_onboarding_complete=db_role != UserRole.PROVIDER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    from app.services.otp_service import request_email_otp

    otp_response = request_email_otp(db, user.email)
    return user, otp_response


def authenticate_user(db: Session, email: str, password: str) -> AuthSessionResponse:
    """Login with email/password after the account email is verified."""
    user = get_user_by_email(db, email)
    if user is None or not user.hashed_password:
        raise AuthError("Invalid email or password", code="invalid_credentials")

    if not verify_password(password, user.hashed_password):
        raise AuthError("Invalid email or password", code="invalid_credentials")

    if not user.is_active:
        raise AuthError("Inactive user", code="inactive_user")

    if not user.is_email_verified:
        raise AuthError(
            "Please verify your email before signing in",
            code="email_not_verified",
        )

    return build_session_response(user)
