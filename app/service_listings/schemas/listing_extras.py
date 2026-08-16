"""Pydantic DTOs for listing tags, availability, and discounts."""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.service_listings.models.discount import DiscountType


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str


class TagAttachRequest(BaseModel):
    """Attach by name (get-or-create) or existing tag_id."""

    name: str | None = Field(default=None, min_length=2, max_length=80)
    tag_id: UUID | None = None

    @model_validator(mode="after")
    def require_one(self) -> TagAttachRequest:
        if self.name is None and self.tag_id is None:
            raise ValueError("Provide name or tag_id")
        if self.name is not None and self.tag_id is not None:
            raise ValueError("Provide only one of name or tag_id")
        return self

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("name too short")
        return cleaned


class TagListResponse(BaseModel):
    items: list[TagRead]
    total: int


class AvailabilityCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0=Monday … 6=Sunday")
    start_time: time
    end_time: time
    is_active: bool = True

    @model_validator(mode="after")
    def start_before_end(self) -> AvailabilityCreate:
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be before end_time")
        return self


class AvailabilityUpdate(BaseModel):
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    is_active: bool | None = None


class AvailabilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    listing_id: UUID
    day_of_week: int
    start_time: time
    end_time: time
    is_active: bool
    created_at: datetime


class AvailabilityListResponse(BaseModel):
    items: list[AvailabilityRead]
    total: int


class DiscountCreate(BaseModel):
    discount_type: DiscountType
    value: Decimal = Field(gt=0)
    starts_at: datetime
    ends_at: datetime
    is_active: bool = True

    @model_validator(mode="after")
    def validate_window_and_value(self) -> DiscountCreate:
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        if self.discount_type is DiscountType.PERCENT and self.value > Decimal("100"):
            raise ValueError("percent discount cannot exceed 100")
        return self


class DiscountUpdate(BaseModel):
    discount_type: DiscountType | None = None
    value: Decimal | None = Field(default=None, gt=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None


class DiscountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    listing_id: UUID
    discount_type: DiscountType
    value: Decimal
    starts_at: datetime
    ends_at: datetime
    is_active: bool
    created_at: datetime


class DiscountListResponse(BaseModel):
    items: list[DiscountRead]
    total: int
