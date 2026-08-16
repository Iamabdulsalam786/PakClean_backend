"""
ServiceListingImageRepository — SQL access for listing gallery images.

Layering:
  API → ListingImageService → this repository → Postgres

Owns persistence only. Ownership / max-image caps / primary-image rules
live in the service (which also clears other primaries in one transaction).

Feature path: app/service_listings/repositories/
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.service_listings.models.service_listing_image import ServiceListingImage


class ServiceListingImageRepository:
    """Thin data-access layer around ServiceListingImage rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, image_id: UUID) -> ServiceListingImage | None:
        """Primary-key lookup."""
        return self._db.get(ServiceListingImage, image_id)

    def list_for_listing(self, listing_id: UUID) -> list[ServiceListingImage]:
        """
        All images for a listing, gallery order (sort_order ASC, then created_at).

        Used by provider manage UI and public listing detail.
        """
        statement = (
            select(ServiceListingImage)
            .where(ServiceListingImage.listing_id == listing_id)
            .order_by(
                ServiceListingImage.sort_order.asc(),
                ServiceListingImage.created_at.asc(),
            )
        )
        return list(self._db.scalars(statement).all())

    def count_for_listing(self, listing_id: UUID) -> int:
        """Enforce max images per listing in the service layer."""
        statement = (
            select(func.count())
            .select_from(ServiceListingImage)
            .where(ServiceListingImage.listing_id == listing_id)
        )
        return int(self._db.scalar(statement) or 0)

    def get_primary(self, listing_id: UUID) -> ServiceListingImage | None:
        """Current primary image, if any."""
        statement = select(ServiceListingImage).where(
            ServiceListingImage.listing_id == listing_id,
            ServiceListingImage.is_primary.is_(True),
        )
        return self._db.scalar(statement)

    def add(
        self,
        *,
        listing_id: UUID,
        image_url: str,
        sort_order: int = 0,
        is_primary: bool = False,
        alt_text: str | None = None,
    ) -> ServiceListingImage:
        """
        Insert an image row (not committed).

        Caller must already own the listing and validate URL shape.
        """
        row = ServiceListingImage(
            listing_id=listing_id,
            image_url=image_url,
            sort_order=sort_order,
            is_primary=is_primary,
            alt_text=alt_text,
        )
        self._db.add(row)
        return row

    def clear_primary_for_listing(self, listing_id: UUID) -> int:
        """
        Set is_primary=False for every image on this listing.

        Used before promoting a new primary so the partial unique index holds.
        Returns rows updated.
        """
        statement = (
            update(ServiceListingImage)
            .where(
                ServiceListingImage.listing_id == listing_id,
                ServiceListingImage.is_primary.is_(True),
            )
            .values(is_primary=False)
        )
        result = self._db.execute(statement)
        return result.rowcount or 0

    def save(self, image: ServiceListingImage) -> ServiceListingImage:
        """Persist in-memory changes (no commit)."""
        self._db.add(image)
        return image

    def delete(self, image: ServiceListingImage) -> None:
        """
        Hard-delete one image row (no commit).

        Object-storage cleanup (S3 delete) belongs in the service/worker,
        not here — repository only touches Postgres.
        """
        self._db.delete(image)

    def next_sort_order(self, listing_id: UUID) -> int:
        """
        Append position: max(sort_order)+1, or 0 if empty.

        Avoids collisions when clients omit sort_order on upload.
        """
        statement = select(func.max(ServiceListingImage.sort_order)).where(
            ServiceListingImage.listing_id == listing_id
        )
        current_max = self._db.scalar(statement)
        if current_max is None:
            return 0
        return int(current_max) + 1
