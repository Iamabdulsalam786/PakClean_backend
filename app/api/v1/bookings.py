"""
Booking HTTP endpoints — marketplace listing bookings.

Customer:
  POST   /bookings                 create (listing_id)
  GET    /bookings                 list mine
  GET    /bookings/{id}            get mine
  POST   /bookings/{id}/cancel     cancel (pending/confirmed)

Provider:
  GET    /bookings/provider/mine
  GET    /bookings/provider/pending
  GET    /bookings/provider/{id}
  POST   /bookings/{id}/accept
  POST   /bookings/{id}/reject
  POST   /bookings/{id}/start
  POST   /bookings/{id}/complete

Admin (legacy helpers retained):
  GET    /bookings/admin/all
  POST   /bookings/admin/{id}/assign
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import CurrentCustomer, CurrentProvider, DbSession, require_roles
from app.models.user import User, UserRole
from app.schemas.booking import (
    BookingAssignProvider,
    BookingCreate,
    BookingRead,
    BookingRejectRequest,
)
from app.services.booking_service import (
    BookingError,
    accept_provider_booking,
    assign_provider_to_booking,
    cancel_customer_booking,
    complete_provider_booking,
    create_booking,
    get_customer_booking,
    get_provider_booking,
    list_all_bookings,
    list_customer_bookings,
    list_provider_bookings,
    list_provider_pending_bookings,
    reject_provider_booking,
    start_provider_booking,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _http_for_booking_error(exc: BookingError) -> HTTPException:
    code = exc.code
    if code in {
        "not_found",
        "listing_not_found",
        "service_not_found",
        "provider_not_found",
        "address_not_found",
    }:
        status_code = status.HTTP_404_NOT_FOUND
    elif code in {"provider_inactive", "email_not_verified"}:
        status_code = status.HTTP_403_FORBIDDEN
    elif code in {"already_taken", "invalid_status"}:
        status_code = status.HTTP_409_CONFLICT
    elif code == "invalid_schedule":
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Book an active service listing (customer)",
)
def post_booking(
    payload: BookingCreate,
    db: DbSession,
    customer: CurrentCustomer,
) -> BookingRead:
    """
    Creates a PENDING booking for the listing's provider.

    Snapshots price_pkr, duration_minutes, and listing title from the listing.
    """
    try:
        booking = create_booking(db, customer, payload)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


@router.get(
    "",
    response_model=list[BookingRead],
    summary="List my bookings (customer)",
)
def get_my_bookings(db: DbSession, customer: CurrentCustomer) -> list[BookingRead]:
    rows = list_customer_bookings(db, customer)
    return [BookingRead.model_validate(row) for row in rows]


@router.get(
    "/admin/all",
    response_model=list[BookingRead],
    summary="List all bookings (admin)",
)
def get_all_bookings(
    db: DbSession,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
) -> list[BookingRead]:
    _ = admin
    rows = list_all_bookings(db)
    return [BookingRead.model_validate(row) for row in rows]


@router.post(
    "/admin/{booking_id}/assign",
    response_model=BookingRead,
    summary="Assign provider to booking (admin, legacy)",
)
def assign_booking_provider(
    booking_id: UUID,
    payload: BookingAssignProvider,
    db: DbSession,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
) -> BookingRead:
    _ = admin
    try:
        booking = assign_provider_to_booking(
            db,
            booking_id=booking_id,
            provider_id=payload.provider_id,
        )
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


# ---------------------------------------------------------------------------
# Provider (static paths before /{booking_id})
# ---------------------------------------------------------------------------


@router.get(
    "/provider/mine",
    response_model=list[BookingRead],
    summary="List bookings assigned to me (provider)",
)
def get_my_provider_bookings(
    db: DbSession,
    provider: CurrentProvider,
) -> list[BookingRead]:
    rows = list_provider_bookings(db, provider)
    return [BookingRead.model_validate(row) for row in rows]


@router.get(
    "/provider/pending",
    response_model=list[BookingRead],
    summary="List pending booking requests for me (provider inbox)",
)
def get_my_pending_bookings(
    db: DbSession,
    provider: CurrentProvider,
) -> list[BookingRead]:
    rows = list_provider_pending_bookings(db, provider)
    return [BookingRead.model_validate(row) for row in rows]


@router.get(
    "/provider/{booking_id}",
    response_model=BookingRead,
    summary="Get one of my bookings (provider)",
)
def get_provider_side_booking(
    booking_id: UUID,
    db: DbSession,
    provider: CurrentProvider,
) -> BookingRead:
    try:
        booking = get_provider_booking(db, provider, booking_id)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


@router.post(
    "/{booking_id}/accept",
    response_model=BookingRead,
    summary="Accept pending booking (provider)",
)
def accept_booking(
    booking_id: UUID,
    db: DbSession,
    provider: CurrentProvider,
) -> BookingRead:
    try:
        booking = accept_provider_booking(db, provider, booking_id)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


@router.post(
    "/{booking_id}/reject",
    response_model=BookingRead,
    summary="Reject pending booking (provider)",
)
def reject_booking(
    booking_id: UUID,
    payload: BookingRejectRequest,
    db: DbSession,
    provider: CurrentProvider,
) -> BookingRead:
    try:
        booking = reject_provider_booking(db, provider, booking_id, payload)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


@router.post(
    "/{booking_id}/start",
    response_model=BookingRead,
    summary="Start confirmed booking / mark in progress (provider)",
)
def start_booking(
    booking_id: UUID,
    db: DbSession,
    provider: CurrentProvider,
) -> BookingRead:
    try:
        booking = start_provider_booking(db, provider, booking_id)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


@router.post(
    "/{booking_id}/complete",
    response_model=BookingRead,
    summary="Complete in-progress booking (provider)",
)
def complete_booking(
    booking_id: UUID,
    db: DbSession,
    provider: CurrentProvider,
) -> BookingRead:
    try:
        booking = complete_provider_booking(db, provider, booking_id)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


@router.get(
    "/{booking_id}",
    response_model=BookingRead,
    summary="Get one of my bookings (customer)",
)
def get_booking(
    booking_id: UUID,
    db: DbSession,
    customer: CurrentCustomer,
) -> BookingRead:
    try:
        booking = get_customer_booking(db, customer, booking_id)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


@router.post(
    "/{booking_id}/cancel",
    response_model=BookingRead,
    summary="Cancel my booking (customer, pending/confirmed only)",
)
def cancel_booking(
    booking_id: UUID,
    db: DbSession,
    customer: CurrentCustomer,
) -> BookingRead:
    try:
        booking = cancel_customer_booking(db, customer, booking_id)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)
