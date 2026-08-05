"""
ReviewService — create reviews after completed bookings + public/mine lists.

Layering:
  API route → this service → ReviewRepository (+ Booking / Listing / Profile)
  Does not import FastAPI.

Business rules owned here:
  - Only role=customer may create
  - Booking must belong to actor and status=COMPLETED
  - One review per booking (pre-check + UNIQUE / IntegrityError)
  - After insert, recompute listing + provider denormalized averages
    in the same transaction

Feature path: app/reviews/services/
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bookings.models.booking_status import BookingStatus
from app.models.booking import Booking
from app.models.user import User, UserRole
from app.providers.repositories.provider_profile_repository import (
    ProviderProfileRepository,
)
from app.reviews.models.review import Review
from app.reviews.repositories.review_repository import ReviewRepository
from app.reviews.schemas.review import (
    ReviewCreate,
    ReviewListResponse,
    ReviewRead,
)
from app.service_listings.models.service_listing import ServiceListing

logger = logging.getLogger(__name__)


class ReviewDomainError(Exception):
    """Base review-feature error with a stable machine code."""

    def __init__(self, message: str, *, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class NotACustomerError(ReviewDomainError):
    def __init__(self) -> None:
        super().__init__(
            "Only customer accounts can create reviews",
            code="not_a_customer",
        )


class BookingNotFoundError(ReviewDomainError):
    def __init__(self) -> None:
        super().__init__("Booking not found", code="booking_not_found")


class BookingNotCompletedError(ReviewDomainError):
    def __init__(self) -> None:
        super().__init__(
            "Only completed bookings can be reviewed",
            code="booking_not_completed",
        )


class ReviewAlreadyExistsError(ReviewDomainError):
    def __init__(self) -> None:
        super().__init__(
            "This booking already has a review",
            code="review_already_exists",
        )


class ReviewService:
    """Application service for marketplace reviews."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._reviews = ReviewRepository(db)
        self._profiles = ProviderProfileRepository(db)

    def create_review(self, actor: User, data: ReviewCreate) -> Review:
        if actor.role != UserRole.CUSTOMER:
            raise NotACustomerError()

        booking = self._db.get(Booking, data.booking_id)
        if booking is None or booking.customer_id != actor.id:
            raise BookingNotFoundError()

        if booking.status != BookingStatus.COMPLETED:
            raise BookingNotCompletedError()

        if booking.provider_id is None:
            raise BookingNotFoundError()

        if self._reviews.get_by_booking_id(booking.id) is not None:
            raise ReviewAlreadyExistsError()

        review = self._reviews.add(
            booking_id=booking.id,
            customer_id=actor.id,
            provider_id=booking.provider_id,
            listing_id=booking.listing_id,
            rating=data.rating,
            comment=data.comment,
        )

        try:
            self._db.flush()
        except IntegrityError as exc:
            self._db.rollback()
            raise ReviewAlreadyExistsError() from exc

        self._refresh_denormalized_ratings(
            listing_id=booking.listing_id,
            provider_user_id=booking.provider_id,
        )

        self._db.commit()
        self._db.refresh(review)
        logger.info(
            "review_created review_id=%s booking_id=%s rating=%s",
            review.id,
            booking.id,
            review.rating,
        )
        return review

    def list_my_reviews(
        self,
        actor: User,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> ReviewListResponse:
        if actor.role != UserRole.CUSTOMER:
            raise NotACustomerError()
        page = max(1, page)
        page_size = min(max(1, page_size), 50)
        offset = (page - 1) * page_size
        total = self._reviews.count_for_customer(actor.id)
        rows = self._reviews.list_for_customer(
            actor.id,
            limit=page_size,
            offset=offset,
        )
        return ReviewListResponse(
            items=[ReviewRead.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_listing_reviews(
        self,
        listing_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> ReviewListResponse:
        """Public feed — no auth required at service level (route decides)."""
        page = max(1, page)
        page_size = min(max(1, page_size), 50)
        offset = (page - 1) * page_size
        total = self._reviews.count_for_listing(listing_id)
        rows = self._reviews.list_for_listing(
            listing_id,
            limit=page_size,
            offset=offset,
        )
        return ReviewListResponse(
            items=[ReviewRead.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def _refresh_denormalized_ratings(
        self,
        *,
        listing_id: UUID | None,
        provider_user_id: UUID,
    ) -> None:
        if listing_id is not None:
            avg, _total = self._reviews.aggregate_for_listing(listing_id)
            listing = self._db.get(ServiceListing, listing_id)
            if listing is not None:
                listing.average_rating = avg
                self._db.add(listing)

        avg, total = self._reviews.aggregate_for_provider(provider_user_id)
        profile = self._profiles.get_by_user_id(provider_user_id)
        if profile is not None:
            profile.average_rating = avg
            profile.total_reviews = total
            self._profiles.save(profile)
