"""
ORM models package — one module per domain table (or tightly related tables).

Import every model here so Alembic (and app startup) register tables on Base.metadata.
"""

from app.models.booking import Booking, BookingStatus
from app.models.category import Category
from app.models.otp import OtpChallenge
from app.models.service import Service
from app.models.user import User, UserRole

__all__ = [
    "Booking",
    "BookingStatus",
    "Category",
    "OtpChallenge",
    "Service",
    "User",
    "UserRole",
]
