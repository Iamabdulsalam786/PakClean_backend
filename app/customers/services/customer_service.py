"""
CustomerService — profile self-view/update + saved address book.

Layering:
  API route → this service → CustomerAddressRepository (+ User row)
  Does not import FastAPI.

Business rules owned here:
  - Only role=customer may use these APIs (route also gates; defense in depth)
  - Profile updates touch full_name/phone only (not email/role/password)
  - Max 10 saved addresses per customer
  - At most one is_default=True (clear siblings in same transaction)
  - First address becomes default if none exists yet
  - Ownership misses → not_found (no IDOR leak)

Feature path: app/customers/services/
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.customers.models.customer_address import CustomerAddress
from app.customers.repositories.customer_address_repository import (
    CustomerAddressRepository,
)
from app.customers.schemas.customer import (
    CustomerAddressCreate,
    CustomerAddressListResponse,
    CustomerAddressRead,
    CustomerAddressSummary,
    CustomerAddressUpdate,
    CustomerProfileRead,
    CustomerProfileUpdate,
)
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

MAX_ADDRESSES_PER_CUSTOMER = 10


class CustomerDomainError(Exception):
    """Base customer-feature error with a stable machine code."""

    def __init__(self, message: str, *, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class NotACustomerError(CustomerDomainError):
    def __init__(self) -> None:
        super().__init__(
            "Only customer accounts can manage customer profile and addresses",
            code="not_a_customer",
        )


class AddressNotFoundError(CustomerDomainError):
    def __init__(self) -> None:
        super().__init__("Address not found", code="address_not_found")


class AddressLimitExceededError(CustomerDomainError):
    def __init__(self) -> None:
        super().__init__(
            f"Maximum of {MAX_ADDRESSES_PER_CUSTOMER} saved addresses reached",
            code="address_limit_exceeded",
        )


class PhoneConflictError(CustomerDomainError):
    def __init__(self) -> None:
        super().__init__(
            "Phone number is already in use",
            code="phone_conflict",
        )


class CustomerService:
    """Application service for customer profile and saved addresses."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._addresses = CustomerAddressRepository(db)

    # ------------------------------------------------------------------
    # Profile (User-backed)
    # ------------------------------------------------------------------

    def get_profile(self, actor: User) -> CustomerProfileRead:
        self._require_customer(actor)
        default = self._addresses.get_default_for_customer(actor.id)
        return self._to_profile_read(actor, default)

    def update_profile(
        self,
        actor: User,
        data: CustomerProfileUpdate,
    ) -> CustomerProfileRead:
        self._require_customer(actor)

        if data.full_name is not None:
            actor.full_name = data.full_name
        if data.phone is not None:
            if data.phone != actor.phone:
                existing = self._db.scalar(
                    select(User).where(
                        User.phone == data.phone,
                        User.id != actor.id,
                    )
                )
                if existing is not None:
                    raise PhoneConflictError()
            actor.phone = data.phone

        try:
            self._db.add(actor)
            self._db.commit()
            self._db.refresh(actor)
        except IntegrityError as exc:
            self._db.rollback()
            raise PhoneConflictError() from exc

        default = self._addresses.get_default_for_customer(actor.id)
        logger.info("customer_profile_updated user_id=%s", actor.id)
        return self._to_profile_read(actor, default)

    # ------------------------------------------------------------------
    # Addresses
    # ------------------------------------------------------------------

    def list_addresses(self, actor: User) -> CustomerAddressListResponse:
        self._require_customer(actor)
        rows = self._addresses.list_for_customer(actor.id)
        return CustomerAddressListResponse(
            items=[CustomerAddressRead.model_validate(row) for row in rows],
            total=len(rows),
        )

    def get_address(self, actor: User, address_id: UUID) -> CustomerAddress:
        self._require_customer(actor)
        address = self._addresses.get_for_customer(address_id, actor.id)
        if address is None:
            raise AddressNotFoundError()
        return address

    def create_address(
        self,
        actor: User,
        data: CustomerAddressCreate,
    ) -> CustomerAddress:
        self._require_customer(actor)

        count = self._addresses.count_for_customer(actor.id)
        if count >= MAX_ADDRESSES_PER_CUSTOMER:
            raise AddressLimitExceededError()

        make_default = data.is_default or count == 0
        if make_default:
            self._addresses.clear_defaults_for_customer(actor.id)

        address = self._addresses.add(
            customer_id=actor.id,
            label=data.label,
            address_line=data.address_line,
            city=data.city,
            area=data.area,
            landmark=data.landmark,
            latitude=data.latitude,
            longitude=data.longitude,
            is_default=make_default,
        )
        self._db.commit()
        self._db.refresh(address)
        logger.info(
            "customer_address_created address_id=%s customer_id=%s default=%s",
            address.id,
            actor.id,
            address.is_default,
        )
        return address

    def update_address(
        self,
        actor: User,
        address_id: UUID,
        data: CustomerAddressUpdate,
    ) -> CustomerAddress:
        address = self.get_address(actor, address_id)

        if data.label is not None:
            address.label = data.label
        if data.address_line is not None:
            address.address_line = data.address_line
        if data.city is not None:
            address.city = data.city
        if data.area is not None:
            address.area = data.area
        if data.landmark is not None:
            address.landmark = data.landmark
        if data.latitude is not None:
            address.latitude = data.latitude
        if data.longitude is not None:
            address.longitude = data.longitude

        if data.is_default is True:
            self._addresses.clear_defaults_for_customer(actor.id)
            address.is_default = True
        elif data.is_default is False and address.is_default:
            # Allow unsetting; customer may have zero defaults temporarily.
            address.is_default = False

        self._addresses.save(address)
        self._db.commit()
        self._db.refresh(address)
        logger.info("customer_address_updated address_id=%s", address.id)
        return address

    def delete_address(self, actor: User, address_id: UUID) -> None:
        address = self.get_address(actor, address_id)
        was_default = address.is_default
        self._addresses.delete(address)
        self._db.flush()

        # If we deleted the default, promote the newest remaining address.
        if was_default:
            remaining = self._addresses.list_for_customer(actor.id)
            if remaining:
                remaining[0].is_default = True
                self._addresses.save(remaining[0])

        self._db.commit()
        logger.info("customer_address_deleted address_id=%s", address_id)

    def set_default_address(self, actor: User, address_id: UUID) -> CustomerAddress:
        address = self.get_address(actor, address_id)
        self._addresses.clear_defaults_for_customer(actor.id)
        address.is_default = True
        self._addresses.save(address)
        self._db.commit()
        self._db.refresh(address)
        logger.info(
            "customer_address_set_default address_id=%s customer_id=%s",
            address.id,
            actor.id,
        )
        return address

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_customer(self, actor: User) -> None:
        if actor.role != UserRole.CUSTOMER:
            raise NotACustomerError()

    def _to_profile_read(
        self,
        user: User,
        default: CustomerAddress | None,
    ) -> CustomerProfileRead:
        return CustomerProfileRead(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            role=user.role.value,
            is_verified=user.is_verified,
            default_address=(
                CustomerAddressSummary.model_validate(default)
                if default is not None
                else None
            ),
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
