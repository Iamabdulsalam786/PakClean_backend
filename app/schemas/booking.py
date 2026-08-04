"""
Booking request/response schemas.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.booking import BookingStatus


class BookingCreate(BaseModel):
    """Body for POST /bookings — customer creates a job request."""

    service_id: UUID
    scheduled_at: datetime = Field(
        description="When the job should start (timezone-aware ISO datetime)",
    )
    address_text: str = Field(min_length=5, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class BookingAssignProvider(BaseModel):
    """Body for admin assignment of a provider to a booking."""

    provider_id: UUID


class BookingRead(BaseModel):
    """Safe booking representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    service_id: UUID
    provider_id: UUID | None
    status: BookingStatus
    scheduled_at: datetime
    address_text: str
    notes: str | None
    price_pkr: int = Field(description="Snapshotted price in PKR at booking time")
    duration_minutes: int
    created_at: datetime
    updated_at: datetime
