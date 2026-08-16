"""
ListingExtrasService — tags, availability slots, and discounts.

Ownership always goes through ServiceListingService.get_my_listing /
get_public_listing.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User
from app.service_listings.repositories.listing_extras_repository import (
    AvailabilityRepository,
    DiscountRepository,
    TagRepository,
)
from app.service_listings.schemas.listing_extras import (
    AvailabilityCreate,
    AvailabilityListResponse,
    AvailabilityRead,
    AvailabilityUpdate,
    DiscountCreate,
    DiscountListResponse,
    DiscountRead,
    DiscountUpdate,
    TagAttachRequest,
    TagListResponse,
    TagRead,
)
from app.service_listings.services.service_listing_service import (
    ListingDomainError,
    ServiceListingService,
)

logger = logging.getLogger(__name__)

MAX_TAGS_PER_LISTING = 20


class ListingExtrasError(ListingDomainError):
    pass


class ListingExtrasService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._listings = ServiceListingService(db)
        self._tags = TagRepository(db)
        self._availability = AvailabilityRepository(db)
        self._discounts = DiscountRepository(db)

    # ----- tags -----

    def list_catalog_tags(self) -> TagListResponse:
        rows = self._tags.list_all()
        return TagListResponse(
            items=[TagRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def list_listing_tags_owner(self, actor: User, listing_id: UUID) -> TagListResponse:
        self._listings.get_my_listing(actor, listing_id)
        rows = self._tags.list_for_listing(listing_id)
        return TagListResponse(
            items=[TagRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def list_listing_tags_public(self, listing_id: UUID) -> TagListResponse:
        self._listings.get_public_listing(listing_id)
        rows = self._tags.list_for_listing(listing_id)
        return TagListResponse(
            items=[TagRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def attach_tag(
        self,
        actor: User,
        listing_id: UUID,
        data: TagAttachRequest,
    ) -> TagRead:
        self._listings.get_my_listing(actor, listing_id)
        if len(self._tags.list_for_listing(listing_id)) >= MAX_TAGS_PER_LISTING:
            raise ListingExtrasError(
                f"Maximum of {MAX_TAGS_PER_LISTING} tags per listing",
                code="listing_tag_limit",
            )

        if data.tag_id is not None:
            tag = self._tags.get_by_id(data.tag_id)
            if tag is None:
                raise ListingExtrasError("Tag not found", code="tag_not_found")
        else:
            assert data.name is not None
            tag = self._tags.get_or_create(name=data.name)

        if self._tags.is_attached(listing_id=listing_id, tag_id=tag.id):
            return TagRead.model_validate(tag)

        try:
            self._tags.attach(listing_id=listing_id, tag_id=tag.id)
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise ListingExtrasError("Could not attach tag", code="tag_conflict") from exc

        self._db.refresh(tag)
        return TagRead.model_validate(tag)

    def detach_tag(self, actor: User, listing_id: UUID, tag_id: UUID) -> None:
        self._listings.get_my_listing(actor, listing_id)
        deleted = self._tags.detach(listing_id=listing_id, tag_id=tag_id)
        if deleted == 0:
            raise ListingExtrasError("Tag not attached", code="tag_not_found")
        self._db.commit()

    # ----- availability -----

    def list_availability_owner(
        self, actor: User, listing_id: UUID
    ) -> AvailabilityListResponse:
        self._listings.get_my_listing(actor, listing_id)
        rows = self._availability.list_for_listing(listing_id)
        return AvailabilityListResponse(
            items=[AvailabilityRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def list_availability_public(self, listing_id: UUID) -> AvailabilityListResponse:
        self._listings.get_public_listing(listing_id)
        rows = self._availability.list_for_listing(listing_id, active_only=True)
        return AvailabilityListResponse(
            items=[AvailabilityRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def add_availability(
        self,
        actor: User,
        listing_id: UUID,
        data: AvailabilityCreate,
    ) -> AvailabilityRead:
        self._listings.get_my_listing(actor, listing_id)
        try:
            row = self._availability.add(
                listing_id=listing_id,
                day_of_week=data.day_of_week,
                start_time=data.start_time,
                end_time=data.end_time,
                is_active=data.is_active,
            )
            self._db.commit()
            self._db.refresh(row)
        except IntegrityError as exc:
            self._db.rollback()
            raise ListingExtrasError(
                "Duplicate or invalid availability slot",
                code="availability_conflict",
            ) from exc
        return AvailabilityRead.model_validate(row)

    def update_availability(
        self,
        actor: User,
        listing_id: UUID,
        slot_id: UUID,
        data: AvailabilityUpdate,
    ) -> AvailabilityRead:
        self._listings.get_my_listing(actor, listing_id)
        row = self._availability.get_by_id(slot_id)
        if row is None or row.listing_id != listing_id:
            raise ListingExtrasError("Availability slot not found", code="availability_not_found")

        if data.day_of_week is not None:
            row.day_of_week = data.day_of_week
        if data.start_time is not None:
            row.start_time = data.start_time
        if data.end_time is not None:
            row.end_time = data.end_time
        if data.is_active is not None:
            row.is_active = data.is_active
        if row.start_time >= row.end_time:
            raise ListingExtrasError(
                "start_time must be before end_time",
                code="availability_invalid",
            )

        try:
            self._availability.save(row)
            self._db.commit()
            self._db.refresh(row)
        except IntegrityError as exc:
            self._db.rollback()
            raise ListingExtrasError(
                "Duplicate or invalid availability slot",
                code="availability_conflict",
            ) from exc
        return AvailabilityRead.model_validate(row)

    def delete_availability(self, actor: User, listing_id: UUID, slot_id: UUID) -> None:
        self._listings.get_my_listing(actor, listing_id)
        row = self._availability.get_by_id(slot_id)
        if row is None or row.listing_id != listing_id:
            raise ListingExtrasError("Availability slot not found", code="availability_not_found")
        self._availability.delete(row)
        self._db.commit()

    # ----- discounts -----

    def list_discounts_owner(self, actor: User, listing_id: UUID) -> DiscountListResponse:
        self._listings.get_my_listing(actor, listing_id)
        rows = self._discounts.list_for_listing(listing_id)
        return DiscountListResponse(
            items=[DiscountRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def list_discounts_public(self, listing_id: UUID) -> DiscountListResponse:
        self._listings.get_public_listing(listing_id)
        rows = self._discounts.list_for_listing(listing_id, active_only=True)
        return DiscountListResponse(
            items=[DiscountRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    def add_discount(
        self,
        actor: User,
        listing_id: UUID,
        data: DiscountCreate,
    ) -> DiscountRead:
        self._listings.get_my_listing(actor, listing_id)
        try:
            row = self._discounts.add(
                listing_id=listing_id,
                discount_type=data.discount_type,
                value=data.value,
                starts_at=data.starts_at,
                ends_at=data.ends_at,
                is_active=data.is_active,
            )
            self._db.commit()
            self._db.refresh(row)
        except IntegrityError as exc:
            self._db.rollback()
            raise ListingExtrasError(
                "Could not create discount",
                code="discount_conflict",
            ) from exc
        return DiscountRead.model_validate(row)

    def update_discount(
        self,
        actor: User,
        listing_id: UUID,
        discount_id: UUID,
        data: DiscountUpdate,
    ) -> DiscountRead:
        self._listings.get_my_listing(actor, listing_id)
        row = self._discounts.get_by_id(discount_id)
        if row is None or row.listing_id != listing_id:
            raise ListingExtrasError("Discount not found", code="discount_not_found")

        if data.discount_type is not None:
            row.discount_type = data.discount_type
        if data.value is not None:
            row.value = data.value
        if data.starts_at is not None:
            row.starts_at = data.starts_at
        if data.ends_at is not None:
            row.ends_at = data.ends_at
        if data.is_active is not None:
            row.is_active = data.is_active

        if row.starts_at >= row.ends_at:
            raise ListingExtrasError(
                "starts_at must be before ends_at",
                code="discount_invalid",
            )
        from app.service_listings.models.discount import DiscountType
        from decimal import Decimal

        if row.discount_type is DiscountType.PERCENT and row.value > Decimal("100"):
            raise ListingExtrasError(
                "percent discount cannot exceed 100",
                code="discount_invalid",
            )

        self._discounts.save(row)
        self._db.commit()
        self._db.refresh(row)
        return DiscountRead.model_validate(row)

    def delete_discount(self, actor: User, listing_id: UUID, discount_id: UUID) -> None:
        self._listings.get_my_listing(actor, listing_id)
        row = self._discounts.get_by_id(discount_id)
        if row is None or row.listing_id != listing_id:
            raise ListingExtrasError("Discount not found", code="discount_not_found")
        self._discounts.delete(row)
        self._db.commit()
