"""
Security helpers: passwords, JWTs, OTP codes, and refresh tokens.

Interview talking points:
  - Never store plain-text passwords; store a one-way bcrypt hash.
  - Access tokens are short-lived JWTs signed with SECRET_KEY (HS256).
  - OTPs are generated with secrets (CSPRNG), stored as HMAC hashes (with server pepper).
  - Refresh tokens are high-entropy secrets; DB stores only a hash.

Note: we use the bcrypt library directly (not passlib) because passlib 1.7.x
is incompatible with bcrypt 4.1+/5.x — a common production footgun.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
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
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """
    Decode and verify a JWT access token.

    Returns the claims dict on success, or None if invalid/expired/tampered.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except JWTError:
        return None

    # Reject refresh tokens accidentally sent as Bearer access tokens.
    if payload.get("type") not in (None, "access"):
        return None
    return payload


# ---------------------------------------------------------------------------
# Email OTP (6-digit)
# ---------------------------------------------------------------------------


def generate_otp_code(length: int = 6) -> str:
    """
    Cryptographically secure numeric OTP.

    secrets.randbelow is the correct tool — do NOT use random.randint
    for security-sensitive values.
    """
    if length < 4 or length > 10:
        raise ValueError("OTP length must be between 4 and 10")
    # Example length=6 → 000000..999999, zero-padded.
    upper = 10**length
    return str(secrets.randbelow(upper)).zfill(length)


def hash_otp_code(plain_code: str) -> str:
    """
    Hash an OTP for storage using HMAC-SHA256 + SECRET_KEY as pepper.

    Why not plain SHA256(code)?
      - 6-digit space is tiny; unsalted hashes are rainbow-table trivial.
    Why not bcrypt for OTP?
      - Also valid, but HMAC+pepper is fast and standard for short codes
        when combined with attempt limits + expiry.
    """
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        plain_code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_otp_code(plain_code: str, code_hash: str) -> bool:
    """Constant-time comparison of OTP against stored HMAC hash."""
    candidate = hash_otp_code(plain_code.strip())
    return hmac.compare_digest(candidate, code_hash)


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------


def generate_refresh_token() -> str:
    """
    Create a high-entropy opaque refresh token for the client.

    urlsafe ~256 bits of randomness — not a JWT (revocation is DB-based).
    """
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    """
    Hash refresh token for DB storage.

    High entropy ⇒ SHA256 is enough; still fine to pepper with HMAC.
    """
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_refresh_token(raw_token: str, token_hash: str) -> bool:
    """Constant-time compare for refresh token hashes."""
    candidate = hash_refresh_token(raw_token)
    return hmac.compare_digest(candidate, token_hash)
