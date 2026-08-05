"""
ProviderProfile — business identity for a marketplace provider.

Why this table exists (not just User.role == provider):
  - Email OTP (`users.is_verified`) proves mailbox ownership only.
  - Marketplace trust requires a SEPARATE admin verification of the business.
  - Listings, ratings, and geo belong to the business profile, not the login row.
  - 1:1 with users keeps auth thin and provider domain rich (SRP).

Verification is first-class production state:
  pending → verified | rejected
  Only VERIFIED (+ active) profiles may create ServiceListings (enforced later
  in ProviderListingService — never trust the client to send is_verified).

Feature module: app/providers (feature-based architecture).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProviderVerificationStatus(str, enum.Enum):
    """
    Admin review state for a provider business profile.

    PENDING:
      Profile submitted (or auto-created). Cannot publish listings yet.

    VERIFIED:
      Admin approved. Eligible to create/publish service listings.

    REJECTED:
      Admin declined. Must update profile / re-apply (service will define flow).
      Cannot create listings.
    """

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ProviderProfile(Base):
    """
    One marketplace business profile per provider user.

    Lifecycle (high level):
      1. User registers with role=provider + verifies email
      2. Provider creates/updates this profile → verification_status=PENDING
      3. Admin verifies → VERIFIED (sets verified_at, verified_by_admin_id)
      4. Verified provider creates ServiceListings (next feature slice)
    """

    __tablename__ = "provider_profiles"
    __table_args__ = (
        # Defensive: unique index on user_id column + named table constraint
        # for clear migration/error messages if a duplicate insert slips through.
        UniqueConstraint("user_id", name="uq_provider_profiles_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Owner login account. CASCADE: delete user → delete profile.
    # unique=True enforces 1:1 at the database (not only in Python).
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Public-facing business name (may differ from users.full_name).
    business_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Denormalized for provider discovery filters; index for city browse.
    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # --- Admin verification (NOT the same as users.is_verified email OTP) ---
    verification_status: Mapped[ProviderVerificationStatus] = mapped_column(
        Enum(
            ProviderVerificationStatus,
            name="provider_verification_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ProviderVerificationStatus.PENDING,
        server_default=ProviderVerificationStatus.PENDING.value,
        index=True,  # Admin queue: WHERE verification_status = 'pending'
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Which admin approved/rejected. SET NULL if that admin user is deleted.
    verified_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # --- Denormalized metrics (updated by review/booking services later) ---
    # Avoid AVG(reviews) on every search when listings scale to millions.
    average_rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    total_reviews: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    total_bookings: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Soft operational flag (banned / paused by admin or self).
    # Independent of verification_status so we can suspend a verified provider.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Two FKs to users → must disambiguate with foreign_keys=
    user = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="joined",
    )
    verified_by_admin = relationship(
        "User",
        foreign_keys=[verified_by_admin_id],
        lazy="select",
    )

    # Populated when ServiceListing model lands in service_listings feature.
    # listings = relationship("ServiceListing", back_populates="provider")

    def can_create_listings(self) -> bool:
        """
        Single gate used by listing services.

        Beginner mistake: checking only verification_status and forgetting
        is_active (suspended providers must not publish).
        """
        return (
            self.is_active
            and self.verification_status is ProviderVerificationStatus.VERIFIED
        )

    def __repr__(self) -> str:
        return (
            f"<ProviderProfile id={self.id} user_id={self.user_id} "
            f"status={self.verification_status} active={self.is_active}>"
        )
