"""
Booking HTTP endpoints — customer + provider actions.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import CurrentCustomer, CurrentProvider, DbSession, require_roles
from app.models.user import User, UserRole
from app.schemas.booking import BookingAssignProvider, BookingCreate, BookingRead
from app.services.booking_service import (
    BookingError,
    accept_provider_booking,
    assign_provider_to_booking,
    cancel_customer_booking,
    complete_provider_booking,
    confirm_provider_booking,
    create_booking,
    get_customer_booking,
    get_provider_booking,
    list_all_bookings,
    list_customer_bookings,
    list_open_bookings_for_providers,
    list_provider_bookings,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _http_for_booking_error(exc: BookingError) -> HTTPException:
    if exc.code == "not_found" or exc.code == "service_not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code == "provider_not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    if exc.code == "provider_inactive":
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)
    if exc.code == "already_taken":
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    if exc.code in {"invalid_schedule", "invalid_status"}:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)


@router.post(
    "",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a booking (customer)",
)
def post_booking(
    payload: BookingCreate,
    db: DbSession,
    customer: CurrentCustomer,
) -> BookingRead:
    """
    Book an active catalog service for a future time.

    Price is snapshotted from the service (`price_pkr`) at create time.
    """
    try:
        booking = create_booking(db, customer, payload)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


@router.get(
    "",
    response_model=list[BookingRead],
    summary="List my bookings",
)
def get_my_bookings(db: DbSession, customer: CurrentCustomer) -> list[BookingRead]:
    """Returns bookings for the authenticated customer only."""
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
    summary="Assign provider to booking (admin)",
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


@router.get(
    "/provider/open",
    response_model=list[BookingRead],
    summary="List open bookings (provider)",
)
def get_open_bookings(db: DbSession, provider: CurrentProvider) -> list[BookingRead]:
    """Shows pending bookings not yet assigned to any provider."""
    _ = provider
    rows = list_open_bookings_for_providers(db)
    return [BookingRead.model_validate(row) for row in rows]


@router.get(
    "/provider/mine",
    response_model=list[BookingRead],
    summary="List my assigned bookings (provider)",
)
def get_my_provider_bookings(
    db: DbSession,
    provider: CurrentProvider,
) -> list[BookingRead]:
    rows = list_provider_bookings(db, provider)
    return [BookingRead.model_validate(row) for row in rows]


@router.post(
    "/{booking_id}/accept",
    response_model=BookingRead,
    summary="Accept an open booking (provider)",
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
    "/{booking_id}/confirm",
    response_model=BookingRead,
    summary="Confirm one of my bookings (provider)",
)
def confirm_booking(
    booking_id: UUID,
    db: DbSession,
    provider: CurrentProvider,
) -> BookingRead:
    try:
        booking = confirm_provider_booking(db, provider, booking_id)
    except BookingError as exc:
        raise _http_for_booking_error(exc) from exc
    return BookingRead.model_validate(booking)


@router.post(
    "/{booking_id}/complete",
    response_model=BookingRead,
    summary="Complete one of my bookings (provider)",
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
    summary="Get one of my bookings",
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


@router.get(
    "/provider/{booking_id}",
    response_model=BookingRead,
    summary="Get one assigned booking (provider)",
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
    "/{booking_id}/cancel",
    response_model=BookingRead,
    summary="Cancel one of my bookings",
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
