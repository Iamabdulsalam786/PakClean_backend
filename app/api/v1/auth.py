"""
Auth HTTP endpoints: register, login, email OTP, and current user profile.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.dependencies import CurrentUser, DbSession
from app.schemas.auth import Token, UserLogin, UserRead, UserRegister
from app.schemas.otp import OtpRequest, OtpRequestResponse, OtpVerify, OtpVerifyResponse
from app.services.auth_service import AuthError, authenticate_user, register_user
from app.services.otp_service import OtpError, request_email_otp, verify_email_otp

router = APIRouter(prefix="/auth", tags=["auth"])


def _http_for_auth_error(exc: AuthError) -> HTTPException:
    """Map domain AuthError codes to HTTP status codes."""
    if exc.code in {"email_taken", "phone_taken"}:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code == "inactive_user":
        status_code = status.HTTP_403_FORBIDDEN
    else:
        # invalid_credentials and anything unexpected → 401
        status_code = status.HTTP_401_UNAUTHORIZED
    return HTTPException(status_code=status_code, detail=exc.message)


def _http_for_otp_error(exc: OtpError) -> HTTPException:
    """Map domain OtpError codes to HTTP status codes."""
    if exc.code == "otp_cooldown":
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif exc.code == "otp_locked":
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif exc.code == "inactive_user":
        status_code = status.HTTP_403_FORBIDDEN
    else:
        # otp_invalid and unknown → 400 (bad code / expired)
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer",
)
def register(payload: UserRegister, db: DbSession) -> Token:
    """
    Create a customer account and return an access token.

    The mobile app can store the token and call protected routes immediately.
    """
    try:
        _user, token = register_user(db, payload)
    except AuthError as exc:
        raise _http_for_auth_error(exc) from exc
    return token


@router.post(
    "/login",
    response_model=Token,
    summary="Login with email and password (JSON)",
)
def login_json(payload: UserLogin, db: DbSession) -> Token:
    """JSON login for React Native / normal API clients."""
    try:
        _user, token = authenticate_user(db, payload.email, payload.password)
    except AuthError as exc:
        raise _http_for_auth_error(exc) from exc
    return token


@router.post(
    "/login/form",
    response_model=Token,
    summary="Login (OAuth2 form) for Swagger Authorize",
    include_in_schema=True,
)
def login_form(
    db: DbSession,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Token:
    """
    Form-encoded login used by Swagger UI's Authorize button.

    OAuth2PasswordRequestForm provides `username` + `password`.
    We treat `username` as the user's email.
    """
    try:
        _user, token = authenticate_user(db, form_data.username, form_data.password)
    except AuthError as exc:
        raise _http_for_auth_error(exc) from exc
    return token


@router.post(
    "/otp/request",
    response_model=OtpRequestResponse,
    summary="Request an email OTP",
)
def otp_request(payload: OtpRequest, db: DbSession) -> OtpRequestResponse:
    """
    Send a 6-digit code to the email (logged + optional dev_code when DEBUG=true).
    """
    try:
        return request_email_otp(db, payload.email)
    except OtpError as exc:
        raise _http_for_otp_error(exc) from exc


@router.post(
    "/otp/verify",
    response_model=OtpVerifyResponse,
    summary="Verify email OTP and get access token",
)
def otp_verify(payload: OtpVerify, db: DbSession) -> OtpVerifyResponse:
    """
    Verify the code. Creates a customer account if the email is new.
    """
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
    """Requires Authorization: Bearer <access_token>."""
    return UserRead.model_validate(current_user)
