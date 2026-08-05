"""
ProviderProfileService — create/update profile + admin verify/reject.

Layering:
  API route → this service → ProviderProfileRepository
  Does not import FastAPI.

Business rules owned here:
  - Only role=provider (email-verified) may create a profile
  - One profile per user (1:1)
  - Providers never set verification_status themselves
  - After REJECTED, profile update resets status to PENDING (re-apply)
  - Only VERIFIED + is_active may create listings (can_create_listings)
  - Admin verify/reject transitions with audit fields

Feature path: app/providers/services/
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.providers.models.provider_profile import (
    ProviderProfile,
    ProviderVerificationStatus,
)
from app.providers.repositories.provider_profile_repository import (
    ProviderProfileRepository,
)
from app.providers.schemas.provider_profile import (
    AdminProviderQueueResponse,
    AdminRejectProviderRequest,
    AdminVerifyProviderRequest,
    ProviderProfileCreate,
    ProviderProfileRead,
    ProviderProfileUpdate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain errors (HTTP mapping happens in the API layer)
# ---------------------------------------------------------------------------


class ProviderDomainError(Exception):
    """Base provider-feature error with a stable machine code."""

    def __init__(self, message: str, *, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class ProviderProfileNotFoundError(ProviderDomainError):
    def __init__(self) -> None:
        super().__init__("Provider profile not found", code="provider_profile_not_found")


class ProviderProfileExistsError(ProviderDomainError):
    def __init__(self) -> None:
        super().__init__(
            "Provider profile already exists for this user",
            code="provider_profile_exists",
        )


class NotAProviderError(ProviderDomainError):
    def __init__(self) -> None:
        super().__init__(
            "Only provider accounts can manage a provider profile",
            code="not_a_provider",
        )


class ProviderEmailNotVerifiedError(ProviderDomainError):
    def __init__(self) -> None:
        super().__init__(
            "Verify your email before creating a provider profile",
            code="email_not_verified",
        )


class InvalidVerificationTransitionError(ProviderDomainError):
    def __init__(self, message: str = "Invalid verification transition") -> None:
        super().__init__(message, code="invalid_verification_transition")


class ProviderNotVerifiedError(ProviderDomainError):
    """Raised when a listing (or similar) action requires a verified profile."""

    def __init__(self) -> None:
        super().__init__(
            "Provider must be verified before performing this action",
            code="provider_not_verified",
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProviderProfileService:
    """Application service for provider business profiles and verification."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._profiles = ProviderProfileRepository(db)

    # ------------------------------------------------------------------
    # Provider self-service
    # ------------------------------------------------------------------

    def create_profile(
        self,
        actor: User,
        data: ProviderProfileCreate,
    ) -> ProviderProfileRead:
        """
        Create a PENDING provider profile for the authenticated provider.

        verification_status is forced to PENDING — never taken from the client.
        """
        self._assert_provider_actor(actor)

        if self._profiles.get_by_user_id(actor.id) is not None:
            raise ProviderProfileExistsError()

        profile = self._profiles.add(
            user_id=actor.id,
            business_name=data.business_name,
            city=data.city,
            bio=data.bio,
            verification_status=ProviderVerificationStatus.PENDING,
        )
        self._db.commit()
        self._db.refresh(profile)

        logger.info(
            "provider_profile_created profile_id=%s city=%s",
            profile.id,
            profile.city,
        )
        return ProviderProfileRead.model_validate(profile)

    def get_my_profile(self, actor: User) -> ProviderProfileRead:
        """Return the caller's profile or 404-equivalent domain error."""
        self._assert_provider_actor(actor)
        profile = self._profiles.get_by_user_id(actor.id)
        if profile is None:
            raise ProviderProfileNotFoundError()
        return ProviderProfileRead.model_validate(profile)

    def update_my_profile(
        self,
        actor: User,
        data: ProviderProfileUpdate,
    ) -> ProviderProfileRead:
        """
        Update writable business fields.

        If status was REJECTED, treat update as re-application → PENDING,
        clear rejection_reason / verified_* audit fields.
        """
        self._assert_provider_actor(actor)
        profile = self._profiles.get_by_user_id(actor.id)
        if profile is None:
            raise ProviderProfileNotFoundError()

        if data.business_name is not None:
            profile.business_name = data.business_name
        if data.city is not None:
            profile.city = data.city
        if data.bio is not None:
            profile.bio = data.bio

        if profile.verification_status is ProviderVerificationStatus.REJECTED:
            profile.verification_status = ProviderVerificationStatus.PENDING
            profile.rejection_reason = None
            profile.verified_at = None
            profile.verified_by_admin_id = None
            logger.info("provider_profile_reapplied profile_id=%s", profile.id)

        self._profiles.save(profile)
        self._db.commit()
        self._db.refresh(profile)
        return ProviderProfileRead.model_validate(profile)

    def require_verified_profile(self, actor: User) -> ProviderProfile:
        """
        Gate for ServiceListing creation (and similar).

        Returns the profile ORM entity for FK use (provider_id).
        """
        self._assert_provider_actor(actor)
        profile = self._profiles.get_by_user_id(actor.id)
        if profile is None:
            raise ProviderProfileNotFoundError()
        if not profile.can_create_listings():
            raise ProviderNotVerifiedError()
        return profile

    # ------------------------------------------------------------------
    # Admin verification
    # ------------------------------------------------------------------

    def list_queue(
        self,
        *,
        status: ProviderVerificationStatus = ProviderVerificationStatus.PENDING,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminProviderQueueResponse:
        """Admin moderation queue. Role check belongs in the API dependency."""
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        total = self._profiles.count_by_verification_status(status)
        rows = self._profiles.list_by_verification_status(
            status,
            limit=limit,
            offset=offset,
        )
        return AdminProviderQueueResponse(
            items=[ProviderProfileRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_profile_for_admin(self, profile_id: UUID) -> ProviderProfileRead:
        profile = self._profiles.get_by_id(profile_id)
        if profile is None:
            raise ProviderProfileNotFoundError()
        return ProviderProfileRead.model_validate(profile)

    def verify_provider(
        self,
        admin: User,
        profile_id: UUID,
        data: AdminVerifyProviderRequest | None = None,
    ) -> ProviderProfileRead:
        """
        PENDING|REJECTED → VERIFIED.

        Sets verified_at + verified_by_admin_id. Clears rejection_reason.
        """
        self._assert_admin_actor(admin)
        profile = self._profiles.get_by_id(profile_id)
        if profile is None:
            raise ProviderProfileNotFoundError()

        if profile.verification_status is ProviderVerificationStatus.VERIFIED:
            raise InvalidVerificationTransitionError("Provider is already verified")

        if not profile.is_active:
            raise InvalidVerificationTransitionError(
                "Cannot verify an inactive provider profile"
            )

        profile.verification_status = ProviderVerificationStatus.VERIFIED
        profile.verified_at = _utcnow()
        profile.verified_by_admin_id = admin.id
        profile.rejection_reason = None

        self._profiles.save(profile)
        self._db.commit()
        self._db.refresh(profile)

        logger.info(
            "provider_verified profile_id=%s admin_id=%s note=%s",
            profile.id,
            admin.id,
            bool(data.note) if data else False,
        )
        return ProviderProfileRead.model_validate(profile)

    def reject_provider(
        self,
        admin: User,
        profile_id: UUID,
        data: AdminRejectProviderRequest,
    ) -> ProviderProfileRead:
        """PENDING|VERIFIED → REJECTED (revokes listing eligibility)."""
        self._assert_admin_actor(admin)
        profile = self._profiles.get_by_id(profile_id)
        if profile is None:
            raise ProviderProfileNotFoundError()

        if profile.verification_status is ProviderVerificationStatus.REJECTED:
            raise InvalidVerificationTransitionError("Provider is already rejected")

        profile.verification_status = ProviderVerificationStatus.REJECTED
        profile.rejection_reason = data.rejection_reason
        profile.verified_at = None
        profile.verified_by_admin_id = admin.id  # auditor who rejected

        self._profiles.save(profile)
        self._db.commit()
        self._db.refresh(profile)

        logger.info(
            "provider_rejected profile_id=%s admin_id=%s",
            profile.id,
            admin.id,
        )
        return ProviderProfileRead.model_validate(profile)

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_provider_actor(actor: User) -> None:
        if actor.role is not UserRole.PROVIDER:
            raise NotAProviderError()
        if not actor.is_verified:
            raise ProviderEmailNotVerifiedError()
        if not actor.is_active:
            raise ProviderDomainError("Inactive user", code="inactive_user")

    @staticmethod
    def _assert_admin_actor(actor: User) -> None:
        """
        Defense in depth — API should also use require_roles(ADMIN).

        Service still checks so CLI/tests/scripts cannot skip auth by mistake.
        """
        if actor.role is not UserRole.ADMIN:
            raise ProviderDomainError(
                "Only admins can perform this action",
                code="insufficient_permissions",
            )
        if not actor.is_active:
            raise ProviderDomainError("Inactive user", code="inactive_user")
