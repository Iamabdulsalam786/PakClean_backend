"""
Provider profile HTTP endpoints — provider self-service + admin verification.

Thin controllers: schema validation → ProviderProfileService → map errors → HTTP.

Routes:
  Provider:
    POST   /provider/profile
    GET    /provider/profile
    PATCH  /provider/profile

  Admin:
    GET    /admin/providers
    GET    /admin/providers/{profile_id}
    POST   /admin/providers/{profile_id}/verify
    POST   /admin/providers/{profile_id}/reject
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import CurrentProvider, DbSession, require_roles
from app.models.user import User, UserRole
from app.providers.models.provider_profile import ProviderVerificationStatus
from app.providers.schemas.provider_profile import (
    AdminProviderQueueResponse,
    AdminRejectProviderRequest,
    AdminVerifyProviderRequest,
    ProviderProfileCreate,
    ProviderProfileRead,
    ProviderProfileUpdate,
)
from app.providers.services.provider_profile_service import (
    ProviderDomainError,
    ProviderProfileService,
)

provider_router = APIRouter(prefix="/provider", tags=["provider-profile"])
admin_router = APIRouter(prefix="/admin/providers", tags=["admin-providers"])


def _http_for_provider_error(exc: ProviderDomainError) -> HTTPException:
    """Map ProviderDomainError.code → HTTP status."""
    code = exc.code
    if code == "provider_profile_not_found":
        status_code = status.HTTP_404_NOT_FOUND
    elif code == "provider_profile_exists":
        status_code = status.HTTP_409_CONFLICT
    elif code in {
        "not_a_provider",
        "email_not_verified",
        "provider_not_verified",
        "insufficient_permissions",
        "inactive_user",
    }:
        status_code = status.HTTP_403_FORBIDDEN
    elif code == "invalid_verification_transition":
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=status_code, detail=exc.message)


def _service(db: DbSession) -> ProviderProfileService:
    return ProviderProfileService(db)


# ---------------------------------------------------------------------------
# Provider self-service
# ---------------------------------------------------------------------------


@provider_router.post(
    "/profile",
    response_model=ProviderProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create my provider profile (starts as pending)",
)
def create_my_profile(
    payload: ProviderProfileCreate,
    db: DbSession,
    current_user: CurrentProvider,
) -> ProviderProfileRead:
    """
    Requires role=provider + valid JWT.

    Email verification is enforced again in the service.
    Profile is always created as verification_status=pending.
    """
    try:
        return _service(db).create_profile(current_user, payload)
    except ProviderDomainError as exc:
        raise _http_for_provider_error(exc) from exc


@provider_router.get(
    "/profile",
    response_model=ProviderProfileRead,
    summary="Get my provider profile",
)
def get_my_profile(
    db: DbSession,
    current_user: CurrentProvider,
) -> ProviderProfileRead:
    try:
        return _service(db).get_my_profile(current_user)
    except ProviderDomainError as exc:
        raise _http_for_provider_error(exc) from exc


@provider_router.patch(
    "/profile",
    response_model=ProviderProfileRead,
    summary="Update my provider profile",
)
def update_my_profile(
    payload: ProviderProfileUpdate,
    db: DbSession,
    current_user: CurrentProvider,
) -> ProviderProfileRead:
    """
    Updates business fields only.

    If previously rejected, service resets status to pending (re-apply).
    """
    try:
        return _service(db).update_my_profile(current_user, payload)
    except ProviderDomainError as exc:
        raise _http_for_provider_error(exc) from exc


# ---------------------------------------------------------------------------
# Admin verification
# ---------------------------------------------------------------------------


@admin_router.get(
    "",
    response_model=AdminProviderQueueResponse,
    summary="List provider profiles by verification status",
)
def list_provider_queue(
    db: DbSession,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    status_filter: ProviderVerificationStatus = Query(
        default=ProviderVerificationStatus.PENDING,
        alias="status",
        description="Filter by verification status",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminProviderQueueResponse:
    _ = admin  # role enforced by dependency; service also asserts admin on mutations
    try:
        return _service(db).list_queue(
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except ProviderDomainError as exc:
        raise _http_for_provider_error(exc) from exc


@admin_router.get(
    "/{profile_id}",
    response_model=ProviderProfileRead,
    summary="Get one provider profile (admin)",
)
def get_provider_profile_admin(
    profile_id: UUID,
    db: DbSession,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProviderProfileRead:
    _ = admin
    try:
        return _service(db).get_profile_for_admin(profile_id)
    except ProviderDomainError as exc:
        raise _http_for_provider_error(exc) from exc


@admin_router.post(
    "/{profile_id}/verify",
    response_model=ProviderProfileRead,
    summary="Verify a provider (allows listings)",
)
def verify_provider(
    profile_id: UUID,
    db: DbSession,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    payload: AdminVerifyProviderRequest = AdminVerifyProviderRequest(),
) -> ProviderProfileRead:
    try:
        return _service(db).verify_provider(admin, profile_id, payload)
    except ProviderDomainError as exc:
        raise _http_for_provider_error(exc) from exc


@admin_router.post(
    "/{profile_id}/reject",
    response_model=ProviderProfileRead,
    summary="Reject a provider application",
)
def reject_provider(
    profile_id: UUID,
    payload: AdminRejectProviderRequest,
    db: DbSession,
    admin: User = Depends(require_roles(UserRole.ADMIN)),
) -> ProviderProfileRead:
    try:
        return _service(db).reject_provider(admin, profile_id, payload)
    except ProviderDomainError as exc:
        raise _http_for_provider_error(exc) from exc
