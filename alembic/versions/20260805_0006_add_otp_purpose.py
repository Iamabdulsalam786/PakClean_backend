"""add otp_codes.purpose for password reset

Revision ID: 20260805_0006
Revises: 20260804_0005
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260805_0006"
down_revision: Union[str, None] = "20260804_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

otp_purpose_enum = postgresql.ENUM(
    "email_verification",
    "password_reset",
    name="otp_purpose",
    create_type=False,
)


def upgrade() -> None:
    """Add purpose discriminator to otp_codes."""
    otp_purpose_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "otp_codes",
        sa.Column(
            "purpose",
            otp_purpose_enum,
            nullable=False,
            server_default="email_verification",
        ),
    )
    op.create_index("ix_otp_codes_purpose", "otp_codes", ["purpose"], unique=False)

    # Composite-friendly indexes for purpose-scoped lookups / rate limits.
    op.create_index(
        "ix_otp_codes_email_purpose_created_at",
        "otp_codes",
        ["email", "purpose", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_otp_codes_user_purpose_used",
        "otp_codes",
        ["user_id", "purpose", "is_used"],
        unique=False,
    )

    # Existing rows were all registration/verification OTPs.
    op.execute(sa.text("UPDATE otp_codes SET purpose = 'email_verification'"))


def downgrade() -> None:
    """Remove purpose from otp_codes."""
    op.drop_index("ix_otp_codes_user_purpose_used", table_name="otp_codes")
    op.drop_index("ix_otp_codes_email_purpose_created_at", table_name="otp_codes")
    op.drop_index("ix_otp_codes_purpose", table_name="otp_codes")
    op.drop_column("otp_codes", "purpose")
    otp_purpose_enum.drop(op.get_bind(), checkfirst=True)
