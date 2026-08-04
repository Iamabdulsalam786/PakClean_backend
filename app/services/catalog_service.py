"""
Catalog business logic: list/get categories and services.

Public browse only for now (active rows). Admin CRUD comes later.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.category import Category
from app.models.service import Service


class CatalogError(Exception):
    """Domain error for catalog lookups (routes map to HTTP)."""

    def __init__(self, message: str, *, code: str = "catalog_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def list_categories(db: Session, *, active_only: bool = True) -> list[Category]:
    """Return categories ordered for the app home screen."""
    statement = select(Category).order_by(Category.sort_order, Category.name)
    if active_only:
        statement = statement.where(Category.is_active.is_(True))
    return list(db.scalars(statement).all())


def get_category_by_slug(
    db: Session,
    slug: str,
    *,
    with_services: bool = False,
    active_only: bool = True,
) -> Category:
    """Fetch one category by slug, or raise CatalogError(not_found)."""
    statement = select(Category).where(Category.slug == slug)
    if with_services:
        statement = statement.options(selectinload(Category.services))
    if active_only:
        statement = statement.where(Category.is_active.is_(True))

    category = db.scalar(statement)
    if category is None:
        raise CatalogError("Category not found", code="not_found")

    # When embedding services, only expose active ones (and keep sort order).
    if with_services and active_only:
        category.services = sorted(
            [s for s in category.services if s.is_active],
            key=lambda s: (s.sort_order, s.name),
        )
    return category


def list_services(
    db: Session,
    *,
    category_slug: str | None = None,
    active_only: bool = True,
) -> list[Service]:
    """
    Return services, optionally filtered by category slug.

    Example: category_slug="plumbing" → Tap Repair, Drain Unclog, ...
    """
    statement = (
        select(Service)
        .join(Category, Service.category_id == Category.id)
        .order_by(Service.sort_order, Service.name)
    )
    if active_only:
        statement = statement.where(
            Service.is_active.is_(True),
            Category.is_active.is_(True),
        )
    if category_slug is not None:
        statement = statement.where(Category.slug == category_slug)

    return list(db.scalars(statement).all())


def get_service_by_slug(
    db: Session,
    slug: str,
    *,
    active_only: bool = True,
) -> Service:
    """Fetch one service by slug, or raise CatalogError(not_found)."""
    statement = select(Service).where(Service.slug == slug)
    if active_only:
        statement = statement.where(Service.is_active.is_(True))

    service = db.scalar(statement)
    if service is None:
        raise CatalogError("Service not found", code="not_found")
    return service


def get_service_by_id(
    db: Session,
    service_id: UUID,
    *,
    active_only: bool = True,
) -> Service:
    """Fetch one service by id (useful later for bookings)."""
    statement = select(Service).where(Service.id == service_id)
    if active_only:
        statement = statement.where(Service.is_active.is_(True))

    service = db.scalar(statement)
    if service is None:
        raise CatalogError("Service not found", code="not_found")
    return service
