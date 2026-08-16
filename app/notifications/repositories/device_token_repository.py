from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.notifications.models.device_token import DeviceToken


class DeviceTokenRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def upsert(self, *, user_id: UUID, token: str, platform: str) -> DeviceToken:
        existing = self._db.scalar(select(DeviceToken).where(DeviceToken.token == token))
        now = datetime.now(timezone.utc)
        if existing is not None:
            existing.user_id = user_id
            existing.platform = platform
            existing.updated_at = now
            self._db.add(existing)
            return existing

        row = DeviceToken(user_id=user_id, token=token, platform=platform)
        self._db.add(row)
        return row

    def delete_token(self, *, user_id: UUID, token: str) -> None:
        row = self._db.scalar(
            select(DeviceToken).where(DeviceToken.user_id == user_id, DeviceToken.token == token)
        )
        if row is not None:
            self._db.delete(row)

    def list_tokens_for_user(self, user_id: UUID) -> list[str]:
        rows = self._db.scalars(
            select(DeviceToken.token).where(DeviceToken.user_id == user_id)
        ).all()
        return list(rows)
