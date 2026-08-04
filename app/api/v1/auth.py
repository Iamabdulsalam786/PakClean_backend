"""
Auth HTTP endpoints — email-verified registration flow.

Thin controllers: validate via schemas, call AuthVerificationService, map errors → HTTP.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.auth_exceptions import AuthDomainError
from app.core.dependencies import CurrentUser, DbSession
from app.schemas.auth import (
    MessageResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterResponse,
    ResendOtpRequest,
    TokenPair,
    UserLogin,
    UserRead,
    UserRegister,
    VerifyOtpRequest,
)
from app.services.auth_verification_service import AuthVerificationService

router = APIRouter(prefix="/auth", tags=["auth"])


def _http_for_domain_error(exc: AuthDomainError) -> HTTPException:
    """Map AuthDomainError.code → HTTP status."""
    code = exc.code
    if code in {"email_taken", "phone_taken"}:
        status_code = status.HTTP_409_CONFLICT
    elif code in {"email_not_verified", "inactive_user"}:
        status_code = status.HTTP_403_FORBIDDEN
    elif code in {"otp_resend_cooldown", "otp_attempts_exceeded"}:
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
