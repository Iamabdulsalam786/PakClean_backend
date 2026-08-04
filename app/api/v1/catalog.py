"""
Catalog HTTP endpoints — public browse of categories and services.

No auth required (customers discover offerings before login).
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dependencies import DbSession
from app.schemas.catalog import CategoryRead, CategoryWithServices, ServiceRead
from app.services.catalog_service import (
    CatalogError,
    get_category_by_slug,
    get_service_by_slug,
    list_categories,
    list_services,
)

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
    response_model=CategoryWithServices,
    summary="Get a category by slug (with its services)",
)
def get_category(slug: str, db: DbSession) -> CategoryWithServices:
    """Example: GET /catalog/categories/plumbing"""
    try:
        category = get_category_by_slug(db, slug, with_services=True, active_only=True)
    except CatalogError as exc:
        raise _http_for_catalog_error(exc) from exc
    return CategoryWithServices.model_validate(category)


@router.get(
    "/services",
    response_model=list[ServiceRead],
    summary="List active services",
)
def get_services(
    db: DbSession,
    category: str | None = Query(
        default=None,
        description="Optional category slug filter, e.g. plumbing",
    ),
) -> list[ServiceRead]:
    """All services, or filter: GET /catalog/services?category=plumbing"""
    rows = list_services(db, category_slug=category, active_only=True)
    return [ServiceRead.model_validate(row) for row in rows]


@router.get(
    "/services/{slug}",
    response_model=ServiceRead,
    summary="Get a service by slug",
)
def get_service(slug: str, db: DbSession) -> ServiceRead:
    """Example: GET /catalog/services/tap-repair"""
    try:
        service = get_service_by_slug(db, slug, active_only=True)
    except CatalogError as exc:
        raise _http_for_catalog_error(exc) from exc
    return ServiceRead.model_validate(service)
