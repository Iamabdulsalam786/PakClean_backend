"""
Marketplace discovery DTOs — customer browse / search / detail contract.

Why this file exists:
  - Provider write schemas (ServiceListingCreate/Update) must NOT be reused
    for public discovery — they expose owner fields (deleted_at, draft status).
  - Cards are lean (feed performance); detail is an aggregate (joins/loads).
  - Query params are validated here so SQL never sees unbounded junk
    (SQL injection is already prevented by SQLAlchemy binds; validation
    still protects CPU/memory from abusive page_size / q length).

Feature module: app/discovery (read-optimized marketplace surface).
Provider ownership APIs stay in app/service_listings.
"""

from __future__ import annotations

import enum
from datetime import datetime, time
from decimal import Decimal
from math import ceil
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DiscoverySort(str, enum.Enum):
    """
    Public sort keys for marketplace feeds.

    MOST_BOOKED uses denormalized service_listings.booking_count
    (updated later by the booking module — 0 is fine until then).
    """

    NEWEST = "newest"
    OLDEST = "oldest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    RATING_DESC = "rating_desc"
    MOST_BOOKED = "most_booked"


# ---------------------------------------------------------------------------
# Nested public fragments (detail + optional card enrichment)
# ---------------------------------------------------------------------------


class DiscoveryCategoryBrief(BaseModel):
    """Category chip on cards / detail — no admin fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str


class DiscoveryProviderBrief(BaseModel):
    """
    Provider teaser for customers.

    Never include rejection_reason, verification admin ids, or user email.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_name: str
    city: str
    average_rating: Decimal
    total_reviews: int
    total_bookings: int


class DiscoveryImageBrief(BaseModel):
    """Gallery thumb for cards (primary) or full gallery on detail."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    image_url: str
    sort_order: int
    is_primary: bool
    alt_text: str | None = None


class DiscoveryAvailabilityBrief(BaseModel):
    """Active weekly slot shown on listing detail."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    day_of_week: int
    start_time: time
    end_time: time


# ---------------------------------------------------------------------------
# List card vs detail
# ---------------------------------------------------------------------------


class ListingCard(BaseModel):
    """
    Feed / search result row.

    Lean on purpose: mobile lists should not download full description HTML,
    full galleries, or full weekly schedules.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    # Short teaser — service may truncate description when mapping.
    description: str
    base_price: int
    estimated_duration: int
    city: str
    is_featured: bool
    average_rating: Decimal
    booking_count: int
    created_at: datetime

    category: DiscoveryCategoryBrief
    provider: DiscoveryProviderBrief
    primary_image: DiscoveryImageBrief | None = None


class ListingDetail(BaseModel):
    """
    Full public listing page payload (one round-trip for the mobile detail screen).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    base_price: int
    estimated_duration: int
    city: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    service_radius_km: Decimal
    is_featured: bool
    average_rating: Decimal
    booking_count: int
    created_at: datetime

    category: DiscoveryCategoryBrief
    provider: DiscoveryProviderBrief
    images: list[DiscoveryImageBrief] = Field(default_factory=list)
    availability: list[DiscoveryAvailabilityBrief] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Query + paginated envelope
# ---------------------------------------------------------------------------


class DiscoverySearchParams(BaseModel):
    """
    Validated query string for browse/search endpoints.

    available_on: ISO weekday 0=Monday … 6=Sunday (same as availability model).
    min_rating: applies to listing.average_rating (provider rating can be
    added later as min_provider_rating without breaking this contract).
    """

    q: str | None = Field(default=None, max_length=200)
    category_id: UUID | None = None
    city: str | None = Field(default=None, max_length=100)
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    min_rating: Decimal | None = Field(default=None, ge=0, le=5)
    is_featured: bool | None = None
    available_on: int | None = Field(
        default=None,
        ge=0,
        le=6,
        description="Filter listings with an active slot on this weekday",
    )
    sort: DiscoverySort = DiscoverySort.NEWEST
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)

    @field_validator("q", "city")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_price_range(self) -> DiscoverySearchParams:
        if (
            self.max_price is not None
            and self.min_price is not None
            and self.max_price < self.min_price
        ):
            raise ValueError("max_price must be >= min_price")
        return self

    @property
    def offset(self) -> int:
        """SQL OFFSET derived from page (1-based)."""
        return (self.page - 1) * self.page_size


class DiscoveryListResponse(BaseModel):
    """Paginated marketplace feed."""

    items: list[ListingCard]
    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def build(
        cls,
        *,
        items: list[ListingCard],
        page: int,
        page_size: int,
        total: int,
    ) -> DiscoveryListResponse:
        """
        Single constructor so total_pages math is not duplicated in routes.

        total_pages is 0 when total is 0 (empty marketplace), else ceil division.
        """
        total_pages = 0 if total == 0 else ceil(total / page_size)
        return cls(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )
