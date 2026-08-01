"""
ORM models package — one module per domain table (or tightly related tables).

Import every model here so Alembic (and app startup) register tables on Base.metadata.
"""

from app.models.otp import OtpChallenge
from app.models.user import User, UserRole

__all__ = ["OtpChallenge", "User", "UserRole"]
