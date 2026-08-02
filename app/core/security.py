import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def hash_value(value: str) -> str:
    return pwd_context.hash(value)


def verify_value(value: str, hashed: str) -> bool:
    return pwd_context.verify(value, hashed)


def generate_otp() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(settings.otp_length))


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(*, user_id: UUID, email: str, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_expires_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_access_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_access_secret, algorithms=["HS256"])
    except InvalidTokenError as exc:
        raise ValueError("Invalid or expired access token") from exc

    if payload.get("type") != "access":
        raise ValueError("Invalid token type")

    return payload


def get_refresh_expiry(*, remember_me: bool) -> datetime:
    days = settings.jwt_refresh_expires_days if remember_me else settings.jwt_refresh_expires_days_short
    return datetime.now(UTC) + timedelta(days=days)


def get_otp_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.otp_expires_minutes)


def get_reset_token_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=15)
