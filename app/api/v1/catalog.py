"""
Catalog HTTP endpoints — public category taxonomy only.

Marketplace listings replace legacy catalog services. Providers pick a category
when creating a listing; customers browse /marketplace/listings, not /catalog/services.
"""

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import DbSession
from app.schemas.catalog import CategoryRead
from app.services.catalog_service import CatalogError, get_category_by_slug, list_categories

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _http_for_catalog_error(exc: CatalogError) -> HTTPException:
    if exc.code == "not_found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)


@router.get(
    "/categories",
    response_model=list[CategoryRead],
    summary="List active categories",
)
def get_categories(db: DbSession) -> list[CategoryRead]:
    """Home-screen category list (Cleaning, Plumbing, ...)."""
    rows = list_categories(db, active_only=True)
    return [CategoryRead.model_validate(row) for row in rows]


@router.get(
    "/categories/{slug}",
    response_model=CategoryRead,
    summary="Get a category by slug",
)
def get_category(slug: str, db: DbSession) -> CategoryRead:
    """Example: GET /catalog/categories/plumbing"""
    try:
        category = get_category_by_slug(db, slug, active_only=True)
    except CatalogError as exc:
        raise _http_for_catalog_error(exc) from exc
    return CategoryRead.model_validate(category)
