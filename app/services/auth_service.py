"""
Auth business logic: register and login (customer + provider).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import PUBLIC_ROLES, Token, UserRegister


class AuthError(Exception):
    """
    Domain error for auth failures.

    Routes catch this and map to the correct HTTP status
    (409 conflict, 401 unauthorized, etc.).
    """

    def __init__(self, message: str, *, code: str = "auth_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def get_user_by_email(db: Session, email: str) -> User | None:
    """Lookup helper used by register (uniqueness) and login."""
    statement = select(User).where(User.email == email.lower())
    return db.scalar(statement)


def _issue_token(user: User) -> Token:
    return Token(
        access_token=create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.value},
        ),
        role=user.role,
    )


def register_user(db: Session, data: UserRegister) -> tuple[User, Token]:
    """
    Create a customer or provider account and return (user, access token).

    Rules:
      - email stored lowercased for consistent uniqueness
      - role may be customer or provider only (admin never via this path)
      - password hashed before insert
    """
    if data.role not in PUBLIC_ROLES:
        raise AuthError("Invalid role for registration", code="invalid_role")

    existing = get_user_by_email(db, data.email)
    if existing is not None:
        raise AuthError("Email already registered", code="email_taken")

    if data.phone:
        phone_taken = db.scalar(select(User).where(User.phone == data.phone))
        if phone_taken is not None:
            raise AuthError("Phone already registered", code="phone_taken")

    user = User(
        email=data.email.lower(),
        phone=data.phone,
        full_name=data.full_name.strip(),
        hashed_password=hash_password(data.password),
        role=data.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user, _issue_token(user)


def authenticate_user(db: Session, email: str, password: str) -> tuple[User, Token]:
    """
    Verify credentials and return (user, access token).

    Works for customer, provider, and admin accounts that have a password.
    Same generic error for unknown email and wrong password.
    """
    user = get_user_by_email(db, email)
    if user is None or not user.hashed_password:
        raise AuthError("Invalid email or password", code="invalid_credentials")

    if not verify_password(password, user.hashed_password):
        raise AuthError("Invalid email or password", code="invalid_credentials")

    if not user.is_active:
        raise AuthError("Inactive user", code="inactive_user")

    return user, _issue_token(user)
