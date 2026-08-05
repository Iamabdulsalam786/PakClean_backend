"""
Booking business logic — marketplace listing bookings + legacy admin helpers.

Marketplace create:
  - Customer books an ACTIVE ServiceListing by listing_id
  - provider_id snapshotted from listing.provider.user_id
  - price / duration / title snapshotted
  - status = PENDING

Provider lifecycle:
  pending → confirmed (accept) | rejected (reject) | cancelled (customer)
  confirmed → in_progress (start) | cancelled
  in_progress → completed

Transitions use BookingStatus.can_transition_to + row locks on mutations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.bookings.models.booking_status import BookingStatus
from app.customers.repositories.customer_address_repository import (
    CustomerAddressRepository,
)
from app.models.booking import Booking
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate, BookingRejectRequest
from app.service_listings.models.service_listing import ServiceListing

logger = logging.getLogger(__name__)


class BookingError(Exception):
    """Domain error for booking failures (routes map to HTTP)."""

    def __init__(self, message: str, *, code: str = "booking_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _transition(booking: Booking, new_status: BookingStatus) -> None:
    if not booking.status.can_transition_to(new_status):
        raise BookingError(
            f"Cannot transition from {booking.status.value} to {new_status.value}",
            code="invalid_status",
        )
    booking.status = new_status


def _resolve_address_text(db: Session, customer: User, data: BookingCreate) -> str:
    """
    Build the immutable address_text snapshot for a new booking.

    Schema already enforces XOR(address_id, address_text).
    address_id must belong to this customer (404 otherwise — no IDOR leak).
    """
    if data.address_id is not None:
        address = CustomerAddressRepository(db).get_for_customer(
            data.address_id,
            customer.id,
        )
        if address is None:
            raise BookingError("Address not found", code="address_not_found")
        return address.to_address_text()

    # Schema XOR guarantees address_text is set when address_id is absent.
    assert data.address_text is not None
    return data.address_text


# ------------------------------------------------------------------
# Customer
# ------------------------------------------------------------------


def create_booking(db: Session, customer: User, data: BookingCreate) -> Booking:
    """
    Create a pending marketplace booking for an ACTIVE listing.

    Rules:
      - listing must be publicly visible (active + not deleted)
      - scheduled_at must be in the future
      - provider_id taken from the listing's provider profile user
      - price/duration/title snapshotted from the listing
      - address from address_id (owned) or address_text — stored as snapshot only
    """
    if not customer.is_verified:
        raise BookingError("Verify your email before booking", code="email_not_verified")

    listing = db.scalar(
        select(ServiceListing)
        .where(ServiceListing.id == data.listing_id)
        .options(selectinload(ServiceListing.provider))
    )
    if listing is None or not listing.is_publicly_visible():
        raise BookingError("Listing not found or not available", code="listing_not_found")

    provider_profile = listing.provider
    if provider_profile is None or not provider_profile.is_active:
        raise BookingError("Provider is not available", code="provider_inactive")

    scheduled_at = _ensure_aware(data.scheduled_at)
    if scheduled_at <= _utcnow():
        raise BookingError("scheduled_at must be in the future", code="invalid_schedule")

    address_text = _resolve_address_text(db, customer, data)

    booking = Booking(
        customer_id=customer.id,
        listing_id=listing.id,
        service_id=None,
        provider_id=provider_profile.user_id,
        status=BookingStatus.PENDING,
        scheduled_at=scheduled_at,
        address_text=address_text,
        notes=data.notes,
        price_pkr=listing.base_price,
        duration_minutes=listing.estimated_duration,
        listing_title_snapshot=listing.title,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    logger.info(
        "booking_created booking_id=%s listing_id=%s customer_id=%s",
        booking.id,
        listing.id,
        customer.id,
    )
    return booking


def list_customer_bookings(db: Session, customer: User) -> list[Booking]:
    statement = (
        select(Booking)
        .where(Booking.customer_id == customer.id)
        .order_by(Booking.created_at.desc())
    )
    return list(db.scalars(statement).all())


def get_customer_booking(db: Session, customer: User, booking_id: UUID) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None or booking.customer_id != customer.id:
        raise BookingError("Booking not found", code="not_found")
    return booking


def cancel_customer_booking(db: Session, customer: User, booking_id: UUID) -> Booking:
    """Customer may cancel while pending or confirmed (not in_progress+)."""
    booking = get_customer_booking(db, customer, booking_id)
    _transition(booking, BookingStatus.CANCELLED)
    booking.cancelled_at = _utcnow()
    db.add(booking)
    db.commit()
    db.refresh(booking)
    logger.info("booking_cancelled booking_id=%s by=customer", booking.id)
    return booking


# ------------------------------------------------------------------
# Provider inbox / actions
# ------------------------------------------------------------------


def list_provider_bookings(db: Session, provider: User) -> list[Booking]:
    statement = (
        select(Booking)
        .where(Booking.provider_id == provider.id)
        .order_by(Booking.created_at.desc())
    )
    return list(db.scalars(statement).all())


def list_provider_pending_bookings(db: Session, provider: User) -> list[Booking]:
    """Inbox: pending requests assigned to this listing owner."""
    statement = (
        select(Booking)
        .where(
            Booking.provider_id == provider.id,
            Booking.status == BookingStatus.PENDING,
        )
        .order_by(Booking.created_at.desc())
    )
    return list(db.scalars(statement).all())


def get_provider_booking(db: Session, provider: User, booking_id: UUID) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None or booking.provider_id != provider.id:
        raise BookingError("Booking not found", code="not_found")
    return booking


def accept_provider_booking(db: Session, provider: User, booking_id: UUID) -> Booking:
    """
    Provider accepts a PENDING booking assigned to them.

    Uses conditional UPDATE for concurrency safety.
    """
    now = _utcnow()
    result = db.execute(
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.provider_id == provider.id,
            Booking.status == BookingStatus.PENDING,
        )
        .values(
            status=BookingStatus.CONFIRMED,
            accepted_at=now,
            updated_at=now,
        )
    )
    if (result.rowcount or 0) != 1:
        # Distinguish not found vs wrong state for clearer errors
        booking = db.get(Booking, booking_id)
        if booking is None or booking.provider_id != provider.id:
            raise BookingError("Booking not found", code="not_found")
        raise BookingError(
            f"Cannot accept a {booking.status.value} booking",
            code="invalid_status",
        )

    db.commit()
    booking = get_provider_booking(db, provider, booking_id)
    logger.info("booking_accepted booking_id=%s", booking.id)
    return booking


def reject_provider_booking(
    db: Session,
    provider: User,
    booking_id: UUID,
    data: BookingRejectRequest,
) -> Booking:
    """Provider rejects a PENDING booking."""
    now = _utcnow()
    result = db.execute(
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.provider_id == provider.id,
            Booking.status == BookingStatus.PENDING,
        )
        .values(
            status=BookingStatus.REJECTED,
            rejection_reason=data.rejection_reason,
            updated_at=now,
        )
    )
    if (result.rowcount or 0) != 1:
        booking = db.get(Booking, booking_id)
        if booking is None or booking.provider_id != provider.id:
            raise BookingError("Booking not found", code="not_found")
        raise BookingError(
            f"Cannot reject a {booking.status.value} booking",
            code="invalid_status",
        )

    db.commit()
    booking = get_provider_booking(db, provider, booking_id)
    logger.info("booking_rejected booking_id=%s", booking.id)
    return booking


def start_provider_booking(db: Session, provider: User, booking_id: UUID) -> Booking:
    """confirmed → in_progress."""
    now = _utcnow()
    result = db.execute(
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.provider_id == provider.id,
            Booking.status == BookingStatus.CONFIRMED,
        )
        .values(
            status=BookingStatus.IN_PROGRESS,
            started_at=now,
            updated_at=now,
        )
    )
    if (result.rowcount or 0) != 1:
        booking = db.get(Booking, booking_id)
        if booking is None or booking.provider_id != provider.id:
            raise BookingError("Booking not found", code="not_found")
        raise BookingError(
            f"Cannot start a {booking.status.value} booking",
            code="invalid_status",
        )

    db.commit()
    booking = get_provider_booking(db, provider, booking_id)
    logger.info("booking_started booking_id=%s", booking.id)
    return booking


def complete_provider_booking(db: Session, provider: User, booking_id: UUID) -> Booking:
    """in_progress → completed; bumps listing.booking_count when listing_id set."""
    now = _utcnow()
    result = db.execute(
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.provider_id == provider.id,
            Booking.status == BookingStatus.IN_PROGRESS,
        )
        .values(
            status=BookingStatus.COMPLETED,
            completed_at=now,
            updated_at=now,
        )
    )
    if (result.rowcount or 0) != 1:
        booking = db.get(Booking, booking_id)
        if booking is None or booking.provider_id != provider.id:
            raise BookingError("Booking not found", code="not_found")
        raise BookingError(
            f"Cannot complete a {booking.status.value} booking",
            code="invalid_status",
        )

    booking = db.get(Booking, booking_id)
    assert booking is not None
    if booking.listing_id is not None:
        listing = db.get(ServiceListing, booking.listing_id)
        if listing is not None:
            listing.booking_count = int(listing.booking_count or 0) + 1
            db.add(listing)

    db.commit()
    db.refresh(booking)
    logger.info("booking_completed booking_id=%s", booking.id)
    return booking


# ------------------------------------------------------------------
# Legacy helpers (admin / old open marketplace grab)
# ------------------------------------------------------------------


def list_open_bookings_for_providers(db: Session) -> list[Booking]:
    """Legacy: pending bookings with no provider (catalog-era)."""
    statement = (
        select(Booking)
        .where(
            Booking.status == BookingStatus.PENDING,
            Booking.provider_id.is_(None),
        )
        .order_by(Booking.created_at.desc())
    )
    return list(db.scalars(statement).all())


def confirm_provider_booking(db: Session, provider: User, booking_id: UUID) -> Booking:
    """Legacy alias — prefer accept_provider_booking for pending → confirmed."""
    booking = get_provider_booking(db, provider, booking_id)
    if booking.status == BookingStatus.CONFIRMED:
        return booking
    _transition(booking, BookingStatus.CONFIRMED)
    booking.accepted_at = booking.accepted_at or _utcnow()
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def list_all_bookings(db: Session) -> list[Booking]:
    statement = select(Booking).order_by(Booking.created_at.desc())
    return list(db.scalars(statement).all())


def assign_provider_to_booking(
    db: Session,
    *,
    booking_id: UUID,
    provider_id: UUID,
) -> Booking:
    """Admin assigns a provider (legacy open bookings)."""
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise BookingError("Booking not found", code="not_found")

    provider = db.get(User, provider_id)
    if provider is None or provider.role != UserRole.PROVIDER:
        raise BookingError("Provider not found", code="provider_not_found")
    if not provider.is_active:
        raise BookingError("Provider is inactive", code="provider_inactive")

    if booking.status.is_terminal():
        raise BookingError(
            f"Cannot assign provider to a {booking.status.value} booking",
            code="invalid_status",
        )

    booking.provider_id = provider.id
    if booking.status == BookingStatus.PENDING:
        booking.status = BookingStatus.CONFIRMED
        booking.accepted_at = _utcnow()

    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking
