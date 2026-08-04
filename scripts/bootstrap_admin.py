"""
Create (or promote) an admin user for Pak Clean.

Run from pak-clean-backend (venv active):
  python -m scripts.bootstrap_admin --email admin@example.com --password "StrongPass123" --full-name "Admin User"

Safe to re-run:
  - If email does not exist: creates a new admin user.
  - If email exists: upgrades role to admin and updates profile fields.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User, UserRole


def bootstrap_admin(
    *,
    email: str,
    password: str,
    full_name: str,
    phone: str | None = None,
) -> User:
    db = SessionLocal()
    try:
        normalized_email = email.strip().lower()
        existing = db.scalar(select(User).where(User.email == normalized_email))

        if existing is None:
            user = User(
                email=normalized_email,
                hashed_password=hash_password(password),
                full_name=full_name.strip(),
                phone=phone,
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"created admin user: {user.email} ({user.id})")
            return user

        existing.role = UserRole.ADMIN
        existing.is_active = True
        existing.full_name = full_name.strip()
        existing.phone = phone
        existing.hashed_password = hash_password(password)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        print(f"updated existing user as admin: {existing.email} ({existing.id})")
        return existing
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap or promote an admin user.")
    parser.add_argument("--email", required=True, help="Admin login email")
    parser.add_argument("--password", required=True, help="Admin password (plain text input)")
    parser.add_argument("--full-name", required=True, help="Admin full name")
    parser.add_argument("--phone", default=None, help="Optional phone number")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    bootstrap_admin(
        email=args.email,
        password=args.password,
        full_name=args.full_name,
        phone=args.phone,
    )
