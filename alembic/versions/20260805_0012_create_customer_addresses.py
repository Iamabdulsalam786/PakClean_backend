"""create customer_addresses for saved customer locations

Revision ID: 20260805_0012
Revises: 20260805_0011
Create Date: 2026-08-05 00:00:00.000000

Why this migration:
  - Bookings currently take free-text address_text only.
  - customer_addresses is the reusable address book for Home/Office pins.
  - Bookings will keep snapshotting text; this table is the source of truth
    for the customer's saved locations (not booking history).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0012"
down_revision: Union[str, None] = "20260805_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create customer_addresses table + indexes."""
    op.create_table(
        "customer_addresses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("address_line", sa.String(length=500), nullable=False),
        sa.Column("area", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("landmark", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
            ["customer_id"],
            ["users.id"],
            name="fk_customer_addresses_customer_id_users",
            ondelete="CASCADE",
        ),
    )

    # List / ownership queries always filter by customer_id.
    op.create_index(
        "ix_customer_addresses_customer_id",
        "customer_addresses",
        ["customer_id"],
        unique=False,
    )
    # Optional city filter / analytics.
    op.create_index(
        "ix_customer_addresses_city",
        "customer_addresses",
        ["city"],
        unique=False,
    )
    # Fast path: find default address for a customer
    # (service still clears siblings; index helps WHERE is_default).
    op.create_index(
        "ix_customer_addresses_is_default",
        "customer_addresses",
        ["is_default"],
        unique=False,
    )
    # Composite for "get my default" — common mobile path.
    op.create_index(
        "ix_customer_addresses_customer_id_is_default",
        "customer_addresses",
        ["customer_id", "is_default"],
        unique=False,
    )


def downgrade() -> None:
    """Drop customer_addresses indexes + table."""
    op.drop_index(
        "ix_customer_addresses_customer_id_is_default",
        table_name="customer_addresses",
    )
    op.drop_index("ix_customer_addresses_is_default", table_name="customer_addresses")
    op.drop_index("ix_customer_addresses_city", table_name="customer_addresses")
    op.drop_index("ix_customer_addresses_customer_id", table_name="customer_addresses")
    op.drop_table("customer_addresses")
