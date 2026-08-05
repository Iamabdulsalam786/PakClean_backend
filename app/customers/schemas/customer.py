"""
Customer profile + saved-address request/response DTOs.

Why schemas exist:
  - Validate HTTP JSON before the service runs.
  - Prevent mass assignment: clients cannot set customer_id or forged ids.
  - Profile updates only touch User-writable fields (not email/role/password).

No DB access here — Pydantic only.
Feature path: app/customers/schemas/
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Customer profile (backed by User — no CustomerProfile table in MVP)
# ---------------------------------------------------------------------------


class CustomerProfileUpdate(BaseModel):
    """
    Body for PATCH /customers/me.

    Email / password / role stay in auth flows — not here.
    """

    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    phone: str | None = Field(default=None, min_length=10, max_length=20)

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("full_name must be at least 2 characters")
        return cleaned

    @field_validator("phone")
    @classmethod
    def strip_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) < 10:
            raise ValueError("phone must be at least 10 characters")
        return cleaned


class CustomerAddressSummary(BaseModel):
    """Compact default-address card nested on profile read."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    address_line: str
    area: str | None
    city: str
    is_default: bool


class CustomerProfileRead(BaseModel):
    """
    Safe self-view for GET /customers/me.

    Built from User (+ optional default address). Never exposes password hash.
    """

    id: UUID
    email: str
    full_name: str
    phone: str | None
    role: str
    is_verified: bool
    default_address: CustomerAddressSummary | None = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Saved addresses
# ---------------------------------------------------------------------------


class CustomerAddressCreate(BaseModel):
    """Body for POST /customers/me/addresses."""

    label: str = Field(min_length=1, max_length=50)
    address_line: str = Field(min_length=5, max_length=500)
    city: str = Field(min_length=2, max_length=100)
    area: str | None = Field(default=None, max_length=120)
    landmark: str | None = Field(default=None, max_length=2000)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    is_default: bool = False

    @field_validator("label", "address_line", "city")
    @classmethod
    def strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("area", "landmark")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def coords_together(self) -> CustomerAddressCreate:
        if (self.latitude is None) ^ (self.longitude is None):
            raise ValueError("latitude and longitude must be sent together")
        return self


class CustomerAddressUpdate(BaseModel):
    """Body for PATCH /customers/me/addresses/{id} — all fields optional."""

    label: str | None = Field(default=None, min_length=1, max_length=50)
    address_line: str | None = Field(default=None, min_length=5, max_length=500)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    area: str | None = Field(default=None, max_length=120)
    landmark: str | None = Field(default=None, max_length=2000)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    is_default: bool | None = None

    @field_validator("label", "address_line", "city")
    @classmethod
    def strip_optional_required(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("area", "landmark")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CustomerAddressRead(BaseModel):
    """Safe address representation for the owning customer."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    label: str
    address_line: str
    area: str | None
    city: str
    landmark: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class CustomerAddressListResponse(BaseModel):
    """List envelope for GET /customers/me/addresses."""

    items: list[CustomerAddressRead]
    total: int
