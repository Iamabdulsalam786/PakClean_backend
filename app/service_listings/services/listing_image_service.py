"""
ListingImageService — gallery management for service listings.

Layering:
  API → this service → image + listing repositories (+ ownership via listing service helpers)

Rules:
  - Only the listing owner may add/update/reorder/delete images
  - Max images per listing (MAX_IMAGES)
  - At most one primary: clear others then set (respects partial unique index)
  - First image becomes primary automatically if none exists
  - Public list only through public listing detail (ACTIVE + not deleted)
  - Hard-delete DB row; object-storage cleanup is a future hook

Feature path: app/service_listings/services/
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.service_listings.repositories.service_listing_image_repository import (
    ServiceListingImageRepository,
)
from app.service_listings.schemas.service_listing_image import (
    ServiceListingImageCreate,
    ServiceListingImageListResponse,
    ServiceListingImageRead,
    ServiceListingImageReorderRequest,
    ServiceListingImageUpdate,
)
from app.service_listings.services.service_listing_service import (
    ListingDomainError,
    ServiceListingService,
)

logger = logging.getLogger(__name__)

# Product cap — keep galleries small for mobile payloads / CDN cost.
MAX_IMAGES_PER_LISTING = 10


class ListingImageDomainError(ListingDomainError):
    """Image-specific errors share ListingDomainError for one HTTP mapper."""


class ListingImageNotFoundError(ListingImageDomainError):
    def __init__(self) -> None:
        super().__init__("Listing image not found", code="listing_image_not_found")


class ListingImageLimitError(ListingImageDomainError):
    def __init__(self) -> None:
        super().__init__(
            f"Maximum of {MAX_IMAGES_PER_LISTING} images per listing",
            code="listing_image_limit",
        )


class ListingImageConflictError(ListingImageDomainError):
    def __init__(self, message: str = "Image conflict") -> None:
        super().__init__(message, code="listing_image_conflict")


class ListingImageService:
    """Application service for service listing images."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._images = ServiceListingImageRepository(db)
        self._listings = ServiceListingService(db)

    # ------------------------------------------------------------------
    # Provider operations
    # ------------------------------------------------------------------

    def add_image(
        self,
        actor: User,
        listing_id: UUID,
        data: ServiceListingImageCreate,
    ) -> ServiceListingImageRead:
        listing = self._listings.get_my_listing(actor, listing_id)
        # get_my_listing already enforced ownership; re-check soft-delete via id
        _ = listing

        if self._images.count_for_listing(listing_id) >= MAX_IMAGES_PER_LISTING:
            raise ListingImageLimitError()

        sort_order = (
            data.sort_order
            if data.sort_order is not None
            else self._images.next_sort_order(listing_id)
        )

        make_primary = data.is_primary
        if self._images.get_primary(listing_id) is None:
            # First image (or no primary yet) → promote automatically
            make_primary = True

        if make_primary:
            self._images.clear_primary_for_listing(listing_id)

        try:
            row = self._images.add(
                listing_id=listing_id,
                image_url=data.image_url,
                sort_order=sort_order,
                is_primary=make_primary,
                alt_text=data.alt_text,
            )
            self._db.commit()
            self._db.refresh(row)
        except IntegrityError as exc:
            self._db.rollback()
            raise ListingImageConflictError(
                "Duplicate image URL for this listing or primary conflict"
            ) from exc

        logger.info(
            "listing_image_added listing_id=%s image_id=%s primary=%s",
            listing_id,
            row.id,
            row.is_primary,
        )
        return ServiceListingImageRead.model_validate(row)

    def list_for_owner(
        self,
        actor: User,
        listing_id: UUID,
    ) -> ServiceListingImageListResponse:
        self._listings.get_my_listing(actor, listing_id)
        rows = self._images.list_for_listing(listing_id)
        return ServiceListingImageListResponse(
            items=[ServiceListingImageRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def list_public(self, listing_id: UUID) -> ServiceListingImageListResponse:
        """Only if the listing is publicly visible."""
        self._listings.get_public_listing(listing_id)
        rows = self._images.list_for_listing(listing_id)
        return ServiceListingImageListResponse(
            items=[ServiceListingImageRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def update_image(
        self,
        actor: User,
        listing_id: UUID,
        image_id: UUID,
        data: ServiceListingImageUpdate,
    ) -> ServiceListingImageRead:
        self._listings.get_my_listing(actor, listing_id)
        image = self._get_owned_image(listing_id, image_id)

        if data.alt_text is not None:
            image.alt_text = data.alt_text
        if data.sort_order is not None:
            image.sort_order = data.sort_order

        if data.is_primary is True:
            self._images.clear_primary_for_listing(listing_id)
            image.is_primary = True
        elif data.is_primary is False and image.is_primary:
            # Disallow ending with zero primaries if other images exist
            image.is_primary = False
            self._images.save(image)
            self._db.flush()
            if (
                self._images.count_for_listing(listing_id) > 0
                and self._images.get_primary(listing_id) is None
            ):
                # Promote the first remaining image
                gallery = self._images.list_for_listing(listing_id)
                if gallery:
                    gallery[0].is_primary = True
                    self._images.save(gallery[0])

        try:
            self._images.save(image)
            self._db.commit()
            self._db.refresh(image)
        except IntegrityError as exc:
            self._db.rollback()
            raise ListingImageConflictError("Could not update image") from exc

        return ServiceListingImageRead.model_validate(image)

    def set_primary(
        self,
        actor: User,
        listing_id: UUID,
        image_id: UUID,
    ) -> ServiceListingImageRead:
        self._listings.get_my_listing(actor, listing_id)
        image = self._get_owned_image(listing_id, image_id)
        self._images.clear_primary_for_listing(listing_id)
        image.is_primary = True
        try:
            self._images.save(image)
            self._db.commit()
            self._db.refresh(image)
        except IntegrityError as exc:
            self._db.rollback()
            raise ListingImageConflictError("Could not set primary image") from exc
        return ServiceListingImageRead.model_validate(image)

    def reorder(
        self,
        actor: User,
        listing_id: UUID,
        data: ServiceListingImageReorderRequest,
    ) -> ServiceListingImageListResponse:
        self._listings.get_my_listing(actor, listing_id)
        existing = {img.id: img for img in self._images.list_for_listing(listing_id)}

        for item in data.items:
            image = existing.get(item.image_id)
            if image is None:
                raise ListingImageNotFoundError()
            image.sort_order = item.sort_order
            self._images.save(image)

        self._db.commit()
        rows = self._images.list_for_listing(listing_id)
        return ServiceListingImageListResponse(
            items=[ServiceListingImageRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def delete_image(
        self,
        actor: User,
        listing_id: UUID,
        image_id: UUID,
    ) -> None:
        self._listings.get_my_listing(actor, listing_id)
        image = self._get_owned_image(listing_id, image_id)
        was_primary = image.is_primary
        self._images.delete(image)
        self._db.flush()

        if was_primary:
            gallery = self._images.list_for_listing(listing_id)
            if gallery:
                gallery[0].is_primary = True
                self._images.save(gallery[0])

        self._db.commit()
        logger.info(
            "listing_image_deleted listing_id=%s image_id=%s",
            listing_id,
            image_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_owned_image(self, listing_id: UUID, image_id: UUID):
        image = self._images.get_by_id(image_id)
        if image is None or image.listing_id != listing_id:
            # Same anti-enumeration pattern as listings
            raise ListingImageNotFoundError()
        return image
