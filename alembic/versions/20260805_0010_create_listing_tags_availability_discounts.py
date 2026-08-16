"""create tags, availability, and discounts for service listings

Revision ID: 20260805_0010
Revises: 20260805_0009
Create Date: 2026-08-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0010"
down_revision: Union[str, None] = "20260805_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

discount_type = postgresql.ENUM(
    "percent",
    "fixed",
    name="discount_type",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("name", name="uq_tags_name"),
        sa.UniqueConstraint("slug", name="uq_tags_slug"),
    )
    op.create_index("ix_tags_slug", "tags", ["slug"], unique=False)

    op.create_table(
        "service_listing_tags",
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["service_listings.id"],
            ondelete="CASCADE",
            name="fk_service_listing_tags_listing_id",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            ondelete="CASCADE",
            name="fk_service_listing_tags_tag_id",
        ),
    )
    op.create_index(
        "ix_service_listing_tags_tag_id",
        "service_listing_tags",
        ["tag_id"],
        unique=False,
    )

    op.create_table(
        "service_listing_availability",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["service_listings.id"],
            ondelete="CASCADE",
            name="fk_service_listing_availability_listing_id",
        ),
        sa.UniqueConstraint(
            "listing_id",
            "day_of_week",
            "start_time",
            "end_time",
            name="uq_listing_availability_slot",
        ),
        sa.CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="ck_availability_day_of_week",
        ),
        sa.CheckConstraint(
            "start_time < end_time",
            name="ck_availability_start_before_end",
        ),
    )
    op.create_index(
        "ix_service_listing_availability_listing_id",
        "service_listing_availability",
        ["listing_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_listing_availability_day_of_week",
        "service_listing_availability",
        ["day_of_week"],
        unique=False,
    )

    discount_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "service_listing_discounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discount_type", discount_type, nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["service_listings.id"],
            ondelete="CASCADE",
            name="fk_service_listing_discounts_listing_id",
        ),
        sa.CheckConstraint("value > 0", name="ck_discount_value_positive"),
        sa.CheckConstraint("starts_at < ends_at", name="ck_discount_window"),
    )
    op.create_index(
        "ix_service_listing_discounts_listing_id",
        "service_listing_discounts",
        ["listing_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_listing_discounts_is_active",
        "service_listing_discounts",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_service_listing_discounts_window",
        "service_listing_discounts",
        ["listing_id", "is_active", "starts_at", "ends_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_service_listing_discounts_window", table_name="service_listing_discounts")
    op.drop_index("ix_service_listing_discounts_is_active", table_name="service_listing_discounts")
    op.drop_index("ix_service_listing_discounts_listing_id", table_name="service_listing_discounts")
    op.drop_table("service_listing_discounts")
    discount_type.drop(op.get_bind(), checkfirst=True)

    op.drop_index(
        "ix_service_listing_availability_day_of_week",
        table_name="service_listing_availability",
    )
    op.drop_index(
        "ix_service_listing_availability_listing_id",
        table_name="service_listing_availability",
    )
    op.drop_table("service_listing_availability")

    op.drop_index("ix_service_listing_tags_tag_id", table_name="service_listing_tags")
    op.drop_table("service_listing_tags")
    op.drop_index("ix_tags_slug", table_name="tags")
    op.drop_table("tags")
