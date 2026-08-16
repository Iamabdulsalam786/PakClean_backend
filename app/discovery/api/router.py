"""
Marketplace discovery HTTP endpoints — public browse / search / detail.

No auth required. Only ACTIVE, non-deleted listings are returned
(enforced in DiscoveryRepository / DiscoveryService).

Routes:
  GET /marketplace/listings
  GET /marketplace/listings/search
  GET /marketplace/listings/{listing_id}
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import DbSession
from app.discovery.schemas.discovery import (
    DiscoveryListResponse,
    DiscoverySearchParams,
    DiscoverySort,
    ListingDetail,
)
from app.discovery.services.discovery_service import (
    DiscoveryNotFoundError,
    DiscoveryService,
)

router = APIRouter(prefix="/marketplace", tags=["marketplace-discovery"])


def _service(db: DbSession) -> DiscoveryService:
    return DiscoveryService(db)


def _search_params(
    q: str | None = Query(default=None, max_length=200),
    category_id: UUID | None = None,
    city: str | None = Query(default=None, max_length=100),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    is_featured: bool | None = None,
    available_on: int | None = Query(
        default=None,
        ge=0,
        le=6,
        description="Weekday 0=Monday … 6=Sunday; listing must have an active slot",
    ),
    sort: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> DiscoverySearchParams:
    """Bind and validate query string → DiscoverySearchParams."""
    try:
        sort_enum = DiscoverySort(sort)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid sort. Use newest|oldest|price_asc|price_desc|"
                "rating_desc|most_booked"
            ),
        ) from exc

    try:
        return DiscoverySearchParams(
            q=q,
            category_id=category_id,
            city=city,
            min_price=min_price,
            max_price=max_price,
            min_rating=Decimal(str(min_rating)) if min_rating is not None else None,
            is_featured=is_featured,
            available_on=available_on,
            sort=sort_enum,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/listings",
    response_model=DiscoveryListResponse,
    summary="Browse marketplace listings (filter + sort + pagination)",
)
def browse_listings(
    db: DbSession,
    params: DiscoverySearchParams = Depends(_search_params),
) -> DiscoveryListResponse:
    return _service(db).browse(params)


@router.get(
    "/listings/search",
    response_model=DiscoveryListResponse,
    summary="Search marketplace listings (same engine as browse)",
)
def search_listings(
    db: DbSession,
    params: DiscoverySearchParams = Depends(_search_params),
) -> DiscoveryListResponse:
    """
    Explicit search path for analytics / mobile UX.

    Declared before /listings/{listing_id} so 'search' is not parsed as a UUID.
    """
    return _service(db).browse(params)


@router.get(
    "/listings/{listing_id}",
    response_model=ListingDetail,
    summary="Get public listing detail (category, provider, images, availability)",
)
def get_listing_detail(
    listing_id: UUID,
    db: DbSession,
) -> ListingDetail:
    try:
        return _service(db).get_detail(listing_id)
    except DiscoveryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        ) from exc
