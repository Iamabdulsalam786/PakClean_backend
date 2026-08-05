"""
Review HTTP endpoints — customer create/list + public listing feed.

Thin controllers: schema validation → ReviewService → map errors → HTTP.

Routes:
  POST  /reviews
  GET   /reviews/me
  GET   /marketplace/listings/{listing_id}/reviews
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dependencies import CurrentCustomer, DbSession
from app.reviews.schemas.review import (
    ReviewCreate,
    ReviewListResponse,
    ReviewRead,
)
from app.reviews.services.review_service import (
    ReviewDomainError,
    ReviewService,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])
marketplace_router = APIRouter(prefix="/marketplace", tags=["marketplace-reviews"])


def _http_for_review_error(exc: ReviewDomainError) -> HTTPException:
    code = exc.code
    if code == "booking_not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif code == "not_a_customer":
        status_code = status.HTTP_403_FORBIDDEN
    elif code in {"booking_not_completed", "review_already_exists"}:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


def _service(db: DbSession) -> ReviewService:
    return ReviewService(db)


@router.post(
    "",
    response_model=ReviewRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a review for a completed booking (customer)",
)
def create_review(
    payload: ReviewCreate,
    db: DbSession,
    customer: CurrentCustomer,
) -> ReviewRead:
    try:
        review = _service(db).create_review(customer, payload)
    except ReviewDomainError as exc:
        raise _http_for_review_error(exc) from exc
    return ReviewRead.model_validate(review)


@router.get(
    "/me",
    response_model=ReviewListResponse,
    summary="List my reviews (customer)",
)
def list_my_reviews(
    db: DbSession,
    customer: CurrentCustomer,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> ReviewListResponse:
    try:
        return _service(db).list_my_reviews(
            customer,
            page=page,
            page_size=page_size,
        )
    except ReviewDomainError as exc:
        raise _http_for_review_error(exc) from exc


@marketplace_router.get(
    "/listings/{listing_id}/reviews",
    response_model=ReviewListResponse,
    summary="List public reviews for a listing",
)
def list_listing_reviews(
    listing_id: UUID,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> ReviewListResponse:
    return _service(db).list_listing_reviews(
        listing_id,
        page=page,
        page_size=page_size,
    )
