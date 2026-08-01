"""
Aggregate all v1 route modules into one APIRouter.

main.py will mount this once:
  app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
"""

from fastapi import APIRouter

from app.api.v1 import auth

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router)

# Later:
# api_v1_router.include_router(users.router)
# api_v1_router.include_router(bookings.router)
# api_v1_router.include_router(admin.router)
