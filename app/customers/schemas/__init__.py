"""customers.schemas — Pydantic DTOs for the customer feature."""

from app.customers.schemas.customer import (
    CustomerAddressCreate,
    CustomerAddressListResponse,
    CustomerAddressRead,
    CustomerAddressSummary,
    CustomerAddressUpdate,
    CustomerProfileRead,
    CustomerProfileUpdate,
)

__all__ = [
    "CustomerAddressCreate",
    "CustomerAddressListResponse",
    "CustomerAddressRead",
    "CustomerAddressSummary",
    "CustomerAddressUpdate",
    "CustomerProfileRead",
    "CustomerProfileUpdate",
]
