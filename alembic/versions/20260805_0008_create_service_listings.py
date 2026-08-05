"""create service_listings for provider marketplace inventory

Revision ID: 20260805_0008
Revises: 20260805_0007
Create Date: 2026-08-05 00:00:00.000000

Why this migration:
  - Catalog `services` = platform templates.
  - `service_listings` = verified-provider offerings customers browse/book.
  - Soft delete via deleted_at; status enum is draft|active|inactive only.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260805_0008"
down_revision: Union[str, None] = "20260805_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

listing_status = postgresql.ENUM(
    "draft",
    "active",
    "inactive",
    name="listing_status",
    create_type=False,
)


def upgrade() -> None:
    """Create listing_status enum + service_listings table + browse indexes."""
    listing_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "service_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("base_price", sa.Integer(), nullable=False),
        sa.Column("estimated_duration", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column(
            "service_radius_km",
            sa.Numeric(6, 2),
            nullable=False,
            server_default="5.00",
        ),
        sa.Column(
            "status",
            listing_status,
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "is_featured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "booking_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "average_rating",
            sa.Numeric(3, 2),
            nullable=False,
            server_default="0.00",
        ),
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
            ["provider_id"],
            ["provider_profiles.id"],
            name="fk_service_listings_provider_id_provider_profiles",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_service_listings_category_id_categories",
            ondelete="RESTRICT",
        ),
    )

    # --- Indexes (why each exists) ---
    # Provider dashboard: my listings
    op.create_index(
        "ix_service_listings_provider_id",
        "service_listings",
        ["provider_id"],
        unique=False,
    )
    # Filter by category
    op.create_index(
        "ix_service_listings_category_id",
        "service_listings",
        ["category_id"],
        unique=False,
    )
    # Title search (prefix / equality; trigram GIN comes later at scale)
    op.create_index(
        "ix_service_listings_title",
        "service_listings",
        ["title"],
        unique=False,
    )
    # Price range filters + sort by price
    op.create_index(
        "ix_service_listings_base_price",
        "service_listings",
        ["base_price"],
        unique=False,
    )
    # City filter / search
    op.create_index(
        "ix_service_listings_city",
        "service_listings",
        ["city"],
        unique=False,
    )
    # Status filter (draft/active/inactive)
    op.create_index(
        "ix_service_listings_status",
        "service_listings",
        ["status"],
        unique=False,
    )
    # Featured strip
    op.create_index(
        "ix_service_listings_is_featured",
        "service_listings",
        ["is_featured"],
        unique=False,
    )
    # Soft-delete filter (IS NULL checks)
    op.create_index(
        "ix_service_listings_deleted_at",
        "service_listings",
        ["deleted_at"],
        unique=False,
    )
    # Sort newest / oldest
    op.create_index(
        "ix_service_listings_created_at",
        "service_listings",
        ["created_at"],
        unique=False,
    )
    # Public browse hot path: active + not deleted (+ optional city)
    op.create_index(
        "ix_service_listings_public_feed",
        "service_listings",
        ["status", "deleted_at", "city", "category_id"],
        unique=False,
    )
    # Sort helpers for highest rated / most booked (public queries still filter status)
    op.create_index(
        "ix_service_listings_average_rating",
        "service_listings",
        ["average_rating"],
        unique=False,
    )
    op.create_index(
        "ix_service_listings_booking_count",
        "service_listings",
        ["booking_count"],
        unique=False,
    )


def downgrade() -> None:
    """Drop service_listings and listing_status enum."""
    op.drop_index("ix_service_listings_booking_count", table_name="service_listings")
    op.drop_index("ix_service_listings_average_rating", table_name="service_listings")
    op.drop_index("ix_service_listings_public_feed", table_name="service_listings")
    op.drop_index("ix_service_listings_created_at", table_name="service_listings")
    op.drop_index("ix_service_listings_deleted_at", table_name="service_listings")
    op.drop_index("ix_service_listings_is_featured", table_name="service_listings")
    op.drop_index("ix_service_listings_status", table_name="service_listings")
    op.drop_index("ix_service_listings_city", table_name="service_listings")
    op.drop_index("ix_service_listings_base_price", table_name="service_listings")
    op.drop_index("ix_service_listings_title", table_name="service_listings")
    op.drop_index("ix_service_listings_category_id", table_name="service_listings")
    op.drop_index("ix_service_listings_provider_id", table_name="service_listings")
    op.drop_table("service_listings")
    listing_status.drop(op.get_bind(), checkfirst=True)
