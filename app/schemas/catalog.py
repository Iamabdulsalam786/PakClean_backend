"""
Catalog response schemas — categories only.

Bookable offerings live under marketplace service listings, not catalog services.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
