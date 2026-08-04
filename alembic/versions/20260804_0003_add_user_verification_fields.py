"""add user verification and onboarding fields

Revision ID: 20260804_0003
Revises: 20260801_0002
Create Date: 2026-08-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0003"
down_revision: Union[str, None] = "20260801_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_onboarding_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    # Existing rows were created before email OTP gate — treat them as verified.
    op.execute("UPDATE users SET is_email_verified = true")


def downgrade() -> None:
    op.drop_column("users", "is_onboarding_complete")
    op.drop_column("users", "is_email_verified")
