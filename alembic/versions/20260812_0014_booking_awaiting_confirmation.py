"""Add awaiting_confirmation booking status + customer confirmation timestamps.

Revision ID: 20260812_0014
Revises: 20260805_0013
Create Date: 2026-08-12

Provider marks work done → awaiting_confirmation (not terminal COMPLETED).
Customer confirms → completed. Reviews remain gated on completed.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260812_0014"
down_revision = "20260805_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'awaiting_confirmation'"
    )
    op.add_column(
        "bookings",
        sa.Column("provider_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("customer_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "customer_confirmed_at")
    op.drop_column("bookings", "provider_completed_at")
    # Postgres enums cannot drop values safely; leave awaiting_confirmation in place.
