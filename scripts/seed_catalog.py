"""
Seed categories + starter services (prices in PKR).

Run from pak-clean-backend (venv active):
  python -m scripts.seed_catalog

Safe to re-run: skips categories/services whose slug already exists.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.session import SessionLocal

# Register all ORM models before Session use (Booking → ServiceListing relationship).
from app.customers.models import CustomerAddress  # noqa: F401
from app.models import Booking, Category, Service  # noqa: F401
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
# Grouped by daily home-life needs. AC / fridge / appliances sit near Electrical.
CATEGORIES: list[tuple[str, str, str, int]] = [
    # --- Home care ---
    ("cleaning", "Cleaning", "Home and office cleaning services", 0),
    ("laundry", "Laundry", "Wash, iron, and dry-clean pickup services", 1),
    ("sofa-carpet-cleaning", "Sofa & Carpet Cleaning", "Sofa, carpet, and mattress deep cleaning", 2),
    ("disinfection", "Disinfection", "Home sanitization and fumigation", 3),
    ("pest-control", "Pest Control", "Cockroach, termite, and rodent treatment", 4),
    # --- Plumbing & water ---
    ("plumbing", "Plumbing", "Pipes, taps, drains, and water fixtures", 10),
    ("water-tank", "Water Tank Cleaning", "Overhead and underground tank cleaning", 11),
    ("water-purifier", "Water Purifier", "RO / filter install and service", 12),
    # --- Electrical & appliances (AC / fridge live here logically) ---
    ("electrical", "Electrical", "Wiring, switches, fans, and lighting", 20),
    ("ac", "AC & Cooling", "AC install, service, gas refill, and cooling repair", 21),
    ("fridge-appliance", "Fridge & Appliance Repair", "Fridge, freezer, and kitchen appliance repair", 22),
    ("washing-machine", "Washing Machine Repair", "Washer and dryer repair and service", 23),
    ("microwave-oven", "Microwave & Oven Repair", "Microwave, oven, and hob repair", 24),
    ("generator-solar", "Generator & Solar", "Generator, UPS, and solar panel service", 25),
    # --- Security & electronics ---
    ("cctv-security", "CCTV & Security", "CCTV, door camera, and alarm installation", 30),
    ("tv-electronics", "TV & Electronics Repair", "TV, sound system, and electronics repair", 31),
    ("computer-mobile", "Computer & Mobile Repair", "Laptop, PC, and phone repair at home", 32),
    # --- Home improvement ---
    ("carpentry", "Carpentry", "Furniture repair, doors, and wood work", 40),
    ("painting", "Painting", "Interior and exterior wall painting", 41),
    ("tiles-masonry", "Tiles & Masonry", "Tile fixing, marble, and masonry work", 42),
    ("glass-aluminum", "Glass & Aluminum", "Windows, mirrors, and aluminum work", 43),
    ("welding", "Welding & Fabrication", "Gates, grills, and metal fabrication", 44),
    ("interior-design", "Interior Design", "Room makeovers and interior consultation", 45),
    # --- Outdoor & misc ---
    ("gardening", "Gardening", "Lawn, plants, and garden maintenance", 50),
    ("moving-shifting", "Moving & Shifting", "Home packing, loading, and relocation help", 51),
    ("packaging-design", "Packaging Design", "Custom packaging and label design services", 52),
    ("handyman", "Handyman", "General home fixes and small jobs", 53),
    ("event-support", "Event Support", "Pre/post event cleaning and setup help", 54),
]

# (category_slug, service_slug, name, description, price_pkr, duration_minutes, sort_order)
SERVICES: list[tuple[str, str, str, str, int, int, int]] = [
    # Cleaning
    ("cleaning", "home-cleaning", "Home Cleaning", "Standard home cleaning for apartments and houses", 2500, 120, 0),
    ("cleaning", "deep-cleaning", "Deep Cleaning", "Thorough deep clean including kitchen and bathrooms", 5500, 240, 1),
    ("cleaning", "kitchen-cleaning", "Kitchen Cleaning", "Degreasing cabinets, stove, and kitchen surfaces", 3000, 90, 2),
    # Laundry
    ("laundry", "wash-and-iron", "Wash & Iron", "Per load wash and iron service", 800, 180, 0),
    ("laundry", "dry-clean-pickup", "Dry Clean Pickup", "Dry-clean pickup and delivery for suits and coats", 1500, 240, 1),
    # Sofa & carpet
    ("sofa-carpet-cleaning", "sofa-shampoo", "Sofa Shampoo", "Deep shampoo for fabric and leather sofas", 3500, 120, 0),
    ("sofa-carpet-cleaning", "carpet-cleaning", "Carpet Cleaning", "Room carpet steam / shampoo cleaning", 4000, 150, 1),
    # Disinfection
    ("disinfection", "home-fumigation", "Home Fumigation", "Whole-home disinfection spray service", 4500, 90, 0),
    # Pest control
    ("pest-control", "general-pest-spray", "General Pest Spray", "Cockroaches and ants treatment", 3500, 60, 0),
    ("pest-control", "termite-treatment", "Termite Treatment", "Termite inspection and treatment", 8000, 120, 1),
    # Plumbing
    ("plumbing", "tap-repair", "Tap Repair", "Fix leaking or faulty taps", 1500, 60, 0),
    ("plumbing", "drain-unclog", "Drain Unclog", "Unclog kitchen or bathroom drains", 2000, 90, 1),
    ("plumbing", "geyser-install", "Geyser Install", "Water heater install and pipe connection", 3500, 120, 2),
    # Water tank
    ("water-tank", "overhead-tank-clean", "Overhead Tank Cleaning", "Clean and disinfect overhead water tank", 4000, 120, 0),
    # Water purifier
    ("water-purifier", "ro-service", "RO Service", "RO filter change and service", 2500, 90, 0),
    # Electrical
    ("electrical", "switch-fix", "Switch Fix", "Repair or replace faulty switches", 1200, 45, 0),
    ("electrical", "fan-install", "Fan Install", "Install a ceiling or wall fan", 1800, 90, 1),
    ("electrical", "wiring-fix", "Wiring Fix", "Fix short circuit and loose wiring", 2500, 120, 2),
    # AC & cooling
    ("ac", "ac-service", "AC Service", "Routine AC cleaning and service", 3500, 120, 0),
    ("ac", "ac-gas-refill", "AC Gas Refill", "Refill AC refrigerant gas", 6500, 150, 1),
    ("ac", "ac-install", "AC Install", "Split AC wall mount installation", 5500, 180, 2),
    # Fridge & appliances
    ("fridge-appliance", "fridge-repair", "Fridge Repair", "Cooling and compressor fault repair", 3000, 120, 0),
    ("fridge-appliance", "deep-freezer-repair", "Deep Freezer Repair", "Deep freezer not cooling repair", 2800, 90, 1),
    # Washing machine
    ("washing-machine", "washer-repair", "Washing Machine Repair", "Drum, motor, and leak repair", 2500, 90, 0),
    # Microwave & oven
    ("microwave-oven", "microwave-repair", "Microwave Repair", "Heating and panel fault repair", 2000, 60, 0),
    ("microwave-oven", "oven-repair", "Oven Repair", "Electric / gas oven repair", 2800, 90, 1),
    # Generator & solar
    ("generator-solar", "ups-service", "UPS Service", "UPS battery check and service", 2000, 60, 0),
    ("generator-solar", "solar-panel-clean", "Solar Panel Cleaning", "Roof solar panel wash and check", 3500, 120, 1),
    # CCTV
    ("cctv-security", "cctv-install-4cam", "CCTV Install (4 Cam)", "4-camera DVR / NVR setup with wiring", 15000, 240, 0),
    ("cctv-security", "doorbell-camera", "Doorbell Camera Install", "Smart doorbell camera setup", 4500, 90, 1),
    # TV & electronics
    ("tv-electronics", "tv-wall-mount", "TV Wall Mount", "LED TV bracket install and setup", 2500, 60, 0),
    ("tv-electronics", "tv-repair", "TV Repair", "Display and power board repair", 3500, 120, 1),
    # Computer & mobile
    ("computer-mobile", "laptop-service", "Laptop Service", "Cleanup, SSD upgrade, and OS install", 3000, 120, 0),
    ("computer-mobile", "mobile-screen", "Mobile Screen Replace", "Phone screen replacement at home", 4500, 60, 1),
    # Carpentry
    ("carpentry", "door-lock-fix", "Door & Lock Fix", "Door alignment and lock replacement", 2000, 90, 0),
    ("carpentry", "furniture-assembly", "Furniture Assembly", "IKEA / flat-pack furniture assembly", 2500, 120, 1),
    # Painting
    ("painting", "room-painting", "Room Painting", "Single room paint job (labour only)", 8000, 480, 0),
    ("painting", "wall-touch-up", "Wall Touch Up", "Small area patch and paint", 3000, 180, 1),
    # Tiles & masonry
    ("tiles-masonry", "tile-fix", "Tile Fix", "Replace broken floor or wall tiles", 3500, 120, 0),
    # Glass & aluminum
    ("glass-aluminum", "window-repair", "Window Repair", "Aluminum window and glass replacement", 4000, 120, 0),
    # Welding
    ("welding", "grill-install", "Grill Install", "Window safety grill fabrication and install", 12000, 360, 0),
    # Interior design
    ("interior-design", "room-consult", "Room Consultation", "1-hour in-home interior consultation", 5000, 60, 0),
    # Gardening
    ("gardening", "lawn-mowing", "Lawn Mowing", "Garden grass cutting and cleanup", 2500, 120, 0),
    ("gardening", "plant-trimming", "Plant Trimming", "Trim bushes and small trees", 3000, 150, 1),
    # Moving
    ("moving-shifting", "home-packing", "Home Packing", "Pack 2-bedroom home for move", 8000, 360, 0),
    ("moving-shifting", "load-unload", "Load & Unload", "Labour for loading and unloading truck", 5000, 180, 1),
    # Packaging design
    ("packaging-design", "product-packaging", "Product Packaging Design", "Box and pouch design for small business", 15000, 480, 0),
    ("packaging-design", "label-design", "Label Design", "Product label and sticker design", 8000, 240, 1),
    # Handyman
    ("handyman", "general-fix", "General Home Fix", "Small repairs — shelves, hooks, curtains", 2000, 90, 0),
    # Event support
    ("event-support", "post-event-clean", "Post Event Cleaning", "Cleanup after home party or gathering", 5000, 180, 0),
]


def seed() -> None:
    db = SessionLocal()
    try:
        category_by_slug: dict[str, Category] = {}
        for slug, name, description, sort_order in CATEGORIES:
            existing = db.scalar(select(Category).where(Category.slug == slug))
            if existing:
                existing.name = name
                existing.description = description
                existing.sort_order = sort_order
                existing.is_active = True
                category_by_slug[slug] = existing
                print(f"update category  {slug}")
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
