"""
ListingStatus — lifecycle state of a marketplace ServiceListing.

Why this file exists (feature: service_listings):
  - Draft / Active / Inactive are business states, not UI labels.
  - API, ORM, Alembic, and services must share ONE vocabulary (DRY + type safety).
  - Keeping the enum in its own module avoids circular imports when
    ServiceListing, schemas, and repositories all need the same type.

Soft delete is NOT a status here:
  - status = marketplace visibility / editability
  - deleted_at = tombstone (separate column on ServiceListing)
  Mixing "deleted" into this enum makes queries and analytics harder.

Values are lowercase strings for stable JSON + Postgres ENUM storage
(same pattern as UserRole / OtpPurpose).
"""

from __future__ import annotations

import enum


class ListingStatus(str, enum.Enum):
    """
    Allowed states for service_listings.status.

    DRAFT:
      Provider is still editing. Never shown in public browse/search.
      Default on create (safer than publishing incomplete listings).

    ACTIVE:
      Publicly discoverable and bookable (subject to provider verification
      and listing soft-delete checks enforced in the service layer).

    INACTIVE:
      Provider paused the listing (vacation, price rethink, etc.).
      Hidden from public feed; owner can still see and reactivate.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"

    def is_publicly_visible(self) -> bool:
        """
        Single source of truth for "can anonymous users see this status?"

        Beginner mistake: scattering `status == 'active'` string checks
        across repositories and routes — easy to miss one path.
        """
        return self is ListingStatus.ACTIVE
