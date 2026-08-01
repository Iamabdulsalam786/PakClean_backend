"""
Auth business logic: register and login.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import Token, UserRegister


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


def register_user(db: Session, data: UserRegister) -> tuple[User, Token]:
    """
    Create a new customer account and return (user, access token).

    Rules:
      - email stored lowercased for consistent uniqueness
      - role forced to CUSTOMER (never trust client for privilege)
      - password hashed before insert
    """
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
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # load DB-generated fields (id, timestamps)

    token = Token(
        access_token=create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.value},
        )
    )
    return user, token


def authenticate_user(db: Session, email: str, password: str) -> tuple[User, Token]:
    """
    Verify credentials and return (user, access token).

    Same generic error for unknown email and wrong password
    to avoid user-enumeration via timing/message differences
    (good enough for Phase 1; harden further later).
    """
    user = get_user_by_email(db, email)
    if user is None or not user.hashed_password:
        raise AuthError("Invalid email or password", code="invalid_credentials")

    if not verify_password(password, user.hashed_password):
        raise AuthError("Invalid email or password", code="invalid_credentials")

    if not user.is_active:
        raise AuthError("Inactive user", code="inactive_user")

    token = Token(
        access_token=create_access_token(
            subject=str(user.id),
            extra_claims={"role": user.role.value},
        )
    )
    return user, token
