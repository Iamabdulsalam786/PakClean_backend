"""
Service model — bookable offerings under a Category.

Example: Category "Plumbing" → Service "Tap Repair" at 1,500 PKR.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.category import Category


class Service(Base):
    """ORM mapping for the services table."""

    __tablename__ = "services"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Parent category (required). Cascade delete handled at DB level via FK.
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    slug: Mapped[str] = mapped_column(
        String(170),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Base price in Pakistani Rupees (whole rupees, e.g. 1500 = Rs. 1,500).
    # Not paisa — APIs and the app always treat this as PKR.
    price_pkr: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Estimated job length in minutes (helps scheduling later).
    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=60,
        server_default="60",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

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

    category: Mapped[Category] = relationship(
        "Category",
        back_populates="services",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<Service id={self.id} slug={self.slug!r} price_pkr={self.price_pkr}>"
