"""
Review request/response DTOs.

Why schemas exist:
  - Validate rating/comment before the service runs.
  - Prevent mass assignment of customer_id, provider_id, listing_id.
  - Customers send booking_id + rating only — server resolves the rest.

No DB access here — Pydantic only.
Feature path: app/reviews/schemas/
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewCreate(BaseModel):
    """Body for POST /reviews — customer rates a COMPLETED booking."""

    booking_id: UUID
    rating: int = Field(ge=1, le=5, description="Star rating 1-5")
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ReviewRead(BaseModel):
    """Safe review representation for customer self-view and public lists."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    booking_id: UUID
    customer_id: UUID
    provider_id: UUID
    listing_id: UUID | None
    rating: int
    comment: str | None
    created_at: datetime
    updated_at: datetime


class ReviewListResponse(BaseModel):
    """Paginated list envelope for public listing reviews / my reviews."""

    items: list[ReviewRead]
    total: int
    page: int = 1
    page_size: int = 20
