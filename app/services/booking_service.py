"""
Booking business logic: customer and provider booking actions.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.catalog_service import CatalogError, get_service_by_id


class BookingError(Exception):
    """Domain error for booking failures (routes map to HTTP)."""

    def __init__(self, message: str, *, code: str = "booking_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def create_booking(db: Session, customer: User, data: BookingCreate) -> Booking:
    """
    Create a pending booking for the authenticated customer.

    Rules:
      - service must exist and be active
      - scheduled_at must be in the future
      - price_pkr / duration snapshotted from the service
    """
    try:
        service = get_service_by_id(db, data.service_id, active_only=True)
    except CatalogError as exc:
        raise BookingError("Service not found or inactive", code="service_not_found") from exc

    scheduled_at = data.scheduled_at
    if scheduled_at.tzinfo is None:
        # Treat naive datetimes as UTC so comparisons are safe.
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

    if scheduled_at <= datetime.now(timezone.utc):
        raise BookingError("scheduled_at must be in the future", code="invalid_schedule")

    booking = Booking(
        customer_id=customer.id,
        service_id=service.id,
        provider_id=None,
        status=BookingStatus.PENDING,
        scheduled_at=scheduled_at,
        address_text=data.address_text.strip(),
        notes=data.notes.strip() if data.notes else None,
        price_pkr=service.price_pkr,
        duration_minutes=service.duration_minutes,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def list_customer_bookings(db: Session, customer: User) -> list[Booking]:
    """Return this customer's bookings, newest first."""
    statement = (
        select(Booking)
        .where(Booking.customer_id == customer.id)
        .order_by(Booking.created_at.desc())
    )
    return list(db.scalars(statement).all())


def get_customer_booking(db: Session, customer: User, booking_id: UUID) -> Booking:
    """Fetch one booking owned by this customer."""
    booking = db.get(Booking, booking_id)
    if booking is None or booking.customer_id != customer.id:
        raise BookingError("Booking not found", code="not_found")
    return booking


def cancel_customer_booking(db: Session, customer: User, booking_id: UUID) -> Booking:
    """
    Cancel a booking the customer owns.

    Allowed only while pending or confirmed (not completed/cancelled).
    """
    booking = get_customer_booking(db, customer, booking_id)

    if booking.status in {BookingStatus.CANCELLED, BookingStatus.COMPLETED}:
        raise BookingError(
            f"Cannot cancel a {booking.status.value} booking",
            code="invalid_status",
        )

    booking.status = BookingStatus.CANCELLED
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def list_open_bookings_for_providers(db: Session) -> list[Booking]:
    """Return pending bookings not yet assigned to any provider."""
    statement = (
        select(Booking)
        .where(
            Booking.status == BookingStatus.PENDING,
            Booking.provider_id.is_(None),
        )
        .order_by(Booking.created_at.desc())
    )
    return list(db.scalars(statement).all())


def list_provider_bookings(db: Session, provider: User) -> list[Booking]:
    """Return bookings assigned to this provider, newest first."""
    statement = (
        select(Booking)
        .where(Booking.provider_id == provider.id)
        .order_by(Booking.created_at.desc())
    )
    return list(db.scalars(statement).all())


def get_provider_booking(db: Session, provider: User, booking_id: UUID) -> Booking:
    """Fetch one booking assigned to this provider."""
    booking = db.get(Booking, booking_id)
    if booking is None or booking.provider_id != provider.id:
        raise BookingError("Booking not found", code="not_found")
    return booking


def accept_provider_booking(db: Session, provider: User, booking_id: UUID) -> Booking:
    """
    Provider accepts an open booking.

    Rules:
      - booking must exist
      - status must be pending
      - booking must be unassigned
    """
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise BookingError("Booking not found", code="not_found")

    if booking.status != BookingStatus.PENDING:
        raise BookingError(
            f"Cannot accept a {booking.status.value} booking",
            code="invalid_status",
        )

    if booking.provider_id is not None:
        if booking.provider_id == provider.id:
            raise BookingError("Booking already accepted by you", code="already_taken")
        raise BookingError("Booking already assigned to another provider", code="already_taken")

    booking.provider_id = provider.id
    booking.status = BookingStatus.CONFIRMED
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def confirm_provider_booking(db: Session, provider: User, booking_id: UUID) -> Booking:
    """
    Provider confirms a booking already assigned to them.

    Useful when assignment happens elsewhere in the future.
    """
    booking = get_provider_booking(db, provider, booking_id)
    if booking.status == BookingStatus.CANCELLED:
        raise BookingError("Cannot confirm a cancelled booking", code="invalid_status")
    if booking.status == BookingStatus.COMPLETED:
        raise BookingError("Cannot confirm a completed booking", code="invalid_status")
    if booking.status == BookingStatus.CONFIRMED:
        return booking

    booking.status = BookingStatus.CONFIRMED
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def complete_provider_booking(db: Session, provider: User, booking_id: UUID) -> Booking:
    """Provider marks their confirmed booking as completed."""
    booking = get_provider_booking(db, provider, booking_id)

    if booking.status == BookingStatus.CANCELLED:
        raise BookingError("Cannot complete a cancelled booking", code="invalid_status")
    if booking.status == BookingStatus.COMPLETED:
        raise BookingError("Booking already completed", code="invalid_status")
    if booking.status != BookingStatus.CONFIRMED:
        raise BookingError("Booking must be confirmed before completion", code="invalid_status")

    booking.status = BookingStatus.COMPLETED
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def list_all_bookings(db: Session) -> list[Booking]:
    """Admin list of all bookings, newest first."""
    statement = select(Booking).order_by(Booking.created_at.desc())
    return list(db.scalars(statement).all())


def assign_provider_to_booking(
    db: Session,
    *,
    booking_id: UUID,
    provider_id: UUID,
) -> Booking:
    """
    Admin assigns a provider to a booking.

    Rules:
      - booking and provider must exist
      - provider must have role=provider and be active
      - cannot assign cancelled/completed bookings
      - assignment sets status to confirmed
    """
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise BookingError("Booking not found", code="not_found")

    provider = db.get(User, provider_id)
    if provider is None or provider.role != UserRole.PROVIDER:
        raise BookingError("Provider not found", code="provider_not_found")
    if not provider.is_active:
        raise BookingError("Provider is inactive", code="provider_inactive")

    if booking.status in {BookingStatus.CANCELLED, BookingStatus.COMPLETED}:
        raise BookingError(
            f"Cannot assign provider to a {booking.status.value} booking",
            code="invalid_status",
        )

    booking.provider_id = provider.id
    booking.status = BookingStatus.CONFIRMED
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking
