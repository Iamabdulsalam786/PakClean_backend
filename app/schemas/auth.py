"""
Auth request/response schemas for email-verified registration.

Matches mobile signup:
  full_name, email, phone, password, confirm_password, role (customer|provider)

These DTOs validate INPUT/OUTPUT shapes only — no DB access here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.user import UserRole

# Roles allowed on public signup (never admin via client).
PUBLIC_ROLES = {UserRole.CUSTOMER, UserRole.PROVIDER}


def _reject_non_public_role(role: UserRole) -> UserRole:
    if role not in PUBLIC_ROLES:
        raise ValueError("role must be 'customer' or 'provider'")
    return role


class UserRegister(BaseModel):
    """Body for POST /auth/register."""

    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: str = Field(min_length=5, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.CUSTOMER

    @field_validator("role")
    @classmethod
    def role_must_be_public(cls, value: UserRole) -> UserRole:
        return _reject_non_public_role(value)

    @field_validator("phone")
    @classmethod
    def phone_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("phone is required")
        return cleaned

    @model_validator(mode="after")
    def passwords_must_match(self) -> UserRegister:
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password must match")
        return self


class RegisterResponse(BaseModel):
    """Returned after register — no tokens until email is verified."""

    message: str = "Registration successful. Please verify the OTP sent to your email."
    email: EmailStr
    user_id: UUID


class UserLogin(BaseModel):
    """Body for POST /auth/login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    """Access + refresh tokens after verify-otp or login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: UserRole


class RefreshRequest(BaseModel):
    """Body for POST /auth/refresh."""

    refresh_token: str = Field(min_length=20, max_length=512)


class RefreshResponse(BaseModel):
    """Rotated token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class VerifyOtpRequest(BaseModel):
    """Body for POST /auth/verify-otp."""

    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendOtpRequest(BaseModel):
    """Body for POST /auth/resend-otp."""

    email: EmailStr


class MessageResponse(BaseModel):
    """Generic message wrapper (resend, etc.)."""

    message: str


class UserRead(BaseModel):
    """Safe public user representation — never includes hashed_password."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    phone: str | None
    full_name: str
    role: UserRole
    is_verified: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Backward-compatible aliases used by older otp/auth routes until we cut over.
class Token(BaseModel):
    """Legacy access-only token response (older endpoints)."""

    access_token: str
    token_type: str = "bearer"
    role: UserRole
