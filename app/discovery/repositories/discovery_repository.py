"""
DiscoveryRepository — read-optimized marketplace queries.

Why a dedicated repository (vs ServiceListingRepository.search_public):
  - Customer discovery needs richer search (title + description + provider name)
  - Availability-day filter (EXISTS on schedule slots)
  - Explicit eager-loading strategy safe with LIMIT/OFFSET (selectinload, not joinedload)
  - Keeps provider write SQL separate from public read SQL (SRP)

Visibility (ALWAYS applied):
  status == ACTIVE AND deleted_at IS NULL

Feature path: app/discovery/repositories/
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.discovery.schemas.discovery import DiscoverySearchParams, DiscoverySort
from app.providers.models.provider_profile import ProviderProfile
from app.service_listings.models.availability import ServiceListingAvailability
from app.service_listings.models.listing_status import ListingStatus
from app.service_listings.models.service_listing import ServiceListing


class DiscoveryRepository:
    """Public read model over service_listings + related tables."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Feed / search
    # ------------------------------------------------------------------

    def search(self, params: DiscoverySearchParams) -> list[ServiceListing]:
        """
        Paginated ACTIVE listings matching filters/sort.

        Uses selectinload for provider/category/images so LIMIT/OFFSET apply to
        listings — not to a joined cartesian product (joinedload + limit footgun).
        """
        statement = self._base_filtered_select(params)
        statement = statement.options(
            selectinload(ServiceListing.provider),
            selectinload(ServiceListing.category),
            selectinload(ServiceListing.images),
        )
        statement = self._apply_sort(statement, params.sort)
        statement = statement.limit(params.page_size).offset(params.offset)
        return list(self._db.scalars(statement).unique().all())

    def count(self, params: DiscoverySearchParams) -> int:
        """Same filters as search — for total / total_pages."""
        statement = self._base_filtered_select(params)
        count_statement = select(func.count()).select_from(statement.subquery())
        return int(self._db.scalar(count_statement) or 0)

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------

    def get_active_by_id(self, listing_id: UUID) -> ServiceListing | None:
        """
        Single ACTIVE listing with provider, category, images eager-loaded.

        Returns None for missing, draft, paused, or soft-deleted rows
        (callers map that to 404 — no existence leak of non-public rows).
        """
        statement = (
            select(ServiceListing)
            .where(
                ServiceListing.id == listing_id,
                ServiceListing.status == ListingStatus.ACTIVE,
                ServiceListing.deleted_at.is_(None),
            )
            .options(
                selectinload(ServiceListing.provider),
                selectinload(ServiceListing.category),
                selectinload(ServiceListing.images),
            )
        )
        return self._db.scalars(statement).unique().first()

    def list_active_availability(
        self,
        listing_id: UUID,
    ) -> list[ServiceListingAvailability]:
        """
        Active schedule slots for a listing detail page.

        Separate query keeps ServiceListing model free of a required
        availability relationship for this slice (can add later).
        """
        statement = (
            select(ServiceListingAvailability)
            .where(
                ServiceListingAvailability.listing_id == listing_id,
                ServiceListingAvailability.is_active.is_(True),
            )
            .order_by(
                ServiceListingAvailability.day_of_week.asc(),
                ServiceListingAvailability.start_time.asc(),
            )
        )
        return list(self._db.scalars(statement).all())

    # ------------------------------------------------------------------
    # Query builders
    # ------------------------------------------------------------------

    def _base_filtered_select(
        self,
        params: DiscoverySearchParams,
    ) -> Select[tuple[ServiceListing]]:
        statement: Select[tuple[ServiceListing]] = select(ServiceListing).where(
            ServiceListing.status == ListingStatus.ACTIVE,
            ServiceListing.deleted_at.is_(None),
        )

        needs_provider_join = bool(params.q)
        if needs_provider_join:
            statement = statement.join(
                ProviderProfile,
                ProviderProfile.id == ServiceListing.provider_id,
            )

        if params.q:
            pattern = f"%{params.q}%"
            statement = statement.where(
                or_(
                    ServiceListing.title.ilike(pattern),
                    ServiceListing.description.ilike(pattern),
                    ProviderProfile.business_name.ilike(pattern),
                )
            )

        if params.category_id is not None:
            statement = statement.where(
                ServiceListing.category_id == params.category_id
            )

        if params.city:
            statement = statement.where(
                func.lower(ServiceListing.city) == params.city.lower()
            )

        if params.min_price is not None:
            statement = statement.where(ServiceListing.base_price >= params.min_price)

        if params.max_price is not None:
            statement = statement.where(ServiceListing.base_price <= params.max_price)

        if params.min_rating is not None:
            statement = statement.where(
                ServiceListing.average_rating >= params.min_rating
            )

        if params.is_featured is not None:
            statement = statement.where(
                ServiceListing.is_featured.is_(params.is_featured)
            )

        if params.available_on is not None:
            # EXISTS avoids row duplication from joining multiple slots.
            slot_exists = exists().where(
                ServiceListingAvailability.listing_id == ServiceListing.id,
                ServiceListingAvailability.day_of_week == params.available_on,
                ServiceListingAvailability.is_active.is_(True),
            )
            statement = statement.where(slot_exists)

        return statement

    @staticmethod
    def _apply_sort(
        statement: Select[tuple[ServiceListing]],
        sort: DiscoverySort,
    ) -> Select[tuple[ServiceListing]]:
        if sort is DiscoverySort.OLDEST:
            return statement.order_by(
                ServiceListing.created_at.asc(),
                ServiceListing.id.asc(),
            )
        if sort is DiscoverySort.PRICE_ASC:
            return statement.order_by(
                ServiceListing.base_price.asc(),
                ServiceListing.created_at.desc(),
            )
        if sort is DiscoverySort.PRICE_DESC:
            return statement.order_by(
                ServiceListing.base_price.desc(),
                ServiceListing.created_at.desc(),
            )
        if sort is DiscoverySort.RATING_DESC:
            return statement.order_by(
                ServiceListing.average_rating.desc(),
                ServiceListing.created_at.desc(),
            )
        if sort is DiscoverySort.MOST_BOOKED:
            return statement.order_by(
                ServiceListing.booking_count.desc(),
                ServiceListing.created_at.desc(),
            )
        # NEWEST — id tie-break keeps pages stable
        return statement.order_by(
            ServiceListing.created_at.desc(),
            ServiceListing.id.desc(),
        )
