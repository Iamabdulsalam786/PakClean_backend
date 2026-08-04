"""
Seed starter categories + services (prices in PKR).

Run from pak-clean-backend (venv active):
  python -m scripts.seed_catalog

Safe to re-run: skips categories/services whose slug already exists.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.category import Category
from app.models.service import Service

# (category_slug, name, description, sort_order)
CATEGORIES: list[tuple[str, str, str, int]] = [
    ("cleaning", "Cleaning", "Home and office cleaning services", 0),
    ("plumbing", "Plumbing", "Pipes, taps, drains, and water fixtures", 1),
    ("electrical", "Electrical", "Wiring, switches, fans, and lighting", 2),
    ("ac", "AC", "AC install, service, and gas refill", 3),
]

# (category_slug, service_slug, name, description, price_pkr, duration_minutes, sort_order)
SERVICES: list[tuple[str, str, str, str, int, int, int]] = [
    # Cleaning
    (
        "cleaning",
        "home-cleaning",
        "Home Cleaning",
        "Standard home cleaning for apartments and houses",
        2500,
        120,
        0,
    ),
    (
        "cleaning",
        "deep-cleaning",
        "Deep Cleaning",
        "Thorough deep clean including kitchen and bathrooms",
        5500,
        240,
        1,
    ),
    # Plumbing
    (
        "plumbing",
        "tap-repair",
        "Tap Repair",
        "Fix leaking or faulty taps",
        1500,
        60,
        0,
    ),
    (
        "plumbing",
        "drain-unclog",
        "Drain Unclog",
        "Unclog kitchen or bathroom drains",
        2000,
        90,
        1,
    ),
    # Electrical
    (
        "electrical",
        "switch-fix",
        "Switch Fix",
        "Repair or replace faulty switches",
        1200,
        45,
        0,
    ),
    (
        "electrical",
        "fan-install",
        "Fan Install",
        "Install a ceiling or wall fan",
        1800,
        90,
        1,
    ),
    # AC
    (
        "ac",
        "ac-service",
        "AC Service",
        "Routine AC cleaning and service",
        3500,
        120,
        0,
    ),
    (
        "ac",
        "ac-gas-refill",
        "AC Gas Refill",
        "Refill AC refrigerant gas",
        6500,
        150,
        1,
    ),
]


def seed() -> None:
    db = SessionLocal()
    try:
        # --- categories ---
        category_by_slug: dict[str, Category] = {}
        for slug, name, description, sort_order in CATEGORIES:
            existing = db.scalar(select(Category).where(Category.slug == slug))
            if existing:
                category_by_slug[slug] = existing
                print(f"skip category  {slug}")
                continue

            category = Category(
                id=uuid.uuid4(),
                name=name,
                slug=slug,
                description=description,
                sort_order=sort_order,
                is_active=True,
            )
            db.add(category)
            category_by_slug[slug] = category
            print(f"add  category  {slug}")

        db.flush()

        # --- services ---
        for (
            category_slug,
            service_slug,
            name,
            description,
            price_pkr,
            duration_minutes,
            sort_order,
        ) in SERVICES:
            existing = db.scalar(select(Service).where(Service.slug == service_slug))
            if existing:
                print(f"skip service   {service_slug}")
                continue

            category = category_by_slug.get(category_slug)
            if category is None:
                raise RuntimeError(f"Missing category for slug={category_slug!r}")

            db.add(
                Service(
                    id=uuid.uuid4(),
                    category_id=category.id,
                    name=name,
                    slug=service_slug,
                    description=description,
                    price_pkr=price_pkr,
                    duration_minutes=duration_minutes,
                    sort_order=sort_order,
                    is_active=True,
                )
            )
            print(f"add  service   {service_slug}  ({price_pkr} PKR)")

        db.commit()
        print("seed complete")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
