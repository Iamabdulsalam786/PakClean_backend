"""
Customer profile + saved-address HTTP endpoints.

Thin controllers: schema validation → CustomerService → map errors → HTTP.

Routes:
  GET    /customers/me
  PATCH  /customers/me
  GET    /customers/me/addresses
  POST   /customers/me/addresses
  GET    /customers/me/addresses/{address_id}
  PATCH  /customers/me/addresses/{address_id}
  DELETE /customers/me/addresses/{address_id}
  POST   /customers/me/addresses/{address_id}/set-default
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.core.dependencies import CurrentCustomer, DbSession
from app.customers.schemas.customer import (
    CustomerAddressCreate,
    CustomerAddressListResponse,
    CustomerAddressRead,
    CustomerAddressUpdate,
    CustomerProfileRead,
    CustomerProfileUpdate,
)
from app.customers.services.customer_service import (
    CustomerDomainError,
    CustomerService,
)

router = APIRouter(prefix="/customers", tags=["customers"])


def _http_for_customer_error(exc: CustomerDomainError) -> HTTPException:
    code = exc.code
    if code == "address_not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif code in {"not_a_customer"}:
        status_code = status.HTTP_403_FORBIDDEN
    elif code in {"address_limit_exceeded", "phone_conflict"}:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


def _service(db: DbSession) -> CustomerService:
    return CustomerService(db)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=CustomerProfileRead,
    summary="Get my customer profile",
)
def get_my_profile(
    db: DbSession,
    customer: CurrentCustomer,
) -> CustomerProfileRead:
    try:
        return _service(db).get_profile(customer)
    except CustomerDomainError as exc:
        raise _http_for_customer_error(exc) from exc


@router.patch(
    "/me",
    response_model=CustomerProfileRead,
    summary="Update my customer profile (name/phone)",
)
def patch_my_profile(
    payload: CustomerProfileUpdate,
    db: DbSession,
    customer: CurrentCustomer,
) -> CustomerProfileRead:
    try:
        return _service(db).update_profile(customer, payload)
    except CustomerDomainError as exc:
        raise _http_for_customer_error(exc) from exc


# ---------------------------------------------------------------------------
# Addresses (static paths before {address_id})
# ---------------------------------------------------------------------------


@router.get(
    "/me/addresses",
    response_model=CustomerAddressListResponse,
    summary="List my saved addresses",
)
def list_my_addresses(
    db: DbSession,
    customer: CurrentCustomer,
) -> CustomerAddressListResponse:
    try:
        return _service(db).list_addresses(customer)
    except CustomerDomainError as exc:
        raise _http_for_customer_error(exc) from exc


@router.post(
    "/me/addresses",
    response_model=CustomerAddressRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a saved address",
)
def create_my_address(
    payload: CustomerAddressCreate,
    db: DbSession,
    customer: CurrentCustomer,
) -> CustomerAddressRead:
    try:
        address = _service(db).create_address(customer, payload)
    except CustomerDomainError as exc:
        raise _http_for_customer_error(exc) from exc
    return CustomerAddressRead.model_validate(address)


@router.get(
    "/me/addresses/{address_id}",
    response_model=CustomerAddressRead,
    summary="Get one of my saved addresses",
)
def get_my_address(
    address_id: UUID,
    db: DbSession,
    customer: CurrentCustomer,
) -> CustomerAddressRead:
    try:
        address = _service(db).get_address(customer, address_id)
    except CustomerDomainError as exc:
        raise _http_for_customer_error(exc) from exc
    return CustomerAddressRead.model_validate(address)


@router.patch(
    "/me/addresses/{address_id}",
    response_model=CustomerAddressRead,
    summary="Update one of my saved addresses",
)
def patch_my_address(
    address_id: UUID,
    payload: CustomerAddressUpdate,
    db: DbSession,
    customer: CurrentCustomer,
) -> CustomerAddressRead:
    try:
        address = _service(db).update_address(customer, address_id, payload)
    except CustomerDomainError as exc:
        raise _http_for_customer_error(exc) from exc
    return CustomerAddressRead.model_validate(address)


@router.delete(
    "/me/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one of my saved addresses",
)
def delete_my_address(
    address_id: UUID,
    db: DbSession,
    customer: CurrentCustomer,
) -> Response:
    try:
        _service(db).delete_address(customer, address_id)
    except CustomerDomainError as exc:
        raise _http_for_customer_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/me/addresses/{address_id}/set-default",
    response_model=CustomerAddressRead,
    summary="Mark an address as my default",
)
def set_my_default_address(
    address_id: UUID,
    db: DbSession,
    customer: CurrentCustomer,
) -> CustomerAddressRead:
    try:
        address = _service(db).set_default_address(customer, address_id)
    except CustomerDomainError as exc:
        raise _http_for_customer_error(exc) from exc
    return CustomerAddressRead.model_validate(address)
