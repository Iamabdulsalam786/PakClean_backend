"""
ServiceListingDiscount — optional time-bound discount on a listing.

discount_type:
  percent → value is 1–100 (percent off base_price)
  fixed   → value is PKR amount off base_price

Service layer validates value vs type and date window.
Effective price computation can live on the booking service later.

Feature: service_listings
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DiscountType(str, enum.Enum):
    PERCENT = "percent"
    FIXED = "fixed"


class ServiceListingDiscount(Base):
    """One discount rule attached to a listing."""

    __tablename__ = "service_listing_discounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(
            DiscountType,
            name="discount_type",
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )

    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    listing = relationship("ServiceListing", foreign_keys=[listing_id], lazy="select")

    def is_currently_effective(self, *, now: datetime) -> bool:
        return (
            self.is_active
            and self.starts_at <= now <= self.ends_at
        )
