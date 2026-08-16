"""
FastAPI dependencies shared across routes.

Interview talking point:
  Depends() injects cross-cutting concerns (DB session, auth) into routes
  without repeating boilerplate. Authorization lives here, not in every handler.
"""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole

# Tells OpenAPI/Swagger where the login form posts (we will add that route soon).
# auto_error=False → we raise our own 401 with a consistent body.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login/form",
    auto_error=False,
)

# Short aliases used in route signatures for readability.
DbSession = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str | None, Depends(oauth2_scheme)]


def get_current_user(db: DbSession, token: TokenDep) -> User:
    """
    Resolve the caller from Authorization: Bearer <access_token>.

    Steps:
      1. Require a token
      2. Decode/verify JWT
      3. Load User by sub (user id)
      4. Reject inactive accounts
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    subject = payload.get("sub")
    if subject is None:
        raise credentials_exception

    try:
        user_id = UUID(str(subject))
    except (TypeError, ValueError):
        raise credentials_exception from None

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[..., User]:
    """
    Dependency factory: allow only users whose role is in `roles`.

    Usage later:
      @router.get("/admin/users")
      def list_users(user: User = Depends(require_roles(UserRole.ADMIN))):
          ...
    """

    def _checker(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _checker


# Convenience aliases for customer-only / provider-only routes later.
CurrentCustomer = Annotated[User, Depends(require_roles(UserRole.CUSTOMER))]
CurrentProvider = Annotated[User, Depends(require_roles(UserRole.PROVIDER))]
