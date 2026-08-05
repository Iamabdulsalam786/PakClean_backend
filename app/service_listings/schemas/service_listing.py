"""
Service listing request/response DTOs.

Why schemas exist:
  - Validate HTTP input before the service runs.
  - Prevent mass assignment (providers cannot set is_featured, booking_count,
    average_rating, deleted_at, or force ACTIVE without a publish flow).
  - Separate provider write models from public read models.

No DB access — Pydantic only.
Feature path: app/service_listings/schemas/
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.service_listings.models.listing_status import ListingStatus
from app.service_listings.repositories.service_listing_repository import ListingSort


# ---------------------------------------------------------------------------
# Provider write models
# ---------------------------------------------------------------------------


class ServiceListingCreate(BaseModel):
    """
    Body for POST /provider/service-listings.

    Omits status/is_featured/metrics — service forces DRAFT on create.
    Publish is a separate intentional action later.
    """

    category_id: UUID
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=10000)
    base_price: int = Field(ge=1, le=10_000_000, description="Price in PKR")
    estimated_duration: int = Field(ge=15, le=24 * 60, description="Minutes")
    city: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=5, max_length=500)
    service_radius_km: Decimal = Field(default=Decimal("5.00"), ge=0.5, le=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("title", "city", "address", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class ServiceListingUpdate(BaseModel):
    """
    Body for PATCH /provider/service-listings/{id}.

    All fields optional. Status changes go through dedicated endpoints
    (publish / deactivate) so we don't smuggle state transitions here.
    """

    category_id: UUID | None = None
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=10, max_length=10000)
    base_price: int | None = Field(default=None, ge=1, le=10_000_000)
    estimated_duration: int | None = Field(default=None, ge=15, le=24 * 60)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    address: str | None = Field(default=None, min_length=5, max_length=500)
    service_radius_km: Decimal | None = Field(default=None, ge=0.5, le=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("title", "city", "address", "description")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class ServiceListingStatusUpdate(BaseModel):
    """
    Body for POST .../publish or .../deactivate style endpoints.

    Using an explicit status target keeps OpenAPI clear; service still
    validates allowed transitions (e.g. DRAFT|INACTIVE → ACTIVE).
    """

    status: ListingStatus


# ---------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------


class ServiceListingRead(BaseModel):
    """Full listing for provider owner / admin views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    category_id: UUID
    title: str
    description: str
    base_price: int
    estimated_duration: int
    city: str
    address: str
    latitude: float | None
    longitude: float | None
    service_radius_km: Decimal
    status: ListingStatus
    is_featured: bool
    deleted_at: datetime | None
    booking_count: int
    average_rating: Decimal
    created_at: datetime
    updated_at: datetime


class ServiceListingPublicRead(BaseModel):
    """
    Customer/anonymous card + detail fields.

    Hides soft-delete tombstone; only returned for ACTIVE public rows.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    category_id: UUID
    title: str
    description: str
    base_price: int
    estimated_duration: int
    city: str
    address: str
    latitude: float | None
    longitude: float | None
    service_radius_km: Decimal
    is_featured: bool
    booking_count: int
    average_rating: Decimal
    created_at: datetime


# ---------------------------------------------------------------------------
# Search / pagination
# ---------------------------------------------------------------------------


class ServiceListingSearchParams(BaseModel):
    """
    Query params for GET /service-listings and GET /service-listings/search.

    Kept as a model so FastAPI can Depends() it and services receive one object.
    """

    q: str | None = Field(default=None, max_length=200)
    category_id: UUID | None = None
    city: str | None = Field(default=None, max_length=100)
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    min_listing_rating: Decimal | None = Field(default=None, ge=0, le=5)
    min_provider_rating: Decimal | None = Field(default=None, ge=0, le=5)
    is_featured: bool | None = None
    sort: ListingSort = ListingSort.NEWEST
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("q", "city")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def max_price_gte_min_price(self) -> ServiceListingSearchParams:
        if (
            self.max_price is not None
            and self.min_price is not None
            and self.max_price < self.min_price
        ):
            raise ValueError("max_price must be >= min_price")
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class ServiceListingPublicListResponse(BaseModel):
    """Paginated public discovery response."""

    items: list[ServiceListingPublicRead]
    total: int
    page: int
    page_size: int


class ServiceListingProviderListResponse(BaseModel):
    """Paginated provider dashboard response."""

    items: list[ServiceListingRead]
    total: int
    page: int
    page_size: int
