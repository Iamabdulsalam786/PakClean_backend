"""create provider_profiles for admin marketplace verification

Revision ID: 20260805_0007
Revises: 20260805_0006
Create Date: 2026-08-05 00:00:00.000000

Why this migration:
  - Email OTP (users.is_verified) is not marketplace trust.
  - provider_profiles holds admin verification + business fields.
  - Service listings will FK to provider_profiles.id, not users.id.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260805_0007"
down_revision: Union[str, None] = "20260805_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

provider_verification_status = postgresql.ENUM(
    "pending",
    "verified",
    "rejected",
    name="provider_verification_status",
    create_type=False,
)


def upgrade() -> None:
    """Create provider_verification_status enum + provider_profiles table."""
    provider_verification_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "provider_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_name", sa.String(length=200), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column(
            "verification_status",
            provider_verification_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "average_rating",
            sa.Numeric(3, 2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "total_reviews",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_bookings",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_provider_profiles_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_admin_id"],
            ["users.id"],
            name="fk_provider_profiles_verified_by_admin_id_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("user_id", name="uq_provider_profiles_user_id"),
    )

    # --- Indexes (why each exists) ---
    # Lookup profile by login user (1:1); unique already covers equality,
    # but explicit ix keeps naming consistent with ORM unique+index.
    op.create_index(
        "ix_provider_profiles_user_id",
        "provider_profiles",
        ["user_id"],
        unique=True,
    )
    # Admin moderation queue: WHERE verification_status = 'pending'
    op.create_index(
        "ix_provider_profiles_verification_status",
        "provider_profiles",
        ["verification_status"],
        unique=False,
    )
    # Filter providers by city for discovery / ops
    op.create_index(
        "ix_provider_profiles_city",
        "provider_profiles",
        ["city"],
        unique=False,
    )
    # Suspended vs active providers without a full scan
    op.create_index(
        "ix_provider_profiles_is_active",
        "provider_profiles",
        ["is_active"],
        unique=False,
    )
    # Optional audit trail joins / "who verified this?"
    op.create_index(
        "ix_provider_profiles_verified_by_admin_id",
        "provider_profiles",
        ["verified_by_admin_id"],
        unique=False,
    )
    # Composite: admin queue of pending + still active businesses
    op.create_index(
        "ix_provider_profiles_status_active",
        "provider_profiles",
        ["verification_status", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    """Drop provider_profiles and the verification enum."""
    op.drop_index("ix_provider_profiles_status_active", table_name="provider_profiles")
    op.drop_index(
        "ix_provider_profiles_verified_by_admin_id",
        table_name="provider_profiles",
    )
    op.drop_index("ix_provider_profiles_is_active", table_name="provider_profiles")
    op.drop_index("ix_provider_profiles_city", table_name="provider_profiles")
    op.drop_index(
        "ix_provider_profiles_verification_status",
        table_name="provider_profiles",
    )
    op.drop_index("ix_provider_profiles_user_id", table_name="provider_profiles")
    op.drop_table("provider_profiles")
    provider_verification_status.drop(op.get_bind(), checkfirst=True)
