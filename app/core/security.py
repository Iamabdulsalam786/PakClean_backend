"""
Security helpers: password hashing and JWT access tokens.

Interview talking points:
  - Never store plain-text passwords; store a one-way bcrypt hash.
  - Access tokens are short-lived JWTs signed with SECRET_KEY (HS256).
  - Verification fails closed: bad/expired token → None / raise in deps later.

Note: we use the bcrypt library directly (not passlib) because passlib 1.7.x
is incompatible with bcrypt 4.1+/5.x — a common production footgun.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(plain_password: str) -> str:
    """
    Hash a plain password for storage in users.hashed_password.

    bcrypt salts automatically — two hashes of the same password differ.
    """
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Check a login password against the stored hash.

    Returns False on mismatch (never raises for wrong password).
    """
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(
    subject: str,
    *,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a signed JWT access token.

    subject: usually the user id (string UUID).
    extra_claims: optional fields like {"role": "customer"} for quick authz checks.
    """
    if expires_minutes is None:
        expires_minutes = settings.access_token_expire_minutes

    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes)

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """
    Decode and verify a JWT.

    Returns the claims dict on success, or None if invalid/expired/tampered.
    """
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except JWTError:
        return None
