"""
Smoke-test marketplace booking lifecycle against a running server.

Covers:
  - customer books ACTIVE listing by listing_id (PENDING + snapshots)
  - book via saved address_id (snapshot address_text)
  - foreign/unknown address_id -> 404; both address fields -> 422
  - provider pending inbox
  - accept -> start -> complete
  - reject path (separate booking)
  - customer cancel (pending)
  - complete without start -> 409
  - draft listing cannot be booked -> 404

Prerequisites:
  - alembic upgrade head
  - python -m scripts.seed_catalog
  - uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Usage:
  python -m scripts.smoke_marketplace_bookings
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.customers.models.customer_address import CustomerAddress
from app.db.session import SessionLocal
from app.models.booking import Booking
from app.models.category import Category
from app.models.user import User, UserRole
from app.providers.models.provider_profile import ProviderProfile
from app.providers.schemas.provider_profile import (
    AdminVerifyProviderRequest,
    ProviderProfileCreate,
)
from app.providers.services.provider_profile_service import ProviderProfileService
from app.service_listings.models.service_listing import ServiceListing
from app.service_listings.schemas.service_listing import ServiceListingCreate
from app.service_listings.services.service_listing_service import ServiceListingService


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
        bookings = db.scalars(
            select(Booking).where(
                (Booking.customer_id.in_(user_ids)) | (Booking.provider_id.in_(user_ids))
            )
        ).all()
        for booking in bookings:
            db.delete(booking)
        for address in db.scalars(
            select(CustomerAddress).where(CustomerAddress.customer_id.in_(user_ids))
        ).all():
            db.delete(address)
        db.flush()

    for user in users:
        profile = db.scalar(select(ProviderProfile).where(ProviderProfile.user_id == user.id))
        if profile is not None:
            for listing in db.scalars(
                select(ServiceListing).where(ServiceListing.provider_id == profile.id)
            ).all():
                db.delete(listing)
            db.delete(profile)
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
    prefix = f"smoke-book-{suffix}"

    try:
        cleanup(db, "smoke-book-")

        category = db.scalar(select(Category).where(Category.is_active.is_(True)).limit(1))
        if category is None:
            print("FAIL: seed catalog first (python -m scripts.seed_catalog)")
            return 1

        admin = User(
            full_name="Booking Smoke Admin",
            email=f"{prefix}-admin@example.com",
            phone=f"0900{suffix[:7]}",
            hashed_password=hash_password("x"),
            role=UserRole.ADMIN,
            is_verified=True,
            is_active=True,
        )
        provider = User(
            full_name="Booking Smoke Provider",
            email=f"{prefix}-provider@example.com",
            phone=f"0911{suffix[:7]}",
            hashed_password=hash_password("x"),
            role=UserRole.PROVIDER,
            is_verified=True,
            is_active=True,
        )
        customer = User(
            full_name="Booking Smoke Customer",
            email=f"{prefix}-customer@example.com",
            phone=f"0922{suffix[:7]}",
            hashed_password=hash_password("x"),
            role=UserRole.CUSTOMER,
            is_verified=True,
            is_active=True,
        )
        db.add_all([admin, provider, customer])
        db.commit()
        db.refresh(admin)
        db.refresh(provider)
        db.refresh(customer)

        psvc = ProviderProfileService(db)
        lsvc = ServiceListingService(db)

        profile = psvc.create_profile(
            provider,
            ProviderProfileCreate(business_name="Booking Smoke Co", city="Karachi"),
        )
        psvc.verify_provider(admin, profile.id, AdminVerifyProviderRequest())

        draft = lsvc.create_listing(
            provider,
            ServiceListingCreate(
                category_id=category.id,
                title="HIDDEN Draft Booking Listing",
                description="Draft must not be bookable via marketplace bookings API",
                base_price=2000,
                estimated_duration=60,
                city="Karachi",
                address="Hidden Ave 1",
            ),
        )
        active = lsvc.create_listing(
            provider,
            ServiceListingCreate(
                category_id=category.id,
                title="Deep Kitchen Cleaning",
                description="Full kitchen deep clean for Booking Smoke Co customers",
                base_price=4500,
                estimated_duration=90,
                city="Karachi",
                address="Clifton Block 5",
            ),
        )
        active = lsvc.publish_listing(provider, active.id)
        listing_id = str(active.id)
        print(f"OK seeded draft={draft.id} active={listing_id}")

        cust_tok = token_for(customer)
        prov_tok = token_for(provider)
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

        # --- Draft not bookable ---
        code, body = http_json(
            base,
            "POST",
            "/api/v1/bookings",
            token=cust_tok,
            body={
                "listing_id": str(draft.id),
                "scheduled_at": future,
                "address_text": "House 12 Street 4",
            },
        )
        assert code == 404, (code, body)
        print("OK draft listing not bookable")

        # --- Create PENDING + snapshots ---
        code, body = http_json(
            base,
            "POST",
            "/api/v1/bookings",
            token=cust_tok,
            body={
                "listing_id": listing_id,
                "scheduled_at": future,
                "address_text": "House 12 Street 4 Clifton",
                "notes": "Please bring supplies",
            },
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        booking_id = body["id"]
        assert body["status"] == "pending"
        assert body["listing_id"] == listing_id
        assert body["provider_id"] == str(provider.id)
        assert body["price_pkr"] == 4500
        assert body["duration_minutes"] == 90
        assert body["listing_title_snapshot"] == "Deep Kitchen Cleaning"
        print("OK create PENDING with snapshots")

        # --- Provider pending inbox ---
        code, body = http_json(
            base,
            "GET",
            "/api/v1/bookings/provider/pending",
            token=prov_tok,
        )
        assert code == 200 and isinstance(body, list), (code, body)
        assert any(b["id"] == booking_id for b in body)
        print("OK provider pending inbox")

        # --- Complete without start → 409 ---
        code, body = http_json(
            base,
            "POST",
            f"/api/v1/bookings/{booking_id}/complete",
            token=prov_tok,
        )
        assert code == 409, (code, body)
        print("OK complete-from-pending rejected (409)")

        # --- Accept → start → complete ---
        code, body = http_json(
            base,
            "POST",
            f"/api/v1/bookings/{booking_id}/accept",
            token=prov_tok,
        )
        assert code == 200 and isinstance(body, dict) and body["status"] == "confirmed", (
            code,
            body,
        )
        print("OK accept -> confirmed")

        code, body = http_json(
            base,
            "POST",
            f"/api/v1/bookings/{booking_id}/start",
            token=prov_tok,
        )
        assert code == 200 and isinstance(body, dict) and body["status"] == "in_progress", (
            code,
            body,
        )
        print("OK start -> in_progress")

        code, body = http_json(
            base,
            "POST",
            f"/api/v1/bookings/{booking_id}/complete",
            token=prov_tok,
        )
        assert code == 200 and isinstance(body, dict) and body["status"] == "completed", (
            code,
            body,
        )
        print("OK complete -> completed")

        db.expire_all()
        refreshed = db.get(ServiceListing, active.id)
        assert refreshed is not None and refreshed.booking_count >= 1
        print("OK listing.booking_count bumped")

        # --- Reject path (separate booking) ---
        code, body = http_json(
            base,
            "POST",
            "/api/v1/bookings",
            token=cust_tok,
            body={
                "listing_id": listing_id,
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                "address_text": "Flat 3 DHA Phase 6",
            },
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        reject_id = body["id"]

        code, body = http_json(
            base,
            "POST",
            f"/api/v1/bookings/{reject_id}/reject",
            token=prov_tok,
            body={"rejection_reason": "Fully booked that day"},
        )
        assert code == 200 and isinstance(body, dict) and body["status"] == "rejected", (
            code,
            body,
        )
        print("OK reject -> rejected")

        # --- Customer cancel pending ---
        code, body = http_json(
            base,
            "POST",
            "/api/v1/bookings",
            token=cust_tok,
            body={
                "listing_id": listing_id,
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
                "address_text": "Office 9 I.I. Chundrigar",
            },
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        cancel_id = body["id"]

        code, body = http_json(
            base,
            "POST",
            f"/api/v1/bookings/{cancel_id}/cancel",
            token=cust_tok,
        )
        assert code == 200 and isinstance(body, dict) and body["status"] == "cancelled", (
            code,
            body,
        )
        print("OK customer cancel -> cancelled")

        # --- Book via saved address_id ---
        code, body = http_json(
            base,
            "POST",
            "/api/v1/customers/me/addresses",
            token=cust_tok,
            body={
                "label": "Home",
                "address_line": "House 99 Beach Avenue",
                "city": "Karachi",
                "area": "Clifton",
                "landmark": "Near park",
            },
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        address_id = body["id"]

        code, body = http_json(
            base,
            "POST",
            "/api/v1/bookings",
            token=cust_tok,
            body={
                "listing_id": listing_id,
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                "address_id": address_id,
            },
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        assert "House 99 Beach Avenue" in body["address_text"]
        assert "Karachi" in body["address_text"]
        assert "Clifton" in body["address_text"]
        print("OK book via address_id (snapshot text)")

        # --- Foreign / unknown address_id -> 404 ---
        code, body = http_json(
            base,
            "POST",
            "/api/v1/bookings",
            token=cust_tok,
            body={
                "listing_id": listing_id,
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
                "address_id": str(uuid4()),
            },
        )
        assert code == 404, (code, body)
        print("OK unknown address_id -> 404")

        # --- XOR: both address fields -> 422 ---
        code, body = http_json(
            base,
            "POST",
            "/api/v1/bookings",
            token=cust_tok,
            body={
                "listing_id": listing_id,
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "address_id": address_id,
                "address_text": "Should not be allowed together",
            },
        )
        assert code == 422, (code, body)
        print("OK both address fields -> 422")

        print("\nALL MARKETPLACE BOOKING CHECKS PASSED")
        return 0
    except AssertionError as exc:
        print(f"\nFAIL assertion: {exc}")
        return 1
    finally:
        cleanup(db, "smoke-book-")
        print("OK cleaned smoke users")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
