"""
Auth HTTP endpoints — email-verified registration + password reset.

Thin controllers: validate via schemas, call services, map errors → HTTP.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.auth_exceptions import AuthDomainError
from app.core.dependencies import CurrentUser, DbSession
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    MessageResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterResponse,
    ResendOtpRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenPair,
    UserLogin,
    UserRead,
    UserRegister,
    VerifyOtpRequest,
    VerifyResetOtpRequest,
    VerifyResetOtpResponse,
)
from app.services.auth_verification_service import AuthVerificationService
from app.services.password_reset_service import PasswordResetService

router = APIRouter(prefix="/auth", tags=["auth"])


def _http_for_domain_error(exc: AuthDomainError) -> HTTPException:
    """Map AuthDomainError.code → HTTP status."""
    code = exc.code
    if code in {"email_taken", "phone_taken"}:
        status_code = status.HTTP_409_CONFLICT
    elif code in {"email_not_verified", "inactive_user"}:
        status_code = status.HTTP_403_FORBIDDEN
    elif code in {"otp_resend_cooldown", "otp_attempts_exceeded", "otp_rate_limit"}:
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif code == "email_delivery_failed":
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif code in {"invalid_otp", "invalid_role"}:
        status_code = (
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if code == "invalid_role"
            else status.HTTP_400_BAD_REQUEST
        )
    elif code in {"invalid_credentials", "invalid_refresh_token"}:
        status_code = status.HTTP_401_UNAUTHORIZED
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


def _service(db: DbSession) -> AuthVerificationService:
    return AuthVerificationService(db)


def _password_reset_service(db: DbSession) -> PasswordResetService:
    return PasswordResetService(db)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register customer or provider (sends email OTP)",
)
def register(payload: UserRegister, db: DbSession) -> RegisterResponse:
    """
    Create unverified account and email a 6-digit OTP.

    Does not return JWT — client must call /auth/verify-otp next.
    """
    try:
        return _service(db).register(payload)
    except AuthDomainError as exc:
        raise _http_for_domain_error(exc) from exc


@router.post(
    "/verify-otp",
    response_model=TokenPair,
    summary="Verify email OTP and issue tokens",
)
def verify_otp(payload: VerifyOtpRequest, db: DbSession) -> TokenPair:
    """Marks OTP used, sets is_verified=true, returns access + refresh tokens."""
    try:
        return _service(db).verify_otp(email=str(payload.email), code=payload.code)
    except AuthDomainError as exc:
        raise _http_for_domain_error(exc) from exc


@router.post(
    "/resend-otp",
    response_model=MessageResponse,
    summary="Resend email OTP (60s cooldown)",
)
def resend_otp(payload: ResendOtpRequest, db: DbSession) -> MessageResponse:
    """Invalidates previous OTPs and emails a new code."""
    try:
        message = _service(db).resend_otp(email=str(payload.email))
    except AuthDomainError as exc:
        raise _http_for_domain_error(exc) from exc
    return MessageResponse(message=message)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Login with email and password",
)
def login_json(payload: UserLogin, db: DbSession) -> TokenPair:
    """Requires is_verified=true. Returns access + refresh tokens."""
    try:
        return _service(db).login(payload)
    except AuthDomainError as exc:
        raise _http_for_domain_error(exc) from exc


@router.post(
    "/login/form",
    response_model=TokenPair,
    summary="Login (OAuth2 form) for Swagger Authorize",
)
def login_form(
    db: DbSession,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> TokenPair:
    """Swagger Authorize helper — username field is the email."""
    try:
        return _service(db).login(
            UserLogin(email=form_data.username, password=form_data.password)
        )
    except AuthDomainError as exc:
        raise _http_for_domain_error(exc) from exc


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Rotate refresh token and get a new access token",
)
def refresh_tokens(payload: RefreshRequest, db: DbSession) -> RefreshResponse:
    try:
        return _service(db).refresh(payload.refresh_token)
    except AuthDomainError as exc:
        raise _http_for_domain_error(exc) from exc


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get the current authenticated user",
)
def read_me(current_user: CurrentUser) -> UserRead:
    """Requires Authorization: Bearer <access_token>."""
    return UserRead.model_validate(current_user)


# ---------------------------------------------------------------------------
# Forgot / reset password
# ---------------------------------------------------------------------------


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request a password-reset OTP (anti-enumeration)",
)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: DbSession,
) -> ForgotPasswordResponse:
    """
    Always returns the same success message.

    If a verified account exists: emails a PASSWORD_RESET OTP (60s cooldown, 5/hour).
    """
    try:
        return _password_reset_service(db).forgot_password(email=str(payload.email))
    except AuthDomainError as exc:
        raise _http_for_domain_error(exc) from exc


@router.post(
    "/verify-reset-otp",
    response_model=VerifyResetOtpResponse,
    summary="Validate password-reset OTP without consuming it",
)
def verify_reset_otp(
    payload: VerifyResetOtpRequest,
    db: DbSession,
) -> VerifyResetOtpResponse:
    """Approach B: OTP stays usable until /auth/reset-password succeeds."""
    try:
        return _password_reset_service(db).verify_reset_otp(payload)
    except AuthDomainError as exc:
        raise _http_for_domain_error(exc) from exc


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    summary="Set a new password using a valid reset OTP",
)
def reset_password(
    payload: ResetPasswordRequest,
    db: DbSession,
) -> ResetPasswordResponse:
    """
    Re-checks OTP, updates password hash, marks OTP used, revokes all refresh tokens.

    Client must log in again with the new password.
    """
    try:
        return _password_reset_service(db).reset_password(payload)
    except AuthDomainError as exc:
        raise _http_for_domain_error(exc) from exc
