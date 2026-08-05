"""
ServiceListingService — provider CRUD + publish/deactivate + public search.

Layering:
  API → this service → ServiceListingRepository + ProviderProfileService
  Does not import FastAPI.

Business rules:
  - Only verified+active provider profiles may create listings
  - Providers mutate only their own listings (ownership)
  - Create always starts as DRAFT (never ACTIVE from client)
  - Publish: DRAFT|INACTIVE → ACTIVE
  - Deactivate: ACTIVE → INACTIVE
  - Soft delete sets deleted_at (no hard delete)
  - Public get/search: ACTIVE + not deleted only
  - Customers never write listings

Feature path: app/service_listings/services/
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.user import User
from app.providers.repositories.provider_profile_repository import (
    ProviderProfileRepository,
)
from app.providers.services.provider_profile_service import (
    ProviderDomainError,
    ProviderNotVerifiedError,
    ProviderProfileNotFoundError,
    ProviderProfileService,
)
from app.service_listings.models.listing_status import ListingStatus
from app.service_listings.models.service_listing import ServiceListing
from app.service_listings.repositories.service_listing_repository import (
    ServiceListingRepository,
)
from app.service_listings.schemas.service_listing import (
    ServiceListingCreate,
    ServiceListingProviderListResponse,
    ServiceListingPublicListResponse,
    ServiceListingPublicRead,
    ServiceListingRead,
    ServiceListingSearchParams,
    ServiceListingUpdate,
)

logger = logging.getLogger(__name__)


class ListingDomainError(Exception):
    """Base listing-feature error with a stable machine code."""

    def __init__(self, message: str, *, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class ListingNotFoundError(ListingDomainError):
    def __init__(self) -> None:
        super().__init__("Service listing not found", code="listing_not_found")


class ListingForbiddenError(ListingDomainError):
    def __init__(self, message: str = "Not allowed to modify this listing") -> None:
        super().__init__(message, code="listing_forbidden")


class CategoryNotFoundError(ListingDomainError):
    def __init__(self) -> None:
        super().__init__("Category not found or inactive", code="category_not_found")


class InvalidListingTransitionError(ListingDomainError):
    def __init__(self, message: str = "Invalid listing status transition") -> None:
        super().__init__(message, code="invalid_listing_transition")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ServiceListingService:
    """Application service for marketplace service listings."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._listings = ServiceListingRepository(db)
        self._providers = ProviderProfileService(db)
        self._profiles = ProviderProfileRepository(db)

    # ------------------------------------------------------------------
    # Provider write paths
    # ------------------------------------------------------------------

    def create_listing(
        self,
        actor: User,
        data: ServiceListingCreate,
    ) -> ServiceListingRead:
        """Create a DRAFT listing for a verified provider."""
        profile = self._require_verified_profile(actor)
        self._assert_category_active(data.category_id)

        listing = self._listings.add(
            provider_id=profile.id,
            category_id=data.category_id,
            title=data.title,
            description=data.description,
            base_price=data.base_price,
            estimated_duration=data.estimated_duration,
            city=data.city,
            address=data.address,
            service_radius_km=data.service_radius_km,
            latitude=data.latitude,
            longitude=data.longitude,
            status=ListingStatus.DRAFT,
            is_featured=False,
        )
        self._db.commit()
        self._db.refresh(listing)

        logger.info(
            "listing_created listing_id=%s provider_id=%s city=%s",
            listing.id,
            profile.id,
            listing.city,
        )
        return ServiceListingRead.model_validate(listing)

    def list_my_listings(
        self,
        actor: User,
        *,
        page: int = 1,
        page_size: int = 20,
        status: ListingStatus | None = None,
    ) -> ServiceListingProviderListResponse:
        profile = self._require_provider_profile(actor)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        offset = (page - 1) * page_size

        total = self._listings.count_for_provider(
            profile.id,
            status=status,
        )
        rows = self._listings.list_for_provider(
            profile.id,
            status=status,
            limit=page_size,
            offset=offset,
        )
        return ServiceListingProviderListResponse(
            items=[ServiceListingRead.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_my_listing(self, actor: User, listing_id: UUID) -> ServiceListingRead:
        listing = self._get_owned_listing(actor, listing_id)
        return ServiceListingRead.model_validate(listing)

    def update_listing(
        self,
        actor: User,
        listing_id: UUID,
        data: ServiceListingUpdate,
    ) -> ServiceListingRead:
        listing = self._get_owned_listing(actor, listing_id)

        if data.category_id is not None:
            self._assert_category_active(data.category_id)
            listing.category_id = data.category_id
        if data.title is not None:
            listing.title = data.title
        if data.description is not None:
            listing.description = data.description
        if data.base_price is not None:
            listing.base_price = data.base_price
        if data.estimated_duration is not None:
            listing.estimated_duration = data.estimated_duration
        if data.city is not None:
            listing.city = data.city
        if data.address is not None:
            listing.address = data.address
        if data.service_radius_km is not None:
            listing.service_radius_km = data.service_radius_km
        if data.latitude is not None:
            listing.latitude = data.latitude
        if data.longitude is not None:
            listing.longitude = data.longitude

        self._listings.save(listing)
        self._db.commit()
        self._db.refresh(listing)
        return ServiceListingRead.model_validate(listing)

    def publish_listing(self, actor: User, listing_id: UUID) -> ServiceListingRead:
        """DRAFT or INACTIVE → ACTIVE. Provider must still be verified."""
        self._require_verified_profile(actor)
        listing = self._get_owned_listing(actor, listing_id)

        if listing.status not in {ListingStatus.DRAFT, ListingStatus.INACTIVE}:
            raise InvalidListingTransitionError(
                "Only draft or inactive listings can be published"
            )

        listing.status = ListingStatus.ACTIVE
        self._listings.save(listing)
        self._db.commit()
        self._db.refresh(listing)

        logger.info("listing_published listing_id=%s", listing.id)
        return ServiceListingRead.model_validate(listing)

    def deactivate_listing(self, actor: User, listing_id: UUID) -> ServiceListingRead:
        """ACTIVE → INACTIVE."""
        listing = self._get_owned_listing(actor, listing_id)

        if listing.status is not ListingStatus.ACTIVE:
            raise InvalidListingTransitionError("Only active listings can be deactivated")

        listing.status = ListingStatus.INACTIVE
        self._listings.save(listing)
        self._db.commit()
        self._db.refresh(listing)

        logger.info("listing_deactivated listing_id=%s", listing.id)
        return ServiceListingRead.model_validate(listing)

    def soft_delete_listing(self, actor: User, listing_id: UUID) -> None:
        """Soft delete — hidden from public and provider default lists."""
        listing = self._get_owned_listing(actor, listing_id)
        listing.soft_delete(when=_utcnow())
        # Also park status so accidental publish of tombstoned rows is harder
        if listing.status is ListingStatus.ACTIVE:
            listing.status = ListingStatus.INACTIVE

        self._listings.save(listing)
        self._db.commit()
        logger.info("listing_soft_deleted listing_id=%s", listing.id)

    # ------------------------------------------------------------------
    # Public read paths
    # ------------------------------------------------------------------

    def get_public_listing(self, listing_id: UUID) -> ServiceListingPublicRead:
        listing = self._listings.get_by_id(listing_id)
        if listing is None or not listing.is_publicly_visible():
            raise ListingNotFoundError()
        return ServiceListingPublicRead.model_validate(listing)

    def search_public(
        self,
        params: ServiceListingSearchParams,
    ) -> ServiceListingPublicListResponse:
        total = self._listings.count_public(
            q=params.q,
            category_id=params.category_id,
            city=params.city,
            min_price=params.min_price,
            max_price=params.max_price,
            min_listing_rating=params.min_listing_rating,
            min_provider_rating=params.min_provider_rating,
            is_featured=params.is_featured,
        )
        rows = self._listings.search_public(
            q=params.q,
            category_id=params.category_id,
            city=params.city,
            min_price=params.min_price,
            max_price=params.max_price,
            min_listing_rating=params.min_listing_rating,
            min_provider_rating=params.min_provider_rating,
            is_featured=params.is_featured,
            sort=params.sort,
            limit=params.page_size,
            offset=params.offset,
        )
        return ServiceListingPublicListResponse(
            items=[ServiceListingPublicRead.model_validate(row) for row in rows],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    # ------------------------------------------------------------------
    # Guards / helpers
    # ------------------------------------------------------------------

    def _require_verified_profile(self, actor: User):
        try:
            return self._providers.require_verified_profile(actor)
        except ProviderProfileNotFoundError as exc:
            raise ListingForbiddenError(
                "Create and verify a provider profile before managing listings"
            ) from exc
        except ProviderNotVerifiedError as exc:
            raise ListingForbiddenError(
                "Provider must be verified before managing listings"
            ) from exc
        except ProviderDomainError as exc:
            raise ListingForbiddenError(exc.message) from exc

    def _require_provider_profile(self, actor: User):
        """
        Load the actor's provider profile for ownership checks.

        Verification is NOT required here so a pending provider can open an
        empty dashboard. create/publish still call _require_verified_profile.
        """
        try:
            # Reuse role + email-verified guards from provider service
            self._providers.get_my_profile(actor)
        except ProviderProfileNotFoundError as exc:
            raise ListingForbiddenError(
                "Create a provider profile before managing listings"
            ) from exc
        except ProviderDomainError as exc:
            # not_a_provider / email_not_verified / inactive
            raise ListingForbiddenError(exc.message) from exc

        profile = self._profiles.get_by_user_id(actor.id)
        if profile is None:
            raise ListingForbiddenError(
                "Create a provider profile before managing listings"
            )
        return profile

    def _get_owned_listing(self, actor: User, listing_id: UUID) -> ServiceListing:
        profile = self._require_provider_profile(actor)
        listing = self._listings.get_by_id(listing_id)
        if listing is None or listing.deleted_at is not None:
            raise ListingNotFoundError()
        if listing.provider_id != profile.id:
            # Do not leak existence of other providers' listings
            raise ListingNotFoundError()
        return listing

    def _assert_category_active(self, category_id: UUID) -> None:
        category = self._db.get(Category, category_id)
        if category is None or not category.is_active:
            raise CategoryNotFoundError()
