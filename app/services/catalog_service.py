"""
Catalog business logic: list/get categories.

Legacy Service rows may still exist in the DB for old data, but there are no
public /catalog/services routes — marketplace listings are the bookable surface.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category


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
    active_only: bool = True,
) -> Category:
    """Fetch one category by slug, or raise CatalogError(not_found)."""
    statement = select(Category).where(Category.slug == slug)
    if active_only:
        statement = statement.where(Category.is_active.is_(True))

    category = db.scalar(statement)
    if category is None:
        raise CatalogError("Category not found", code="not_found")
    return category
