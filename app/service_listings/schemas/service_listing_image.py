"""
Service listing image request/response DTOs.

Why schemas exist:
  - Validate image URL / alt / sort before service runs.
  - Prevent mass assignment of listing_id from a forged body
    (listing_id comes from the path + ownership check).
  - Keep public image cards lean (no internal-only fields today).

Upload strategy (v1):
  Client uploads to storage (or we add a signed-URL endpoint later),
  then registers the resulting HTTPS URL here. We do NOT accept
  raw multipart file bytes in this DTO yet.

Feature path: app/service_listings/schemas/
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _looks_like_http_url(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("image_url must not be blank")
    lower = cleaned.lower()
    if not (lower.startswith("https://") or lower.startswith("http://")):
        # Allow http only for local/dev; production service can require https.
        raise ValueError("image_url must start with http:// or https://")
    if len(cleaned) > 1000:
        raise ValueError("image_url is too long")
    return cleaned


class ServiceListingImageCreate(BaseModel):
    """
    Body for POST /provider/service-listings/{listing_id}/images.

    listing_id is NOT in the body — it comes from the path (anti mass-assignment).
    """

    image_url: str = Field(min_length=8, max_length=1000)
    alt_text: str | None = Field(default=None, max_length=255)
    is_primary: bool = False
    # If omitted, service appends via repository.next_sort_order().
    sort_order: int | None = Field(default=None, ge=0, le=10_000)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        return _looks_like_http_url(value)

    @field_validator("alt_text")
    @classmethod
    def strip_alt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ServiceListingImageUpdate(BaseModel):
    """Body for PATCH .../images/{image_id} (alt / sort / primary)."""

    alt_text: str | None = Field(default=None, max_length=255)
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    is_primary: bool | None = None

    @field_validator("alt_text")
    @classmethod
    def strip_alt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ServiceListingImageReorderItem(BaseModel):
    """One row in a bulk reorder payload."""

    image_id: UUID
    sort_order: int = Field(ge=0, le=10_000)


class ServiceListingImageReorderRequest(BaseModel):
    """
    Body for PUT .../images/reorder.

    Client sends the full ordered set for that listing (or a subset).
    Service validates every image_id belongs to the listing.
    """

    items: list[ServiceListingImageReorderItem] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_image_ids(self) -> ServiceListingImageReorderRequest:
        ids = [item.image_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate image_id in reorder items")
        return self


class ServiceListingImageRead(BaseModel):
    """Image representation for provider and public listing detail."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    listing_id: UUID
    image_url: str
    sort_order: int
    is_primary: bool
    alt_text: str | None
    created_at: datetime


class ServiceListingImageListResponse(BaseModel):
    """Gallery envelope."""

    items: list[ServiceListingImageRead]
    total: int
