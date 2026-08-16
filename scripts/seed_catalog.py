"""
Seed catalog categories for the marketplace taxonomy.

Run from pak-clean-backend (venv active):
  python -m scripts.seed_catalog

Safe to re-run: updates existing categories by slug; skips unknown rows.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.session import SessionLocal

# Register all ORM models before Session use.
from app.customers.models import CustomerAddress  # noqa: F401
from app.models import Booking, Category  # noqa: F401
from app.providers.models import ProviderProfile  # noqa: F401
from app.reviews.models import Review  # noqa: F401
from app.service_listings.models import (  # noqa: F401
    ServiceListing,
    ServiceListingAvailability,
    ServiceListingDiscount,
    ServiceListingImage,
    ServiceListingTag,
)

# (category_slug, name, description, sort_order)
CATEGORIES: list[tuple[str, str, str, int]] = [
    ("cleaning", "Cleaning", "Home and office cleaning services", 0),
    ("laundry", "Laundry", "Wash, iron, and dry-clean pickup services", 1),
    ("sofa-carpet-cleaning", "Sofa & Carpet Cleaning", "Sofa, carpet, and mattress deep cleaning", 2),
    ("disinfection", "Disinfection", "Home sanitization and fumigation", 3),
    ("pest-control", "Pest Control", "Cockroach, termite, and rodent treatment", 4),
    ("plumbing", "Plumbing", "Pipes, taps, drains, and water fixtures", 10),
    ("water-tank", "Water Tank Cleaning", "Overhead and underground tank cleaning", 11),
    ("water-purifier", "Water Purifier", "RO / filter install and service", 12),
    ("electrical", "Electrical", "Wiring, switches, fans, and lighting", 20),
    ("ac", "AC & Cooling", "AC install, service, gas refill, and cooling repair", 21),
    ("fridge-appliance", "Fridge & Appliance Repair", "Fridge, freezer, and kitchen appliance repair", 22),
    ("washing-machine", "Washing Machine Repair", "Washer and dryer repair and service", 23),
    ("microwave-oven", "Microwave & Oven Repair", "Microwave, oven, and hob repair", 24),
    ("generator-solar", "Generator & Solar", "Generator, UPS, and solar panel service", 25),
    ("cctv-security", "CCTV & Security", "CCTV, door camera, and alarm installation", 30),
    ("tv-electronics", "TV & Electronics Repair", "TV, sound system, and electronics repair", 31),
    ("computer-mobile", "Computer & Mobile Repair", "Laptop, PC, and phone repair at home", 32),
    ("carpentry", "Carpentry", "Furniture repair, doors, and wood work", 40),
    ("painting", "Painting", "Interior and exterior wall painting", 41),
    ("tiles-masonry", "Tiles & Masonry", "Tile fixing, marble, and masonry work", 42),
    ("glass-aluminum", "Glass & Aluminum", "Windows, mirrors, and aluminum work", 43),
    ("welding", "Welding & Fabrication", "Gates, grills, and metal fabrication", 44),
    ("interior-design", "Interior Design", "Room makeovers and interior consultation", 45),
    ("gardening", "Gardening", "Lawn, plants, and garden maintenance", 50),
    ("moving-shifting", "Moving & Shifting", "Home packing, loading, and relocation help", 51),
    ("packaging-design", "Packaging Design", "Custom packaging and label design services", 52),
    ("handyman", "Handyman", "General home fixes and small jobs", 53),
    ("event-support", "Event Support", "Pre/post event cleaning and setup help", 54),
]


def seed() -> None:
    db = SessionLocal()
    try:
        for slug, name, description, sort_order in CATEGORIES:
            existing = db.scalar(select(Category).where(Category.slug == slug))
            if existing:
                existing.name = name
                existing.description = description
                existing.sort_order = sort_order
                existing.is_active = True
                print(f"update category  {slug}")
                continue

            db.add(
                Category(
                    id=uuid.uuid4(),
                    name=name,
                    slug=slug,
                    description=description,
                    sort_order=sort_order,
                    is_active=True,
                )
            )
            print(f"add  category  {slug}")

        db.commit()
        print("seed complete")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
