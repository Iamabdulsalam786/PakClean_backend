"""marketplace bookings: listing_id + expanded status lifecycle

Revision ID: 20260805_0011
Revises: 20260805_0010
Create Date: 2026-08-05 00:00:00.000000

Why this migration:
  - Customers book a ServiceListing (listing_id), not only catalog services.
  - Lifecycle needs rejected + in_progress beyond Phase-1 statuses.
  - Snapshot / audit columns support immutable price and transition history.
  - service_id becomes nullable so new marketplace bookings need not set it.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0011"
down_revision: Union[str, None] = "20260805_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand booking_status enum + add marketplace booking columns."""
    # Postgres: ADD VALUE should run outside a transaction on older versions;
    # autocommit_block is the Alembic-safe pattern.
    with op.get_context().autocommit_block():
        op.execute(
            sa.text(
                "ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'rejected'"
            )
        )
        op.execute(
            sa.text(
                "ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'in_progress'"
            )
        )

    # New marketplace bookings attach to a listing; legacy rows keep service_id only.
    op.add_column(
        "bookings",
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_bookings_listing_id_service_listings",
        "bookings",
        "service_listings",
        ["listing_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_bookings_listing_id", "bookings", ["listing_id"], unique=False)

    # Allow listing-only bookings (catalog service_id optional going forward).
    op.alter_column(
        "bookings",
        "service_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # Denormalized title at book time (listing title may change later).
    op.add_column(
        "bookings",
        sa.Column("listing_title_snapshot", sa.String(length=200), nullable=True),
    )

    op.add_column(
        "bookings",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )

    # Transition audit timestamps (null until that event happens).
    op.add_column(
        "bookings",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Provider inbox: open/pending work by provider
    op.create_index(
        "ix_bookings_provider_status",
        "bookings",
        ["provider_id", "status"],
        unique=False,
    )
    # Customer history
    op.create_index(
        "ix_bookings_customer_created_at",
        "bookings",
        ["customer_id", "created_at"],
        unique=False,
    )
    # Schedule lookups per listing (overlap checks later)
    op.create_index(
        "ix_bookings_listing_scheduled_at",
        "bookings",
        ["listing_id", "scheduled_at"],
        unique=False,
    )


def downgrade() -> None:
    """
    Remove marketplace columns / indexes.

    Note: Postgres cannot easily DROP enum values ('rejected', 'in_progress').
    We leave those values on booking_status; reversing them requires recreating
    the type (not done here to avoid data loss risk).
    """
    op.drop_index("ix_bookings_listing_scheduled_at", table_name="bookings")
    op.drop_index("ix_bookings_customer_created_at", table_name="bookings")
    op.drop_index("ix_bookings_provider_status", table_name="bookings")

    op.drop_column("bookings", "cancelled_at")
    op.drop_column("bookings", "completed_at")
    op.drop_column("bookings", "started_at")
    op.drop_column("bookings", "accepted_at")
    op.drop_column("bookings", "rejection_reason")
    op.drop_column("bookings", "listing_title_snapshot")

    op.alter_column(
        "bookings",
        "service_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.drop_index("ix_bookings_listing_id", table_name="bookings")
    op.drop_constraint(
        "fk_bookings_listing_id_service_listings",
        "bookings",
        type_="foreignkey",
    )
    op.drop_column("bookings", "listing_id")
