"""
Smoke-test reviews against a running server.

Covers:
  - review incomplete booking -> 409
  - complete booking then create review -> 201
  - listing average_rating + provider total_reviews updated
  - duplicate review -> 409
  - public listing reviews feed
  - GET /reviews/me

Prerequisites:
  - alembic upgrade head
  - python -m scripts.seed_catalog
  - uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Usage:
  python -m scripts.smoke_reviews
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.core.security import create_access_token, hash_password
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
from app.reviews.models.review import Review
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
        for review in db.scalars(
            select(Review).where(
                (Review.customer_id.in_(user_ids)) | (Review.provider_id.in_(user_ids))
            )
        ).all():
            db.delete(review)
        db.flush()
        for booking in db.scalars(
            select(Booking).where(
                (Booking.customer_id.in_(user_ids)) | (Booking.provider_id.in_(user_ids))
            )
        ).all():
            db.delete(booking)
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
    prefix = f"smoke-rev-{suffix}"

    try:
        cleanup(db, "smoke-rev-")

        category = db.scalar(select(Category).where(Category.is_active.is_(True)).limit(1))
        if category is None:
            print("FAIL: seed catalog first (python -m scripts.seed_catalog)")
            return 1

        admin = User(
            full_name="Review Smoke Admin",
            email=f"{prefix}-admin@example.com",
            phone=f"0950{suffix[:7]}",
            hashed_password=hash_password("x"),
            role=UserRole.ADMIN,
            is_verified=True,
            is_active=True,
        )
        provider = User(
            full_name="Review Smoke Provider",
            email=f"{prefix}-provider@example.com",
            phone=f"0951{suffix[:7]}",
            hashed_password=hash_password("x"),
            role=UserRole.PROVIDER,
            is_verified=True,
            is_active=True,
        )
        customer = User(
            full_name="Review Smoke Customer",
            email=f"{prefix}-customer@example.com",
            phone=f"0952{suffix[:7]}",
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
            ProviderProfileCreate(business_name="Review Smoke Co", city="Lahore"),
        )
        psvc.verify_provider(admin, profile.id, AdminVerifyProviderRequest())
        listing = lsvc.create_listing(
            provider,
            ServiceListingCreate(
                category_id=category.id,
                title="Review Smoke Deep Clean",
                description="Listing used only for review smoke lifecycle checks",
                base_price=3000,
                estimated_duration=60,
                city="Lahore",
                address="Model Town Block A",
            ),
        )
        listing = lsvc.publish_listing(provider, listing.id)
        listing_id = str(listing.id)
        print(f"OK seeded listing={listing_id}")

        cust_tok = token_for(customer)
        prov_tok = token_for(provider)
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

        # Create pending booking
        code, body = http_json(
            base,
            "POST",
            "/api/v1/bookings",
            token=cust_tok,
            body={
                "listing_id": listing_id,
                "scheduled_at": future,
                "address_text": "House 7 Review Street Lahore",
            },
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        booking_id = body["id"]

        # Review before complete -> 409
        code, body = http_json(
            base,
            "POST",
            "/api/v1/reviews",
            token=cust_tok,
            body={"booking_id": booking_id, "rating": 5, "comment": "Too early"},
        )
        assert code == 409, (code, body)
        print("OK review before complete -> 409")

        # Complete lifecycle
        for action in ("accept", "start", "complete"):
            code, body = http_json(
                base,
                "POST",
                f"/api/v1/bookings/{booking_id}/{action}",
                token=prov_tok,
            )
            assert code == 200, (action, code, body)
        print("OK booking completed")

        # Create review
        code, body = http_json(
            base,
            "POST",
            "/api/v1/reviews",
            token=cust_tok,
            body={
                "booking_id": booking_id,
                "rating": 5,
                "comment": "Excellent cleaning service",
            },
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        assert body["rating"] == 5
        assert body["listing_id"] == listing_id
        review_id = body["id"]
        print("OK create review")

        # Denormalized averages
        db.expire_all()
        refreshed_listing = db.get(ServiceListing, listing.id)
        refreshed_profile = db.get(ProviderProfile, profile.id)
        assert refreshed_listing is not None
        assert refreshed_profile is not None
        assert Decimal(str(refreshed_listing.average_rating)) == Decimal("5.00")
        assert Decimal(str(refreshed_profile.average_rating)) == Decimal("5.00")
        assert refreshed_profile.total_reviews == 1
        print("OK listing + provider averages updated")

        # Duplicate -> 409
        code, body = http_json(
            base,
            "POST",
            "/api/v1/reviews",
            token=cust_tok,
            body={"booking_id": booking_id, "rating": 4},
        )
        assert code == 409, (code, body)
        print("OK duplicate review -> 409")

        # Public feed
        code, body = http_json(
            base,
            "GET",
            f"/api/v1/marketplace/listings/{listing_id}/reviews",
        )
        assert code == 200 and isinstance(body, dict), (code, body)
        assert body["total"] >= 1
        assert any(i["id"] == review_id for i in body["items"])
        print("OK public listing reviews feed")

        # Mine
        code, body = http_json(base, "GET", "/api/v1/reviews/me", token=cust_tok)
        assert code == 200 and isinstance(body, dict), (code, body)
        assert any(i["id"] == review_id for i in body["items"])
        print("OK reviews/me")

        print("\nALL REVIEW CHECKS PASSED")
        return 0
    except AssertionError as exc:
        print(f"\nFAIL assertion: {exc}")
        return 1
    finally:
        cleanup(db, "smoke-rev-")
        print("OK cleaned smoke users")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
