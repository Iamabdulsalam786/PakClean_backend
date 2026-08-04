"""
Auth HTTP endpoints aligned with mobile flow:

  Sign up  → POST /auth/register  → OTP sent (no JWT)
  Verify   → POST /auth/otp/verify → JWT + user
  Login    → POST /auth/login     → JWT + user
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.auth import (
    AuthSessionResponse,
    RegisterResponse,
    UserLogin,
    UserRead,
    UserRegister,
)
from app.schemas.otp import OtpRequest, OtpRequestResponse, OtpVerify
from app.services.auth_service import AuthError, authenticate_user, signup_user
from app.services.otp_service import OtpError, request_email_otp, verify_email_otp

router = APIRouter(prefix="/auth", tags=["auth"])


def _http_for_auth_error(exc: AuthError) -> HTTPException:
    if exc.code in {"email_taken", "phone_taken"}:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code in {"inactive_user", "email_not_verified"}:
        status_code = status.HTTP_403_FORBIDDEN
    else:
        status_code = status.HTTP_401_UNAUTHORIZED
    return HTTPException(status_code=status_code, detail=exc.message)


def _http_for_otp_error(exc: OtpError) -> HTTPException:
    if exc.code == "otp_cooldown":
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif exc.code == "otp_locked":
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif exc.code == "inactive_user":
        status_code = status.HTTP_403_FORBIDDEN
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sign up — create account and send email OTP",
)
def register(payload: UserRegister, db: DbSession) -> RegisterResponse:
    """
    Step 1 of sign-up. Creates an unverified account and emails a 6-digit OTP.
    The app navigates to the OTP screen; JWT is issued only after verify.
    """
    try:
        user, otp = signup_user(db, payload)
    except AuthError as exc:
        raise _http_for_auth_error(exc) from exc

    return RegisterResponse(
        user_id=user.id,
        email=user.email,
        role=payload.role,
        otp_sent=True,
        email_delivered=otp.email_delivered,
        expires_in_seconds=otp.expires_in_seconds,
        dev_code=otp.dev_code,
        next_step="verify_email",
    )


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    summary="Login with email and password",
)
def login_json(payload: UserLogin, db: DbSession) -> AuthSessionResponse:
    try:
        return authenticate_user(db, payload.email, payload.password)
    except AuthError as exc:
        raise _http_for_auth_error(exc) from exc


@router.post(
    "/login/form",
    response_model=AuthSessionResponse,
    summary="Login (OAuth2 form) for Swagger Authorize",
    include_in_schema=True,
)
def login_form(
    db: DbSession,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> AuthSessionResponse:
    try:
        return authenticate_user(db, form_data.username, form_data.password)
    except AuthError as exc:
        raise _http_for_auth_error(exc) from exc


@router.post(
    "/otp/request",
    response_model=OtpRequestResponse,
    summary="Resend email OTP",
)
def otp_request(payload: OtpRequest, db: DbSession) -> OtpRequestResponse:
    try:
        return request_email_otp(db, payload.email)
    except OtpError as exc:
        raise _http_for_otp_error(exc) from exc


@router.post(
    "/otp/verify",
    response_model=AuthSessionResponse,
    summary="Verify email OTP and sign in",
)
def otp_verify(payload: OtpVerify, db: DbSession) -> AuthSessionResponse:
    try:
        return verify_email_otp(db, payload.email, payload.code)
    except OtpError as exc:
        raise _http_for_otp_error(exc) from exc


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get the current authenticated user",
)
def read_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
