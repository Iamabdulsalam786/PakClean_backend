"""
RefreshTokenRepository — database access for refresh_tokens.

Supports:
  - creating a hashed refresh session
  - looking up by token hash
  - revoking one token (logout / rotation)
  - revoking all tokens for a user (logout-all later)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    """Thin data-access layer around RefreshToken rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def add(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> RefreshToken:
        """Insert a new refresh session (hash only — never raw token)."""
        row = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            revoked_at=None,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._db.add(row)
        return row

    def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        """Used by POST /auth/refresh to load the session row."""
        statement = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self._db.scalar(statement)

    def revoke(self, token: RefreshToken, *, revoked_at: datetime) -> RefreshToken:
        """Mark one refresh token as revoked (rotation / logout)."""
        token.revoked_at = revoked_at
        self._db.add(token)
        return token

    def revoke_all_for_user(self, user_id: UUID, *, revoked_at: datetime) -> int:
        """
        Revoke every active refresh token for a user.

        Useful later for "logout all devices" or password change.
        """
        statement = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
        result = self._db.execute(statement)
        return result.rowcount or 0
