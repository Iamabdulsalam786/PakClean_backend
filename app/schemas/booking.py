"""
Booking request/response DTOs — marketplace listing bookings (+ legacy admin assign).

Why schemas exist:
  - Validate create/reject payloads before the service runs.
  - Prevent mass assignment of status, price_pkr, provider_id, audit timestamps.
  - Customers send listing_id only — server resolves provider + snapshots price.

Marketplace create uses listing_id (not catalog service_id).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.bookings.models.booking_status import BookingStatus


class BookingCreate(BaseModel):
    """
    Body for POST /bookings — customer books an ACTIVE service listing.

    Address: send exactly one of address_id (saved address) or address_text.
    status/price/provider_id are NOT accepted here (server-owned).
    """

    listing_id: UUID
    scheduled_at: datetime = Field(
        description="When the job should start (timezone-aware ISO datetime)",
    )
    address_id: UUID | None = Field(
        default=None,
        description="Saved customer address id — server snapshots address_text",
    )
    address_text: str | None = Field(
        default=None,
        min_length=5,
        max_length=500,
        description="Free-text service location (when not using address_id)",
    )
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("address_text")
    @classmethod
    def strip_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("address_text must be at least 5 characters")
        return cleaned

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def exactly_one_address_source(self) -> BookingCreate:
        has_id = self.address_id is not None
        has_text = self.address_text is not None
        if has_id == has_text:
            raise ValueError("Provide exactly one of address_id or address_text")
        return self


class BookingRejectRequest(BaseModel):
    """Body for POST /provider/bookings/{id}/reject."""

    rejection_reason: str = Field(min_length=5, max_length=2000)

    @field_validator("rejection_reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("rejection_reason must be at least 5 characters")
        return cleaned


class BookingAssignProvider(BaseModel):
    """Legacy admin assignment body (catalog-era open bookings)."""

    provider_id: UUID


class BookingRead(BaseModel):
    """Safe booking representation for customer and provider APIs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    listing_id: UUID | None = None
    service_id: UUID | None = None
    provider_id: UUID | None
    status: BookingStatus
    scheduled_at: datetime
    address_text: str
    notes: str | None
    price_pkr: int = Field(description="Snapshotted price in PKR at booking time")
    duration_minutes: int
    listing_title_snapshot: str | None = None
    rejection_reason: str | None = None
    accepted_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class BookingListResponse(BaseModel):
    """Simple list envelope for mine / provider inbox."""

    items: list[BookingRead]
    total: int
