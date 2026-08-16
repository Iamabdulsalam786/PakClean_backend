"""
Smoke-test customer profile + saved addresses against a running server.

Covers:
  - GET/PATCH /customers/me
  - create address (first becomes default)
  - list / get / patch / set-default / delete
  - delete default promotes remaining
  - address cap (10) -> 409
  - provider token cannot access customer routes -> 403

Prerequisites:
  - alembic upgrade head
  - uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Usage:
  python -m scripts.smoke_customer_addresses
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from uuid import uuid4

from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.customers.models.customer_address import CustomerAddress
from app.db.session import SessionLocal
from app.models.user import User, UserRole
# Feature models needed so Booking/ServiceListing relationship mappers resolve
# when app.models.__init__ pulls Booking into the registry.
from app.providers.models import ProviderProfile  # noqa: F401
from app.service_listings.models import (  # noqa: F401
    ServiceListing,
    ServiceListingAvailability,
    ServiceListingDiscount,
    ServiceListingImage,
    ServiceListingTag,
    Tag,
)


def http_json(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload: object = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"FAIL: cannot reach {base_url} ({exc})\n"
            "Start uvicorn on 127.0.0.1:8000 first."
        ) from exc


def cleanup(db, prefix: str) -> None:
    users = db.scalars(select(User).where(User.email.like(f"{prefix}%@example.com"))).all()
    user_ids = [u.id for u in users]
    if user_ids:
        for row in db.scalars(
            select(CustomerAddress).where(CustomerAddress.customer_id.in_(user_ids))
        ).all():
            db.delete(row)
        db.flush()
    for user in users:
        db.delete(user)
    db.commit()


def token_for(user: User) -> str:
    return create_access_token(str(user.id), extra_claims={"role": user.role.value})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url

    code, health = http_json(base, "GET", "/health")
    assert code == 200, (code, health)
    print("OK health")

    db = SessionLocal()
    suffix = uuid4().hex[:8]
    prefix = f"smoke-cust-{suffix}"

    try:
        cleanup(db, "smoke-cust-")

        customer = User(
            full_name="Address Smoke Customer",
            email=f"{prefix}-customer@example.com",
            phone=f"0933{suffix[:7]}",
            hashed_password=hash_password("x"),
            role=UserRole.CUSTOMER,
            is_verified=True,
            is_active=True,
        )
        provider = User(
            full_name="Address Smoke Provider",
            email=f"{prefix}-provider@example.com",
            phone=f"0944{suffix[:7]}",
            hashed_password=hash_password("x"),
            role=UserRole.PROVIDER,
            is_verified=True,
            is_active=True,
        )
        db.add_all([customer, provider])
        db.commit()
        db.refresh(customer)
        db.refresh(provider)

        cust_tok = token_for(customer)
        prov_tok = token_for(provider)
        print(f"OK seeded customer={customer.id}")

        # --- Provider blocked ---
        code, body = http_json(base, "GET", "/api/v1/customers/me", token=prov_tok)
        assert code == 403, (code, body)
        print("OK provider blocked from customer profile")

        # --- Profile get / patch ---
        code, body = http_json(base, "GET", "/api/v1/customers/me", token=cust_tok)
        assert code == 200 and isinstance(body, dict), (code, body)
        assert body["email"] == customer.email
        assert body["default_address"] is None
        print("OK get profile")

        code, body = http_json(
            base,
            "PATCH",
            "/api/v1/customers/me",
            token=cust_tok,
            body={"full_name": "Updated Smoke Customer"},
        )
        assert code == 200 and isinstance(body, dict), (code, body)
        assert body["full_name"] == "Updated Smoke Customer"
        print("OK patch profile")

        # --- First address becomes default ---
        code, body = http_json(
            base,
            "POST",
            "/api/v1/customers/me/addresses",
            token=cust_tok,
            body={
                "label": "Home",
                "address_line": "House 12 Street 4",
                "city": "Karachi",
                "area": "Clifton",
            },
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        home_id = body["id"]
        assert body["is_default"] is True
        print("OK create first address (auto-default)")

        code, body = http_json(base, "GET", "/api/v1/customers/me", token=cust_tok)
        assert code == 200 and isinstance(body, dict)
        assert body["default_address"] is not None
        assert body["default_address"]["id"] == home_id
        print("OK profile nests default address")

        # --- Second address + set-default ---
        code, body = http_json(
            base,
            "POST",
            "/api/v1/customers/me/addresses",
            token=cust_tok,
            body={
                "label": "Office",
                "address_line": "Office 9 I.I. Chundrigar",
                "city": "Karachi",
            },
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        office_id = body["id"]
        assert body["is_default"] is False
        print("OK create second address")

        code, body = http_json(
            base,
            "POST",
            f"/api/v1/customers/me/addresses/{office_id}/set-default",
            token=cust_tok,
        )
        assert code == 200 and isinstance(body, dict) and body["is_default"] is True, (
            code,
            body,
        )

        code, body = http_json(
            base,
            "GET",
            f"/api/v1/customers/me/addresses/{home_id}",
            token=cust_tok,
        )
        assert code == 200 and isinstance(body, dict) and body["is_default"] is False
        print("OK set-default switches default")

        # --- Patch + list ---
        code, body = http_json(
            base,
            "PATCH",
            f"/api/v1/customers/me/addresses/{home_id}",
            token=cust_tok,
            body={"landmark": "Near cafe"},
        )
        assert code == 200 and isinstance(body, dict)
        assert body["landmark"] == "Near cafe"
        print("OK patch address")

        code, body = http_json(base, "GET", "/api/v1/customers/me/addresses", token=cust_tok)
        assert code == 200 and isinstance(body, dict)
        assert body["total"] == 2
        assert len(body["items"]) == 2
        print("OK list addresses")

        # --- Delete default promotes remaining ---
        code, body = http_json(
            base,
            "DELETE",
            f"/api/v1/customers/me/addresses/{office_id}",
            token=cust_tok,
        )
        assert code == 204, (code, body)

        code, body = http_json(
            base,
            "GET",
            f"/api/v1/customers/me/addresses/{home_id}",
            token=cust_tok,
        )
        assert code == 200 and isinstance(body, dict) and body["is_default"] is True
        print("OK delete default promotes remaining")

        # --- Cap at 10 ---
        # home still exists (1); create 9 more -> total 10; 11th must 409
        for i in range(9):
            code, body = http_json(
                base,
                "POST",
                "/api/v1/customers/me/addresses",
                token=cust_tok,
                body={
                    "label": f"Extra {i}",
                    "address_line": f"Extra address line number {i} xx",
                    "city": "Lahore",
                },
            )
            assert code == 201, (i, code, body)

        code, body = http_json(
            base,
            "POST",
            "/api/v1/customers/me/addresses",
            token=cust_tok,
            body={
                "label": "Overflow",
                "address_line": "This should be rejected by the cap rule",
                "city": "Islamabad",
            },
        )
        assert code == 409, (code, body)
        print("OK address cap returns 409")

        print("\nALL CUSTOMER ADDRESS CHECKS PASSED")
        return 0
    except AssertionError as exc:
        print(f"\nFAIL assertion: {exc}")
        return 1
    finally:
        cleanup(db, "smoke-cust-")
        print("OK cleaned smoke users")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
