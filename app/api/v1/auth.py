from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, get_current_user_id
from app.schemas.auth import (
    APIResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshTokenRequest,
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
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=APIResponse[RegisterResponse], status_code=201)
async def register(payload: RegisterRequest, db: DbSession) -> APIResponse[RegisterResponse]:
    data = await AuthService.register(db, payload)
    return APIResponse(message="Verification code sent to your email", data=data)


@router.post("/verify-otp", response_model=APIResponse[VerifyOtpResponse])
async def verify_otp(payload: VerifyOtpRequest, db: DbSession) -> APIResponse[VerifyOtpResponse]:
    data = await AuthService.verify_otp(db, payload)
    return APIResponse(message="OTP verified successfully", data=data)


@router.post("/resend-otp", response_model=APIResponse[ResendOtpResponse])
async def resend_otp(payload: ResendOtpRequest, db: DbSession) -> APIResponse[ResendOtpResponse]:
    data = await AuthService.resend_otp(db, payload)
    return APIResponse(message="Verification code resent", data=data)


@router.post("/login", response_model=APIResponse[LoginResponse])
async def login(payload: LoginRequest, db: DbSession) -> APIResponse[LoginResponse]:
    data = await AuthService.login(db, payload)
    return APIResponse(message="Login successful", data=data)


@router.post("/forgot-password", response_model=APIResponse[dict[str, str]])
async def forgot_password(payload: ForgotPasswordRequest, db: DbSession) -> APIResponse[dict[str, str]]:
    data = await AuthService.forgot_password(db, payload)
    return APIResponse(message=data["message"], data=data)


@router.post("/reset-password", response_model=APIResponse[ResetPasswordResponse])
async def reset_password(payload: ResetPasswordRequest, db: DbSession) -> APIResponse[ResetPasswordResponse]:
    data = await AuthService.reset_password(db, payload)
    return APIResponse(message="Password reset successful. Please login with your new password", data=data)


@router.post("/refresh-token", response_model=APIResponse[RefreshTokenResponse])
async def refresh_token(payload: RefreshTokenRequest, db: DbSession) -> APIResponse[RefreshTokenResponse]:
    data = await AuthService.refresh_token(db, payload.refreshToken)
    return APIResponse(message="Token refreshed", data=data)


@router.post("/logout", response_model=APIResponse[dict[str, str]])
async def logout(payload: LogoutRequest, db: DbSession) -> APIResponse[dict[str, str]]:
    await AuthService.logout(db, payload.refreshToken)
    return APIResponse(message="Logged out successfully", data={"status": "ok"})


@router.get("/me", response_model=APIResponse[UserPublic])
async def me(
    db: DbSession,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
) -> APIResponse[UserPublic]:
    data = await AuthService.get_me(db, user_id)
    return APIResponse(data=data)
