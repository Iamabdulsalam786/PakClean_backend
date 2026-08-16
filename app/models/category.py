"""
Category model — top-level service groups (Cleaning, Plumbing, Electrical, ...).

Customers browse categories first; services hang under a category.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.service import Service


class Category(Base):
    """ORM mapping for the categories table."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Human label shown in the app, e.g. "AC Repair & Installation"
    name: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        nullable=False,
        index=True,
    )

    # URL-friendly unique key, e.g. "ac-repair" (stable for deep links)
    slug: Mapped[str] = mapped_column(
        String(140),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Optional icon URL for mobile UI (CDN / S3 later)
    icon_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # Lower number = higher in the list (admin can reorder)
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # One category has many services (Service model comes next).
    services: Mapped[list[Service]] = relationship(
        "Service",
        back_populates="category",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} slug={self.slug!r}>"
