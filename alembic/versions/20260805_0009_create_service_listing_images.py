"""create service_listing_images for listing photo galleries

Revision ID: 20260805_0009
Revises: 20260805_0008
Create Date: 2026-08-05 00:00:00.000000

Why this migration:
  - Multiple ordered images per marketplace listing
  - Primary flag for cards; unique URL per listing
  - Partial unique index: at most one is_primary=true per listing

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260805_0009"
down_revision: Union[str, None] = "20260805_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create service_listing_images + gallery indexes."""
    op.create_table(
        "service_listing_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("image_url", sa.String(length=1000), nullable=False),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("alt_text", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["service_listings.id"],
            name="fk_service_listing_images_listing_id_service_listings",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "listing_id",
            "image_url",
            name="uq_service_listing_images_listing_url",
        ),
    )

    # Load all images for one listing (provider gallery / public detail)
    op.create_index(
        "ix_service_listing_images_listing_id",
        "service_listing_images",
        ["listing_id"],
        unique=False,
    )
    # Order within a listing
    op.create_index(
        "ix_service_listing_images_sort_order",
        "service_listing_images",
        ["sort_order"],
        unique=False,
    )
    # Find primary quickly (non-unique; uniqueness via partial index below)
    op.create_index(
        "ix_service_listing_images_is_primary",
        "service_listing_images",
        ["is_primary"],
        unique=False,
    )
    # Composite: gallery ordered fetch
    op.create_index(
        "ix_service_listing_images_listing_sort",
        "service_listing_images",
        ["listing_id", "sort_order"],
        unique=False,
    )
    # DB-level: at most ONE primary image per listing
    op.create_index(
        "uq_service_listing_images_one_primary",
        "service_listing_images",
        ["listing_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )


def downgrade() -> None:
    """Drop service_listing_images."""
    op.drop_index(
        "uq_service_listing_images_one_primary",
        table_name="service_listing_images",
    )
    op.drop_index(
        "ix_service_listing_images_listing_sort",
        table_name="service_listing_images",
    )
    op.drop_index(
        "ix_service_listing_images_is_primary",
        table_name="service_listing_images",
    )
    op.drop_index(
        "ix_service_listing_images_sort_order",
        table_name="service_listing_images",
    )
    op.drop_index(
        "ix_service_listing_images_listing_id",
        table_name="service_listing_images",
    )
    op.drop_table("service_listing_images")
