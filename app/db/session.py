"""
SQLAlchemy engine and session factory.

Request lifecycle (interview talking point):
  1. FastAPI dependency get_db() opens a Session
  2. Route / service uses that Session for queries
  3. finally: session.close() returns the connection to the pool

We use sync SQLAlchemy here for Phase 1 clarity. Async engines are a later upgrade.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


# create_engine = connection pool + dialect for Postgres (via DATABASE_URL).
# pool_pre_ping=True: check a connection is alive before using it (survives DB restarts).
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

# sessionmaker builds Session objects bound to our engine.
# autocommit=False / autoflush=False: we control commits explicitly in services.
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a DB session per request.

    Usage later:
      def list_bookings(db: Session = Depends(get_db)):
          ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
