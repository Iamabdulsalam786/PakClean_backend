"""
ServiceListingRepository — SQL access for service_listings.

Layering:
  API → ServiceListingService → this repository → Postgres

Owns queries/persistence only — not ownership checks or "verified provider" gates.

Public browse always filters: status=ACTIVE AND deleted_at IS NULL.
Provider "mine" lists exclude soft-deleted by default.

Feature path: app/service_listings/repositories/
"""

from __future__ import annotations

import enum
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.providers.models.provider_profile import ProviderProfile
from app.service_listings.models.listing_status import ListingStatus
from app.service_listings.models.service_listing import ServiceListing


class ListingSort(str, enum.Enum):
    """Stable sort keys for public/provider listing feeds."""

    NEWEST = "newest"
    OLDEST = "oldest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    RATING_DESC = "rating_desc"
    BOOKINGS_DESC = "bookings_desc"


class ServiceListingRepository:
    """Thin data-access layer around ServiceListing rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Basic CRUD primitives
    # ------------------------------------------------------------------

    def get_by_id(self, listing_id: UUID) -> ServiceListing | None:
        """Load by PK (service still decides public vs owner visibility)."""
        return self._db.get(ServiceListing, listing_id)

    def add(
        self,
        *,
        provider_id: UUID,
        category_id: UUID,
        title: str,
        description: str,
        base_price: int,
        estimated_duration: int,
        city: str,
        address: str,
        service_radius_km: Decimal = Decimal("5.00"),
        latitude: float | None = None,
        longitude: float | None = None,
        status: ListingStatus = ListingStatus.DRAFT,
        is_featured: bool = False,
    ) -> ServiceListing:
        """
        Insert a listing row (not committed).

        Defaults to DRAFT + not featured. Service must force these for
        provider-created rows (prevent mass assignment of ACTIVE/featured).
        """
        row = ServiceListing(
            provider_id=provider_id,
            category_id=category_id,
            title=title,
            description=description,
            base_price=base_price,
            estimated_duration=estimated_duration,
            city=city,
            address=address,
            service_radius_km=service_radius_km,
            latitude=latitude,
            longitude=longitude,
            status=status,
            is_featured=is_featured,
        )
        self._db.add(row)
        return row

    def save(self, listing: ServiceListing) -> ServiceListing:
        """Persist in-memory changes (no commit)."""
        self._db.add(listing)
        return listing

    # ------------------------------------------------------------------
    # Provider dashboard
    # ------------------------------------------------------------------

    def list_for_provider(
        self,
        provider_id: UUID,
        *,
        include_deleted: bool = False,
        status: ListingStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ServiceListing]:
        """Listings owned by one provider profile (newest first)."""
        statement = select(ServiceListing).where(
            ServiceListing.provider_id == provider_id
        )
        if not include_deleted:
            statement = statement.where(ServiceListing.deleted_at.is_(None))
        if status is not None:
            statement = statement.where(ServiceListing.status == status)

        statement = (
            statement.order_by(ServiceListing.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement).all())

    def count_for_provider(
        self,
        provider_id: UUID,
        *,
        include_deleted: bool = False,
        status: ListingStatus | None = None,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(ServiceListing)
            .where(ServiceListing.provider_id == provider_id)
        )
        if not include_deleted:
            statement = statement.where(ServiceListing.deleted_at.is_(None))
        if status is not None:
            statement = statement.where(ServiceListing.status == status)
        return int(self._db.scalar(statement) or 0)

    # ------------------------------------------------------------------
    # Public browse / search
    # ------------------------------------------------------------------

    def search_public(
        self,
        *,
        q: str | None = None,
        category_id: UUID | None = None,
        city: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        min_listing_rating: Decimal | None = None,
        min_provider_rating: Decimal | None = None,
        is_featured: bool | None = None,
        sort: ListingSort = ListingSort.NEWEST,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ServiceListing]:
        """
        Customer/anonymous discovery query.

        Always scoped to ACTIVE + not soft-deleted.
        Availability-day filter waits until service_listing_availability exists.
        """
        statement = self._public_base_select(
            q=q,
            category_id=category_id,
            city=city,
            min_price=min_price,
            max_price=max_price,
            min_listing_rating=min_listing_rating,
            min_provider_rating=min_provider_rating,
            is_featured=is_featured,
        )
        statement = self._apply_sort(statement, sort)
        statement = statement.limit(limit).offset(offset)
        return list(self._db.scalars(statement).unique().all())

    def count_public(
        self,
        *,
        q: str | None = None,
        category_id: UUID | None = None,
        city: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        min_listing_rating: Decimal | None = None,
        min_provider_rating: Decimal | None = None,
        is_featured: bool | None = None,
    ) -> int:
        """Total matches for public pagination meta."""
        statement = self._public_base_select(
            q=q,
            category_id=category_id,
            city=city,
            min_price=min_price,
            max_price=max_price,
            min_listing_rating=min_listing_rating,
            min_provider_rating=min_provider_rating,
            is_featured=is_featured,
        )
        count_statement = select(func.count()).select_from(statement.subquery())
        return int(self._db.scalar(count_statement) or 0)

    # ------------------------------------------------------------------
    # Query builders
    # ------------------------------------------------------------------

    def _public_base_select(
        self,
        *,
        q: str | None,
        category_id: UUID | None,
        city: str | None,
        min_price: int | None,
        max_price: int | None,
        min_listing_rating: Decimal | None,
        min_provider_rating: Decimal | None,
        is_featured: bool | None,
    ) -> Select[tuple[ServiceListing]]:
        statement: Select[tuple[ServiceListing]] = select(ServiceListing).where(
            ServiceListing.status == ListingStatus.ACTIVE,
            ServiceListing.deleted_at.is_(None),
        )

        # Join provider only when filtering on provider rating (avoid needless join).
        if min_provider_rating is not None:
            statement = statement.join(
                ProviderProfile,
                ProviderProfile.id == ServiceListing.provider_id,
            ).where(ProviderProfile.average_rating >= min_provider_rating)

        if q:
            # Case-insensitive substring match. At millions of rows, replace with
            # pg_trgm GIN or a search engine (Meilisearch/Elasticsearch).
            pattern = f"%{q.strip()}%"
            statement = statement.where(ServiceListing.title.ilike(pattern))

        if category_id is not None:
            statement = statement.where(ServiceListing.category_id == category_id)

        if city:
            statement = statement.where(
                func.lower(ServiceListing.city) == city.strip().lower()
            )

        if min_price is not None:
            statement = statement.where(ServiceListing.base_price >= min_price)

        if max_price is not None:
            statement = statement.where(ServiceListing.base_price <= max_price)

        if min_listing_rating is not None:
            statement = statement.where(
                ServiceListing.average_rating >= min_listing_rating
            )

        if is_featured is not None:
            statement = statement.where(ServiceListing.is_featured.is_(is_featured))

        return statement

    @staticmethod
    def _apply_sort(
        statement: Select[tuple[ServiceListing]],
        sort: ListingSort,
    ) -> Select[tuple[ServiceListing]]:
        if sort is ListingSort.OLDEST:
            return statement.order_by(ServiceListing.created_at.asc())
        if sort is ListingSort.PRICE_ASC:
            return statement.order_by(
                ServiceListing.base_price.asc(),
                ServiceListing.created_at.desc(),
            )
        if sort is ListingSort.PRICE_DESC:
            return statement.order_by(
                ServiceListing.base_price.desc(),
                ServiceListing.created_at.desc(),
            )
        if sort is ListingSort.RATING_DESC:
            return statement.order_by(
                ServiceListing.average_rating.desc(),
                ServiceListing.created_at.desc(),
            )
        if sort is ListingSort.BOOKINGS_DESC:
            return statement.order_by(
                ServiceListing.booking_count.desc(),
                ServiceListing.created_at.desc(),
            )
        # NEWEST (default) — tie-break with id for stable pagination
        return statement.order_by(
            ServiceListing.created_at.desc(),
            ServiceListing.id.desc(),
        )
