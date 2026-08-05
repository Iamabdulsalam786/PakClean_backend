"""
Listing image HTTP endpoints — provider gallery management + public read.

Routes:
  Provider:
    POST   /provider/service-listings/{listing_id}/images
    GET    /provider/service-listings/{listing_id}/images
    PUT    /provider/service-listings/{listing_id}/images/reorder
    PATCH  /provider/service-listings/{listing_id}/images/{image_id}
    POST   /provider/service-listings/{listing_id}/images/{image_id}/primary
    DELETE /provider/service-listings/{listing_id}/images/{image_id}

  Public:
    GET    /service-listings/{listing_id}/images
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.core.dependencies import CurrentProvider, DbSession
from app.service_listings.schemas.service_listing_image import (
    ServiceListingImageCreate,
    ServiceListingImageListResponse,
    ServiceListingImageRead,
    ServiceListingImageReorderRequest,
    ServiceListingImageUpdate,
)
from app.service_listings.services.listing_image_service import ListingImageService
from app.service_listings.services.service_listing_service import ListingDomainError

provider_images_router = APIRouter(
    prefix="/provider/service-listings/{listing_id}/images",
    tags=["provider-listing-images"],
)
public_images_router = APIRouter(
    prefix="/service-listings/{listing_id}/images",
    tags=["service-listing-images"],
)


def _http_for_listing_error(exc: ListingDomainError) -> HTTPException:
    code = exc.code
    if code in {"listing_not_found", "listing_image_not_found", "category_not_found"}:
        status_code = status.HTTP_404_NOT_FOUND
    elif code == "listing_forbidden":
        status_code = status.HTTP_403_FORBIDDEN
    elif code in {
        "invalid_listing_transition",
        "listing_image_limit",
        "listing_image_conflict",
    }:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


def _service(db: DbSession) -> ListingImageService:
    return ListingImageService(db)


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


@provider_images_router.post(
    "",
    response_model=ServiceListingImageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an image URL on my listing",
)
def add_image(
    listing_id: UUID,
    payload: ServiceListingImageCreate,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingImageRead:
    try:
        return _service(db).add_image(current_user, listing_id, payload)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_images_router.get(
    "",
    response_model=ServiceListingImageListResponse,
    summary="List images for my listing",
)
def list_my_images(
    listing_id: UUID,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingImageListResponse:
    try:
        return _service(db).list_for_owner(current_user, listing_id)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_images_router.put(
    "/reorder",
    response_model=ServiceListingImageListResponse,
    summary="Reorder images on my listing",
)
def reorder_images(
    listing_id: UUID,
    payload: ServiceListingImageReorderRequest,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingImageListResponse:
    try:
        return _service(db).reorder(current_user, listing_id, payload)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_images_router.patch(
    "/{image_id}",
    response_model=ServiceListingImageRead,
    summary="Update image alt/sort/primary",
)
def update_image(
    listing_id: UUID,
    image_id: UUID,
    payload: ServiceListingImageUpdate,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingImageRead:
    try:
        return _service(db).update_image(current_user, listing_id, image_id, payload)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_images_router.post(
    "/{image_id}/primary",
    response_model=ServiceListingImageRead,
    summary="Set image as primary",
)
def set_primary_image(
    listing_id: UUID,
    image_id: UUID,
    db: DbSession,
    current_user: CurrentProvider,
) -> ServiceListingImageRead:
    try:
        return _service(db).set_primary(current_user, listing_id, image_id)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc


@provider_images_router.delete(
    "/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an image from my listing",
)
def delete_image(
    listing_id: UUID,
    image_id: UUID,
    db: DbSession,
    current_user: CurrentProvider,
) -> Response:
    try:
        _service(db).delete_image(current_user, listing_id, image_id)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


@public_images_router.get(
    "",
    response_model=ServiceListingImageListResponse,
    summary="List images for a public (active) listing",
)
def list_public_images(
    listing_id: UUID,
    db: DbSession,
) -> ServiceListingImageListResponse:
    try:
        return _service(db).list_public(listing_id)
    except ListingDomainError as exc:
        raise _http_for_listing_error(exc) from exc
