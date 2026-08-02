from typing import Any, Generic, TypeVar

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: T


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    code: str
    errors: dict[str, list[str]] | None = None


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    fullName: str = Field(validation_alias="full_name")
    email: EmailStr
    phone: str
    role: str
    isEmailVerified: bool = Field(validation_alias="is_email_verified")
    isOnboardingComplete: bool = Field(validation_alias="is_onboarding_complete")
    profileImageUrl: str | None = Field(default=None, validation_alias="profile_image_url")


class TokenBundle(BaseModel):
    accessToken: str
    refreshToken: str
    expiresIn: int


def _validate_password_strength(password: str) -> str:
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one number")
    return password


class RegisterRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=10, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    confirmPassword: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern="^(customer|cleaner)$")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    rememberMe: bool = False


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    purpose: str = Field(pattern="^(email_verification|password_reset)$")


class ResendOtpRequest(BaseModel):
    email: EmailStr
    purpose: str = Field(pattern="^(email_verification|password_reset)$")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    resetToken: str = Field(min_length=20)
    newPassword: str = Field(min_length=8, max_length=128)
    confirmPassword: str = Field(min_length=8, max_length=128)

    @field_validator("newPassword")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class RefreshTokenRequest(BaseModel):
    refreshToken: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    refreshToken: str = Field(min_length=20)


class RegisterResponse(BaseModel):
    userId: str
    email: EmailStr
    role: str
    otpSent: bool
    expiresIn: int
    nextStep: str


class VerifyOtpResponse(BaseModel):
    user: UserPublic | None = None
    accessToken: str | None = None
    refreshToken: str | None = None
    expiresIn: int | None = None
    resetToken: str | None = None
    nextStep: str


class LoginResponse(BaseModel):
    user: UserPublic
    accessToken: str
    refreshToken: str
    expiresIn: int
    nextStep: str


class ResendOtpResponse(BaseModel):
    expiresIn: int
    retryAfter: int


class ResetPasswordResponse(BaseModel):
    nextStep: str


class RefreshTokenResponse(BaseModel):
    accessToken: str
    refreshToken: str
    expiresIn: int
