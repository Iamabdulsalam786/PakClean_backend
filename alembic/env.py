"""
Alembic environment script.

Alembic runs this file when you execute commands like:
  alembic revision --autogenerate
  alembic upgrade head

Responsibilities:
  1. Point Alembic at our SQLAlchemy metadata (Base.metadata)
  2. Import all models so tables are registered on that metadata
  3. Use DATABASE_URL from app settings (not a duplicated URL in alembic.ini)
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base

# Import models so each class registers on Base.metadata.
# Without this, autogenerate would see an empty schema and invent wrong diffs.
# Legacy layer-based models:
from app.models import (  # noqa: F401
    Booking,
    Category,
    OtpChallenge,
    OtpCode,
    RefreshToken,
    Service,
    User,
)
# Feature-based models:
from app.customers.models import CustomerAddress  # noqa: F401
from app.providers.models import ProviderProfile  # noqa: F401
from app.reviews.models import Review  # noqa: F401
from app.service_listings.models import (  # noqa: F401
    ServiceListing,
    ServiceListingAvailability,
    ServiceListingDiscount,
    ServiceListingImage,
    ServiceListingTag,
    Tag,
)

# Alembic Config object — reads alembic.ini
config = context.config

# Inject DB URL from our Settings (.env). Overrides empty sqlalchemy.url in ini.
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up Python logging from the ini file's [loggers] sections (if present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for 'autogenerate' support — compared against the live DB.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations without a live DBAPI connection (generates SQL script mode).

    Used less often locally; useful for emitting SQL to review/apply elsewhere.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations with a live connection to Postgres (normal local/prod path).
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        # NullPool: migrations are short-lived CLI processes; no need for a pool.
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
