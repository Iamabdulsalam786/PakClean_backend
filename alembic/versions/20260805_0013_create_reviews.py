"""create reviews table for completed-booking ratings

Revision ID: 20260805_0013
Revises: 20260805_0012
Create Date: 2026-08-05 00:00:00.000000

Why this migration:
  - Customers rate COMPLETED bookings (one review per booking).
  - reviews is the source of truth; listing/provider average_rating
    columns are denormalized caches updated by ReviewService.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0013"
down_revision: Union[str, None] = "20260805_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create reviews table + indexes + rating check."""
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            name="fk_reviews_booking_id_bookings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            name="fk_reviews_customer_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["users.id"],
            name="fk_reviews_provider_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["service_listings.id"],
            name="fk_reviews_listing_id_service_listings",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("booking_id", name="uq_reviews_booking_id"),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_reviews_rating_range",
        ),
    )

    op.create_index("ix_reviews_booking_id", "reviews", ["booking_id"], unique=True)
    op.create_index("ix_reviews_customer_id", "reviews", ["customer_id"], unique=False)
    op.create_index("ix_reviews_provider_id", "reviews", ["provider_id"], unique=False)
    op.create_index("ix_reviews_listing_id", "reviews", ["listing_id"], unique=False)
    # Public listing review feeds: newest first.
    op.create_index("ix_reviews_created_at", "reviews", ["created_at"], unique=False)
    op.create_index(
        "ix_reviews_listing_id_created_at",
        "reviews",
        ["listing_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop reviews indexes + table."""
    op.drop_index("ix_reviews_listing_id_created_at", table_name="reviews")
    op.drop_index("ix_reviews_created_at", table_name="reviews")
    op.drop_index("ix_reviews_listing_id", table_name="reviews")
    op.drop_index("ix_reviews_provider_id", table_name="reviews")
    op.drop_index("ix_reviews_customer_id", table_name="reviews")
    op.drop_index("ix_reviews_booking_id", table_name="reviews")
    op.drop_table("reviews")
