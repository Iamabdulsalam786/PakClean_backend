"""
Service listing HTTP endpoints — provider CRUD + public browse/search.

Thin controllers: schemas → ServiceListingService → map domain errors → HTTP.

Routes:
  Provider:
    POST   /provider/service-listings
    GET    /provider/service-listings
    GET    /provider/service-listings/{id}
    PATCH  /provider/service-listings/{id}
    POST   /provider/service-listings/{id}/publish
    POST   /provider/service-listings/{id}/deactivate
    DELETE /provider/service-listings/{id}

  Public:
    GET    /service-listings
    GET    /service-listings/search
    GET    /service-listings/{id}
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.core.dependencies import CurrentProvider, DbSession
from app.service_listings.models.listing_status import ListingStatus
from app.service_listings.schemas.service_listing import (
    ServiceListingCreate,
    ServiceListingProviderListResponse,
    ServiceListingPublicListResponse,
    ServiceListingPublicRead,
    ServiceListingRead,
    ServiceListingSearchParams,
    ServiceListingUpdate,
)
from app.service_listings.services.service_listing_service import (
    ListingDomainError,
    ServiceListingService,
)

provider_listings_router = APIRouter(
    prefix="/provider/service-listings",
    tags=["provider-service-listings"],
)
public_listings_router = APIRouter(
    prefix="/service-listings",
    tags=["service-listings"],
)


def _http_for_listing_error(exc: ListingDomainError) -> HTTPException:
    code = exc.code
    if code == "listing_not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif code == "category_not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif code == "listing_forbidden":
        status_code = status.HTTP_403_FORBIDDEN
    elif code == "invalid_listing_transition":
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


def _service(db: DbSession) -> ServiceListingService:
    return ServiceListingService(db)


def _search_params(
    q: str | None = Query(default=None, max_length=200),
    category_id: UUID | None = None,
    city: str | None = Query(default=None, max_length=100),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    min_listing_rating: float | None = Query(default=None, ge=0, le=5),
    min_provider_rating: float | None = Query(default=None, ge=0, le=5),
    is_featured: bool | None = None,
    sort: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ServiceListingSearchParams:
    """Build validated search params from query string."""
    from decimal import Decimal

    from app.service_listings.repositories.service_listing_repository import ListingSort

    try:
        sort_enum = ListingSort(sort)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid sort. Use newest|oldest|price_asc|price_desc|"
                "rating_desc|bookings_desc"
            ),
        ) from exc

    try:
        return ServiceListingSearchParams(
            q=q,
            category_id=category_id,
            city=city,
            min_price=min_price,
            max_price=max_price,
            min_listing_rating=(
                Decimal(str(min_listing_rating))
                if min_listing_rating is not None
                else None
            ),
            min_provider_rating=(
                Decimal(str(min_provider_rating))
                if min_provider_rating is not None
                else None
            ),
            is_featured=is_featured,
            sort=sort_enum,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Provider routes
# ---------------------------------------------------------------------------


@provider_listings_router.post(
    "",
    response_model=ServiceListingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a service listing (draft)",
)
def create_listing(
    payload: ServiceListingCreate,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingRead:
    try:
        return _service(db).create_listing(current_user, payload)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_listings_router.get(
    "",
    response_model=ServiceListingProviderListResponse,
    summary="List my service listings",
)
def list_my_listings(
    db: DbSession,
    current_user: CurrentProvider,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: ListingStatus | None = Query(default=None, alias="status"),
) -> ServiceListingProviderListResponse:
    try:
        return _service(db).list_my_listings(
            current_user,
            page=page,
            page_size=page_size,
            status=status_filter,
        )
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_listings_router.get(
    "/{listing_id}",
    response_model=ServiceListingRead,
    summary="Get one of my service listings",
)
def get_my_listing(
    listing_id: UUID,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingRead:
    try:
        return _service(db).get_my_listing(current_user, listing_id)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_listings_router.patch(
    "/{listing_id}",
    response_model=ServiceListingRead,
    summary="Update my service listing",
)
def update_listing(
    listing_id: UUID,
    payload: ServiceListingUpdate,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingRead:
    try:
        return _service(db).update_listing(current_user, listing_id, payload)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_listings_router.post(
    "/{listing_id}/publish",
    response_model=ServiceListingRead,
    summary="Publish listing (draft/inactive → active)",
)
def publish_listing(
    listing_id: UUID,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingRead:
    try:
        return _service(db).publish_listing(current_user, listing_id)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_listings_router.post(
    "/{listing_id}/deactivate",
    response_model=ServiceListingRead,
    summary="Deactivate listing (active → inactive)",
)
def deactivate_listing(
    listing_id: UUID,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingRead:
    try:
        return _service(db).deactivate_listing(current_user, listing_id)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_listings_router.delete(
    "/{listing_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete my service listing",
)
def delete_listing(
    listing_id: UUID,
    db: DbSession,
    current_user: CurrentProvider,
) -> Response:
    try:
        _service(db).soft_delete_listing(current_user, listing_id)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------


@public_listings_router.get(
    "",
    response_model=ServiceListingPublicListResponse,
    summary="Browse service listings (filters + sort + pagination)",
)
def browse_listings(
    db: DbSession,
    params: ServiceListingSearchParams = Depends(_search_params),
) -> ServiceListingPublicListResponse:
    try:
        return _service(db).search_public(params)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@public_listings_router.get(
    "/search",
    response_model=ServiceListingPublicListResponse,
    summary="Search service listings (same filters as list)",
)
def search_listings(
    db: DbSession,
    params: ServiceListingSearchParams = Depends(_search_params),
) -> ServiceListingPublicListResponse:
    """Alias of GET /service-listings for clients that prefer an explicit search path."""
    try:
        return _service(db).search_public(params)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@public_listings_router.get(
    "/{listing_id}",
    response_model=ServiceListingPublicRead,
    summary="Get a public (active) service listing",
)
def get_public_listing(
    listing_id: UUID,
    db: DbSession,
) -> ServiceListingPublicRead:
    try:
        return _service(db).get_public_listing(listing_id)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc
