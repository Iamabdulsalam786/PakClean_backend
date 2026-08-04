"""
Booking model — a customer request for a catalog Service at a scheduled time.

Phase 1:
  - Customer creates a booking (service + time + address)
  - provider_id stays null until assignment (later)
  - price_pkr is snapshotted from the service at create time
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.service import Service
    from app.models.user import User


class BookingStatus(str, enum.Enum):
    """Lifecycle of a booking."""

    PENDING = "pending"  # Created; waiting for provider / confirmation
    CONFIRMED = "confirmed"  # Accepted (manual/admin for now)
    CANCELLED = "cancelled"
    COMPLETED = "completed"


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

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Null until a provider is assigned (Phase 1 leaves this empty).
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

    # When the customer wants the job done (timezone-aware).
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Simple address text for Phase 1 (structured addresses later).
    address_text: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Snapshot of catalog price at booking time (PKR whole rupees).
    price_pkr: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
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

    service: Mapped[Service] = relationship(
        "Service",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<Booking id={self.id} status={self.status.value}>"
