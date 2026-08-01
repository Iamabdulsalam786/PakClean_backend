"""
Declarative base for all SQLAlchemy ORM models.

Every table class will inherit from Base, e.g.:

    class User(Base):
        __tablename__ = "users"
        ...

Alembic reads Base.metadata to know which tables exist and generate migrations.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Shared superclass for ORM models (SQLAlchemy 2.0 style).

    DeclarativeBase replaces the older:
        Base = declarative_base()
    Same idea, modern API.
    """

    pass
