"""
Provider profile request/response DTOs.

Why schemas exist:
  - Validate and shape HTTP JSON before it reaches the service.
  - Prevent mass assignment: providers cannot send verification_status=verified.
  - Separate "what a provider may write" from "what an admin may write".

No DB access here — Pydantic only.
Feature path: app/providers/schemas/
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.models.provider_profile import ProviderVerificationStatus


# ---------------------------------------------------------------------------
# Provider-facing (create / update) — writable fields ONLY
# ---------------------------------------------------------------------------


class ProviderProfileCreate(BaseModel):
    """
    Body for POST /provider/profile.

    Intentionally omits verification_*, ratings, and is_active.
    Those are server-controlled (admin or internal jobs).
    """

    business_name: str = Field(min_length=2, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    bio: str | None = Field(default=None, max_length=5000)

    @field_validator("business_name", "city")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("bio")
    @classmethod
    def strip_optional_bio(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProviderProfileUpdate(BaseModel):
    """
    Body for PUT/PATCH /provider/profile.

    All fields optional for PATCH-style updates.
    Re-submission after REJECTED should reset status in the SERVICE
    (not by accepting verification_status from this body).
    """

    business_name: str | None = Field(default=None, min_length=2, max_length=200)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    bio: str | None = Field(default=None, max_length=5000)

    @field_validator("business_name", "city")
    @classmethod
    def strip_optional_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("bio")
    @classmethod
    def strip_optional_bio(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------


class ProviderProfileRead(BaseModel):
    """
    Safe profile representation for provider self-view and admin detail.

    Includes verification_status so the app can show "pending / verified".
    Does not expose internal secrets (there are none on this table today).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    business_name: str
    bio: str | None
    city: str
    verification_status: ProviderVerificationStatus
    verified_at: datetime | None
    rejection_reason: str | None
    average_rating: Decimal
    total_reviews: int
    total_bookings: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProviderProfilePublicRead(BaseModel):
    """
    Customer-facing subset (listing detail / provider card).

    Hides rejection_reason and admin-oriented noise.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_name: str
    bio: str | None
    city: str
    average_rating: Decimal
    total_reviews: int
    total_bookings: int


# ---------------------------------------------------------------------------
# Admin verification
# ---------------------------------------------------------------------------


class AdminVerifyProviderRequest(BaseModel):
    """
    Body for POST /admin/providers/{profile_id}/verify.

    Empty body is valid; optional note for internal audit later.
    """

    note: str | None = Field(default=None, max_length=2000)


class AdminRejectProviderRequest(BaseModel):
    """Body for POST /admin/providers/{profile_id}/reject."""

    rejection_reason: str = Field(min_length=5, max_length=2000)

    @field_validator("rejection_reason")
    @classmethod
    def reason_must_be_meaningful(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("rejection_reason must be at least 5 characters")
        return cleaned


class AdminProviderQueueResponse(BaseModel):
    """Paginated admin queue of profiles by verification status."""

    items: list[ProviderProfileRead]
    total: int
    limit: int
    offset: int
