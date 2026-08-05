"""
ProviderProfileRepository — SQL access for provider_profiles.

Layering (Clean Architecture / feature module):
  API → ProviderProfileService → this repository → Postgres

This class owns QUERIES and persistence only.
It must NOT decide who may verify a provider or create listings
(that is service-layer authorization + business rules).

Feature path: app/providers/repositories/
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.providers.models.provider_profile import (
    ProviderProfile,
    ProviderVerificationStatus,
)


class ProviderProfileRepository:
    """Thin data-access layer around ProviderProfile rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, profile_id: UUID) -> ProviderProfile | None:
        """Primary-key lookup (admin verify, listing ownership via profile id)."""
        return self._db.get(ProviderProfile, profile_id)

    def get_by_user_id(self, user_id: UUID) -> ProviderProfile | None:
        """
        Resolve the 1:1 profile for a logged-in provider user.

        Used by: get my profile, create listing (gate on can_create_listings).
        """
        statement = select(ProviderProfile).where(ProviderProfile.user_id == user_id)
        return self._db.scalar(statement)

    def count_by_verification_status(
        self,
        status: ProviderVerificationStatus,
    ) -> int:
        """Total rows for an admin queue (pagination meta)."""
        statement = (
            select(func.count())
            .select_from(ProviderProfile)
            .where(ProviderProfile.verification_status == status)
        )
        return int(self._db.scalar(statement) or 0)

    def list_by_verification_status(
        self,
        status: ProviderVerificationStatus,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ProviderProfile]:
        """
        Admin moderation queue (e.g. all PENDING profiles).

        Pagination is offset/limit for now; switch to keyset when the queue
        grows large (offset becomes expensive past tens of thousands).
        """
        statement = (
            select(ProviderProfile)
            .where(ProviderProfile.verification_status == status)
            .order_by(ProviderProfile.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement).all())

    def add(
        self,
        *,
        user_id: UUID,
        business_name: str,
        city: str,
        bio: str | None = None,
        verification_status: ProviderVerificationStatus = (
            ProviderVerificationStatus.PENDING
        ),
    ) -> ProviderProfile:
        """
        Insert a new profile row (not committed).

        Defaults to PENDING — callers must not pass VERIFIED from provider APIs.
        Service layer is responsible for rejecting mass-assignment of status.
        """
        profile = ProviderProfile(
            user_id=user_id,
            business_name=business_name,
            city=city,
            bio=bio,
            verification_status=verification_status,
        )
        self._db.add(profile)
        return profile

    def save(self, profile: ProviderProfile) -> ProviderProfile:
        """
        Persist in-memory field changes (verification, bio, counters, etc.).

        Does not commit — the service owns the transaction boundary.
        """
        self._db.add(profile)
        return profile
