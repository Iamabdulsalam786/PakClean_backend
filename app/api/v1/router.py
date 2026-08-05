"""
Aggregate all v1 route modules into one APIRouter.

main.py will mount this once:
  app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
"""

from fastapi import APIRouter

from app.api.v1 import auth, bookings, catalog
from app.customers.api.profile import router as customers_router
from app.discovery.api.router import router as discovery_router
from app.providers.api.profiles import admin_router as provider_admin_router
from app.providers.api.profiles import provider_router
from app.reviews.api.reviews import marketplace_router as marketplace_reviews_router
from app.reviews.api.reviews import router as reviews_router
from app.service_listings.api.extras import (
    provider_extras_router,
    public_extras_router,
    tags_catalog_router,
)
from app.service_listings.api.images import (
    provider_images_router,
    public_images_router,
)
from app.service_listings.api.listings import (
    provider_listings_router,
    public_listings_router,
)

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)
api_v1_router.include_router(catalog.router)
api_v1_router.include_router(bookings.router)
api_v1_router.include_router(customers_router)
api_v1_router.include_router(reviews_router)
api_v1_router.include_router(provider_router)
api_v1_router.include_router(provider_admin_router)
api_v1_router.include_router(provider_listings_router)
api_v1_router.include_router(provider_images_router)
api_v1_router.include_router(provider_extras_router)
api_v1_router.include_router(discovery_router)
api_v1_router.include_router(marketplace_reviews_router)
api_v1_router.include_router(public_listings_router)
api_v1_router.include_router(public_images_router)
api_v1_router.include_router(public_extras_router)
api_v1_router.include_router(tags_catalog_router)
