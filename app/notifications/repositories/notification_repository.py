from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.notifications.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(
        self,
        *,
        user_id: UUID,
        type: str,
        title: str,
        body: str,
        booking_id: UUID | None = None,
    ) -> Notification:
        row = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            booking_id=booking_id,
        )
        self._db.add(row)
        return row

    def count_unread(self, user_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        return int(self._db.scalar(statement) or 0)

    def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement).all())

    def count_for_user(self, user_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id)
        )
        return int(self._db.scalar(statement) or 0)

    def mark_read(self, *, user_id: UUID, notification_id: UUID) -> Notification | None:
        row = self._db.get(Notification, notification_id)
        if row is None or row.user_id != user_id:
            return None
        if row.read_at is None:
            row.read_at = datetime.now(timezone.utc)
            self._db.add(row)
        return row

    def mark_all_read(self, user_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        result = self._db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=now)
        )
        return int(result.rowcount or 0)
