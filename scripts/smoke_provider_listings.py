"""
Smoke-test provider service-listing APIs against a running server.

Prerequisites:
  1. Postgres up, migrations applied (alembic upgrade head)
  2. Catalog seeded (python -m scripts.seed_catalog) — needs at least one category
  3. API running: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Usage (from pak-clean-backend, venv active):
  python -m scripts.smoke_provider_listings
  python -m scripts.smoke_provider_listings --base-url http://127.0.0.1:8000
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


def cleanup_smoke_users(db, prefix: str) -> None:
    users = db.scalars(select(User).where(User.email.like(f"{prefix}%@example.com"))).all()
    for user in users:
        profile = db.scalar(select(ProviderProfile).where(ProviderProfile.user_id == user.id))
        if profile is not None:
            listings = db.scalars(
                select(ServiceListing).where(ServiceListing.provider_id == profile.id)
            ).all()
            for listing in listings:
                db.delete(listing)
            db.delete(profile)
        db.delete(user)
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test provider listing APIs")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Running API base URL",
    )
    parser.add_argument(
        "--keep-users",
        action="store_true",
        help="Do not delete smoke users at the end",
    )
    args = parser.parse_args()
    base = args.base_url

    # Health check
    try:
        code, health = http_json(base, "GET", "/health")
    except urllib.error.URLError as exc:
        print(f"FAIL: cannot reach {base}/health")
        print(f"       {exc}")
        print()
        print("Start the API in another terminal first:")
        print("  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
        print()
        print("Then re-run:")
        print("  python -m scripts.smoke_provider_listings")
        return 1
    if code != 200:
        print(f"FAIL: API not healthy at {base}/health ({code})")
        return 1
    print(f"OK health {health}")

    db = SessionLocal()
    suffix = uuid4().hex[:8]
    prefix = f"smoke-listing-cli-{suffix}"

    try:
        cleanup_smoke_users(db, "smoke-listing-cli-")

        category = db.scalar(select(Category).where(Category.is_active.is_(True)).limit(1))
        if category is None:
            print("FAIL: no active category. Run: python -m scripts.seed_catalog")
            return 1
        print(f"OK category {category.name} ({category.id})")

        admin = User(
            full_name="Smoke CLI Admin",
            email=f"{prefix}-admin@example.com",
            phone=f"0700{suffix[:7]}",
            hashed_password=hash_password("SmokeAdmin1!"),
            role=UserRole.ADMIN,
            is_verified=True,
            is_active=True,
        )
        provider = User(
            full_name="Smoke CLI Provider",
            email=f"{prefix}-provider@example.com",
            phone=f"0711{suffix[:7]}",
            hashed_password=hash_password("SmokeProv1!"),
            role=UserRole.PROVIDER,
            is_verified=True,
            is_active=True,
        )
        db.add_all([admin, provider])
        db.commit()
        db.refresh(admin)
        db.refresh(provider)

        psvc = ProviderProfileService(db)
        profile = psvc.create_profile(
            provider,
            ProviderProfileCreate(
                business_name="CLI Smoke Cleaners",
                city="Lahore",
                bio="Automated smoke test profile",
            ),
        )
        psvc.verify_provider(admin, profile.id, AdminVerifyProviderRequest(note="cli smoke"))
        print(f"OK provider verified profile_id={profile.id}")

        provider_token = create_access_token(
            str(provider.id),
            extra_claims={"role": provider.role.value},
        )

        # 1) CREATE
        create_body = {
            "category_id": str(category.id),
            "title": "AC Deep Clean CLI",
            "description": "Full AC cleaning service for homes and offices",
            "base_price": 2500,
            "estimated_duration": 90,
            "city": "Lahore",
            "address": "DHA Phase 5, Block A",
        }
        code, body = http_json(
            base,
            "POST",
            "/api/v1/provider/service-listings",
            token=provider_token,
            body=create_body,
        )
        assert code == 201 and isinstance(body, dict), (code, body)
        assert body["status"] == "draft"
        listing_id = body["id"]
        print(f"OK POST create draft listing_id={listing_id}")

        # 2) LIST
        code, body = http_json(
            base,
            "GET",
            "/api/v1/provider/service-listings",
            token=provider_token,
        )
        assert code == 200 and isinstance(body, dict), (code, body)
        assert any(item["id"] == listing_id for item in body["items"])
        print("OK GET list mine")

        # 3) PATCH
        code, body = http_json(
            base,
            "PATCH",
            f"/api/v1/provider/service-listings/{listing_id}",
            token=provider_token,
            body={"base_price": 2700, "title": "AC Deep Clean CLI Updated"},
        )
        assert code == 200 and isinstance(body, dict), (code, body)
        assert body["base_price"] == 2700
        print("OK PATCH update")

        # 4) PUBLISH
        code, body = http_json(
            base,
            "POST",
            f"/api/v1/provider/service-listings/{listing_id}/publish",
            token=provider_token,
        )
        assert code == 200 and isinstance(body, dict) and body["status"] == "active"
        print("OK POST publish")

        # Public browse
        code, body = http_json(base, "GET", f"/api/v1/service-listings/{listing_id}")
        assert code == 200 and isinstance(body, dict)
        print("OK public GET after publish")

        # 5) DEACTIVATE (= pause)
        code, body = http_json(
            base,
            "POST",
            f"/api/v1/provider/service-listings/{listing_id}/deactivate",
            token=provider_token,
        )
        assert code == 200 and isinstance(body, dict) and body["status"] == "inactive"
        print("OK POST deactivate (pause)")

        code, body = http_json(base, "GET", f"/api/v1/service-listings/{listing_id}")
        assert code == 404
        print("OK public hidden while inactive")

        # Re-publish then soft-delete
        code, body = http_json(
            base,
            "POST",
            f"/api/v1/provider/service-listings/{listing_id}/publish",
            token=provider_token,
        )
        assert code == 200
        print("OK re-publish")

        # 6) DELETE
        code, body = http_json(
            base,
            "DELETE",
            f"/api/v1/provider/service-listings/{listing_id}",
            token=provider_token,
        )
        assert code == 204, (code, body)
        print("OK DELETE soft-delete")

        code, body = http_json(base, "GET", f"/api/v1/service-listings/{listing_id}")
        assert code == 404
        print("OK public hidden after delete")

        print("\nALL PROVIDER LISTING API CHECKS PASSED")
        return 0
    except AssertionError as exc:
        print(f"\nFAIL assertion: {exc}")
        return 1
    finally:
        if not args.keep_users:
            cleanup_smoke_users(db, "smoke-listing-cli-")
            print("OK cleaned smoke users")
        db.close()


if __name__ == "__main__":
    sys.exit(main())
