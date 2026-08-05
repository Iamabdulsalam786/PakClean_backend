"""
Booking model — customer request for a marketplace ServiceListing (or legacy catalog Service).

Marketplace (current):
  - Customer books an ACTIVE listing by listing_id
  - provider_id is set from the listing owner at create time
  - price_pkr / duration / title are snapshotted (listing may change later)
  - Status follows BookingStatus state machine (pending → … → completed)

Legacy Phase 1:
  - service_id pointed at catalog services; still nullable for old rows
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.bookings.models.booking_status import BookingStatus
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.service import Service
    from app.models.user import User
    from app.service_listings.models.service_listing import ServiceListing

# Re-export so `from app.models.booking import BookingStatus` keeps working.
__all__ = ["Booking", "BookingStatus"]


class Booking(Base):
    """ORM mapping for the bookings table."""

    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Marketplace target. Null only on legacy catalog-era rows.
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_listings.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Legacy catalog FK — nullable so new listing bookings need not set it.
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Listing owner's user id (set on marketplace create). Null on some legacy rows.
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=BookingStatus.PENDING,
        server_default=BookingStatus.PENDING.value,
        index=True,
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    address_text: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Snapshots at book time (immutable commercial terms for this booking).
    price_pkr: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    listing_title_snapshot: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Lifecycle audit (null until that transition occurs).
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    customer: Mapped[User] = relationship(
        "User",
        foreign_keys=[customer_id],
        lazy="joined",
    )

    provider: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[provider_id],
        lazy="joined",
    )

    service: Mapped[Service | None] = relationship(
        "Service",
        lazy="joined",
    )

    listing: Mapped[ServiceListing | None] = relationship(
        "ServiceListing",
        foreign_keys=[listing_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Booking id={self.id} status={self.status.value} "
            f"listing_id={self.listing_id}>"
        )
