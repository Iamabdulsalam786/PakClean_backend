"""
ServiceListing — provider-owned marketplace offering.

Why this table (vs existing catalog `services`):
  - `services` = platform template catalog (seeded, admin-curated).
  - `service_listings` = what a VERIFIED provider sells (price, area, photos…).
  - Customers browse/book a listing; ownership and RBAC hang off provider_profiles.

Business gates (enforced in services, not DB):
  - Only ProviderProfile.can_create_listings() may insert rows
  - Providers may mutate only their own provider_id rows
  - Public read: status=ACTIVE AND deleted_at IS NULL

Feature module: app/service_listings
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.service_listings.models.listing_status import ListingStatus


class ServiceListing(Base):
    """
    One sellable offering owned by a provider profile.

    Lifecycle:
      create   → status=DRAFT (default), deleted_at=NULL
      publish  → ACTIVE (service checks provider verified + ownership)
      pause    → INACTIVE
      soft del → deleted_at set (hidden everywhere public; row retained)
    """

    __tablename__ = "service_listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Ownership root — FK to provider_profiles, NOT users.
    # RESTRICT: cannot delete a profile that still has listings (force soft-delete first).
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provider_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Taxonomy — reuse existing categories table.
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,  # title search / ILIKE support (trigram later at scale)
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Integer PKR (same convention as catalog price_pkr) — avoids float money bugs.
    base_price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,  # min/max price filters
    )

    # Minutes — mirrors catalog duration_minutes naming intent.
    estimated_duration: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,  # city filter / search
    )

    address: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # Nullable until the provider sets a pin / geo onboarding exists.
    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    service_radius_km: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
        default=Decimal("5.00"),
        server_default="5.00",
    )

    status: Mapped[ListingStatus] = mapped_column(
        Enum(
            ListingStatus,
            name="listing_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ListingStatus.DRAFT,
        server_default=ListingStatus.DRAFT.value,
        index=True,
    )

    is_featured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    # Soft delete tombstone — NOT a ListingStatus value.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Denormalized for sort=most_booked / highest_rated without heavy joins.
    booking_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    average_rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,  # sort=newest / oldest
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    provider = relationship(
        "ProviderProfile",
        foreign_keys=[provider_id],
        lazy="joined",
    )
    category = relationship(
        "Category",
        foreign_keys=[category_id],
        lazy="joined",
    )
    images = relationship(
        "ServiceListingImage",
        back_populates="listing",
        lazy="selectin",
        order_by="ServiceListingImage.sort_order",
        cascade="all, delete-orphan",
    )

    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def is_publicly_visible(self) -> bool:
        """
        Anonymous/customer browse eligibility.

        Must stay in sync with public repository filters.
        """
        return (
            self.deleted_at is None
            and self.status.is_publicly_visible()
        )

    def soft_delete(self, *, when: datetime) -> None:
        """Mark deleted; service must also hide from public queries."""
        self.deleted_at = when

    def __repr__(self) -> str:
        return (
            f"<ServiceListing id={self.id} provider_id={self.provider_id} "
            f"status={self.status} deleted={self.deleted_at is not None}>"
        )
