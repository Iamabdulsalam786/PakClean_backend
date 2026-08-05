"""
CustomerAddressRepository — SQL access for customer_addresses.

Layering (Clean Architecture / feature module):
  API → CustomerService → this repository → Postgres

This class owns QUERIES and persistence only.
It must NOT decide address caps, default-address policy, or RBAC
(that is service-layer authorization + business rules).

Feature path: app/customers/repositories/
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.customers.models.customer_address import CustomerAddress


class CustomerAddressRepository:
    """Thin data-access layer around CustomerAddress rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, address_id: UUID) -> CustomerAddress | None:
        """Primary-key lookup (no ownership check — service must filter)."""
        return self._db.get(CustomerAddress, address_id)

    def get_for_customer(
        self,
        address_id: UUID,
        customer_id: UUID,
    ) -> CustomerAddress | None:
        """Load one address only if it belongs to the customer (IDOR-safe helper)."""
        statement = select(CustomerAddress).where(
            CustomerAddress.id == address_id,
            CustomerAddress.customer_id == customer_id,
        )
        return self._db.scalar(statement)

    def list_for_customer(self, customer_id: UUID) -> list[CustomerAddress]:
        """All saved addresses for one customer (default first, then newest)."""
        statement = (
            select(CustomerAddress)
            .where(CustomerAddress.customer_id == customer_id)
            .order_by(
                CustomerAddress.is_default.desc(),
                CustomerAddress.created_at.desc(),
            )
        )
        return list(self._db.scalars(statement).all())

    def count_for_customer(self, customer_id: UUID) -> int:
        """Used by the service to enforce max addresses per customer."""
        statement = (
            select(func.count())
            .select_from(CustomerAddress)
            .where(CustomerAddress.customer_id == customer_id)
        )
        return int(self._db.scalar(statement) or 0)

    def get_default_for_customer(self, customer_id: UUID) -> CustomerAddress | None:
        """Return the default address, if any."""
        statement = (
            select(CustomerAddress)
            .where(
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.is_default.is_(True),
            )
            .limit(1)
        )
        return self._db.scalar(statement)

    def clear_defaults_for_customer(self, customer_id: UUID) -> None:
        """
        Set is_default=False for all of this customer's addresses.

        Call before marking a new default so at most one remains True.
        Does not commit — service owns the transaction.
        """
        self._db.execute(
            update(CustomerAddress)
            .where(
                CustomerAddress.customer_id == customer_id,
                CustomerAddress.is_default.is_(True),
            )
            .values(is_default=False)
        )

    def add(
        self,
        *,
        customer_id: UUID,
        label: str,
        address_line: str,
        city: str,
        area: str | None = None,
        landmark: str | None = None,
        latitude: Decimal | None = None,
        longitude: Decimal | None = None,
        is_default: bool = False,
    ) -> CustomerAddress:
        """Insert a new address row (not committed)."""
        address = CustomerAddress(
            customer_id=customer_id,
            label=label,
            address_line=address_line,
            city=city,
            area=area,
            landmark=landmark,
            latitude=latitude,
            longitude=longitude,
            is_default=is_default,
        )
        self._db.add(address)
        return address

    def save(self, address: CustomerAddress) -> CustomerAddress:
        """Persist in-memory field changes. Does not commit."""
        self._db.add(address)
        return address

    def delete(self, address: CustomerAddress) -> None:
        """Hard-delete an address row. Does not commit."""
        self._db.delete(address)
