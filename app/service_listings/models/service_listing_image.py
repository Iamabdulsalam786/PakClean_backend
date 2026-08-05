"""
ServiceListingImage — photos attached to a marketplace listing.

Why a child table (not JSON on service_listings):
  - Multiple images per listing with stable ordering
  - Primary image flag for cards / Open Graph
  - Future: moderation, CDN keys, dimensions, soft-delete per image
  - Avoid rewriting a JSON blob on every upload/reorder

Security (enforced later in service layer):
  - Only the listing owner (verified provider) may add/reorder/delete images
  - Public APIs return image URLs only for ACTIVE, non-deleted listings
  - Never accept arbitrary filesystem paths — store HTTPS/CDN URLs (or object keys)

Feature module: app/service_listings
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ServiceListingImage(Base):
    """
    One image row belonging to a ServiceListing.

    Lifecycle:
      upload/register → insert with sort_order
      set primary     → is_primary=True for one row (service clears others)
      delete          → hard-delete child row (or soft-delete later if needed)
      parent soft-del → images remain for audit; public queries never join them
    """

    __tablename__ = "service_listing_images"
    __table_args__ = (
        # A listing should not register the same URL twice.
        UniqueConstraint(
            "listing_id",
            "image_url",
            name="uq_service_listing_images_listing_url",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Parent listing. CASCADE: hard-deleting a listing removes its images.
    # (We soft-delete listings in product flow, so CASCADE is a safety net.)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Public HTTPS URL or object-storage key resolved by the API/CDN layer.
    # max 1000 covers signed URL query strings without going unbounded.
    image_url: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    # Lower sorts first in galleries (0, 1, 2, ...).
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        index=True,
    )

    # Card thumbnail / hero. At most one True per listing — enforced in service
    # (partial unique index can be added in migration for DB-level guarantee).
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    # Optional accessibility / SEO alt text.
    alt_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    listing = relationship(
        "ServiceListing",
        back_populates="images",
        foreign_keys=[listing_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<ServiceListingImage id={self.id} listing_id={self.listing_id} "
            f"primary={self.is_primary} order={self.sort_order}>"
        )
