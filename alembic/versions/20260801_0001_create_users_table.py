"""create users table

Revision ID: 20260801_0001
Revises:
Create Date: 2026-08-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260801_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Postgres ENUM for UserRole — created explicitly so downgrade can drop it cleanly.
user_role_enum = postgresql.ENUM(
    "customer",
    "provider",
    "admin",
    name="user_role",
    create_type=False,
)


def upgrade() -> None:
    """Apply this migration (move schema forward)."""
    # 1) Create the enum type in Postgres (must exist before the column uses it).
    user_role_enum.create(op.get_bind(), checkfirst=True)

    # 2) Create the users table matching app.models.user.User
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column(
            "role",
            user_role_enum,
            nullable=False,
            server_default="customer",
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
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("phone", name="uq_users_phone"),
    )

    # 3) Indexes for common lookups (login by email/phone, filter by role)
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_phone", "users", ["phone"], unique=False)
    op.create_index("ix_users_role", "users", ["role"], unique=False)


def downgrade() -> None:
    """Undo this migration (move schema backward)."""
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    user_role_enum.drop(op.get_bind(), checkfirst=True)
