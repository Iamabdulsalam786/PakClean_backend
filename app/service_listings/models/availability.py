"""
ServiceListingAvailability — weekly schedule windows for a listing.

day_of_week: 0=Monday … 6=Sunday (ISO-like, document in API).
Multiple rows per day allowed (e.g. 09:00–12:00 and 14:00–18:00).

Feature: service_listings
"""

from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ServiceListingAvailability(Base):
    """One availability slot for a listing."""

    __tablename__ = "service_listing_availability"
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "day_of_week",
            "start_time",
            "end_time",
            name="uq_listing_availability_slot",
        ),
    )

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

    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    listing = relationship("ServiceListing", foreign_keys=[listing_id], lazy="select")
