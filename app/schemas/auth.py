"""
Auth-related request and response schemas.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole

# Roles allowed on public signup (never admin via client).
PUBLIC_ROLES = {UserRole.CUSTOMER, UserRole.PROVIDER}


def _reject_non_public_role(role: UserRole) -> UserRole:
    if role not in PUBLIC_ROLES:
        raise ValueError("role must be 'customer' or 'provider'")
    return role


class UserRegister(BaseModel):
    """Body for POST /auth/register — customer or provider."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    role: UserRole = UserRole.CUSTOMER

    @field_validator("role")
    @classmethod
    def role_must_be_public(cls, value: UserRole) -> UserRole:
        return _reject_non_public_role(value)


class UserLogin(BaseModel):
    """
    Body for POST /auth/login (JSON).

    Works for any role (customer, provider, admin) that has a password.
    """

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Token(BaseModel):
    """Access token response after successful login/register."""

    access_token: str
    token_type: str = "bearer"
    role: UserRole


class UserRead(BaseModel):
    """
    Safe public user representation — never includes hashed_password.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    phone: str | None
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
