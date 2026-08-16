"""
Smoke-test marketplace discovery APIs against a running server.

Covers: browse, detail, pagination, search, filtering, sorting.
Hides draft/inactive from public feed.

Prerequisites:
  - alembic upgrade head
  - python -m scripts.seed_catalog
  - uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Usage:
  python -m scripts.smoke_marketplace_discovery
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import time
from uuid import uuid4

from sqlalchemy import select

from app.core.security import create_access_token, hash_password
from app.db.session import SessionLocal
from app.models.category import Category
from app.models.user import User, UserRole
from app.providers.models.provider_profile import ProviderProfile
from app.providers.schemas.provider_profile import (
    AdminVerifyProviderRequest,
    ProviderProfileCreate,
)
from app.providers.services.provider_profile_service import ProviderProfileService
from app.service_listings.models.service_listing import ServiceListing
from app.service_listings.schemas.listing_extras import AvailabilityCreate
from app.service_listings.schemas.service_listing import ServiceListingCreate
from app.service_listings.services.listing_extras_service import ListingExtrasService
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
    prefix = f"smoke-discovery-{suffix}"

    try:
        cleanup(db, "smoke-discovery-")

        category = db.scalar(select(Category).where(Category.is_active.is_(True)).limit(1))
        if category is None:
            print("FAIL: seed catalog first")
            return 1

        admin = User(
            full_name="Discovery Admin",
            email=f"{prefix}-admin@example.com",
            phone=f"0800{suffix[:7]}",
            hashed_password=hash_password("x"),
            role=UserRole.ADMIN,
            is_verified=True,
            is_active=True,
        )
        provider = User(
            full_name="Discovery Provider",
            email=f"{prefix}-provider@example.com",
            phone=f"0811{suffix[:7]}",
            hashed_password=hash_password("x"),
            role=UserRole.PROVIDER,
            is_verified=True,
            is_active=True,
        )
        db.add_all([admin, provider])
        db.commit()
        db.refresh(admin)
        db.refresh(provider)

        psvc = ProviderProfileService(db)
        lsvc = ServiceListingService(db)
        xsvc = ListingExtrasService(db)

        profile = psvc.create_profile(
            provider,
            ProviderProfileCreate(
                business_name="Discovery Smoke Co",
                city="Lahore",
            ),
        )
        psvc.verify_provider(admin, profile.id, AdminVerifyProviderRequest())

        # Draft should NEVER appear in marketplace
        draft = lsvc.create_listing(
            provider,
            ServiceListingCreate(
                category_id=category.id,
                title="HIDDEN Draft Cleaning",
                description="This draft must not appear in marketplace browse results",
                base_price=1000,
                estimated_duration=60,
                city="Lahore",
                address="Hidden Street 1",
            ),
        )

        active = lsvc.create_listing(
            provider,
            ServiceListingCreate(
                category_id=category.id,
                title="Marketplace Sofa Cleaning",
                description="Professional sofa deep cleaning for Discovery Smoke Co customers",
                base_price=3500,
                estimated_duration=120,
                city="Lahore",
                address="Gulberg III",
            ),
        )
        active = lsvc.publish_listing(provider, active.id)
        listing_id = str(active.id)

        cheaper = lsvc.create_listing(
            provider,
            ServiceListingCreate(
                category_id=category.id,
                title="Marketplace Quick Dusting",
                description="Quick dusting service by Discovery Smoke Co in Lahore",
                base_price=1500,
                estimated_duration=45,
                city="Lahore",
                address="Gulberg III",
            ),
        )
        cheaper = lsvc.publish_listing(provider, cheaper.id)

        xsvc.add_availability(
            provider,
            active.id,
            AvailabilityCreate(
                day_of_week=1,
                start_time=time(10, 0),
                end_time=time(14, 0),
            ),
        )
        print(f"OK seeded draft={draft.id} active={listing_id} cheaper={cheaper.id}")

        # --- Browse ---
        code, body = http_json(base, "GET", "/api/v1/marketplace/listings?city=Lahore")
        assert code == 200 and isinstance(body, dict), (code, body)
        ids = {item["id"] for item in body["items"]}
        assert listing_id in ids
        assert str(draft.id) not in ids
        assert "total_pages" in body
        assert "provider" in body["items"][0]
        assert "category" in body["items"][0]
        print("OK browse (active only, nested provider/category, total_pages)")

        # --- Detail ---
        code, body = http_json(base, "GET", f"/api/v1/marketplace/listings/{listing_id}")
        assert code == 200 and isinstance(body, dict), (code, body)
        assert body["title"] == "Marketplace Sofa Cleaning"
        assert body["provider"]["business_name"] == "Discovery Smoke Co"
        assert body["category"]["id"] == str(category.id)
        assert isinstance(body["availability"], list) and len(body["availability"]) >= 1
        print("OK detail aggregate")

        # Draft detail must 404
        code, body = http_json(base, "GET", f"/api/v1/marketplace/listings/{draft.id}")
        assert code == 404, (code, body)
        print("OK draft detail hidden")

        # --- Pagination ---
        code, body = http_json(
            base,
            "GET",
            "/api/v1/marketplace/listings?city=Lahore&page=1&page_size=1",
        )
        assert code == 200 and isinstance(body, dict)
        assert body["page"] == 1 and body["page_size"] == 1
        assert len(body["items"]) == 1
        assert body["total"] >= 2
        assert body["total_pages"] >= 2
        print("OK pagination")

        # --- Search (title / description / provider name) ---
        code, body = http_json(
            base,
            "GET",
            "/api/v1/marketplace/listings/search?q=Sofa",
        )
        assert code == 200 and isinstance(body, dict)
        assert any(i["id"] == listing_id for i in body["items"])
        print("OK search title")

        code, body = http_json(
            base,
            "GET",
            "/api/v1/marketplace/listings/search?q=Discovery%20Smoke",
        )
        assert code == 200 and isinstance(body, dict)
        assert any(i["id"] == listing_id for i in body["items"])
        print("OK search provider name")

        # --- Filter price ---
        code, body = http_json(
            base,
            "GET",
            "/api/v1/marketplace/listings?city=Lahore&min_price=3000&max_price=4000",
        )
        assert code == 200 and isinstance(body, dict)
        ids = {i["id"] for i in body["items"]}
        assert listing_id in ids
        assert str(cheaper.id) not in ids
        print("OK filter price range")

        # --- Filter availability ---
        code, body = http_json(
            base,
            "GET",
            "/api/v1/marketplace/listings?city=Lahore&available_on=1",
        )
        assert code == 200 and isinstance(body, dict)
        ids = {i["id"] for i in body["items"]}
        assert listing_id in ids
        print("OK filter available_on")

        # --- Sort price asc ---
        code, body = http_json(
            base,
            "GET",
            "/api/v1/marketplace/listings?city=Lahore&q=Marketplace&sort=price_asc",
        )
        assert code == 200 and isinstance(body, dict)
        prices = [i["base_price"] for i in body["items"]]
        assert prices == sorted(prices)
        print("OK sort price_asc")

        # --- Pause hides from feed ---
        token = create_access_token(
            str(provider.id),
            extra_claims={"role": "provider"},
        )
        code, body = http_json(
            base,
            "POST",
            f"/api/v1/provider/service-listings/{listing_id}/deactivate",
            token=token,
        )
        assert code == 200, (code, body)

        code, body = http_json(base, "GET", f"/api/v1/marketplace/listings/{listing_id}")
        assert code == 404
        print("OK paused listing hidden from marketplace")

        print("\nALL MARKETPLACE DISCOVERY CHECKS PASSED")
        return 0
    except AssertionError as exc:
        print(f"\nFAIL assertion: {exc}")
        return 1
    finally:
        cleanup(db, "smoke-discovery-")
        print("OK cleaned smoke users")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
