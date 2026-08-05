"""
CustomerAddress — saved service locations for a customer.

Why this table exists (not only booking.address_text):
  - Mobile UX needs reusable Home / Office / Other pins.
  - Bookings still snapshot free-text at create time (history stays stable if
    the address row is edited or deleted later).
  - Structured city/area enable future "near me" filters without parsing blobs.

Feature module: app/customers (feature-based architecture).
No CustomerProfile table in MVP — full_name/phone live on users.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerAddress(Base):
    """
    One saved address owned by a customer user.

    Lifecycle:
      - Customer creates up to N addresses (cap enforced in service)
      - At most one is_default=True per customer (service clears others)
      - Soft product delete = hard DELETE (addresses are not audit history;
        bookings keep their own address_text snapshot)
    """

    __tablename__ = "customer_addresses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Owner. CASCADE: delete user → delete their address book.
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # UI label: "Home", "Office", "Mom's place".
    label: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Street / house / flat — required free-text line for providers.
    address_line: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # Optional neighbourhood (DHA Phase 6, Gulberg).
    area: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    landmark: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Optional map pin for a later maps slice. Precision matches provider geo.
    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    # Application enforces one default per customer in the same transaction.
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
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

    def to_address_text(self) -> str:
        """
        Build a booking snapshot string from structured fields.

        Used later when create-booking accepts address_id.
        """
        parts = [self.address_line]
        if self.area:
            parts.append(self.area)
        parts.append(self.city)
        if self.landmark:
            parts.append(f"near {self.landmark}")
        return ", ".join(parts)

    def __repr__(self) -> str:
        return (
            f"<CustomerAddress id={self.id} customer_id={self.customer_id} "
            f"label={self.label!r} default={self.is_default}>"
        )
