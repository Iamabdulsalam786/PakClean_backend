from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.dependencies import CurrentUser, DbSession
from app.notifications.schemas.notification import (
    DeviceRegisterRequest,
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)
from app.notifications.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])
devices_router = APIRouter(prefix="/devices", tags=["devices"])


def _service(db: DbSession) -> NotificationService:
    return NotificationService(db)


@devices_router.post(
    "/register",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Register FCM device token for push notifications",
)
def register_device(
    payload: DeviceRegisterRequest,
    db: DbSession,
    user: CurrentUser,
) -> Response:
    _service(db).register_device(user, token=payload.token, platform=payload.platform)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@devices_router.post(
    "/unregister",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove FCM device token (logout / uninstall)",
)
def unregister_device(
    payload: DeviceRegisterRequest,
    db: DbSession,
    user: CurrentUser,
) -> Response:
    _service(db).unregister_device(user, token=payload.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List my in-app notifications",
)
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> NotificationListResponse:
    return _service(db).list_notifications(user, page=page, page_size=page_size)


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Unread notification count for bell badge",
)
def unread_count(db: DbSession, user: CurrentUser) -> UnreadCountResponse:
    return UnreadCountResponse(unread_count=_service(db).unread_count(user))


@router.post(
    "/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark one notification as read",
)
def mark_notification_read(
    notification_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> NotificationRead:
    row = _service(db).mark_read(user, notification_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return row


@router.post(
    "/read-all",
    summary="Mark all notifications as read",
)
def mark_all_read(db: DbSession, user: CurrentUser) -> dict[str, int]:
    updated = _service(db).mark_all_read(user)
    return {"updated": updated}
