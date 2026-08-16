"""Repositories for listing tags, availability, and discounts."""

from __future__ import annotations

import re
from datetime import time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.service_listings.models.availability import ServiceListingAvailability
from app.service_listings.models.discount import DiscountType, ServiceListingDiscount
from app.service_listings.models.tag import ServiceListingTag, Tag


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:100] or "tag"


class TagRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, tag_id: UUID) -> Tag | None:
        return self._db.get(Tag, tag_id)

    def get_by_slug(self, slug: str) -> Tag | None:
        return self._db.scalar(select(Tag).where(Tag.slug == slug))

    def list_all(self, *, limit: int = 200) -> list[Tag]:
        statement = select(Tag).order_by(Tag.name.asc()).limit(limit)
        return list(self._db.scalars(statement).all())

    def get_or_create(self, *, name: str) -> Tag:
        cleaned = name.strip()
        slug = slugify(cleaned)
        existing = self.get_by_slug(slug)
        if existing is not None:
            return existing
        tag = Tag(name=cleaned, slug=slug)
        self._db.add(tag)
        self._db.flush()
        return tag

    def list_for_listing(self, listing_id: UUID) -> list[Tag]:
        statement = (
            select(Tag)
            .join(ServiceListingTag, ServiceListingTag.tag_id == Tag.id)
            .where(ServiceListingTag.listing_id == listing_id)
            .order_by(Tag.name.asc())
        )
        return list(self._db.scalars(statement).all())

    def attach(self, *, listing_id: UUID, tag_id: UUID) -> ServiceListingTag:
        row = ServiceListingTag(listing_id=listing_id, tag_id=tag_id)
        self._db.add(row)
        return row

    def detach(self, *, listing_id: UUID, tag_id: UUID) -> int:
        result = self._db.execute(
            delete(ServiceListingTag).where(
                ServiceListingTag.listing_id == listing_id,
                ServiceListingTag.tag_id == tag_id,
            )
        )
        return result.rowcount or 0

    def is_attached(self, *, listing_id: UUID, tag_id: UUID) -> bool:
        statement = select(ServiceListingTag).where(
            ServiceListingTag.listing_id == listing_id,
            ServiceListingTag.tag_id == tag_id,
        )
        return self._db.scalar(statement) is not None


class AvailabilityRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, slot_id: UUID) -> ServiceListingAvailability | None:
        return self._db.get(ServiceListingAvailability, slot_id)

    def list_for_listing(
        self,
        listing_id: UUID,
        *,
        active_only: bool = False,
    ) -> list[ServiceListingAvailability]:
        statement = select(ServiceListingAvailability).where(
            ServiceListingAvailability.listing_id == listing_id
        )
        if active_only:
            statement = statement.where(ServiceListingAvailability.is_active.is_(True))
        statement = statement.order_by(
            ServiceListingAvailability.day_of_week.asc(),
            ServiceListingAvailability.start_time.asc(),
        )
        return list(self._db.scalars(statement).all())

    def add(
        self,
        *,
        listing_id: UUID,
        day_of_week: int,
        start_time: time,
        end_time: time,
        is_active: bool = True,
    ) -> ServiceListingAvailability:
        row = ServiceListingAvailability(
            listing_id=listing_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            is_active=is_active,
        )
        self._db.add(row)
        return row

    def save(self, row: ServiceListingAvailability) -> ServiceListingAvailability:
        self._db.add(row)
        return row

    def delete(self, row: ServiceListingAvailability) -> None:
        self._db.delete(row)


class DiscountRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, discount_id: UUID) -> ServiceListingDiscount | None:
        return self._db.get(ServiceListingDiscount, discount_id)

    def list_for_listing(
        self,
        listing_id: UUID,
        *,
        active_only: bool = False,
    ) -> list[ServiceListingDiscount]:
        statement = select(ServiceListingDiscount).where(
            ServiceListingDiscount.listing_id == listing_id
        )
        if active_only:
            statement = statement.where(ServiceListingDiscount.is_active.is_(True))
        statement = statement.order_by(ServiceListingDiscount.starts_at.desc())
        return list(self._db.scalars(statement).all())

    def add(
        self,
        *,
        listing_id: UUID,
        discount_type: DiscountType,
        value: Decimal,
        starts_at,
        ends_at,
        is_active: bool = True,
    ) -> ServiceListingDiscount:
        row = ServiceListingDiscount(
            listing_id=listing_id,
            discount_type=discount_type,
            value=value,
            starts_at=starts_at,
            ends_at=ends_at,
            is_active=is_active,
        )
        self._db.add(row)
        return row

    def save(self, row: ServiceListingDiscount) -> ServiceListingDiscount:
        self._db.add(row)
        return row

    def delete(self, row: ServiceListingDiscount) -> None:
        self._db.delete(row)
