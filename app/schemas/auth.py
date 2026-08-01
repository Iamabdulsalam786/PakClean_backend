"""
Auth-related request and response schemas.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserRegister(BaseModel):
    """Body for POST /auth/register."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    # role is NOT accepted from the client — public register always creates CUSTOMER.
    # Admins/providers are created by admin endpoints later.


class UserLogin(BaseModel):
    """
    Body for POST /auth/login (JSON).

    We also support OAuth2 form login for Swagger's Authorize button;
    that path uses username/password form fields in the route.
    """

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Token(BaseModel):
    """Access token response after successful login/register."""

    access_token: str
    token_type: str = "bearer"


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
