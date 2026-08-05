"""
ReviewRepository — SQL access for reviews.

Layering (Clean Architecture / feature module):
  API → ReviewService → this repository → Postgres

This class owns QUERIES and persistence only.
It must NOT decide who may review a booking or when ratings are eligible
(that is service-layer authorization + business rules).

Feature path: app/reviews/repositories/
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.reviews.models.review import Review


class ReviewRepository:
    """Thin data-access layer around Review rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, review_id: UUID) -> Review | None:
        return self._db.get(Review, review_id)

    def get_by_booking_id(self, booking_id: UUID) -> Review | None:
        """Used to enforce one review per booking before insert."""
        statement = select(Review).where(Review.booking_id == booking_id)
        return self._db.scalar(statement)

    def list_for_customer(
        self,
        customer_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Review]:
        statement = (
            select(Review)
            .where(Review.customer_id == customer_id)
            .order_by(Review.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement).all())

    def count_for_customer(self, customer_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(Review)
            .where(Review.customer_id == customer_id)
        )
        return int(self._db.scalar(statement) or 0)

    def list_for_listing(
        self,
        listing_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Review]:
        """Public listing review feed (newest first)."""
        statement = (
            select(Review)
            .where(Review.listing_id == listing_id)
            .order_by(Review.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement).all())

    def count_for_listing(self, listing_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(Review)
            .where(Review.listing_id == listing_id)
        )
        return int(self._db.scalar(statement) or 0)

    def aggregate_for_listing(self, listing_id: UUID) -> tuple[Decimal, int]:
        """Return (average_rating, total) for a listing. (0, 0) if none."""
        statement = select(
            func.coalesce(func.avg(Review.rating), 0),
            func.count(),
        ).where(Review.listing_id == listing_id)
        row = self._db.execute(statement).one()
        avg_val = Decimal(str(row[0])).quantize(Decimal("0.01"))
        return avg_val, int(row[1] or 0)

    def aggregate_for_provider(self, provider_user_id: UUID) -> tuple[Decimal, int]:
        """Return (average_rating, total) for a provider user id."""
        statement = select(
            func.coalesce(func.avg(Review.rating), 0),
            func.count(),
        ).where(Review.provider_id == provider_user_id)
        row = self._db.execute(statement).one()
        avg_val = Decimal(str(row[0])).quantize(Decimal("0.01"))
        return avg_val, int(row[1] or 0)

    def add(
        self,
        *,
        booking_id: UUID,
        customer_id: UUID,
        provider_id: UUID,
        listing_id: UUID | None,
        rating: int,
        comment: str | None = None,
    ) -> Review:
        """Insert a new review row (not committed)."""
        review = Review(
            booking_id=booking_id,
            customer_id=customer_id,
            provider_id=provider_id,
            listing_id=listing_id,
            rating=rating,
            comment=comment,
        )
        self._db.add(review)
        return review
