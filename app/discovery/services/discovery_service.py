"""
DiscoveryService — marketplace browse / search / detail use-cases.

Layering:
  API → this service → DiscoveryRepository
  Does not import FastAPI.

Responsibilities:
  - Call repository with validated DiscoverySearchParams
  - Map ORM graphs → ListingCard / ListingDetail (never leak owner fields)
  - Truncate card description teasers for mobile feeds
  - Pick primary image (fallback: first by sort_order)
  - Build paginated envelope with total_pages

Visibility rules live in the repository; this layer trusts ACTIVE-only rows
but still double-checks is_publicly_visible() on detail as defense in depth.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.discovery.repositories.discovery_repository import DiscoveryRepository
from app.discovery.schemas.discovery import (
    DiscoveryAvailabilityBrief,
    DiscoveryCategoryBrief,
    DiscoveryImageBrief,
    DiscoveryListResponse,
    DiscoveryProviderBrief,
    DiscoverySearchParams,
    ListingCard,
    ListingDetail,
)
from app.service_listings.models.service_listing import ServiceListing
from app.service_listings.models.service_listing_image import ServiceListingImage

logger = logging.getLogger(__name__)

# Card teaser length — keeps feed payloads small on slow mobile networks.
_CARD_DESCRIPTION_MAX = 180


class DiscoveryNotFoundError(Exception):
    """Public listing missing or not visible — API maps to HTTP 404."""

    def __init__(self, message: str = "Listing not found") -> None:
        self.message = message
        self.code = "listing_not_found"
        super().__init__(message)


class DiscoveryService:
    """Application service for customer marketplace discovery."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = DiscoveryRepository(db)

    def browse(self, params: DiscoverySearchParams) -> DiscoveryListResponse:
        """
        Browse / filter / sort feed (also used by /search — same engine).

        Logging uses filter summary only — never log raw PII-heavy queries at scale
        without sampling; q is truncated in logs.
        """
        total = self._repo.count(params)
        rows = self._repo.search(params)
        cards = [self._to_card(row) for row in rows]

        logger.info(
            "discovery_browse page=%s page_size=%s total=%s sort=%s city=%s q=%s",
            params.page,
            params.page_size,
            total,
            params.sort.value,
            params.city,
            (params.q[:40] + "…") if params.q and len(params.q) > 40 else params.q,
        )

        return DiscoveryListResponse.build(
            items=cards,
            page=params.page,
            page_size=params.page_size,
            total=total,
        )

    def get_detail(self, listing_id: UUID) -> ListingDetail:
        """Rich public detail aggregate for the listing page."""
        listing = self._repo.get_active_by_id(listing_id)
        if listing is None or not listing.is_publicly_visible():
            raise DiscoveryNotFoundError()

        slots = self._repo.list_active_availability(listing_id)
        detail = self._to_detail(listing, slots)
        logger.info("discovery_detail listing_id=%s", listing_id)
        return detail

    # ------------------------------------------------------------------
    # Mappers
    # ------------------------------------------------------------------

    def _to_card(self, listing: ServiceListing) -> ListingCard:
        return ListingCard(
            id=listing.id,
            title=listing.title,
            description=self._teaser(listing.description),
            base_price=listing.base_price,
            estimated_duration=listing.estimated_duration,
            city=listing.city,
            is_featured=listing.is_featured,
            average_rating=listing.average_rating,
            booking_count=listing.booking_count,
            created_at=listing.created_at,
            category=DiscoveryCategoryBrief.model_validate(listing.category),
            provider=DiscoveryProviderBrief.model_validate(listing.provider),
            primary_image=self._primary_image(list(listing.images or [])),
        )

    def _to_detail(
        self,
        listing: ServiceListing,
        slots: list,
    ) -> ListingDetail:
        images = sorted(
            list(listing.images or []),
            key=lambda img: (img.sort_order, str(img.id)),
        )
        return ListingDetail(
            id=listing.id,
            title=listing.title,
            description=listing.description,
            base_price=listing.base_price,
            estimated_duration=listing.estimated_duration,
            city=listing.city,
            address=listing.address,
            latitude=listing.latitude,
            longitude=listing.longitude,
            service_radius_km=listing.service_radius_km,
            is_featured=listing.is_featured,
            average_rating=listing.average_rating,
            booking_count=listing.booking_count,
            created_at=listing.created_at,
            category=DiscoveryCategoryBrief.model_validate(listing.category),
            provider=DiscoveryProviderBrief.model_validate(listing.provider),
            images=[DiscoveryImageBrief.model_validate(img) for img in images],
            availability=[
                DiscoveryAvailabilityBrief.model_validate(slot) for slot in slots
            ],
        )

    @staticmethod
    def _teaser(description: str) -> str:
        text = description.strip()
        if len(text) <= _CARD_DESCRIPTION_MAX:
            return text
        return text[: _CARD_DESCRIPTION_MAX - 1].rstrip() + "…"

    @staticmethod
    def _primary_image(
        images: list[ServiceListingImage],
    ) -> DiscoveryImageBrief | None:
        if not images:
            return None
        for img in images:
            if img.is_primary:
                return DiscoveryImageBrief.model_validate(img)
        ordered = sorted(images, key=lambda img: (img.sort_order, str(img.id)))
        return DiscoveryImageBrief.model_validate(ordered[0])
