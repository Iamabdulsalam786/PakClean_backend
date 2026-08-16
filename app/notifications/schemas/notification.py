from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceRegisterRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    platform: str = Field(pattern="^(android|ios)$")


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    title: str
    body: str
    booking_id: UUID | None
    read_at: datetime | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    total: int
    unread_count: int
    page: int = 1
    page_size: int = 20


class UnreadCountResponse(BaseModel):
    unread_count: int
