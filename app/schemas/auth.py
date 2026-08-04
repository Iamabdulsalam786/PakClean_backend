"""
Auth-related request and response schemas.
"""

import re
from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


class SignupRole(str, Enum):
    """Role selected on the mobile sign-up screen."""

    CUSTOMER = "customer"
    CLEANER = "cleaner"


_PASSWORD_UPPER = re.compile(r"[A-Z]")
_PASSWORD_LOWER = re.compile(r"[a-z]")
_PASSWORD_DIGIT = re.compile(r"\d")


def validate_password_strength(password: str) -> str:
    """Match PakClean mobile app password rules."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not _PASSWORD_UPPER.search(password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not _PASSWORD_LOWER.search(password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not _PASSWORD_DIGIT.search(password):
        raise ValueError("Password must contain at least one number")
    return password


class UserRegister(BaseModel):
    """Body for POST /auth/register — creates account and sends email OTP."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    role: SignupRole = SignupRole.CUSTOMER

    @field_validator("password")
    @classmethod
    def password_rules(cls, value: str) -> str:
        return validate_password_strength(value)


class UserLogin(BaseModel):
    """Body for POST /auth/login (JSON)."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Token(BaseModel):
    """Access token response."""

    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    """Safe public user representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    phone: str | None
    full_name: str
    role: UserRole
    is_active: bool
    is_email_verified: bool
    is_onboarding_complete: bool
    created_at: datetime
    updated_at: datetime


class RegisterResponse(BaseModel):
    """
    Sign-up step 1 response — account created, OTP sent, no JWT yet.

    Client navigates to the OTP screen after this.
    """

    user_id: UUID
    email: EmailStr
    role: SignupRole
    otp_sent: bool = True
    email_delivered: bool = False
    expires_in_seconds: int
    next_step: str = "verify_email"
    dev_code: str | None = None


class AuthSessionResponse(BaseModel):
    """Login or OTP verify — JWT plus user profile and navigation hint."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead
    next_step: str
