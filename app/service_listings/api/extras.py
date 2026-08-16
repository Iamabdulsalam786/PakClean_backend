"""
HTTP endpoints for listing tags, availability, and discounts.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.core.dependencies import CurrentProvider, DbSession
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
from app.service_listings.services.listing_extras_service import ListingExtrasService
from app.service_listings.services.service_listing_service import ListingDomainError

provider_extras_router = APIRouter(
    prefix="/provider/service-listings/{listing_id}",
    tags=["provider-listing-extras"],
)
public_extras_router = APIRouter(
    prefix="/service-listings/{listing_id}",
    tags=["service-listing-extras"],
)
tags_catalog_router = APIRouter(prefix="/tags", tags=["tags"])


def _http(exc: ListingDomainError) -> HTTPException:
    code = exc.code
    if code.endswith("_not_found") or code == "listing_not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif code == "listing_forbidden":
        status_code = status.HTTP_403_FORBIDDEN
    elif code.endswith("_limit") or code.endswith("_conflict") or code.endswith("_invalid"):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


def _svc(db: DbSession) -> ListingExtrasService:
    return ListingExtrasService(db)


@tags_catalog_router.get("", response_model=TagListResponse, summary="List tag catalog")
def list_tags(db: DbSession) -> TagListResponse:
    return _svc(db).list_catalog_tags()


# ---- tags ----
@provider_extras_router.get("/tags", response_model=TagListResponse)
def list_my_tags(listing_id: UUID, db: DbSession, user: CurrentProvider) -> TagListResponse:
    try:
        return _svc(db).list_listing_tags_owner(user, listing_id)
    except ListingDomainError as exc:
        raise _http(exc) from exc


@provider_extras_router.post("/tags", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def attach_tag(
    listing_id: UUID,
    payload: TagAttachRequest,
    db: DbSession,
    user: CurrentProvider,
) -> TagRead:
    try:
        return _svc(db).attach_tag(user, listing_id, payload)
    except ListingDomainError as exc:
        raise _http(exc) from exc


@provider_extras_router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_tag(
    listing_id: UUID,
    tag_id: UUID,
    db: DbSession,
    user: CurrentProvider,
) -> Response:
    try:
        _svc(db).detach_tag(user, listing_id, tag_id)
    except ListingDomainError as exc:
        raise _http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_extras_router.get("/tags", response_model=TagListResponse)
def list_public_tags(listing_id: UUID, db: DbSession) -> TagListResponse:
    try:
        return _svc(db).list_listing_tags_public(listing_id)
    except ListingDomainError as exc:
        raise _http(exc) from exc


# ---- availability ----
@provider_extras_router.get("/availability", response_model=AvailabilityListResponse)
def list_my_availability(
    listing_id: UUID, db: DbSession, user: CurrentProvider
) -> AvailabilityListResponse:
    try:
        return _svc(db).list_availability_owner(user, listing_id)
    except ListingDomainError as exc:
        raise _http(exc) from exc


@provider_extras_router.post(
    "/availability",
    response_model=AvailabilityRead,
    status_code=status.HTTP_201_CREATED,
)
def add_availability(
    listing_id: UUID,
    payload: AvailabilityCreate,
    db: DbSession,
    user: CurrentProvider,
) -> AvailabilityRead:
    try:
        return _svc(db).add_availability(user, listing_id, payload)
    except ListingDomainError as exc:
        raise _http(exc) from exc


@provider_extras_router.patch("/availability/{slot_id}", response_model=AvailabilityRead)
def update_availability(
    listing_id: UUID,
    slot_id: UUID,
    payload: AvailabilityUpdate,
    db: DbSession,
    user: CurrentProvider,
) -> AvailabilityRead:
    try:
        return _svc(db).update_availability(user, listing_id, slot_id, payload)
    except ListingDomainError as exc:
        raise _http(exc) from exc


@provider_extras_router.delete("/availability/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_availability(
    listing_id: UUID,
    slot_id: UUID,
    db: DbSession,
    user: CurrentProvider,
) -> Response:
    try:
        _svc(db).delete_availability(user, listing_id, slot_id)
    except ListingDomainError as exc:
        raise _http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_extras_router.get("/availability", response_model=AvailabilityListResponse)
def list_public_availability(listing_id: UUID, db: DbSession) -> AvailabilityListResponse:
    try:
        return _svc(db).list_availability_public(listing_id)
    except ListingDomainError as exc:
        raise _http(exc) from exc


# ---- discounts ----
@provider_extras_router.get("/discounts", response_model=DiscountListResponse)
def list_my_discounts(
    listing_id: UUID, db: DbSession, user: CurrentProvider
) -> DiscountListResponse:
    try:
        return _svc(db).list_discounts_owner(user, listing_id)
    except ListingDomainError as exc:
        raise _http(exc) from exc


@provider_extras_router.post(
    "/discounts",
    response_model=DiscountRead,
    status_code=status.HTTP_201_CREATED,
)
def add_discount(
    listing_id: UUID,
    payload: DiscountCreate,
    db: DbSession,
    user: CurrentProvider,
) -> DiscountRead:
    try:
        return _svc(db).add_discount(user, listing_id, payload)
    except ListingDomainError as exc:
        raise _http(exc) from exc


@provider_extras_router.patch("/discounts/{discount_id}", response_model=DiscountRead)
def update_discount(
    listing_id: UUID,
    discount_id: UUID,
    payload: DiscountUpdate,
    db: DbSession,
    user: CurrentProvider,
) -> DiscountRead:
    try:
        return _svc(db).update_discount(user, listing_id, discount_id, payload)
    except ListingDomainError as exc:
        raise _http(exc) from exc


@provider_extras_router.delete("/discounts/{discount_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discount(
    listing_id: UUID,
    discount_id: UUID,
    db: DbSession,
    user: CurrentProvider,
) -> Response:
    try:
        _svc(db).delete_discount(user, listing_id, discount_id)
    except ListingDomainError as exc:
        raise _http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_extras_router.get("/discounts", response_model=DiscountListResponse)
def list_public_discounts(listing_id: UUID, db: DbSession) -> DiscountListResponse:
    try:
        return _svc(db).list_discounts_public(listing_id)
    except ListingDomainError as exc:
        raise _http(exc) from exc
