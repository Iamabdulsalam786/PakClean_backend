"""
Catalog request/response schemas (categories + services).

Public browse APIs return these shapes — prices are always whole PKR.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CategoryRead(BaseModel):
    """One category as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    icon_url: str | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ServiceRead(BaseModel):
    """One bookable service — price_pkr is Pakistani Rupees (whole rupees)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    name: str
    slug: str
    description: str | None
    price_pkr: int = Field(description="Base price in PKR (e.g. 1500 = Rs. 1,500)")
    duration_minutes: int
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class CategoryWithServices(CategoryRead):
    """Category detail including its active services."""

    services: list[ServiceRead] = []
