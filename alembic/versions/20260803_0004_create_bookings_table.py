"""create bookings table

Revision ID: 20260803_0004
Revises: 20260803_0003
Create Date: 2026-08-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260803_0004"
down_revision: Union[str, None] = "20260803_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

booking_status_enum = postgresql.ENUM(
    "pending",
    "confirmed",
    "cancelled",
    "completed",
    name="booking_status",
    create_type=False,
)


def upgrade() -> None:
    """Apply this migration (move schema forward)."""
    booking_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            booking_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("address_text", sa.String(length=500), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("price_pkr", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
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
            name="fk_bookings_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name="fk_bookings_service_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["users.id"],
            name="fk_bookings_provider_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_bookings_customer_id", "bookings", ["customer_id"], unique=False)
    op.create_index("ix_bookings_service_id", "bookings", ["service_id"], unique=False)
    op.create_index("ix_bookings_provider_id", "bookings", ["provider_id"], unique=False)
    op.create_index("ix_bookings_status", "bookings", ["status"], unique=False)
    op.create_index("ix_bookings_scheduled_at", "bookings", ["scheduled_at"], unique=False)


def downgrade() -> None:
    """Undo this migration (move schema backward)."""
    op.drop_index("ix_bookings_scheduled_at", table_name="bookings")
    op.drop_index("ix_bookings_status", table_name="bookings")
    op.drop_index("ix_bookings_provider_id", table_name="bookings")
    op.drop_index("ix_bookings_service_id", table_name="bookings")
    op.drop_index("ix_bookings_customer_id", table_name="bookings")
    op.drop_table("bookings")
    booking_status_enum.drop(op.get_bind(), checkfirst=True)
